# scripts/grant_role.py
"""Usage: python scripts/grant_role.py [email protected] admin"""
import sys
import firebase_admin
from firebase_admin import auth, credentials

firebase_admin.initialize_app(credentials.Certificate("serviceAccountKey.json"))

email, role = sys.argv[1], sys.argv[2]
assert role in ("viewer", "editor", "admin"), "role must be viewer|editor|admin"

user = auth.get_user_by_email(email)
existing = user.custom_claims or {}
auth.set_custom_user_claims(user.uid, {**existing, "role": role})
print(f"Granted {role} to {email} (uid={user.uid}). They must sign out and back in to refresh the ID token.")