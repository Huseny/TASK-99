import hashlib
import hmac
import os
import re
import secrets

PBKDF2_ITERATIONS = 390000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
        candidate_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(candidate_digest, expected_digest)
    except (ValueError, TypeError):
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_password_complexity(password: str) -> tuple[bool, str | None]:
    if len(password) < 12:
        return False, "Password must be at least 12 characters long."
    checks = [
        (r"[A-Z]", "uppercase letter"),
        (r"[a-z]", "lowercase letter"),
        (r"\d", "number"),
        (r"[^A-Za-z0-9]", "special character"),
    ]
    missing: list[str] = [label for pattern, label in checks if not re.search(pattern, password)]
    if missing:
        return False, f"Password must include at least one {', '.join(missing)}."
    return True, None
