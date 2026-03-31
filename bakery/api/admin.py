#!/usr/bin/env python3
"""Admin APIs for Bakery monitor bootstrap management."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from bakery.auth import require_bootstrap_admin_access
from bakery.database import get_db
from bakery.monitoring import create_or_rotate_bootstrap_credential
from shared.bakery_contract import MonitorBootstrapCredentialResponse

router = APIRouter()


@router.put(
    "/admin/monitors/{monitor_id}/bootstrap-credential",
    response_model=MonitorBootstrapCredentialResponse,
)
async def put_monitor_bootstrap_credential(
    monitor_id: str,
    _access: str = Depends(require_bootstrap_admin_access),
    db: Session = Depends(get_db),
) -> MonitorBootstrapCredentialResponse:
    response = create_or_rotate_bootstrap_credential(db, monitor_id=monitor_id)
    db.commit()
    return response
