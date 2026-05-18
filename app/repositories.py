"""
Repository layer: all Firestore writes go through here.

Why a repository layer?
- Centralizes audit logging (every write creates an audit log entry)
- Centralizes soft-delete (we never call .delete() on docs)
- Makes the codebase testable — routes don't talk to Firestore directly
- Single place to add caching, batching, etc. later
"""
import re
from typing import Optional
from datetime import datetime

from google.cloud import firestore as gcf

from .firebase_client import get_db, server_timestamp
from .models import validate_person_input, diff_dict, ROLE_VALUES, ValidationError


# ------------------------------ ID helpers ------------------------------

def slugify_for_id(name: str) -> str:
    """
    Turn a name into a Firestore-safe ID slug.
    'Khairul Anwar bin Sedek' -> 'khairul-anwar-bin-sedek'
    """
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s)
    s = s.strip("-")
    return s[:80] or "unnamed"


def generate_person_id(full_name: str, suffix: Optional[str] = None) -> str:
    base = "p_" + slugify_for_id(full_name)
    return f"{base}_{suffix}" if suffix else base


# ------------------------------ Audit ------------------------------

def _write_audit(doc_ref, *, action: str, actor: dict,
                 fields_changed: list, before: dict, after: dict):
    """Write a single audit log entry as a sub-document of the parent doc."""
    log_ref = doc_ref.collection("audit_log").document()
    log_ref.set({
        "changed_at": server_timestamp(),
        "changed_by_uid": actor.get("uid", ""),
        "changed_by_email": actor.get("email", ""),
        "changed_by_name": actor.get("name", ""),
        "action": action,
        "fields_changed": fields_changed,
        "before": before,
        "after": after,
    })


# ------------------------------ Persons ------------------------------

