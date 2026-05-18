"""Seed the local emulator with a small test dataset.
Run with FIRESTORE_EMULATOR_HOST set."""
import os
assert os.getenv("FIRESTORE_EMULATOR_HOST"), "Run with FIRESTORE_EMULATOR_HOST set!"

import firebase_admin
from firebase_admin import firestore, credentials, auth

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Person records matching the schema PersonRepository expects
persons = [
    {"id": "founder",
     "full_name": "Almarhum Kiyai Haji Muhammad Yasin Taha Al-Bakri bin Abu Bakar",
     "gender": "M", "birth_date": "1890", "death_date": "1965", "status": "deceased",
     "parent_ids": [], "spouse_ids": ["wife1", "wife2", "wife3", "wife4"],
     "child_ids": ["child1", "child2", "child3"]},
    {"id": "wife1",
     "full_name": "Almarhumah Hajah Salamah binti Haji Abdul Rahman",
     "gender": "F", "birth_date": "1895", "death_date": "1960", "status": "deceased",
     "parent_ids": [], "spouse_ids": ["founder"], "child_ids": ["child1"]},
    {"id": "wife2",
     "full_name": "Almarhumah Hajah Khadijah binti Haji Hassan",
     "gender": "F", "birth_date": "1900", "death_date": "1970", "status": "deceased",
     "parent_ids": [], "spouse_ids": ["founder"], "child_ids": ["child2"]},
    {"id": "wife3",
     "full_name": "Almarhumah Hajah Safiah binti Hussein",
     "gender": "F", "birth_date": "1905", "death_date": "1975", "status": "deceased",
     "parent_ids": [], "spouse_ids": ["founder"], "child_ids": []},
    {"id": "wife4",
     "full_name": "Almarhumah Hajah Masuti binti Asror",
     "gender": "F", "birth_date": "1910", "death_date": "1985", "status": "deceased",
     "parent_ids": [], "spouse_ids": ["founder"], "child_ids": ["child3"]},
    {"id": "child1", "full_name": "Haji Ahmad bin Muhammad Yasin",
     "gender": "M", "birth_date": "1920", "status": "alive",
     "parent_ids": ["founder", "wife1"], "spouse_ids": [], "child_ids": []},
    {"id": "child2", "full_name": "Hajah Fatimah binti Muhammad Yasin",
     "gender": "F", "birth_date": "1925", "status": "alive",
     "parent_ids": ["founder", "wife2"], "spouse_ids": [], "child_ids": []},
    {"id": "child3", "full_name": "Haji Ismail bin Muhammad Yasin",
     "gender": "M", "birth_date": "1935", "status": "alive",
     "parent_ids": ["founder", "wife4"], "spouse_ids": [], "child_ids": []},
]

for p in persons:
    doc_id = p.pop("id")
    # Add the standard fields PersonRepository expects
    p["full_name_lower"] = p["full_name"].lower()
    p["is_deleted"] = False
    p["claimed_by_uid"] = None
    p["claimed_at"] = None
    p["created_at"] = firestore.SERVER_TIMESTAMP
    p["created_by_uid"] = "seed-script"
    p["updated_at"] = firestore.SERVER_TIMESTAMP
    p["updated_by_uid"] = "seed-script"
    db.collection("persons").document(doc_id).set(p)
    print(f"Seeded {doc_id}")

# Create or fetch test admin user
try:
    test_user = auth.create_user(
        email="admin@test.local",
        password="testpass123",
        display_name="Test Admin",
    )
except auth.EmailAlreadyExistsError:
    test_user = auth.get_user_by_email("admin@test.local")

# Set role in Firestore (matches upsert_user_record convention)
db.collection("users").document(test_user.uid).set({
    "uid": test_user.uid,
    "email": "admin@test.local",
    "display_name": "Test Admin",
    "role": "admin",
}, merge=True)
print(f"\nTest user: admin@test.local / testpass123 (admin)")