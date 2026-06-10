from __future__ import annotations

import hashlib
import hmac
import secrets

# Readable password alphabet: avoid look-alike characters so a password read
# aloud or copied from a screen is hard to get wrong.
_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
_PBKDF2_ITERATIONS = 120_000


def generate_staff_password(groups: int = 3, group_len: int = 4) -> str:
    """Generate a human-shareable staff password like ``Kp7m-Rx29-Tw3h``.

    Grouped, fixed-length, and drawn from an unambiguous alphabet so staff can
    read it to a colleague or type it from a printed sheet without errors.
    """
    parts = ["".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(group_len)) for _ in range(groups)]
    return "-".join(parts)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return ``(hash_hex, salt_hex)`` for a password using PBKDF2-HMAC-SHA256."""
    salt_hex = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERATIONS
    )
    return digest.hex(), salt_hex


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    """Constant-time check of ``password`` against a stored hash+salt."""
    if not hash_hex or not salt_hex:
        return False
    try:
        candidate, _ = hash_password(password or "", salt_hex)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, hash_hex)
