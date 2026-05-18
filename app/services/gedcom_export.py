# app/services/gedcom_export.py
"""
GEDCOM 5.5.1 exporter. UTF-8 encoded. Compatible with FamilySearch,
MyHeritage, Ancestry, Gramps, and most genealogy tools.

Design notes:
  - FAM records are built by grouping children on the sorted (parent_a, parent_b)
    tuple, so step-siblings end up in different FAMs even if they share one parent.
  - Spouse pairs with no children still get a FAM record, with no CHIL lines.
  - Single-parent children (only one entry in parent_ids) get a FAM with only
    HUSB or WIFE based on gender — GEDCOM allows this.
  - Dates are emitted in DD MMM YYYY format (the GEDCOM standard form).
"""
from datetime import datetime
from io import StringIO
from app.services.malay_names import parse_name, to_gedcom_name


_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _gedcom_date(iso_date: str) -> str | None:
    """'2018-03-15' -> '15 MAR 2018'. '2018' -> '2018'. '2018-03' -> 'MAR 2018'."""
    if not iso_date:
        return None
    parts = iso_date.split("-")
    try:
        if len(parts) == 1:
            return str(int(parts[0]))
        if len(parts) == 2:
            y, m = int(parts[0]), int(parts[1])
            return f"{_MONTHS[m - 1]} {y}"
        if len(parts) >= 3:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{d:02d} {_MONTHS[m - 1]} {y}"
    except (ValueError, IndexError):
        return None
    return None


def _person_xref(person_id: str) -> str:
    """Firestore IDs can contain chars GEDCOM doesn't like. Use a stable hash slot."""
    # GEDCOM xrefs: 1-20 alphanumerics. Firestore auto-IDs are 20-char base62.
    # Strip anything non-alphanumeric and uppercase.
    cleaned = "".join(c for c in person_id if c.isalnum()).upper()[:18]
    return f"@I{cleaned}@"


def _fam_xref(parent_ids):
    h = abs(hash(tuple(parent_ids))) % (10 ** 10)
    return f"@F{h}@"

def export_gedcom(persons, *, submitter_name="Embah Yasin Family Registry"):
    persons_by_id = {p["person_id"]: p for p in persons}
    out = StringIO()

    out.write("0 HEAD\n")
    out.write("1 SOUR EmbahYasinRegistry\n")
    out.write("2 VERS 1.0\n")
    out.write("2 NAME Embah Yasin Family Registry\n")
    out.write("1 DEST ANY\n")
    out.write(f"1 DATE {datetime.utcnow().strftime('%d %b %Y').upper()}\n")
    out.write("1 GEDC\n")
    out.write("2 VERS 5.5.1\n")
    out.write("2 FORM LINEAGE-LINKED\n")
    out.write("1 CHAR UTF-8\n")
    out.write("1 SUBM @SUBM1@\n")

    out.write("0 @SUBM1@ SUBM\n")
    out.write(f"1 NAME {submitter_name}\n")

    for person in persons:
        pid = person["person_id"]
        xref = _person_xref(pid)
        out.write(f"0 {xref} INDI\n")

        parsed = parse_name(person.get("full_name", ""))
        if person.get("gedcom_surname"):
            parsed["surname"] = person["gedcom_surname"]

        out.write(f"1 NAME {to_gedcom_name(parsed)}\n")
        if parsed["npfx"]:
            out.write(f"2 NPFX {parsed['npfx']}\n")
        if parsed["given"]:
            out.write(f"2 GIVN {parsed['given']}\n")
        if parsed["surname"]:
            out.write(f"2 SURN {parsed['surname']}\n")

        full = person.get("full_name", "")
        if full and full != to_gedcom_name(parsed):
            out.write(f"1 NOTE Nama penuh asal: {full}\n")

        sex = (person.get("gender") or "").upper()
        if sex in ("M", "MALE", "LELAKI", "L"):
            out.write("1 SEX M\n")
        elif sex in ("F", "FEMALE", "PEREMPUAN", "P"):
            out.write("1 SEX F\n")

        birth = person.get("birth_date") or person.get("dob")
        if birth:
            out.write("1 BIRT\n")
            date_str = _gedcom_date(birth)
            if date_str:
                out.write(f"2 DATE {date_str}\n")
            if person.get("birth_place"):
                out.write(f"2 PLAC {person['birth_place']}\n")

        has_death_date = bool(person.get("death_date"))
        is_deceased = has_death_date or parsed["is_deceased_marker"] or person.get("status") == "deceased"
        if is_deceased:
            out.write("1 DEAT\n" if has_death_date else "1 DEAT Y\n")
            if has_death_date:
                date_str = _gedcom_date(person["death_date"])
                if date_str:
                    out.write(f"2 DATE {date_str}\n")
            if person.get("death_place"):
                out.write(f"2 PLAC {person['death_place']}\n")

        parent_ids = person.get("parent_ids") or []
        if parent_ids:
            out.write(f"1 FAMC {_fam_xref(sorted(parent_ids))}\n")

        for spouse_id in (person.get("spouse_ids") or []):
            out.write(f"1 FAMS {_fam_xref(sorted([pid, spouse_id]))}\n")

    # Families
    families = {}
    for person in persons:
        pid = person["person_id"]
        for spouse_id in (person.get("spouse_ids") or []):
            if spouse_id not in persons_by_id:
                continue
            key = tuple(sorted([pid, spouse_id]))
            families.setdefault(key, {"parents": list(key), "children": []})

        parent_ids = person.get("parent_ids") or []
        if parent_ids:
            key = tuple(sorted(parent_ids))
            fam = families.setdefault(key, {"parents": list(key), "children": []})
            if pid not in fam["children"]:
                fam["children"].append(pid)

    for key, fam in families.items():
        out.write(f"0 {_fam_xref(list(key))} FAM\n")
        for parent_id in fam["parents"]:
            parent = persons_by_id.get(parent_id)
            if not parent:
                continue
            sex = (parent.get("gender") or "").upper()
            tag = "HUSB" if sex in ("M", "MALE", "LELAKI", "L") else \
                  "WIFE" if sex in ("F", "FEMALE", "PEREMPUAN", "P") else \
                  "HUSB"
            out.write(f"1 {tag} {_person_xref(parent_id)}\n")
        for child_id in fam["children"]:
            out.write(f"1 CHIL {_person_xref(child_id)}\n")

    out.write("0 TRLR\n")
    return out.getvalue()