class PersonRepository:

    def __init__(self):
        self.db = get_db()

    def get(self, person_id: str) -> Optional[dict]:
        snap = self.db.collection("persons").document(person_id).get()
        if not snap.exists:
            return None
        d = snap.to_dict()
        if d.get("is_deleted"):
            return None
        d["person_id"] = snap.id
        return d

    def list_all(self, limit: int = 500) -> list[dict]:
        """Return all non-deleted persons, ordered by full_name. For small datasets only."""
        q = (self.db.collection("persons")
                .where(filter=gcf.FieldFilter("is_deleted", "==", False))
                .order_by("full_name")
                .limit(limit))
        out = []
        for snap in q.stream():
            d = snap.to_dict()
            d["person_id"] = snap.id
            out.append(d)
        return out

    def search_by_name(self, query: str, limit: int = 20) -> list[dict]:
        """Prefix search on lowercased name. For 1000s of records this is fine."""
        q_lower = query.lower().strip()
        if not q_lower:
            return []
        end = q_lower[:-1] + chr(ord(q_lower[-1]) + 1)
        q = (self.db.collection("persons")
                .where(filter=gcf.FieldFilter("is_deleted", "==", False))
                .where(filter=gcf.FieldFilter("full_name_lower", ">=", q_lower))
                .where(filter=gcf.FieldFilter("full_name_lower", "<", end))
                .limit(limit))
        out = []
        for snap in q.stream():
            d = snap.to_dict()
            d["person_id"] = snap.id
            out.append(d)
        return out
    
    def search_substring(self, query: str, *, limit: int = 20,
                     exclude_id: Optional[str] = None) -> list[dict]:
        """In-memory substring search across all persons. For relationship picker.
        Returns lightweight records: id, full_name, birth_year, gender.
        Fine for datasets under a few thousand."""
        q_lower = (query or "").lower().strip()
        if len(q_lower) < 2:
            return []

        all_persons = self.list_all(limit=5000)
        results = []
        for p in all_persons:
            if exclude_id and p["person_id"] == exclude_id:
                continue
            haystack = (p.get("full_name_lower") or p.get("full_name", "").lower())
            if q_lower in haystack:
                birth = p.get("birth_date") or p.get("dob") or ""
                results.append({
                    "id": p["person_id"],
                    "full_name": p.get("full_name", "—"),
                    "birth_year": birth[:4] if birth else None,
                    "gender": p.get("gender"),
                })
                if len(results) >= limit:
                    break
        return results

    def create(self, data: dict, *, actor: dict, person_id: Optional[str] = None) -> str:
        """Create a new person. Returns the new person_id."""
        validated = validate_person_input(data)
        if "full_name" not in validated:
            raise ValidationError("full_name is required")

        if person_id is None:
            person_id = generate_person_id(validated["full_name"])

        doc_ref = self.db.collection("persons").document(person_id)
        if doc_ref.get().exists:
            # collision — append a short hash
            import uuid
            person_id = generate_person_id(validated["full_name"], uuid.uuid4().hex[:6])
            doc_ref = self.db.collection("persons").document(person_id)

        record = {
            **validated,
            "is_deleted": False,
            "claimed_by_uid": None,
            "claimed_at": None,
            "created_at": server_timestamp(),
            "created_by_uid": actor.get("uid", ""),
            "updated_at": server_timestamp(),
            "updated_by_uid": actor.get("uid", ""),
        }
        # Set defaults for fields not in input
        record.setdefault("status", "alive")
        record.setdefault("parent_ids", [])
        record.setdefault("spouse_ids", [])
        record.setdefault("child_ids", [])

        doc_ref.set(record)
        _write_audit(doc_ref, action="create", actor=actor,
                     fields_changed=list(validated.keys()),
                     before={}, after=validated)
        return person_id

    def update(self, person_id: str, data: dict, *, actor: dict) -> dict:
        """Partial update. Only fields in `data` are touched."""
        validated = validate_person_input(data)
        if not validated:
            raise ValidationError("No valid fields to update")

        doc_ref = self.db.collection("persons").document(person_id)

        @gcf.transactional
        def txn(transaction):
            snap = doc_ref.get(transaction=transaction)
            if not snap.exists:
                raise ValidationError(f"Person {person_id} not found")
            before = snap.to_dict()
            if before.get("is_deleted"):
                raise ValidationError(f"Person {person_id} is deleted")

            changed_keys, before_sub, after_sub = diff_dict(before, validated)
            if not changed_keys:
                return before  # no-op

            update_payload = {
                **{k: validated[k] for k in changed_keys},
                "updated_at": server_timestamp(),
                "updated_by_uid": actor.get("uid", ""),
            }
            transaction.update(doc_ref, update_payload)

            # Audit log entry — note: written outside transaction since sub-coll
            # writes inside the same txn complicate things; we accept the small
            # window where audit may lag if Flask crashes mid-request.
            return {"_changed_keys": changed_keys,
                    "_before": before_sub, "_after": after_sub,
                    "_before_full": before}

        result = txn(self.db.transaction())
        if "_changed_keys" in result:
            _write_audit(doc_ref, action="update", actor=actor,
                         fields_changed=result["_changed_keys"],
                         before=result["_before"], after=result["_after"])
            updated_full = {**result["_before_full"], **result["_after"]}
            updated_full["person_id"] = person_id
            return updated_full
        result["person_id"] = person_id
        return result

    def soft_delete(self, person_id: str, *, actor: dict):
        """Mark person as deleted. Does not remove from Firestore."""
        doc_ref = self.db.collection("persons").document(person_id)
        snap = doc_ref.get()
        if not snap.exists:
            raise ValidationError(f"Person {person_id} not found")
        doc_ref.update({
            "is_deleted": True,
            "updated_at": server_timestamp(),
            "updated_by_uid": actor.get("uid", ""),
        })
        _write_audit(doc_ref, action="delete", actor=actor,
                     fields_changed=["is_deleted"],
                     before={"is_deleted": False}, after={"is_deleted": True})

    def claim(self, person_id: str, *, actor: dict) -> dict:
        """
        Link the current logged-in user (Google account) to this Person record.
        Each person can only be claimed once. Each user can only claim one person.
        """
        uid = actor["uid"]
        person_ref = self.db.collection("persons").document(person_id)
        user_ref = self.db.collection("users").document(uid)

        @gcf.transactional
        def txn(transaction):
            p_snap = person_ref.get(transaction=transaction)
            if not p_snap.exists:
                raise ValidationError(f"Person {person_id} not found")
            p_data = p_snap.to_dict()
            if p_data.get("claimed_by_uid") and p_data["claimed_by_uid"] != uid:
                raise ValidationError("This profile has already been claimed by another user")

            u_snap = user_ref.get(transaction=transaction)
            u_data = u_snap.to_dict() if u_snap.exists else {}
            if u_data.get("linked_person_id") and u_data["linked_person_id"] != person_id:
                raise ValidationError(
                    f"You have already claimed another profile ({u_data['linked_person_id']})"
                )

            transaction.update(person_ref, {
                "claimed_by_uid": uid,
                "claimed_at": server_timestamp(),
                "updated_at": server_timestamp(),
                "updated_by_uid": uid,
            })
            transaction.update(user_ref, {"linked_person_id": person_id})
            return p_data

        before_data = txn(self.db.transaction())
        _write_audit(person_ref, action="claim", actor=actor,
                     fields_changed=["claimed_by_uid"],
                     before={"claimed_by_uid": before_data.get("claimed_by_uid")},
                     after={"claimed_by_uid": uid})
        return self.get(person_id)


