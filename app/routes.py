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

from .auth import login_required, admin_required
from .repositories import (
    PersonRepository, HouseholdRepository, recent_activity
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
