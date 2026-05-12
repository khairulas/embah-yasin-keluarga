"""
One-off migration: import the cleaned Excel into Firestore.

Usage:
    python migrations/import_excel.py path/to/Ahli_Keluarga_Embah_Yasin_Cleaned.xlsx

Idempotent — uses deterministic IDs derived from Household ID and member name+number,
so re-running won't create duplicates. It WILL update existing docs with any new data.

What it does:
  1. Reads the Households and Members sheets
  2. Creates a Person doc for each member (deterministic ID: p_{hhid}_{n})
  3. Creates a Household doc with members array pointing at those persons
  4. Marks the first member as ketua, second as pasangan, rest as anak (heuristic)
  5. Writes a one-time "import" audit log entry
"""
import sys
import os
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import pandas as pd

from app.firebase_client import get_db, server_timestamp
from app.models import normalize_phone, ValidationError


SYSTEM_ACTOR = {
    "uid": "system_import",
    "email": "system@embah-yasin.local",
    "name": "Sistem Import",
}


def role_for_index(idx: int, jantina: str | None) -> str:
    """Heuristic: first row = ketua, second = pasangan, rest = anak."""
    if idx == 0:
        return "ketua"
    if idx == 1:
        return "pasangan"
    return "anak"


def slugify(s: str) -> str:
    import re
    s = (s or "unnamed").lower().strip()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-")[:60] or "unnamed"


def import_workbook(xlsx_path: str, dry_run: bool = False):
    db = get_db()

    households_df = pd.read_excel(xlsx_path, sheet_name="Households")
    members_df = pd.read_excel(xlsx_path, sheet_name="Members")

    print(f"Loaded {len(households_df)} households, {len(members_df)} members")

    persons_written = 0
    households_written = 0

    for _, hh in households_df.iterrows():
        hh_id = str(hh["Household ID"]).lower()  # 'h001' -> doc id 'h001'
        hh_doc_id = hh_id

        members_in_hh = members_df[members_df["Household ID"] == hh["Household ID"]] \
            .sort_values("Member No")

        member_entries = []
        ketua_person_id = None

        for idx, (_, m) in enumerate(members_in_hh.iterrows()):
            nama = str(m["Nama Ahli Keluarga"] or "").strip()
            if not nama:
                continue
            jantina = m["Jantina"] if pd.notna(m["Jantina"]) else None
            tahun_lahir = int(m["Tahun Lahir"]) if pd.notna(m["Tahun Lahir"]) else None

            person_id = f"p_{hh_doc_id}_{int(m['Member No']):02d}"
            role = role_for_index(idx, jantina)

            person_doc = {
                "full_name": nama,
                "full_name_lower": nama.lower(),
                "jantina": jantina,
                "tahun_lahir": tahun_lahir,
                "tarikh_lahir": None,
                "status": "alive",
                "tarikh_meninggal": None,
                "email": None,
                "phone": None,
                "alt_phone": None,
                "address": {
                    "line1": "", "line2": "", "poskod": "",
                    "bandar": "", "negeri": "", "negara": "Malaysia"
                },
                "notes": "",
                "parent_ids": [],
                "spouse_ids": [],
                "child_ids": [],
                "claimed_by_uid": None,
                "claimed_at": None,
                "is_deleted": False,
                "created_at": server_timestamp(),
                "created_by_uid": SYSTEM_ACTOR["uid"],
                "updated_at": server_timestamp(),
                "updated_by_uid": SYSTEM_ACTOR["uid"],
            }

            # If ketua, attach contact info from the household row
            if role == "ketua":
                try:
                    person_doc["phone"] = normalize_phone(hh.get("No Telefon"))
                except ValidationError:
                    person_doc["phone"] = None
                email = hh.get("Email")
                if pd.notna(email) and email:
                    person_doc["email"] = str(email).strip().lower()
                ketua_person_id = person_id

            if dry_run:
                print(f"  [dry] person {person_id}: {nama} ({role})")
            else:
                db.collection("persons").document(person_id).set(person_doc)
                # Audit
                db.collection("persons").document(person_id) \
                    .collection("audit_log").document().set({
                        "changed_at": server_timestamp(),
                        "changed_by_uid": SYSTEM_ACTOR["uid"],
                        "changed_by_email": SYSTEM_ACTOR["email"],
                        "changed_by_name": SYSTEM_ACTOR["name"],
                        "action": "create",
                        "fields_changed": ["import"],
                        "before": {},
                        "after": {"source": "excel_import", "household": hh_doc_id},
                    })
                persons_written += 1

            member_entries.append({
                "person_id": person_id,
                "role": role,
                "full_name_cached": nama,
            })

        # Try to infer parent-child links: ketua + pasangan are parents of anak rows
        anak_ids = [m["person_id"] for m in member_entries if m["role"] == "anak"]
        parent_ids_for_anak = [m["person_id"] for m in member_entries
                               if m["role"] in ("ketua", "pasangan")]
        if not dry_run and parent_ids_for_anak and anak_ids:
            for anak_id in anak_ids:
                db.collection("persons").document(anak_id).update({
                    "parent_ids": parent_ids_for_anak
                })
            for parent_id in parent_ids_for_anak:
                db.collection("persons").document(parent_id).update({
                    "child_ids": anak_ids
                })
            # spouse linkage
            if len(parent_ids_for_anak) == 2:
                a, b = parent_ids_for_anak
                db.collection("persons").document(a).update({"spouse_ids": [b]})
                db.collection("persons").document(b).update({"spouse_ids": [a]})

        if not member_entries:
            print(f"  [skip] {hh_doc_id}: no parseable members")
            continue

        if ketua_person_id is None:
            ketua_person_id = member_entries[0]["person_id"]

        hh_doc = {
            "ketua_person_id": ketua_person_id,
            "members": member_entries,
            "registered_by_email": str(hh.get("Email", "")).strip().lower(),
            "registered_at": pd.Timestamp(hh["Timestamp"]).to_pydatetime() if pd.notna(hh["Timestamp"]) else None,
            "notes": "",
            "is_deleted": False,
            "created_at": server_timestamp(),
            "created_by_uid": SYSTEM_ACTOR["uid"],
            "updated_at": server_timestamp(),
            "updated_by_uid": SYSTEM_ACTOR["uid"],
        }
        if dry_run:
            print(f"  [dry] household {hh_doc_id}: {len(member_entries)} members")
        else:
            db.collection("households").document(hh_doc_id).set(hh_doc)
            households_written += 1

    print(f"\nDone. Wrote {persons_written} persons and {households_written} households.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx_path", help="Path to cleaned Excel file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written, don't actually write")
    args = parser.parse_args()
    import_workbook(args.xlsx_path, dry_run=args.dry_run)
