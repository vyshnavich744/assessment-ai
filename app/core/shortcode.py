"""
Short-code generation.

Design choice: random base62 code generated per request, checked for
collision against the DB, with bounded retries -- rather than a global
counter/sequence. This avoids a single point of contention (no shared
counter to lock) and keeps codes non-guessable/non-enumerable, which is
a reasonable default for a public shortener. Trade-off: at very large
scale (billions of active codes) collision probability rises and retry
counts increase; documented as a scaling limitation.
"""
import secrets
import string

ALPHABET = string.ascii_letters + string.digits  # 62 chars


def generate_code(length: int = 7) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
