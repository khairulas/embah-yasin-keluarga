"""
Firestore client singleton.

Uses firebase-admin SDK. The Admin SDK has full read/write access to Firestore,
bypassing security rules. This is what we want on the server side — security rules
are still enforced for any client-side reads from the browser.
"""
import os
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import Client


_db: Optional[Client] = None


def get_db() -> Client:
    """Return a process-wide Firestore client, initializing on first call."""
    global _db
    if _db is not None:
        return _db

    if not firebase_admin._apps:
        cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            # Fallback to Application Default Credentials (e.g., on GCP)
            firebase_admin.initialize_app()

    _db = firestore.client()
    return _db


def server_timestamp():
    """Return Firestore SERVER_TIMESTAMP sentinel (set by server, not client)."""
    return firestore.SERVER_TIMESTAMP
