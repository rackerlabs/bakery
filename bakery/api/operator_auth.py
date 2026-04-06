#!/usr/bin/env python3
"""Operator authentication and RBAC APIs for Bakery."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from bakery.config import normalize_external_url, settings
from bakery.database import get_db
from bakery.operator_auth import (
    AccessDeniedError,
    AuthContext,
    DeviceAuthorizationExpired,
    DeviceAuthorizationPending,
    InvalidCredentialsError,
    ProviderConfigurationError,
    authenticate_device_code,
    authenticate_oidc_authorization_code,
    authenticate_password_provider,
    build_auth_callback_url,
    build_login_context,
    create_role_binding,
    create_session,
    delete_role_binding,
    delete_session,
    get_enabled_provider_metadata,
    get_oidc_authorize_url,
    get_principal_by_id,
    get_role_binding,
    list_principals,
    list_role_bindings,
    pop_state,
    provider_label,
    put_state,
    require_admin,
    require_reader,
    start_device_authorization,
    update_role_binding,
    upsert_principal,
)
from bakery.schemas import (
    AuthLoginRequest,
    AuthLogoutResponse,
    AuthMeResponse,
    AuthPrincipalResponse,
    AuthProviderResponse,
    AuthRoleBindingCreate,
    AuthRoleBindingResponse,
    AuthRoleBindingUpdate,
    DeleteResponse,
    DeviceAuthorizationPollRequest,
    DeviceAuthorizationPollResponse,
    DeviceAuthorizationStartRequest,
    DeviceAuthorizationStartResponse,
    SessionResponse,
)

router = APIRouter()


def _request_is_secure(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        first = forwarded_proto.split(",", 1)[0].strip().lower()
        if first:
            return first == "https"
    return request.url.scheme.lower() == "https"


def _allowed_ui_public_url() -> str:
    return normalize_external_url(settings.ui_public_url)


def _set_session_cookie(request: Request, response: Response, session_id: str) -> None:
    split_ui_enabled = bool(_allowed_ui_public_url())
    response.set_cookie(
        key="session_token",
        value=session_id,
        httponly=True,
        samesite="none" if split_ui_enabled else "lax",
        secure=True if split_ui_enabled else _request_is_secure(request),
        path="/",
        max_age=settings.operator_auth_session_timeout,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key="session_token", path="/")


def _normalize_next_target(target: str | None) -> str:
    default_target = _allowed_ui_public_url() or "/"
    if not target:
        return default_target
    if target.startswith("/"):
        if target == "/login" or target.startswith("/login?"):
            return default_target
        return target
    normalized_target = normalize_external_url(target)
    allowed_target = _allowed_ui_public_url()
    if (
        normalized_target
        and allowed_target
        and secrets.compare_digest(
            normalized_target,
            allowed_target,
        )
    ):
        return normalized_target
    return default_target


def _provider_response(item: dict[str, object]) -> AuthProviderResponse:
    return AuthProviderResponse.model_validate(item)


def _principal_response(principal: object) -> AuthPrincipalResponse:
    groups = list(getattr(principal, "groups_json", []) or [])
    return AuthPrincipalResponse(
        id=int(getattr(principal, "id")),
        provider=str(getattr(principal, "provider")),
        subject_id=str(getattr(principal, "subject_id")),
        username=str(getattr(principal, "username")),
        display_name=getattr(principal, "display_name"),
        principal_type=str(getattr(principal, "principal_type")),
        groups=[str(item) for item in groups],
        last_seen_at=getattr(principal, "last_seen_at"),
        created_at=getattr(principal, "created_at"),
        updated_at=getattr(principal, "updated_at"),
    )


def _binding_response(binding: object, db: Session) -> AuthRoleBindingResponse:
    principal = None
    principal_id = getattr(binding, "principal_id", None)
    if principal_id is not None:
        record = get_principal_by_id(db, int(principal_id))
        if record is not None:
            principal = _principal_response(record)
    return AuthRoleBindingResponse(
        id=int(getattr(binding, "id")),
        provider=str(getattr(binding, "provider")),
        binding_type=str(getattr(binding, "binding_type")),
        role=str(getattr(binding, "role")),
        principal_id=principal_id,
        external_group=getattr(binding, "external_group"),
        created_by=getattr(binding, "created_by"),
        created_at=getattr(binding, "created_at"),
        updated_at=getattr(binding, "updated_at"),
        principal=principal,
    )


def _session_response(context: AuthContext) -> SessionResponse:
    return SessionResponse(
        session_id=str(context.session_id or ""),
        username=context.username,
        expires_at=str(context.expires_at or ""),
        provider=context.provider,
        role=context.role,
        display_name=context.display_name,
        is_superuser=context.is_superuser,
        permissions=list(context.permissions),
        token_type="Bearer",
    )


def _resolve_sso_provider(requested_provider: str | None, *, mode: str) -> str:
    capability = "browser login" if mode == "browser" else "CLI device login"
    providers = get_enabled_provider_metadata()
    enabled = [
        str(item["name"])
        for item in providers
        if (item.get("browser_login") if mode == "browser" else item.get("device_login"))
    ]
    provider = str(requested_provider or "").strip().lower()
    if provider:
        if provider not in {"auth0", "azure_ad"}:
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{provider}' does not support {capability}",
            )
        if provider not in enabled:
            raise HTTPException(
                status_code=404,
                detail=f"{provider_label(provider)} {capability} is not enabled",
            )
        return provider
    if len(enabled) == 1:
        return enabled[0]
    if len(enabled) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"provider is required when multiple {capability} providers are enabled",
        )
    raise HTTPException(status_code=404, detail=f"No {capability} providers are enabled")


def _persist_session(
    request: Request, response: Response, db: Session, context: AuthContext
) -> SessionResponse:
    stored = create_session(db, context, ttl_seconds=settings.operator_auth_session_timeout)
    if not stored.session_id:
        raise HTTPException(status_code=500, detail="Could not create session")
    _set_session_cookie(request, response, stored.session_id)
    return _session_response(stored)


def _remember_observed_principal(db: Session, identity: object | None) -> None:
    if identity is None:
        return
    provider = str(getattr(identity, "provider", "") or "").strip().lower()
    if provider in {"", "local", "service"}:
        return
    upsert_principal(db, identity)  # type: ignore[arg-type]


@router.get("/auth/providers", response_model=list[AuthProviderResponse])
async def get_auth_providers() -> list[AuthProviderResponse]:
    return [_provider_response(item) for item in get_enabled_provider_metadata()]


@router.post("/auth/login", response_model=SessionResponse)
async def login(
    request: Request,
    payload: AuthLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionResponse:
    providers = get_enabled_provider_metadata()
    password_providers = [str(item["name"]) for item in providers if item.get("password_login")]
    provider = str(payload.provider or "").strip().lower()
    if not provider:
        if len(password_providers) == 1:
            provider = password_providers[0]
        else:
            raise HTTPException(status_code=400, detail="provider is required")
    try:
        identity = await authenticate_password_provider(
            provider, payload.username, payload.password
        )
        context = build_login_context(db, identity)
        session = _persist_session(request, response, db, context)
        db.commit()
        return session
    except InvalidCredentialsError as exc:
        db.rollback()
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AccessDeniedError as exc:
        db.rollback()
        _remember_observed_principal(db, locals().get("identity"))
        db.commit()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/auth/me", response_model=AuthMeResponse)
async def auth_me(context: AuthContext = Depends(require_reader)) -> AuthMeResponse:
    if not context.is_human():
        raise HTTPException(status_code=403, detail="Service tokens cannot use this endpoint")
    return AuthMeResponse(
        username=context.username,
        display_name=context.display_name,
        provider=context.provider,
        role=context.role,
        principal_type=context.principal_type,
        principal_id=context.principal_id,
        is_superuser=context.is_superuser,
        permissions=context.permissions,
        groups=context.groups,
        expires_at=context.expires_at,
    )


@router.post("/auth/logout", response_model=AuthLogoutResponse)
async def logout(
    request: Request,
    response: Response,
    _context: AuthContext = Depends(require_reader),
    db: Session = Depends(get_db),
) -> AuthLogoutResponse:
    session_token = request.cookies.get("session_token")
    delete_session(db, session_token)
    db.commit()
    _clear_session_cookie(response)
    return AuthLogoutResponse(message="Logged out successfully")


@router.get("/auth/oidc/login")
async def oidc_login(
    request: Request,
    next: str = Query(default="/"),
    provider: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    resolved_provider = _resolve_sso_provider(provider, mode="browser")
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24) if resolved_provider == "azure_ad" else ""
    callback_url = build_auth_callback_url(str(request.base_url).rstrip("/"), resolved_provider)
    target = _normalize_next_target(next)
    try:
        authorize_url = await get_oidc_authorize_url(
            resolved_provider,
            state=state,
            redirect_uri=callback_url,
            nonce=(nonce or None),
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    put_state(
        db,
        kind="oidc_state",
        state_key=state,
        payload={"next": target, "provider": resolved_provider, "nonce": nonce},
        ttl_seconds=settings.operator_auth_oidc_state_ttl,
    )
    db.commit()
    return RedirectResponse(url=authorize_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/auth/oidc/callback")
async def oidc_callback(
    request: Request,
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    state_payload = pop_state(db, kind="oidc_state", state_key=state)
    db.commit()
    if not state_payload:
        raise HTTPException(status_code=400, detail="Invalid or expired login state")
    provider = str(state_payload.get("provider") or "auth0").strip().lower()
    nonce = str(state_payload.get("nonce") or "").strip() or None
    callback_url = build_auth_callback_url(str(request.base_url).rstrip("/"), provider)
    try:
        identity = await authenticate_oidc_authorization_code(
            provider,
            code=code,
            redirect_uri=callback_url,
            nonce=nonce,
        )
        context = build_login_context(db, identity)
        redirect = RedirectResponse(
            url=_normalize_next_target(str(state_payload.get("next") or "/")),
            status_code=status.HTTP_303_SEE_OTHER,
        )
        _persist_session(request, redirect, db, context)
        db.commit()
        return redirect
    except InvalidCredentialsError as exc:
        db.rollback()
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AccessDeniedError as exc:
        db.rollback()
        _remember_observed_principal(db, locals().get("identity"))
        db.commit()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/device/start", response_model=DeviceAuthorizationStartResponse)
async def device_start(
    payload: DeviceAuthorizationStartRequest | None = None,
) -> DeviceAuthorizationStartResponse:
    resolved_provider = _resolve_sso_provider(
        None if payload is None else payload.provider,
        mode="device",
    )
    try:
        result = await start_device_authorization(resolved_provider)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DeviceAuthorizationStartResponse(
        provider=result.provider,
        device_code=result.device_code,
        user_code=result.user_code,
        verification_uri=result.verification_uri,
        verification_uri_complete=result.verification_uri_complete,
        expires_in=result.expires_in,
        interval=result.interval,
    )


@router.post("/auth/device/poll", response_model=DeviceAuthorizationPollResponse)
async def device_poll(
    request: Request,
    payload: DeviceAuthorizationPollRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> DeviceAuthorizationPollResponse:
    resolved_provider = _resolve_sso_provider(payload.provider, mode="device")
    try:
        identity = await authenticate_device_code(resolved_provider, payload.device_code)
        context = build_login_context(db, identity)
        session = _persist_session(request, response, db, context)
        db.commit()
        return DeviceAuthorizationPollResponse(status="authorized", session=session)
    except DeviceAuthorizationPending:
        db.rollback()
        return DeviceAuthorizationPollResponse(status="pending", interval=5)
    except DeviceAuthorizationExpired as exc:
        db.rollback()
        return DeviceAuthorizationPollResponse(status="expired", detail=str(exc))
    except InvalidCredentialsError as exc:
        db.rollback()
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AccessDeniedError as exc:
        db.rollback()
        _remember_observed_principal(db, locals().get("identity"))
        db.commit()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/auth/principals", response_model=list[AuthPrincipalResponse])
async def auth_principals(
    provider: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AuthPrincipalResponse]:
    return [
        _principal_response(item)
        for item in list_principals(
            db, provider=provider, search=search, limit=limit, offset=offset
        )
    ]


@router.get("/auth/bindings", response_model=list[AuthRoleBindingResponse])
async def auth_bindings(
    provider: str | None = Query(default=None),
    _context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AuthRoleBindingResponse]:
    return [_binding_response(item, db) for item in list_role_bindings(db, provider=provider)]


@router.post("/auth/bindings", response_model=AuthRoleBindingResponse, status_code=201)
async def create_auth_binding(
    payload: AuthRoleBindingCreate,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuthRoleBindingResponse:
    if payload.binding_type == "user" and payload.principal_id is None:
        raise HTTPException(status_code=400, detail="principal_id is required for user bindings")
    if payload.binding_type == "group" and not str(payload.external_group or "").strip():
        raise HTTPException(status_code=400, detail="external_group is required for group bindings")
    binding = create_role_binding(
        db,
        provider=payload.provider,
        binding_type=payload.binding_type,
        role=payload.role,
        principal_id=payload.principal_id,
        external_group=payload.external_group,
        created_by=payload.created_by or context.username,
    )
    db.commit()
    db.refresh(binding)
    return _binding_response(binding, db)


@router.patch("/auth/bindings/{binding_id}", response_model=AuthRoleBindingResponse)
async def patch_auth_binding(
    binding_id: int,
    payload: AuthRoleBindingUpdate,
    _context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuthRoleBindingResponse:
    binding = get_role_binding(db, binding_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="Binding not found")
    update_role_binding(db, binding, role=payload.role, external_group=payload.external_group)
    db.commit()
    db.refresh(binding)
    return _binding_response(binding, db)


@router.delete("/auth/bindings/{binding_id}", response_model=DeleteResponse)
async def delete_auth_binding(
    binding_id: int,
    _context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DeleteResponse:
    binding = get_role_binding(db, binding_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="Binding not found")
    delete_role_binding(db, binding)
    db.commit()
    return DeleteResponse(message="Binding deleted")
