"""
Flask routes.

Two flavors of endpoints:
  - HTML pages (served by Jinja, used by the browser): /, /profile, /household/<id>, etc.
  - JSON API (called by frontend JS, all under /api/...): all return JSON

Auth: HTML pages render unconditionally; the frontend JS handles redirect-to-login.
JSON API endpoints all require @login_required.
"""
import os

from flask import Blueprint, jsonify, request, render_template, g, current_app

from .auth import login_required, admin_required, editor_required, is_admin_or_editor
from .repositories import (
    PersonRepository, HouseholdRepository, RelationshipRepository, recent_activity
)
from .models import ValidationError

bp = Blueprint("main", __name__)


# ---------------------------- HTML pages ----------------------------

@bp.route("/")
def index():
    return render_template("index.html",
                           firebase_config=_public_firebase_config())


@bp.route("/login")
def login_page():
    return render_template("login.html",
                           firebase_config=_public_firebase_config())


@bp.route("/profile/<person_id>")
def profile_page(person_id):
    return render_template("profile.html",
                           person_id=person_id,
                           firebase_config=_public_firebase_config())


@bp.route("/household/<household_id>")
def household_page(household_id):
    return render_template("household.html",
                           household_id=household_id,
                           firebase_config=_public_firebase_config())


def _public_firebase_config():
    """Config exposed to the browser. Safe to expose — these are public values."""
    return {
        "apiKey": os.environ.get("FIREBASE_WEB_API_KEY", ""),
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
    }


# ---------------------------- JSON API: persons ----------------------------

@bp.route("/api/me", methods=["GET"])
@login_required
def api_me():
    """Return the current user record."""
    return jsonify({"user": g.user})


@bp.route("/api/persons", methods=["GET"])
@login_required
def api_list_persons():
    q = request.args.get("q", "").strip()
    repo = PersonRepository()
    if q:
        results = repo.search_by_name(q, limit=int(request.args.get("limit", 20)))
    else:
        results = repo.list_all(limit=int(request.args.get("limit", 500)))
    return jsonify({"persons": results})


@bp.route("/api/persons/<person_id>", methods=["GET"])
@login_required
def api_get_person(person_id):
    repo = PersonRepository()
    person = repo.get(person_id)
    if person is None:
        return jsonify({"error": "not found"}), 404
    return jsonify({"person": person})


@bp.route("/api/persons", methods=["POST"])
@login_required
def api_create_person():
    actor = _actor_from_g()
    repo = PersonRepository()
    try:
        new_id = repo.create(request.json or {}, actor=actor)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"person_id": new_id, "person": repo.get(new_id)}), 201


@bp.route("/api/persons/<person_id>", methods=["PATCH"])
@login_required
def api_update_person(person_id):
    actor = _actor_from_g()
    repo = PersonRepository()
    try:
        updated = repo.update(person_id, request.json or {}, actor=actor)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"person": updated})


@bp.route("/api/persons/<person_id>", methods=["DELETE"])
@login_required
def api_delete_person(person_id):
    actor = _actor_from_g()
    repo = PersonRepository()
    try:
        repo.soft_delete(person_id, actor=actor)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


@bp.route("/api/persons/<person_id>/claim", methods=["POST"])
@login_required
def api_claim_person(person_id):
    """Link the current Google user to this Person record."""
    actor = _actor_from_g()
    repo = PersonRepository()
    try:
        person = repo.claim(person_id, actor=actor)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"person": person})


# ---------------------------- JSON API: households ----------------------------

@bp.route("/api/households", methods=["GET"])
@login_required
def api_list_households():
    repo = HouseholdRepository()
    return jsonify({"households": repo.list_all()})


@bp.route("/api/households/<household_id>", methods=["GET"])
@login_required
def api_get_household(household_id):
    repo = HouseholdRepository()
    h = repo.get(household_id)
    if h is None:
        return jsonify({"error": "not found"}), 404
    return jsonify({"household": h})


@bp.route("/api/households", methods=["POST"])
@login_required
def api_create_household():
    actor = _actor_from_g()
    repo = HouseholdRepository()
    try:
        new_id = repo.create(request.json or {}, actor=actor)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"household_id": new_id, "household": repo.get(new_id)}), 201


@bp.route("/api/households/<household_id>", methods=["PATCH"])
@login_required
def api_update_household(household_id):
    actor = _actor_from_g()
    repo = HouseholdRepository()
    try:
        updated = repo.update(household_id, request.json or {}, actor=actor)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"household": updated})


# ---------------------------- JSON API: audit ----------------------------

@bp.route("/api/audit/recent", methods=["GET"])
@login_required
def api_recent_activity():
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({"activity": recent_activity(limit=limit)})


