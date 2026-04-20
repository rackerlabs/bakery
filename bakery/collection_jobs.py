#!/usr/bin/env python3
"""Collection job queue helpers for Bakery operators and PoundCake monitors."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Query, Session

from bakery.config import settings
from bakery.models import CollectionJob, Monitor
from shared.bakery_contract import (
    CollectionJobClaimResponse,
    CollectionJobCompleteRequest,
    CollectionJobCreateRequest,
    CollectionJobResponse,
)

COLLECTOR_CATALOG: dict[str, dict[str, object]] = {
    "monitor_diagnostics": {
        "collector_type": "monitor_diagnostics",
        "label": "Monitor diagnostics",
        "description": "Collect health, runtime, and monitor-registration state from one PoundCake monitor.",
        "default_parameters": {},
        "example_parameters": {},
        "parameters": [],
    },
    "cluster_inventory": {
        "collector_type": "cluster_inventory",
        "label": "Cluster inventory",
        "description": (
            "Collect a full environment inventory: all cluster nodes plus storage topology, "
            "then pair it with a namespace-scoped workload snapshot and report."
        ),
        "default_parameters": {"limit": 50},
        "example_parameters": {"namespace": "example-namespace", "limit": 25},
        "parameters": [
            {
                "name": "namespace",
                "label": "Namespace",
                "field_type": "text",
                "description": (
                    "Namespace to inspect for workload and PVC data. Node, PV, and storage class "
                    "inventory is always cluster-wide."
                ),
                "required": False,
                "default_value": "",
                "placeholder": "example-namespace",
            },
            {
                "name": "limit",
                "label": "Row limit",
                "field_type": "number",
                "description": (
                    "Maximum workload and PVC rows to include from the selected namespace. "
                    "Cluster-wide node and storage inventory is not truncated by this value."
                ),
                "required": False,
                "default_value": 50,
                "placeholder": "50",
            },
        ],
    },
    "ticket_context": {
        "collector_type": "ticket_context",
        "label": "Ticket context",
        "description": "Pull related PoundCake orders, communications, and dishes for one Bakery ticket or request.",
        "default_parameters": {"limit": 20},
        "example_parameters": {"bakery_ticket_id": "bakery-ticket-123", "limit": 20},
        "parameters": [
            {
                "name": "order_id",
                "label": "Order ID",
                "field_type": "number",
                "description": "Specific PoundCake order ID to inspect.",
                "required": False,
                "default_value": None,
                "placeholder": "204",
            },
            {
                "name": "req_id",
                "label": "Request ID",
                "field_type": "text",
                "description": "PoundCake request ID associated with the workflow.",
                "required": False,
                "default_value": "",
                "placeholder": "req-12345",
            },
            {
                "name": "bakery_ticket_id",
                "label": "Bakery ticket ID",
                "field_type": "text",
                "description": "Bakery communication or ticket identifier used by PoundCake.",
                "required": False,
                "default_value": "",
                "placeholder": "bakery-ticket-123",
            },
            {
                "name": "limit",
                "label": "Row limit",
                "field_type": "number",
                "description": "Maximum related records to include in the result set.",
                "required": False,
                "default_value": 20,
                "placeholder": "20",
            },
        ],
    },
}

ALLOWED_COLLECTOR_TYPES = set(COLLECTOR_CATALOG)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def collection_job_response(job: CollectionJob) -> CollectionJobResponse:
    return CollectionJobResponse(
        job_id=job.job_id,
        monitor_uuid=job.monitor_uuid,
        monitor_id=job.monitor_id,
        collector_type=job.collector_type,
        status=job.status,
        parameters=dict(job.parameters or {}),
        reason=job.reason,
        requested_by=job.requested_by,
        lease_expires_at=job.lease_expires_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        result=dict(job.result or {}) if isinstance(job.result, dict) else None,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def list_collection_collectors_metadata() -> list[dict[str, object]]:
    return [dict(COLLECTOR_CATALOG[key]) for key in sorted(COLLECTOR_CATALOG)]


def expire_collection_job_leases(db: Session) -> int:
    now = _now()
    expired = (
        db.query(CollectionJob)
        .filter(
            CollectionJob.status == "leased",
            CollectionJob.lease_expires_at.is_not(None),
            CollectionJob.lease_expires_at < now,
        )
        .all()
    )
    for job in expired:
        job.status = "timed_out"
        job.error = "Collection job lease expired before completion"
        job.completed_at = now
        job.updated_at = now
    return len(expired)


def create_collection_job(
    db: Session,
    *,
    request: CollectionJobCreateRequest,
    requested_by: str | None,
) -> CollectionJobResponse:
    if request.collector_type not in ALLOWED_COLLECTOR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported collector_type",
        )
    monitor = db.query(Monitor).filter(Monitor.monitor_uuid == request.monitor_uuid).first()
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    now = _now()
    job = CollectionJob(
        job_id=str(uuid.uuid4()),
        monitor_uuid=monitor.monitor_uuid,
        monitor_id=monitor.monitor_id,
        collector_type=request.collector_type,
        status="queued",
        parameters=request.parameters,
        reason=request.reason,
        requested_by=requested_by,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()
    return collection_job_response(job)


def list_collection_jobs_query(
    db: Session,
    *,
    monitor_uuid: str | None = None,
    status_value: str | None = None,
    collector_type: str | None = None,
) -> Query[CollectionJob]:
    expire_collection_job_leases(db)
    query = db.query(CollectionJob)
    if monitor_uuid:
        query = query.filter(CollectionJob.monitor_uuid == monitor_uuid)
    if status_value:
        query = query.filter(CollectionJob.status == status_value)
    if collector_type:
        query = query.filter(CollectionJob.collector_type == collector_type)
    return query.order_by(CollectionJob.created_at.desc(), CollectionJob.id.desc())


def get_collection_job(db: Session, *, job_id: str) -> CollectionJob:
    expire_collection_job_leases(db)
    job = db.query(CollectionJob).filter(CollectionJob.job_id == job_id).first()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection job not found"
        )
    return job


def claim_next_collection_job(
    db: Session,
    *,
    monitor: Monitor,
) -> CollectionJobClaimResponse:
    expire_collection_job_leases(db)
    now = _now()
    job = (
        db.query(CollectionJob)
        .filter(
            CollectionJob.monitor_uuid == monitor.monitor_uuid,
            CollectionJob.status == "queued",
        )
        .order_by(CollectionJob.created_at.asc(), CollectionJob.id.asc())
        .first()
    )
    if job is None:
        return CollectionJobClaimResponse(available=False, job=None)

    job.status = "leased"
    job.lease_expires_at = now + timedelta(
        seconds=max(settings.bakery_collection_job_lease_sec, 30)
    )
    job.started_at = now
    job.updated_at = now
    db.flush()
    return CollectionJobClaimResponse(available=True, job=collection_job_response(job))


def complete_collection_job(
    db: Session,
    *,
    monitor: Monitor,
    job_id: str,
    request: CollectionJobCompleteRequest,
) -> CollectionJobResponse:
    expire_collection_job_leases(db)
    job = (
        db.query(CollectionJob)
        .filter(
            CollectionJob.job_id == job_id,
            CollectionJob.monitor_uuid == monitor.monitor_uuid,
        )
        .first()
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection job not found"
        )
    if job.status != "leased":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Collection job is not currently leased",
        )
    if request.status not in {"succeeded", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collection job completion status must be succeeded or failed",
        )
    now = _now()
    job.status = request.status
    job.result = request.result if isinstance(request.result, dict) else None
    job.error = request.error
    job.completed_at = now
    job.lease_expires_at = None
    job.updated_at = now
    db.flush()
    return collection_job_response(job)


def requeue_collection_job(db: Session, *, job_id: str) -> CollectionJobResponse:
    job = get_collection_job(db, job_id=job_id)
    now = _now()
    job.status = "queued"
    job.lease_expires_at = None
    job.started_at = None
    job.completed_at = None
    job.result = None
    job.error = None
    job.updated_at = now
    db.flush()
    return collection_job_response(job)
