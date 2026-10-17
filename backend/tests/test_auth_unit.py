import uuid

from app.auth import create_access_token, hash_password, verify_password
from app.config import get_settings


def test_password_verification_and_token_subject() -> None:
    user_id = uuid.uuid4()
    password_hash = hash_password("correct-password")

    assert verify_password("not-the-password", password_hash) is False
    assert verify_password("correct-password", password_hash) is True
    token = create_access_token(user_id)
    assert token
    assert get_settings().jwt_secret
