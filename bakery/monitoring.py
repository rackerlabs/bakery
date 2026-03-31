#!/usr/bin/env python3
"""Monitor registry, route catalog, and request validation helpers."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from bakery.config import settings
from bakery.models import (
    Monitor,
    MonitorBootstrapCredential,
    MonitorEvent,
    MonitorRouteCatalogEntry,
)
from bakery.secret_store import encrypt_secret
from shared.bakery_contract import (
    MonitorBootstrapCredentialResponse,
    MonitorHeartbeatRequest,
    MonitorHeartbeatResponse,
    MonitorRegistrationRequest,
    MonitorRegistrationResponse,
    MonitorRouteCatalogEntry as MonitorRouteCatalogEntryContract,
    MonitorRouteCatalogSyncRequest,
    MonitorRouteCatalogSyncResponse,
)

POLICY_METADATA_KEY = "poundcake_policy"
ROUTE_VALIDATION_BYPASS_SOURCES = {"poundcake_system"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _random_secret() -> str:
    return secrets.token_urlsafe(32)


def _routes_digest(routes: list[dict[str, Any]]) -> str:
    encoded = json.dumps(routes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def record_monitor_event(
    db: Session,
    *,
    monitor_uuid: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        MonitorEvent(
            monitor_uuid=monitor_uuid,
            event_type=event_type,
            payload=payload,
            created_at=_now(),
        )
    )


def create_or_rotate_bootstrap_credential(
    db: Session,
    *,
    monitor_id: str,
) -> MonitorBootstrapCredentialResponse:
    now = _now()
    credential = (
        db.query(MonitorBootstrapCredential)
        .filter(MonitorBootstrapCredential.monitor_id == monitor_id)
        .first()
    )
    secret = _random_secret()
    if credential is None:
        credential = MonitorBootstrapCredential(
            monitor_id=monitor_id,
            key_id=settings.bakery_monitor_bootstrap_key_id,
            encrypted_secret=encrypt_secret(secret),
            created_at=now,
            updated_at=now,
        )
        db.add(credential)
    else:
        credential.key_id = settings.bakery_monitor_bootstrap_key_id
        credential.encrypted_secret = encrypt_secret(secret)
        credential.updated_at = now
    db.flush()
    return MonitorBootstrapCredentialResponse(
        monitor_id=monitor_id,
        key_id=credential.key_id,
        secret=secret,
        created_at=credential.created_at,
    )


def register_monitor(
    db: Session,
    *,
    request: MonitorRegistrationRequest,
) -> MonitorRegistrationResponse:
    now = _now()
    monitor = db.query(Monitor).filter(Monitor.monitor_id == request.monitor_id).first()
    secret = _random_secret()
    is_new = monitor is None
    if monitor is None:
        monitor = Monitor(
            monitor_uuid=str(uuid.uuid4()),
            monitor_id=request.monitor_id,
            key_id=settings.bakery_monitor_default_key_id,
            encrypted_secret=encrypt_secret(secret),
            status="healthy",
            route_sync_required=True,
            created_at=now,
            updated_at=now,
        )
        db.add(monitor)
    else:
        monitor.key_id = settings.bakery_monitor_default_key_id
        monitor.encrypted_secret = encrypt_secret(secret)
        monitor.route_sync_required = True
        monitor.updated_at = now

    monitor.last_seen_payload = {
        "installation_id": request.installation_id,
        "app_version": request.app_version,
    }
    db.flush()
    record_monitor_event(
        db,
        monitor_uuid=monitor.monitor_uuid,
        event_type="registered" if is_new else "re_registered",
        payload=monitor.last_seen_payload,
    )
    return MonitorRegistrationResponse(
        monitor_uuid=monitor.monitor_uuid,
        monitor_id=monitor.monitor_id,
        hmac_key_id=monitor.key_id,
        hmac_secret=secret,
        heartbeat_interval_sec=settings.bakery_monitor_heartbeat_interval_sec,
        miss_threshold=settings.bakery_monitor_miss_threshold,
        route_sync_required=bool(monitor.route_sync_required),
        created_at=monitor.created_at,
    )


def sync_monitor_routes(
    db: Session,
    *,
    monitor: Monitor,
    request: MonitorRouteCatalogSyncRequest,
) -> MonitorRouteCatalogSyncResponse:
    now = _now()
    route_rows = [item.model_dump(mode="json") for item in request.routes]
    expected_hash = _routes_digest(route_rows)
    if expected_hash != request.catalog_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="catalog_hash does not match routes payload",
        )

    (
        db.query(MonitorRouteCatalogEntry)
        .filter(MonitorRouteCatalogEntry.monitor_uuid == monitor.monitor_uuid)
        .delete()
    )
    for item in request.routes:
        db.add(
            MonitorRouteCatalogEntry(
                monitor_uuid=monitor.monitor_uuid,
                scope=item.scope,
                owner_key=item.owner_key,
                route_id=item.route_id,
                label=item.label,
                execution_target=item.execution_target,
                destination_target=item.destination_target,
                provider_config=item.provider_config,
                enabled=item.enabled,
                outage_enabled=item.outage_enabled,
                position=item.position,
                created_at=now,
                updated_at=now,
            )
        )

    monitor.route_catalog_hash = request.catalog_hash
    monitor.route_sync_required = False
    monitor.updated_at = now
    db.flush()
    record_monitor_event(
        db,
        monitor_uuid=monitor.monitor_uuid,
        event_type="routes_synced",
        payload={
            "catalog_hash": request.catalog_hash,
            "route_count": len(request.routes),
        },
    )
    return MonitorRouteCatalogSyncResponse(
        monitor_uuid=monitor.monitor_uuid,
        catalog_hash=request.catalog_hash,
        route_count=len(request.routes),
        updated_at=now,
    )


def record_heartbeat(
    db: Session,
    *,
    monitor: Monitor,
    request: MonitorHeartbeatRequest,
) -> MonitorHeartbeatResponse:
    now = _now()
    monitor.last_checkin_at = now
    monitor.last_seen_payload = {
        "installation_id": request.installation_id,
        "app_version": request.app_version,
        "details": request.details,
    }
    route_sync_required = bool(monitor.route_sync_required)
    if request.catalog_hash:
        route_sync_required = route_sync_required or request.catalog_hash != monitor.route_catalog_hash
    monitor.updated_at = now
    db.flush()
    return MonitorHeartbeatResponse(
        monitor_uuid=monitor.monitor_uuid,
        monitor_id=monitor.monitor_id,
        status=monitor.status,
        route_sync_required=route_sync_required,
        heartbeat_interval_sec=settings.bakery_monitor_heartbeat_interval_sec,
        miss_threshold=settings.bakery_monitor_miss_threshold,
        recorded_at=now,
    )


def get_outage_enabled_routes(db: Session, *, monitor_uuid: str) -> list[MonitorRouteCatalogEntry]:
    return (
        db.query(MonitorRouteCatalogEntry)
        .filter(
            MonitorRouteCatalogEntry.monitor_uuid == monitor_uuid,
            MonitorRouteCatalogEntry.outage_enabled.is_(True),
        )
        .order_by(MonitorRouteCatalogEntry.position.asc(), MonitorRouteCatalogEntry.label.asc())
        .all()
    )


def _payload_context(payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context")
    if isinstance(context, dict):
        return dict(context)
    return {}


def monitor_route_validation_required(payload: dict[str, Any]) -> bool:
    context = _payload_context(payload)
    source = str(context.get("source") or payload.get("source") or "poundcake").strip().lower()
    return source not in ROUTE_VALIDATION_BYPASS_SOURCES


def _route_metadata_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    context = _payload_context(payload)
    metadata = context.get(POLICY_METADATA_KEY)
    if isinstance(metadata, dict):
        return dict(metadata)
    direct = {
        "scope": context.get("scope"),
        "owner_key": context.get("owner_key"),
        "route_id": context.get("route_id"),
        "execution_target": context.get("execution_target") or context.get("provider_type"),
        "destination_target": context.get("destination_target"),
        "provider_config": context.get("provider_config"),
    }
    if all(direct.get(key) not in (None, "") for key in ("scope", "owner_key", "route_id")):
        return direct
    return {}


def validate_monitor_route_payload(
    db: Session,
    *,
    monitor_uuid: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], MonitorRouteCatalogEntry]:
    metadata = _route_metadata_from_payload(payload)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registered route metadata is required for PoundCake communication requests",
        )

    scope = str(metadata.get("scope") or "").strip()
    owner_key = str(metadata.get("owner_key") or "").strip()
    route_id = str(metadata.get("route_id") or "").strip()
    route = (
        db.query(MonitorRouteCatalogEntry)
        .filter(
            MonitorRouteCatalogEntry.monitor_uuid == monitor_uuid,
            MonitorRouteCatalogEntry.scope == scope,
            MonitorRouteCatalogEntry.owner_key == owner_key,
            MonitorRouteCatalogEntry.route_id == route_id,
        )
        .first()
    )
    if route is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Route is not registered for this monitor",
        )

    execution_target = str(
        metadata.get("execution_target") or payload.get("provider_type") or ""
    ).strip()
    destination_target = str(metadata.get("destination_target") or "").strip()
    provider_config = metadata.get("provider_config")
    if execution_target and execution_target != route.execution_target:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Route execution_target does not match the registered catalog entry",
        )
    if destination_target and destination_target != (route.destination_target or ""):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Route destination_target does not match the registered catalog entry",
        )
    if isinstance(provider_config, dict) and provider_config != (route.provider_config or {}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Route provider_config does not match the registered catalog entry",
        )

    context = _payload_context(payload)
    canonical_metadata = {
        "scope": route.scope,
        "owner_key": route.owner_key,
        "route_id": route.route_id,
        "label": route.label,
        "execution_target": route.execution_target,
        "destination_target": route.destination_target,
        "provider_config": route.provider_config or {},
        "enabled": route.enabled,
        "position": route.position,
    }
    context.update(
        {
            "scope": route.scope,
            "owner_key": route.owner_key,
            "route_id": route.route_id,
            "provider_type": route.execution_target,
            "execution_target": route.execution_target,
            "destination_target": route.destination_target,
            "provider_config": route.provider_config or {},
            POLICY_METADATA_KEY: canonical_metadata,
        }
    )
    normalized = dict(payload)
    normalized["context"] = context
    normalized.setdefault("source", "poundcake")
    return normalized, route


def route_entry_contract(row: MonitorRouteCatalogEntry) -> MonitorRouteCatalogEntryContract:
    return MonitorRouteCatalogEntryContract(
        scope=row.scope,
        owner_key=row.owner_key,
        route_id=row.route_id,
        label=row.label,
        execution_target=row.execution_target,
        destination_target=row.destination_target or "",
        provider_config=row.provider_config or {},
        enabled=row.enabled,
        outage_enabled=row.outage_enabled,
        position=row.position,
    )
