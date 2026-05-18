"""
Authentication helpers.

Flow:
1. Frontend uses Firebase JS SDK to do Google sign-in. Result: an ID token.
2. Frontend sends every API request with `Authorization: Bearer <id_token>` header.
3. Flask verifies the token here, gets the Firebase UID, and looks up our user record.

We DO NOT use Flask sessions for auth. The ID token is the session.
"""
from functools import wraps
from typing import Optional, Callable

from flask import request, jsonify, g
from firebase_admin import auth as firebase_auth

from .firebase_client import get_db, server_timestamp


def verify_token(authorization_header: Optional[str]) -> Optional[dict]:
    """Verify a Bearer token and return decoded claims, or None if invalid."""
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return None
    token = authorization_header.split(" ", 1)[1].strip()
    try:
        return firebase_auth.verify_id_token(token, clock_skew_seconds=10)
    except (firebase_auth.InvalidIdTokenError, firebase_auth.ExpiredIdTokenError, ValueError):
        return None


def upsert_user_record(decoded_token: dict) -> dict:
    """
    Ensure a /users/{uid} doc exists. Returns the user record as a dict
    with real timestamp values (not Sentinel placeholders), so the caller
    can safely JSON-encode it.
    """
    db = get_db()
    uid = decoded_token["uid"]
    email = decoded_token.get("email", "")
    name = decoded_token.get("name", "")
    picture = decoded_token.get("picture", "")

    user_ref = db.collection("users").document(uid)
    snap = user_ref.get()

    if not snap.exists:
        user_ref.set({
            "uid": uid,
            "email": email,
            "display_name": name,
            "photo_url": picture,
            "linked_person_id": None,
            "role": "member",
            "first_login_at": server_timestamp(),
            "last_login_at": server_timestamp(),
        })
    else:
        user_ref.update({
            "email": email,
            "display_name": name,
            "photo_url": picture,
            "last_login_at": server_timestamp(),
        })

    # Re-fetch so we return resolved timestamps, not Sentinel placeholders
    return user_ref.get().to_dict()


def login_required(view: Callable) -> Callable:
    """
    Decorator: rejects requests without a valid Firebase ID token.
    On success, populates `g.user` with the user record and `g.uid`.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        decoded = verify_token(request.headers.get("Authorization"))
        if decoded is None:
            return jsonify({"error": "unauthorized"}), 401

        user = upsert_user_record(decoded)
        g.uid = decoded["uid"]
        g.user = user
        g.user_email = decoded.get("email", "")
        g.user_name = decoded.get("name", "")
        return view(*args, **kwargs)
    return wrapper


def admin_required(view: Callable) -> Callable:
    """Decorator: requires the user to have role='admin'."""
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user.get("role") != "admin":
            return jsonify({"error": "forbidden"}), 403
        return view(*args, **kwargs)
    return wrapper

def editor_required(view: Callable) -> Callable:
    """Decorator: requires role='admin' or role='editor'."""
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user.get("role") not in ("admin", "editor"):
            return jsonify({"error": "forbidden — editor or admin role required"}), 403
        return view(*args, **kwargs)
    return wrapper