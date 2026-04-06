#!/usr/bin/env python3
"""Operator collection job APIs for Bakery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from bakery.collection_jobs import (
    create_collection_job,
    get_collection_job,
    list_collection_collectors_metadata,
    list_collection_jobs_query,
    requeue_collection_job,
)
from bakery.database import get_db
from bakery.operator_auth import AuthContext, require_operator, require_reader
from bakery.schemas import CollectionCollectorResponse
from shared.bakery_contract import CollectionJobCreateRequest, CollectionJobResponse

router = APIRouter()


@router.post("/collection-jobs", response_model=CollectionJobResponse, status_code=201)
async def post_collection_job(
    payload: CollectionJobCreateRequest,
    context: AuthContext = Depends(require_operator),
    db: Session = Depends(get_db),
) -> CollectionJobResponse:
    response = create_collection_job(
        db,
        request=payload,
        requested_by=context.username,
    )
    db.commit()
    return response


@router.get("/collection-jobs", response_model=list[CollectionJobResponse])
async def get_collection_jobs(
    monitor_uuid: str | None = Query(default=None),
    status: str | None = Query(default=None),
    collector_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> list[CollectionJobResponse]:
    rows = (
        list_collection_jobs_query(
            db,
            monitor_uuid=monitor_uuid,
            status_value=status,
            collector_type=collector_type,
        )
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        CollectionJobResponse.model_validate(
            {
                "job_id": row.job_id,
                "monitor_uuid": row.monitor_uuid,
                "monitor_id": row.monitor_id,
                "collector_type": row.collector_type,
                "status": row.status,
                "parameters": row.parameters or {},
                "reason": row.reason,
                "requested_by": row.requested_by,
                "lease_expires_at": row.lease_expires_at,
                "started_at": row.started_at,
                "completed_at": row.completed_at,
                "result": row.result,
                "error": row.error,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )
        for row in rows
    ]


@router.get("/collection-jobs/collectors", response_model=list[CollectionCollectorResponse])
async def get_collection_collectors(
    _context: AuthContext = Depends(require_reader),
) -> list[CollectionCollectorResponse]:
    return [
        CollectionCollectorResponse.model_validate(item)
        for item in list_collection_collectors_metadata()
    ]


@router.get("/collection-jobs/{job_id}", response_model=CollectionJobResponse)
async def get_collection_job_detail(
    job_id: str,
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> CollectionJobResponse:
    row = get_collection_job(db, job_id=job_id)
    return CollectionJobResponse.model_validate(
        {
            "job_id": row.job_id,
            "monitor_uuid": row.monitor_uuid,
            "monitor_id": row.monitor_id,
            "collector_type": row.collector_type,
            "status": row.status,
            "parameters": row.parameters or {},
            "reason": row.reason,
            "requested_by": row.requested_by,
            "lease_expires_at": row.lease_expires_at,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "result": row.result,
            "error": row.error,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


@router.post("/collection-jobs/{job_id}/requeue", response_model=CollectionJobResponse)
async def post_collection_job_requeue(
    job_id: str,
    _context: AuthContext = Depends(require_operator),
    db: Session = Depends(get_db),
) -> CollectionJobResponse:
    response = requeue_collection_job(db, job_id=job_id)
    db.commit()
    return response
