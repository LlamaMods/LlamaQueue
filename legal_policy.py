from datetime import datetime

from database.models import LegalAcceptance

PRIVACY_POLICY_VERSION = "2026-11-18-v1"
TERMS_VERSION = "2026-11-18-v1"


def session_has_current_acceptance(request) -> bool:
    return (
        request.session.get("legal_privacy_version") == PRIVACY_POLICY_VERSION
        and request.session.get("legal_terms_version") == TERMS_VERSION
    )


def save_acceptance(db, user_id: int, request) -> bool:
    if not session_has_current_acceptance(request):
        return False
    row = db.query(LegalAcceptance).filter_by(user_id=user_id).first()
    if row is None:
        row = LegalAcceptance(user_id=user_id)
        db.add(row)
    row.privacy_version = PRIVACY_POLICY_VERSION
    row.terms_version = TERMS_VERSION
    row.accepted_at = datetime.utcnow()
    db.flush()
    return True


def user_has_current_acceptance(db, user_id: int) -> bool:
    row = db.query(LegalAcceptance).filter_by(user_id=user_id).first()
    return bool(
        row
        and row.privacy_version == PRIVACY_POLICY_VERSION
        and row.terms_version == TERMS_VERSION
    )
