from __future__ import annotations

import hashlib
import hmac


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_hash(data: bytes, expected: str) -> bool:
    computed = content_hash(data)
    return hmac.compare_digest(computed, expected)


def hash_string(value: str, encoding: str = "utf-8") -> str:
    return content_hash(value.encode(encoding))