@bp.route("/api/persons/<person_id>/audit", methods=["GET"])
@login_required
def api_person_audit(person_id):
    from .firebase_client import get_db
    from google.cloud import firestore as gcf
    db = get_db()
    q = (db.collection("persons").document(person_id).collection("audit_log")
            .order_by("changed_at", direction=gcf.Query.DESCENDING).limit(100))
    return jsonify({"audit": [{"log_id": s.id, **s.to_dict()} for s in q.stream()]})

# ---------------------------- HTML pages: tree ----------------------------

@bp.route("/tree")
def tree_default_page():
    founder_id = os.environ.get("FOUNDER_PERSON_ID", "")
    return render_template("tree.html",
                           focus_id=founder_id,
                           firebase_config=_public_firebase_config())


@bp.route("/tree/<person_id>")
def tree_focus_page(person_id):
    return render_template("tree.html",
                           focus_id=person_id,
                           firebase_config=_public_firebase_config())


# ---------------------------- JSON API: tree ----------------------------

@bp.route("/api/tree/<person_id>", methods=["GET"])
@login_required
def api_tree(person_id):
    MAX_UP, MAX_DOWN = 4, 6

    def _year(s):
        if not s: return None
        return int(s[:4]) if s[:4].isdigit() else None

    repo = PersonRepository()
    all_persons = repo.list_all(limit=2000)
    persons_by_id = {p["person_id"]: p for p in all_persons}

    if person_id not in persons_by_id:
        return jsonify({"error": "person not found"}), 404

    def _node(p):
        return {
            "id": p["person_id"],
            "name": p.get("full_name", "—"),
            "birth_year": _year(p.get("birth_date") or p.get("dob")),
            "death_year": _year(p.get("death_date")),
            "gender": p.get("gender"),
            "is_deceased": bool(p.get("death_date")) or (p.get("status") == "deceased"),
            "spouse_ids": p.get("spouse_ids") or [],
            "parent_ids": p.get("parent_ids") or [],
            "child_ids": p.get("child_ids") or [],
        }

    def _subtree(pid, depth, max_depth, visited):
        if pid in visited or depth > max_depth:
            return None
        visited.add(pid)
        p = persons_by_id.get(pid)
        if not p:
            return None
        node = _node(p)
        node["spouses"] = [_node(persons_by_id[s])
                            for s in node["spouse_ids"] if s in persons_by_id]
        node["children"] = [c for c in (
            _subtree(cid, depth + 1, max_depth, visited)
            for cid in node["child_ids"]
        ) if c is not None]
        return node

    def _ancestors(pid, depth, max_depth, visited):
        if pid in visited or depth > max_depth:
            return None
        visited.add(pid)
        p = persons_by_id.get(pid)
        if not p:
            return None
        node = _node(p)
        node["children"] = [a for a in (
            _ancestors(parent_id, depth + 1, max_depth, visited)
            for parent_id in node["parent_ids"]
        ) if a is not None]
        return node

    descendants = _subtree(person_id, 0, MAX_DOWN, set())
    ancestors = _ancestors(person_id, 0, MAX_UP, set())

    return jsonify({
        "focus_id": person_id,
        "descendants": descendants,
        "ancestors": ancestors,
    })


# ---------------------------- JSON API: relationships ----------------------------

def _may_edit_edge(endpoints) -> bool:
    """Authorization for ADD operations.

    Admin/editor may edit any edge. A claimed member may edit an edge only if
    their linked person is one of its endpoints (their own spouse/anak/parent).
    Removal is NOT covered here — removals stay @editor_required.
    """
    if is_admin_or_editor(g.user):
        return True
    mine = (g.user or {}).get("linked_person_id")
    return bool(mine) and mine in endpoints


def _forbidden_edge():
    return jsonify({"error": "forbidden — anda hanya boleh menambah hubungan untuk diri sendiri"}), 403