# ------------------------------ Households ------------------------------

class HouseholdRepository:

    def __init__(self):
        self.db = get_db()

    def get(self, household_id: str) -> Optional[dict]:
        snap = self.db.collection("households").document(household_id).get()
        if not snap.exists:
            return None
        d = snap.to_dict()
        if d.get("is_deleted"):
            return None
        d["household_id"] = snap.id
        return d

    def list_all(self, limit: int = 500) -> list[dict]:
        q = (self.db.collection("households")
                .where(filter=gcf.FieldFilter("is_deleted", "==", False))
                .order_by("registered_at", direction=gcf.Query.DESCENDING)
                .limit(limit))
        out = []
        for snap in q.stream():
            d = snap.to_dict()
            d["household_id"] = snap.id
            out.append(d)
        return out

    def create(self, data: dict, *, actor: dict, household_id: Optional[str] = None) -> str:
        ketua_id = data.get("ketua_person_id")
        if not ketua_id:
            raise ValidationError("ketua_person_id is required")
        # validate ketua exists
        if not self.db.collection("persons").document(ketua_id).get().exists:
            raise ValidationError(f"Ketua person {ketua_id} does not exist")

        members = data.get("members", [])
        validated_members = self._validate_members(members)

        if household_id is None:
            # auto-increment style ID
            household_id = self._next_household_id()

        doc_ref = self.db.collection("households").document(household_id)
        record = {
            "ketua_person_id": ketua_id,
            "members": validated_members,
            "registered_by_email": actor.get("email", ""),
            "registered_at": server_timestamp(),
            "notes": str(data.get("notes", "")).strip()[:2000],
            "is_deleted": False,
            "created_at": server_timestamp(),
            "created_by_uid": actor.get("uid", ""),
            "updated_at": server_timestamp(),
            "updated_by_uid": actor.get("uid", ""),
        }
        doc_ref.set(record)
        _write_audit(doc_ref, action="create", actor=actor,
                     fields_changed=list(record.keys()),
                     before={}, after={"ketua_person_id": ketua_id,
                                       "members": validated_members})
        return household_id

    def update(self, household_id: str, data: dict, *, actor: dict) -> dict:
        doc_ref = self.db.collection("households").document(household_id)
        snap = doc_ref.get()
        if not snap.exists:
            raise ValidationError(f"Household {household_id} not found")
        before = snap.to_dict()

        update = {}
        if "members" in data:
            update["members"] = self._validate_members(data["members"])
        if "ketua_person_id" in data:
            kid = data["ketua_person_id"]
            if not self.db.collection("persons").document(kid).get().exists:
                raise ValidationError(f"Ketua {kid} does not exist")
            update["ketua_person_id"] = kid
        if "notes" in data:
            update["notes"] = str(data.get("notes", "")).strip()[:2000]

        if not update:
            raise ValidationError("No valid fields to update")

        update["updated_at"] = server_timestamp()
        update["updated_by_uid"] = actor.get("uid", "")
        doc_ref.update(update)

        changed = list(update.keys() - {"updated_at", "updated_by_uid"})
        _write_audit(doc_ref, action="update", actor=actor,
                     fields_changed=changed,
                     before={k: before.get(k) for k in changed},
                     after={k: update[k] for k in changed})
        return self.get(household_id)

    def _validate_members(self, members) -> list:
        if not isinstance(members, list):
            raise ValidationError("members must be a list")
        out = []
        seen_ids = set()
        for m in members:
            pid = m.get("person_id", "").strip()
            role = m.get("role", "").strip().lower()
            if not pid:
                raise ValidationError("each member needs a person_id")
            if pid in seen_ids:
                raise ValidationError(f"duplicate person_id in household: {pid}")
            seen_ids.add(pid)
            if role not in ROLE_VALUES:
                raise ValidationError(f"invalid role {role!r}; must be one of {ROLE_VALUES}")
            psnap = self.db.collection("persons").document(pid).get()
            if not psnap.exists:
                raise ValidationError(f"person {pid} does not exist")
            pdata = psnap.to_dict()
            out.append({
                "person_id": pid,
                "role": role,
                "full_name_cached": pdata.get("full_name", ""),
            })
        return out

    def _next_household_id(self) -> str:
        # Counter doc strategy: /counters/households { value: N }
        counter_ref = self.db.collection("counters").document("households")

        @gcf.transactional
        def txn(transaction):
            snap = counter_ref.get(transaction=transaction)
            current = snap.to_dict().get("value", 0) if snap.exists else 0
            next_val = current + 1
            transaction.set(counter_ref, {"value": next_val})
            return next_val

        n = txn(self.db.transaction())
        return f"h_{n:04d}"

    def soft_delete(self, household_id: str, *, actor: dict):
        doc_ref = self.db.collection("households").document(household_id)
        snap = doc_ref.get()
        if not snap.exists:
            raise ValidationError(f"Household {household_id} not found")
        doc_ref.update({
            "is_deleted": True,
            "updated_at": server_timestamp(),
            "updated_by_uid": actor.get("uid", ""),
        })
        _write_audit(doc_ref, action="delete", actor=actor,
                     fields_changed=["is_deleted"],
                     before={"is_deleted": False}, after={"is_deleted": True})


