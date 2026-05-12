"""
Domain models and validators.

We use plain dicts as the on-the-wire representation (Firestore stores dicts),
but validate them through these functions before writing.
"""
import re
from datetime import date
from typing import Optional

import phonenumbers


JANTINA_VALUES = {"L", "P"}
STATUS_VALUES = {"alive", "deceased", "unknown"}
ROLE_VALUES = {"ketua", "pasangan", "anak", "ibu_bapa", "lain"}


class ValidationError(ValueError):
    """Raised when input data fails validation."""
    pass


def normalize_phone(raw: Optional[str], default_region: str = "MY") -> Optional[str]:
    """
    Normalize a phone number to E.164 format (e.g., '+60194746960').
    Returns None if input is empty. Raises ValidationError if input is unparseable.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        parsed = phonenumbers.parse(s, default_region)
    except phonenumbers.NumberParseException as e:
        raise ValidationError(f"Invalid phone number: {raw!r} ({e})")
    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError(f"Invalid phone number: {raw!r}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_date(raw: Optional[str]) -> Optional[str]:
    """Validate and normalize an ISO date string YYYY-MM-DD. Returns None if blank."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        raise ValidationError(f"Date must be YYYY-MM-DD format, got {raw!r}")
    try:
        d = date.fromisoformat(s)
    except ValueError as e:
        raise ValidationError(f"Invalid date {raw!r}: {e}")
    if d.year < 1850 or d > date.today():
        raise ValidationError(f"Date {raw!r} out of reasonable range")
    return s


def validate_person_input(data: dict) -> dict:
    """
    Validate and normalize input from the registration/edit form.
    Returns a dict suitable for Firestore. Raises ValidationError on bad input.
    Only includes keys that are present in `data` — caller decides which to update.
    """
    out = {}

    if "full_name" in data:
        name = str(data["full_name"]).strip()
        if not name:
            raise ValidationError("full_name is required")
        if len(name) > 200:
            raise ValidationError("full_name too long (max 200 chars)")
        out["full_name"] = name
        out["full_name_lower"] = name.lower()  # for case-insensitive search

    if "jantina" in data:
        j = str(data["jantina"]).strip().upper()
        if j not in JANTINA_VALUES:
            raise ValidationError(f"jantina must be one of {JANTINA_VALUES}, got {j!r}")
        out["jantina"] = j

    if "tahun_lahir" in data:
        v = data["tahun_lahir"]
        if v in (None, "", 0):
            out["tahun_lahir"] = None
        else:
            try:
                year = int(v)
            except (TypeError, ValueError):
                raise ValidationError(f"tahun_lahir must be an integer, got {v!r}")
            if year < 1850 or year > date.today().year:
                raise ValidationError(f"tahun_lahir {year} out of range")
            out["tahun_lahir"] = year

    if "tarikh_lahir" in data:
        out["tarikh_lahir"] = normalize_date(data["tarikh_lahir"])
        # If tarikh_lahir is set, derive tahun_lahir
        if out["tarikh_lahir"]:
            out["tahun_lahir"] = int(out["tarikh_lahir"][:4])

    if "status" in data:
        s = str(data["status"]).strip().lower()
        if s not in STATUS_VALUES:
            raise ValidationError(f"status must be one of {STATUS_VALUES}, got {s!r}")
        out["status"] = s

    if "tarikh_meninggal" in data:
        out["tarikh_meninggal"] = normalize_date(data["tarikh_meninggal"])

    if "email" in data:
        e = str(data["email"]).strip().lower() if data["email"] else None
        if e and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
            raise ValidationError(f"Invalid email: {e!r}")
        out["email"] = e

    if "phone" in data:
        out["phone"] = normalize_phone(data["phone"])

    if "alt_phone" in data:
        out["alt_phone"] = normalize_phone(data["alt_phone"])

    if "address" in data:
        addr = data["address"] or {}
        if not isinstance(addr, dict):
            raise ValidationError("address must be an object")
        clean_addr = {
            "line1": str(addr.get("line1", "")).strip()[:200],
            "line2": str(addr.get("line2", "")).strip()[:200],
            "poskod": str(addr.get("poskod", "")).strip()[:10],
            "bandar": str(addr.get("bandar", "")).strip()[:100],
            "negeri": str(addr.get("negeri", "")).strip()[:100],
            "negara": str(addr.get("negara", "Malaysia")).strip()[:100],
        }
        out["address"] = clean_addr

    if "notes" in data:
        out["notes"] = str(data.get("notes", "")).strip()[:2000]

    # Relationship arrays — IDs only, no validation of existence here
    # (FK integrity is enforced at write time in the repository)
    for key in ("parent_ids", "spouse_ids", "child_ids"):
        if key in data:
            ids = data[key] or []
            if not isinstance(ids, list):
                raise ValidationError(f"{key} must be an array")
            out[key] = [str(i).strip() for i in ids if str(i).strip()]

    return out


def diff_dict(before: dict, after: dict) -> tuple[list[str], dict, dict]:
    """
    Return (changed_keys, before_subset, after_subset) for fields that differ.
    Used for compact audit log entries.
    """
    changed = []
    b_sub, a_sub = {}, {}
    for k in after:
        if before.get(k) != after.get(k):
            changed.append(k)
            b_sub[k] = before.get(k)
            a_sub[k] = after.get(k)
    return changed, b_sub, a_sub