@bp.route("/api/relationships/parent-child", methods=["POST"])
@login_required
def api_add_parent_child():
    data = request.get_json() or {}
    actor = _actor_from_g()
    try:
        parent_id = data["parent_id"]
        child_id = data["child_id"]
    except KeyError as e:
        return jsonify({"error": str(e)}), 400
    # Ownership: member may add only if they are the parent or the child on this edge
    if not _may_edit_edge([parent_id, child_id]):
        return _forbidden_edge()
    try:
        RelationshipRepository().add_parent_child(
            parent_id=parent_id, child_id=child_id, actor=actor,
        )
        return jsonify({"ok": True})
    except (ValidationError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/relationships/parent-child", methods=["DELETE"])
@editor_required
def api_remove_parent_child():
    data = request.get_json() or {}
    actor = _actor_from_g()
    try:
        RelationshipRepository().remove_parent_child(
            parent_id=data["parent_id"],
            child_id=data["child_id"],
            actor=actor,
            reason=data.get("reason", ""),
        )
        return jsonify({"ok": True})
    except (ValidationError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/relationships/spouse", methods=["POST"])
@login_required
def api_add_spouse():
    data = request.get_json() or {}
    actor = _actor_from_g()
    try:
        a_id = data["a_id"]
        b_id = data["b_id"]
    except KeyError as e:
        return jsonify({"error": str(e)}), 400
    if not _may_edit_edge([a_id, b_id]):
        return _forbidden_edge()
    try:
        RelationshipRepository().add_spouse(a_id=a_id, b_id=b_id, actor=actor)
        return jsonify({"ok": True})
    except (ValidationError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/relationships/spouse", methods=["DELETE"])
@editor_required
def api_remove_spouse():
    data = request.get_json() or {}
    actor = _actor_from_g()
    try:
        RelationshipRepository().remove_spouse(
            a_id=data["a_id"], b_id=data["b_id"],
            actor=actor, reason=data.get("reason", ""),
        )
        return jsonify({"ok": True})
    except (ValidationError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/relationships/new-person", methods=["POST"])
@login_required
def api_add_new_person_relationship():
    """Create a brand-new person and link them to an anchor in one transaction-ish flow.

    Body: { kind: "anak"|"spouse"|"ibu_bapa", anchor_id: <existing person>,
            person: {full_name, jantina, ...} }

    Scope:
      - kind ∈ {anak, spouse, ibu_bapa}. "ibu_bapa" exists because deceased or
        absent ancestors cannot enter themselves — the anchor's child adds them.
      - Admin/editor may anchor to anyone. A member may anchor only to their own
        linked person (so a member can create their OWN parents, not arbitrary ones).
      - The new person is created first (audited), then linked (audited). If the
        link fails, the created person is soft-deleted to avoid orphan records.
    """
    data = request.get_json() or {}
    actor = _actor_from_g()

    kind = (data.get("kind") or "").strip().lower()
    if kind not in ("anak", "spouse", "ibu_bapa"):
        return jsonify({"error": "kind mesti 'anak', 'spouse', atau 'ibu_bapa'"}), 400

    anchor_id = data.get("anchor_id")
    if not anchor_id:
        return jsonify({"error": "anchor_id diperlukan"}), 400

    # Ownership: the anchor must be the member's own person (admin/editor bypass).
    if not _may_edit_edge([anchor_id]):
        return _forbidden_edge()

    person_payload = data.get("person") or {}
    if not (person_payload.get("full_name") or "").strip():
        return jsonify({"error": "Nama penuh diperlukan untuk orang baharu"}), 400

    repo = PersonRepository()
    rel = RelationshipRepository()

    # 1) Verify the anchor exists before creating anything.
    if repo.get(anchor_id) is None:
        return jsonify({"error": "Orang sandaran (anchor) tidak dijumpai"}), 404

    # 2) Create the new person.
    try:
        new_id = repo.create(person_payload, actor=actor)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    # 3) Link, rolling back the created person if the link fails.
    #    anak     -> new person is the anchor's child
    #    spouse   -> new person is the anchor's spouse
    #    ibu_bapa -> new person is the anchor's PARENT (anchor is the child)
    try:
        if kind == "anak":
            rel.add_parent_child(parent_id=anchor_id, child_id=new_id, actor=actor)
        elif kind == "ibu_bapa":
            rel.add_parent_child(parent_id=new_id, child_id=anchor_id, actor=actor)
        else:  # spouse
            rel.add_spouse(a_id=anchor_id, b_id=new_id, actor=actor)
    except (ValidationError, KeyError) as e:
        try:
            repo.soft_delete(new_id, actor=actor)
        except Exception:
            current_app.logger.exception("failed to roll back orphan person %s", new_id)
        return jsonify({"error": str(e)}), 400

    return jsonify({"ok": True, "person_id": new_id, "person": repo.get(new_id)}), 201


# ---------------------------- GEDCOM export ----------------------------

@bp.route("/export/gedcom", methods=["GET"])
@login_required
def export_gedcom():
    from flask import Response
    from datetime import datetime as _dt
    from .services.gedcom_export import export_gedcom as build_gedcom
    repo = PersonRepository()
    all_persons = repo.list_all(limit=2000)
    content = build_gedcom(all_persons)
    filename = f"embah-yasin-{_dt.utcnow().strftime('%Y%m%d')}.ged"
    return Response(
        content,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
    
@bp.route("/api/persons/search", methods=["GET"])
@login_required
def api_persons_search():
    """Substring search for the relationship picker."""
    q = request.args.get("q", "")
    exclude = request.args.get("exclude")
    repo = PersonRepository()
    results = repo.search_substring(q, limit=20, exclude_id=exclude)
    return jsonify({"results": results})

# ---------------------------- helpers ----------------------------

def _actor_from_g() -> dict:
    return {
        "uid": getattr(g, "uid", ""),
        "email": getattr(g, "user_email", ""),
        "name": getattr(g, "user_name", ""),
    }


@bp.errorhandler(Exception)
def _handle_unexpected(e):
    current_app.logger.exception("unhandled exception")
    return jsonify({"error": "internal server error"}), 500