# ------------------------------ Audit log queries ------------------------------

def recent_activity(limit: int = 50) -> list[dict]:
    """Use a collection-group query to list recent audit entries across all docs."""
    db = get_db()
    q = (db.collection_group("audit_log")
            .order_by("changed_at", direction=gcf.Query.DESCENDING)
            .limit(limit))
    out = []
    for snap in q.stream():
        d = snap.to_dict()
        d["log_id"] = snap.id
        # parent is /persons/{pid}/audit_log/{log_id} or /households/{hid}/audit_log/{log_id}
        parent = snap.reference.parent.parent  # the doc above audit_log
        if parent is not None:
            d["parent_collection"] = parent.parent.id
            d["parent_id"] = parent.id
        out.append(d)
    return out

# ------------------------------ Relationships ------------------------------

class RelationshipRepository:
    """
    Manages cross-document relationship edges (parent/child, spouse).
    All writes are batched and audited on both affected documents.
    """

    def __init__(self):
        self.db = get_db()

    def _persons(self):
        return self.db.collection("persons")

    def _get_existing(self, person_id: str) -> dict:
        snap = self._persons().document(person_id).get()
        if not snap.exists:
            raise ValidationError(f"Person {person_id} not found")
        data = snap.to_dict()
        if data.get("is_deleted"):
            raise ValidationError(f"Person {person_id} is deleted")
        return data

    def _would_create_cycle(self, parent_id: str, child_id: str) -> bool:
        """True if parent_id is already a descendant of child_id (so adding
        parent->child would create a loop)."""
        visited, queue = set(), [child_id]
        while queue:
            current = queue.pop(0)
            if current == parent_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            snap = self._persons().document(current).get()
            if snap.exists:
                queue.extend(snap.to_dict().get("child_ids") or [])
        return False

    def add_parent_child(self, parent_id: str, child_id: str, *, actor: dict):
        if parent_id == child_id:
            raise ValidationError("A person cannot be their own parent")

        parent_data = self._get_existing(parent_id)
        child_data = self._get_existing(child_id)

        existing_parents = child_data.get("parent_ids") or []
        if parent_id in existing_parents:
            return  # idempotent — already linked
        if len(existing_parents) >= 2:
            raise ValidationError(
                "Child already has two parents. Remove one first."
            )
        if self._would_create_cycle(parent_id, child_id):
            raise ValidationError("This link would create a cycle in the family tree")

        parent_ref = self._persons().document(parent_id)
        child_ref = self._persons().document(child_id)
        now = server_timestamp()

        batch = self.db.batch()
        batch.update(parent_ref, {
            "child_ids": gcf.ArrayUnion([child_id]),
            "updated_at": now,
            "updated_by_uid": actor.get("uid", ""),
        })
        batch.update(child_ref, {
            "parent_ids": gcf.ArrayUnion([parent_id]),
            "updated_at": now,
            "updated_by_uid": actor.get("uid", ""),
        })
        batch.commit()

        _write_audit(parent_ref, action="add_child", actor=actor,
                     fields_changed=["child_ids"],
                     before={"child_ids": parent_data.get("child_ids") or []},
                     after={"child_ids": (parent_data.get("child_ids") or []) + [child_id]})
        _write_audit(child_ref, action="add_parent", actor=actor,
                     fields_changed=["parent_ids"],
                     before={"parent_ids": existing_parents},
                     after={"parent_ids": existing_parents + [parent_id]})

    def remove_parent_child(self, parent_id: str, child_id: str, *,
                            actor: dict, reason: str):
        if not (reason or "").strip():
            raise ValidationError("Removal requires a reason for the audit log")

        parent_data = self._get_existing(parent_id)
        child_data = self._get_existing(child_id)

        parent_ref = self._persons().document(parent_id)
        child_ref = self._persons().document(child_id)
        now = server_timestamp()

        batch = self.db.batch()
        batch.update(parent_ref, {
            "child_ids": gcf.ArrayRemove([child_id]),
            "updated_at": now,
            "updated_by_uid": actor.get("uid", ""),
        })
        batch.update(child_ref, {
            "parent_ids": gcf.ArrayRemove([parent_id]),
            "updated_at": now,
            "updated_by_uid": actor.get("uid", ""),
        })
        batch.commit()

        actor_with_reason = {**actor, "reason": reason}
        _write_audit(parent_ref, action="remove_child", actor=actor_with_reason,
                     fields_changed=["child_ids"],
                     before={"child_ids": parent_data.get("child_ids") or []},
                     after={"child_ids": [c for c in (parent_data.get("child_ids") or []) if c != child_id],
                            "reason": reason})
        _write_audit(child_ref, action="remove_parent", actor=actor_with_reason,
                     fields_changed=["parent_ids"],
                     before={"parent_ids": child_data.get("parent_ids") or []},
                     after={"parent_ids": [p for p in (child_data.get("parent_ids") or []) if p != parent_id],
                            "reason": reason})

    def add_spouse(self, a_id: str, b_id: str, *, actor: dict):
        if a_id == b_id:
            raise ValidationError("A person cannot be their own spouse")
        a_data = self._get_existing(a_id)
        b_data = self._get_existing(b_id)

        a_ref = self._persons().document(a_id)
        b_ref = self._persons().document(b_id)
        now = server_timestamp()

        batch = self.db.batch()
        batch.update(a_ref, {
            "spouse_ids": gcf.ArrayUnion([b_id]),
            "updated_at": now, "updated_by_uid": actor.get("uid", ""),
        })
        batch.update(b_ref, {
            "spouse_ids": gcf.ArrayUnion([a_id]),
            "updated_at": now, "updated_by_uid": actor.get("uid", ""),
        })
        batch.commit()

        _write_audit(a_ref, action="add_spouse", actor=actor,
                     fields_changed=["spouse_ids"],
                     before={"spouse_ids": a_data.get("spouse_ids") or []},
                     after={"spouse_ids": (a_data.get("spouse_ids") or []) + [b_id]})
        _write_audit(b_ref, action="add_spouse", actor=actor,
                     fields_changed=["spouse_ids"],
                     before={"spouse_ids": b_data.get("spouse_ids") or []},
                     after={"spouse_ids": (b_data.get("spouse_ids") or []) + [a_id]})

    def remove_spouse(self, a_id: str, b_id: str, *, actor: dict, reason: str):
        if not (reason or "").strip():
            raise ValidationError("Removal requires a reason for the audit log")
        a_data = self._get_existing(a_id)
        b_data = self._get_existing(b_id)

        a_ref = self._persons().document(a_id)
        b_ref = self._persons().document(b_id)
        now = server_timestamp()

        batch = self.db.batch()
        batch.update(a_ref, {
            "spouse_ids": gcf.ArrayRemove([b_id]),
            "updated_at": now, "updated_by_uid": actor.get("uid", ""),
        })
        batch.update(b_ref, {
            "spouse_ids": gcf.ArrayRemove([a_id]),
            "updated_at": now, "updated_by_uid": actor.get("uid", ""),
        })
        batch.commit()

        actor_with_reason = {**actor, "reason": reason}
        _write_audit(a_ref, action="remove_spouse", actor=actor_with_reason,
                     fields_changed=["spouse_ids"],
                     before={"spouse_ids": a_data.get("spouse_ids") or []},
                     after={"spouse_ids": [s for s in (a_data.get("spouse_ids") or []) if s != b_id],
                            "reason": reason})
        _write_audit(b_ref, action="remove_spouse", actor=actor_with_reason,
                     fields_changed=["spouse_ids"],
                     before={"spouse_ids": b_data.get("spouse_ids") or []},
                     after={"spouse_ids": [s for s in (b_data.get("spouse_ids") or []) if s != a_id],
                            "reason": reason})