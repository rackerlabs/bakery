#!/usr/bin/env python3
"""HMAC authentication helpers for Bakery service-to-service API calls."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from bakery.config import settings
from bakery.database import get_db
from bakery.models import Monitor, MonitorBootstrapCredential
from bakery.secret_store import decrypt_secret
from shared.hmac import build_hmac_signing_payload, hmac_sha256_hex


@dataclass(slots=True)
class BootstrapAuthContext:
    monitor_id: str
    key_id: str


@dataclass(slots=True)
class MonitorAuthContext:
    monitor_uuid: str
    monitor_id: str
    key_id: str


def _validate_timestamp(ts_raw: str) -> None:
    try:
        ts = int(ts_raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Timestamp header",
        ) from exc

    now = int(time.time())
    if abs(now - ts) > settings.bakery_hmac_timestamp_skew_sec:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Request timestamp outside allowed skew window",
        )


def _parse_hmac_authorization(authorization: str | None) -> tuple[str, str]:
    if not authorization or not authorization.startswith("HMAC "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization[len("HMAC ") :].strip()
    if ":" not in token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC authorization format",
        )
    key_id, signature = token.split(":", 1)
    key_id = key_id.strip()
    signature = signature.strip().lower()
    if not key_id or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC authorization format",
        )
    return key_id, signature


async def _validate_signed_request(
    *,
    request: Request,
    authorization: str | None,
    x_timestamp: str | None,
    expected_key_id: str,
    shared_secret: str,
    body: bytes | None = None,
) -> str:
    if not x_timestamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Timestamp header",
        )
    _validate_timestamp(x_timestamp)
    key_id, signature = _parse_hmac_authorization(authorization)
    if key_id != expected_key_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown key id",
        )

    if body is None:
        body = await request.body()
    payload = build_hmac_signing_payload(
        timestamp=x_timestamp,
        method=request.method,
        path=request.url.path,
        body=body,
    )
    expected = hmac_sha256_hex(shared_secret, payload)
    if not secrets.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid request signature",
        )
    return key_id


def _resolve_admin_key(key_id: str) -> str | None:
    if key_id == settings.bakery_admin_hmac_active_key_id and settings.bakery_admin_hmac_active_key:
        return settings.bakery_admin_hmac_active_key
    if key_id == settings.bakery_admin_hmac_next_key_id and settings.bakery_admin_hmac_next_key:
        return settings.bakery_admin_hmac_next_key
    if key_id == settings.bakery_hmac_active_key_id and settings.bakery_hmac_active_key:
        return settings.bakery_hmac_active_key
    if key_id == settings.bakery_hmac_next_key_id and settings.bakery_hmac_next_key:
        return settings.bakery_hmac_next_key
    return None


async def require_admin_hmac_auth(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_timestamp: str | None = Header(default=None, alias="X-Timestamp"),
) -> str:
    if request.url.path.endswith("/health"):
        return "__health__"
    if not settings.bakery_auth_enabled:
        return "__auth_disabled__"
    if settings.bakery_auth_mode.lower() != "hmac":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unsupported auth mode",
        )

    key_id, _ = _parse_hmac_authorization(authorization)
    shared_secret = _resolve_admin_key(key_id)
    if not shared_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown key id",
        )
    return await _validate_signed_request(
        request=request,
        authorization=authorization,
        x_timestamp=x_timestamp,
        expected_key_id=key_id,
        shared_secret=shared_secret,
    )


async def require_hmac_auth(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_timestamp: str | None = Header(default=None, alias="X-Timestamp"),
) -> str:
    """Backward-compatible alias used by existing auth regression tests."""

    return await require_admin_hmac_auth(
        request=request,
        authorization=authorization,
        x_timestamp=x_timestamp,
    )


async def require_bootstrap_admin_access(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_timestamp: str | None = Header(default=None, alias="X-Timestamp"),
    session_token: str | None = Cookie(default=None),
) -> str:
    if authorization and authorization.startswith("HMAC "):
        return await require_admin_hmac_auth(
            request=request,
            authorization=authorization,
            x_timestamp=x_timestamp,
        )

    from bakery.operator_auth import require_admin as require_operator_admin
    from bakery.operator_auth import require_auth_if_enabled

    context = await require_auth_if_enabled(request=request, session_token=session_token, db=db)
    admin_context = await require_operator_admin(context=context)
    return f"operator:{admin_context.username}"


async def require_bootstrap_hmac_auth(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_timestamp: str | None = Header(default=None, alias="X-Timestamp"),
) -> BootstrapAuthContext:
    body = await request.body()
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body"
        ) from exc

    monitor_id = str(payload.get("monitor_id") or "").strip()
    if not monitor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="monitor_id is required"
        )

    credential = (
        db.query(MonitorBootstrapCredential)
        .filter(MonitorBootstrapCredential.monitor_id == monitor_id)
        .first()
    )
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown monitor bootstrap credential",
        )

    await _validate_signed_request(
        request=request,
        authorization=authorization,
        x_timestamp=x_timestamp,
        expected_key_id=credential.key_id,
        shared_secret=decrypt_secret(credential.encrypted_secret),
        body=body,
    )
    return BootstrapAuthContext(monitor_id=monitor_id, key_id=credential.key_id)


async def require_monitor_hmac_auth(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_timestamp: str | None = Header(default=None, alias="X-Timestamp"),
    x_bakery_monitor_uuid: str | None = Header(default=None, alias="X-Bakery-Monitor-UUID"),
) -> MonitorAuthContext:
    if not x_bakery_monitor_uuid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Bakery-Monitor-UUID header",
        )

    monitor = db.query(Monitor).filter(Monitor.monitor_uuid == x_bakery_monitor_uuid).first()
    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown monitor",
        )

    await _validate_signed_request(
        request=request,
        authorization=authorization,
        x_timestamp=x_timestamp,
        expected_key_id=monitor.key_id,
        shared_secret=decrypt_secret(monitor.encrypted_secret),
    )
    return MonitorAuthContext(
        monitor_uuid=monitor.monitor_uuid,
        monitor_id=monitor.monitor_id,
        key_id=monitor.key_id,
    )
