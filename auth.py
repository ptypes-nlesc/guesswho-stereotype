"""Staff authentication and authorization helpers."""

from flask import session

ROLE_MODERATOR = "moderator"
ROLE_AUDITOR = "auditor"
STAFF_ROLES = frozenset({ROLE_MODERATOR, ROLE_AUDITOR})


def get_session_role():
    """Return the logged-in staff role, or None."""
    role = session.get("role")
    if role in STAFF_ROLES:
        return role
    if session.get("moderator"):
        return ROLE_MODERATOR
    return None


def is_moderator():
    return get_session_role() == ROLE_MODERATOR


def is_staff():
    return get_session_role() in STAFF_ROLES


def set_staff_session(role):
    """Persist staff login in the Flask session."""
    session["role"] = role
    session["moderator"] = role == ROLE_MODERATOR


def clear_staff_session():
    session.pop("role", None)
    session.pop("moderator", None)
    session.pop("moderator_session_game_id", None)


def authenticate_staff(role, password, moderator_password, auditor_password):
    """Validate staff credentials. Returns True when login should succeed."""
    if role == ROLE_MODERATOR:
        return bool(moderator_password) and password == moderator_password
    if role == ROLE_AUDITOR:
        return bool(auditor_password) and password == auditor_password
    return False


def can_view_game(game_id, current_session_game_id):
    """Return whether the current staff user may view a game."""
    if not is_staff():
        return False
    if is_moderator():
        return True
    active_game_id = current_session_game_id()
    return bool(active_game_id and game_id == active_game_id)