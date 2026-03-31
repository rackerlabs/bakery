#!/usr/bin/env python3
"""Encryption helpers for secrets Bakery must persist."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from bakery.config import settings


def _fernet() -> Fernet:
    if not settings.bakery_secret_encryption_key:
        raise RuntimeError("BAKERY_SECRET_ENCRYPTION_KEY is required for monitor secret storage")
    digest = hashlib.sha256(settings.bakery_secret_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
