# Sistem Pendaftaran Keluarga Embah Yasin

Family registration and family-tree system built on **Python + Firebase + PythonAnywhere**.

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | HTML + Bootstrap + Firebase JS SDK (for Google sign-in) |
| Backend | Flask (Python) on PythonAnywhere free tier |
| Database | Cloud Firestore (Firebase Spark plan — free) |
| Auth | Firebase Authentication — Google sign-in only |
| Audit | Firestore sub-collection per document |

## Project structure

```
embah_yasin/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── auth.py              # Firebase token verification
│   ├── firebase_client.py   # Firestore client singleton
│   ├── models.py            # Data classes for Person, Household, Address
│   ├── repositories.py      # Firestore CRUD with audit logging
│   ├── routes.py            # Flask routes (HTML pages + JSON API)
│   ├── templates/           # Jinja2 templates
│   └── static/              # JS, CSS
├── migrations/
│   └── import_excel.py      # One-off import of cleaned Excel into Firestore
├── docs/
│   ├── DATA_MODEL.md        # Firestore collection schema
│   ├── SECURITY_RULES.md    # Firestore security rules
│   └── DEPLOYMENT.md        # PythonAnywhere setup walkthrough
├── requirements.txt
├── wsgi.py                  # Entry point for PythonAnywhere
└── .env.example             # Template for environment variables
```

## Quick start (local dev)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in FIREBASE_PROJECT_ID and place serviceAccountKey.json
python -m flask --app app run --debug
```

See `docs/DEPLOYMENT.md` for PythonAnywhere setup.

## Initial data import

```bash
python migrations/import_excel.py path/to/Ahli_Keluarga_Embah_Yasin_Cleaned.xlsx
```

Imports households and members from the cleaned Excel into Firestore. Idempotent —
safe to re-run; uses deterministic IDs based on Household ID.
