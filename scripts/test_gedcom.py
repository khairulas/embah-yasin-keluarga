# scripts/test_gedcom.py
"""Quick smoke test — exports first N persons and validates basic structure."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.repositories import persons as person_repo
from app.services.gedcom_export import export_gedcom

app = create_app()
with app.app_context():
    all_persons = person_repo.list_all_full()
    print(f"Loaded {len(all_persons)} persons.")

    # Export and write to file
    content = export_gedcom(all_persons)
    out_path = "/tmp/test_export.ged"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Basic sanity checks
    lines = content.split("\n")
    assert lines[0] == "0 HEAD", "Missing HEAD"
    assert "0 TRLR" in content, "Missing TRLR"

    indi_count = sum(1 for l in lines if l.startswith("0 @I") and l.endswith("INDI"))
    fam_count  = sum(1 for l in lines if l.startswith("0 @F") and l.endswith("FAM"))
    print(f"INDI records: {indi_count}")
    print(f"FAM records:  {fam_count}")
    print(f"Output written to {out_path}")

    # Print the first individual for eyeball check
    in_first = False
    for line in lines[:50]:
        if line.startswith("0 @I"):
            in_first = True
        if in_first:
            print(line)
            if line.startswith("0 ") and not line.startswith("0 @I") and in_first:
                break