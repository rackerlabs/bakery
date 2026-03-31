#!/usr/bin/env python3
"""Monitor registration, route sync, and heartbeat APIs for PoundCake."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from bakery.auth import (
    BootstrapAuthContext,
    MonitorAuthContext,
    require_bootstrap_hmac_auth,
    require_monitor_hmac_auth,
)
from bakery.database import get_db
from bakery.models import Monitor
from bakery.monitoring import record_heartbeat, register_monitor, sync_monitor_routes
from shared.bakery_contract import (
    MonitorHeartbeatRequest,
    MonitorHeartbeatResponse,
    MonitorRegistrationRequest,
    MonitorRegistrationResponse,
    MonitorRouteCatalogSyncRequest,
    MonitorRouteCatalogSyncResponse,
)

router = APIRouter()


@router.post("/monitors/register", response_model=MonitorRegistrationResponse)
async def register_monitor_identity(
    payload: MonitorRegistrationRequest,
    bootstrap: BootstrapAuthContext = Depends(require_bootstrap_hmac_auth),
    db: Session = Depends(get_db),
) -> MonitorRegistrationResponse:
    if payload.monitor_id != bootstrap.monitor_id:
        raise HTTPException(status_code=401, detail="monitor_id does not match bootstrap credential")
    response = register_monitor(db, request=payload)
    db.commit()
    return response


@router.put("/monitors/self/routes", response_model=MonitorRouteCatalogSyncResponse)
async def put_monitor_routes(
    payload: MonitorRouteCatalogSyncRequest,
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> MonitorRouteCatalogSyncResponse:
    monitor = db.query(Monitor).filter(Monitor.monitor_uuid == auth.monitor_uuid).first()
    if monitor is None:
        raise HTTPException(status_code=401, detail="Unknown monitor")
    response = sync_monitor_routes(db, monitor=monitor, request=payload)
    db.commit()
    return response


@router.post("/monitors/heartbeat", response_model=MonitorHeartbeatResponse)
async def post_monitor_heartbeat(
    payload: MonitorHeartbeatRequest,
    auth: MonitorAuthContext = Depends(require_monitor_hmac_auth),
    db: Session = Depends(get_db),
) -> MonitorHeartbeatResponse:
    monitor = db.query(Monitor).filter(Monitor.monitor_uuid == auth.monitor_uuid).first()
    if monitor is None:
        raise HTTPException(status_code=401, detail="Unknown monitor")
    response = record_heartbeat(db, monitor=monitor, request=payload)
    db.commit()
    return response
