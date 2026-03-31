#!/usr/bin/env python3
"""Human operator authentication, session, and RBAC helpers for Bakery."""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import re
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from bakery.config import settings
from bakery.database import get_db
from bakery.models import AuthPrincipal, AuthRoleBinding, AuthSession, AuthState

ROLE_PRECEDENCE: dict[str, int] = {
    "reader": 0,
    "operator": 1,
    "admin": 2,
    "service": 3,
}

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "reader": ["read"],
    "operator": ["read", "queue_jobs"],
    "admin": ["read", "queue_jobs", "manage_auth", "manage_bootstrap"],
    "service": ["read", "queue_jobs", "manage_auth", "manage_bootstrap", "service"],
}

AUTH_PROVIDER_LABELS: dict[str, str] = {
    "local": "Local Superuser",
    "auth0": "Auth0",
    "azure_ad": "Azure AD",
    "service": "Internal Service",
}

_OIDC_DISCOVERY_CACHE: dict[str, dict[str, Any]] = {}
_OIDC_JWKS_CACHE: dict[str, dict[str, Any]] = {}


@dataclass
class AuthIdentity:
    provider: str
    subject_id: str
    username: str
    display_name: str | None = None
    groups: list[str] = field(default_factory=list)
    principal_type: str = "user"
    is_superuser: bool = False

    def normalized_groups(self) -> list[str]:
        return normalize_groups(self.groups)


@dataclass
class AuthContext:
    provider: str
    subject_id: str
    username: str
    display_name: str | None
    groups: list[str]
    role: str
    principal_type: str
    is_superuser: bool = False
    permissions: list[str] = field(default_factory=list)
    principal_id: int | None = None
    session_id: str | None = None
    expires_at: str | None = None

    def is_human(self) -> bool:
        return self.principal_type == "user"

    def to_session_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceAuthorizationStart:
    provider: str
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None
    expires_in: int
    interval: int


class AuthError(RuntimeError):
    """Base operator auth error."""


class InvalidCredentialsError(AuthError):
    """Raised when supplied auth credentials are rejected."""


class ProviderConfigurationError(AuthError):
    """Raised when an auth provider is not configured completely."""


class AccessDeniedError(AuthError):
    """Raised when a login succeeded but no RBAC binding matched."""


class DeviceAuthorizationPending(AuthError):
    """Raised when a device flow has not been approved yet."""


class DeviceAuthorizationExpired(AuthError):
    """Raised when a device flow expired or was denied."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_groups(groups: list[str] | None) -> list[str]:
    seen: dict[str, str] = {}
    for group in groups or []:
        value = str(group or "").strip()
        if not value:
            continue
        seen[value.casefold()] = value
    return sorted(seen.values(), key=str.casefold)


def highest_role(roles: list[str]) -> str | None:
    best: str | None = None
    for role in roles:
        normalized = str(role or "").strip().lower()
        if normalized not in ROLE_PRECEDENCE:
            continue
        if best is None or ROLE_PRECEDENCE[normalized] > ROLE_PRECEDENCE[best]:
            best = normalized
    return best


def permissions_for_role(role: str, *, is_superuser: bool = False) -> list[str]:
    permissions = list(ROLE_PERMISSIONS.get(role, []))
    if is_superuser and "superuser" not in permissions:
        permissions.append("superuser")
    return permissions


def is_authorized_for_role(context: AuthContext, required_role: str) -> bool:
    return ROLE_PRECEDENCE.get(context.role, -1) >= ROLE_PRECEDENCE.get(required_role, 99)


def provider_label(provider: str) -> str:
    return AUTH_PROVIDER_LABELS.get(provider, provider)


def auth0_browser_login_enabled() -> bool:
    return bool(
        settings.operator_auth_auth0_enabled
        and settings.operator_auth_auth0_domain
        and settings.operator_auth_auth0_ui_enabled
        and settings.operator_auth_auth0_ui_client_id
    )


def auth0_device_login_enabled() -> bool:
    return bool(
        settings.operator_auth_auth0_enabled
        and settings.operator_auth_auth0_domain
        and settings.operator_auth_auth0_cli_enabled
        and settings.operator_auth_auth0_cli_client_id
    )


def azure_ad_browser_login_enabled() -> bool:
    return bool(
        settings.operator_auth_azure_ad_enabled
        and settings.operator_auth_azure_ad_tenant
        and settings.operator_auth_azure_ad_ui_enabled
        and settings.operator_auth_azure_ad_ui_client_id
    )


def azure_ad_device_login_enabled() -> bool:
    return bool(
        settings.operator_auth_azure_ad_enabled
        and settings.operator_auth_azure_ad_tenant
        and settings.operator_auth_azure_ad_cli_enabled
        and settings.operator_auth_azure_ad_cli_client_id
    )


def get_enabled_provider_metadata() -> list[dict[str, Any]]:
    providers: list[dict[str, Any]] = []
    if settings.operator_auth_local_enabled and (
        (settings.operator_auth_username and settings.operator_auth_password)
        or (settings.operator_auth_dev_username and settings.operator_auth_dev_password)
    ):
        providers.append(
            {
                "name": "local",
                "label": AUTH_PROVIDER_LABELS["local"],
                "login_mode": "password",
                "cli_login_mode": "password",
                "browser_login": False,
                "device_login": False,
                "password_login": True,
            }
        )

    auth0_browser = auth0_browser_login_enabled()
    auth0_device = auth0_device_login_enabled()
    if auth0_browser or auth0_device:
        providers.append(
            {
                "name": "auth0",
                "label": AUTH_PROVIDER_LABELS["auth0"],
                "login_mode": "oidc" if auth0_browser else "device",
                "cli_login_mode": "device" if auth0_device else "unavailable",
                "browser_login": auth0_browser,
                "device_login": auth0_device,
                "password_login": False,
            }
        )

    azure_browser = azure_ad_browser_login_enabled()
    azure_device = azure_ad_device_login_enabled()
    if azure_browser or azure_device:
        providers.append(
            {
                "name": "azure_ad",
                "label": AUTH_PROVIDER_LABELS["azure_ad"],
                "login_mode": "oidc" if azure_browser else "device",
                "cli_login_mode": "device" if azure_device else "unavailable",
                "browser_login": azure_browser,
                "device_login": azure_device,
                "password_login": False,
            }
        )
    return providers


def build_auth_callback_url(base_url: str, provider: str) -> str:
    if provider == "auth0" and settings.operator_auth_auth0_ui_callback_url:
        return settings.operator_auth_auth0_ui_callback_url
    if provider == "azure_ad" and settings.operator_auth_azure_ad_ui_callback_url:
        return settings.operator_auth_azure_ad_ui_callback_url
    return f"{base_url.rstrip('/')}{settings.api_prefix}/auth/oidc/callback"


def _local_superuser_credentials() -> tuple[str, str] | None:
    candidates = [
        (settings.operator_auth_username, settings.operator_auth_password),
        (settings.operator_auth_dev_username, settings.operator_auth_dev_password),
    ]
    for username, password in candidates:
        if username and password:
            return (username, password)
    return None


async def authenticate_password_provider(provider: str, username: str, password: str) -> AuthIdentity:
    normalized = str(provider or "").strip().lower()
    if normalized != "local":
        raise ProviderConfigurationError(f"Provider '{provider}' does not support password login")
    credentials = _local_superuser_credentials()
    if credentials is None:
        raise ProviderConfigurationError("Local superuser credentials are not configured")
    configured_username, configured_password = credentials
    if not (
        secrets.compare_digest(username, configured_username)
        and secrets.compare_digest(password, configured_password)
    ):
        raise InvalidCredentialsError("Invalid username or password")
    return AuthIdentity(
        provider="local",
        subject_id=configured_username,
        username=configured_username,
        display_name=configured_username,
        groups=[],
        principal_type="user",
        is_superuser=True,
    )


def _auth0_base_url() -> str:
    if not (settings.operator_auth_auth0_enabled and settings.operator_auth_auth0_domain):
        raise ProviderConfigurationError("Auth0 is not enabled")
    domain = settings.operator_auth_auth0_domain.strip().rstrip("/")
    if domain.startswith("https://"):
        return domain
    return f"https://{domain}"


def _azure_ad_tenant() -> str:
    if not (settings.operator_auth_azure_ad_enabled and settings.operator_auth_azure_ad_tenant):
        raise ProviderConfigurationError("Azure AD is not enabled")
    tenant = settings.operator_auth_azure_ad_tenant.strip().strip("/")
    if tenant.lower() in {"common", "organizations", "consumers"}:
        raise ProviderConfigurationError("Azure AD tenant must be a single-tenant identifier")
    return tenant


def _azure_ad_authority_base() -> str:
    return f"https://login.microsoftonline.com/{_azure_ad_tenant()}"


def _azure_ad_scope() -> str:
    configured_items = [
        item for item in str(settings.operator_auth_azure_ad_scope or "").split() if item
    ]
    existing = {item.casefold() for item in configured_items}
    for required in ("openid", "profile", "email"):
        if required.casefold() not in existing:
            configured_items.append(required)
    return " ".join(configured_items)


async def _http_post_form(url: str, data: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=15.0) as client:
        return await client.post(url, data=data)


async def _http_post_json(url: str, payload: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=15.0) as client:
        return await client.post(url, json=payload)


async def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=headers)
    if response.status_code >= 400:
        raise ProviderConfigurationError(f"Request failed for {url}")
    data = response.json()
    if not isinstance(data, dict):
        raise ProviderConfigurationError(f"Invalid JSON response from {url}")
    return data


def _normalize_claim_groups(groups_value: Any) -> list[str]:
    if isinstance(groups_value, str):
        return normalize_groups([groups_value])
    if isinstance(groups_value, list):
        return normalize_groups([str(item) for item in groups_value])
    return []


def _auth0_identity_from_profile(profile: dict[str, Any]) -> AuthIdentity:
    username = str(
        profile.get(settings.operator_auth_auth0_username_claim)
        or profile.get("email")
        or profile.get("nickname")
        or profile.get("name")
        or profile.get("sub")
        or ""
    ).strip()
    subject_id = str(
        profile.get(settings.operator_auth_auth0_subject_claim) or profile.get("sub") or ""
    ).strip()
    if not username or not subject_id:
        raise InvalidCredentialsError("Auth0 profile did not include a usable identity")
    display_name = str(
        profile.get(settings.operator_auth_auth0_display_name_claim)
        or profile.get("name")
        or username
    ).strip()
    groups = _normalize_claim_groups(profile.get(settings.operator_auth_auth0_groups_claim) or [])
    return AuthIdentity(
        provider="auth0",
        subject_id=subject_id,
        username=username,
        display_name=display_name or username,
        groups=groups,
    )


async def _azure_ad_discovery_document() -> dict[str, Any]:
    authority = _azure_ad_authority_base()
    cached = _OIDC_DISCOVERY_CACHE.get(authority)
    if cached is not None:
        return dict(cached)
    data = await _http_get_json(f"{authority}/v2.0/.well-known/openid-configuration")
    _OIDC_DISCOVERY_CACHE[authority] = dict(data)
    return dict(data)


async def _azure_ad_jwks() -> dict[str, Any]:
    discovery = await _azure_ad_discovery_document()
    jwks_uri = str(discovery["jwks_uri"])
    cached = _OIDC_JWKS_CACHE.get(jwks_uri)
    if cached is not None:
        return dict(cached)
    data = await _http_get_json(jwks_uri)
    _OIDC_JWKS_CACHE[jwks_uri] = dict(data)
    return dict(data)


def _azure_ad_groups_from_claims(claims: dict[str, Any]) -> list[str]:
    groups_claim = settings.operator_auth_azure_ad_groups_claim
    claim_names = claims.get("_claim_names")
    if claims.get("hasgroups"):
        return []
    if isinstance(claim_names, dict) and (groups_claim in claim_names or "groups" in claim_names):
        return []
    return _normalize_claim_groups(claims.get(groups_claim) or claims.get("groups") or [])


def _azure_ad_identity_from_claims(
    claims: dict[str, Any],
    *,
    expected_nonce: str | None = None,
) -> AuthIdentity:
    if expected_nonce is not None:
        token_nonce = str(claims.get("nonce") or "").strip()
        if not token_nonce or not secrets.compare_digest(token_nonce, expected_nonce):
            raise InvalidCredentialsError("Azure AD token nonce did not match the login request")

    configured_tenant = _azure_ad_tenant()
    token_tenant = str(claims.get("tid") or "").strip()
    if re.fullmatch(r"[0-9a-fA-F-]{36}", configured_tenant) and token_tenant:
        if token_tenant.casefold() != configured_tenant.casefold():
            raise InvalidCredentialsError("Azure AD token tenant did not match the configured tenant")

    username = str(
        claims.get(settings.operator_auth_azure_ad_username_claim)
        or claims.get("email")
        or claims.get("preferred_username")
        or claims.get("name")
        or claims.get("sub")
        or ""
    ).strip()
    subject_id = str(
        claims.get(settings.operator_auth_azure_ad_subject_claim) or claims.get("sub") or ""
    ).strip()
    if not username or not subject_id:
        raise InvalidCredentialsError("Azure AD token did not include a usable identity")
    display_name = str(
        claims.get(settings.operator_auth_azure_ad_display_name_claim)
        or claims.get("name")
        or username
    ).strip()
    return AuthIdentity(
        provider="azure_ad",
        subject_id=subject_id,
        username=username,
        display_name=display_name or username,
        groups=_azure_ad_groups_from_claims(claims),
    )


async def _decode_azure_ad_id_token(
    id_token: str,
    *,
    client_id: str,
    expected_nonce: str | None = None,
) -> AuthIdentity:
    discovery = await _azure_ad_discovery_document()
    jwks = await _azure_ad_jwks()

    from jose import jwt  # type: ignore[import-untyped]
    from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError  # type: ignore[import-untyped]

    try:
        claims = jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256"],
            audience=client_id,
            issuer=str(discovery["issuer"]),
            options={"verify_at_hash": False},
        )
    except ExpiredSignatureError as exc:
        raise InvalidCredentialsError("Azure AD token has expired") from exc
    except JWTClaimsError as exc:
        raise InvalidCredentialsError(str(exc)) from exc
    except JWTError as exc:
        raise InvalidCredentialsError("Azure AD token validation failed") from exc

    if not isinstance(claims, dict):
        raise InvalidCredentialsError("Azure AD token validation failed")
    return _azure_ad_identity_from_claims(claims, expected_nonce=expected_nonce)


async def get_oidc_authorize_url(
    provider: str,
    *,
    state: str,
    redirect_uri: str,
    nonce: str | None = None,
) -> str:
    normalized = str(provider or "").strip().lower()
    if normalized == "auth0":
        if not auth0_browser_login_enabled():
            raise ProviderConfigurationError("Auth0 browser login is not enabled")
        params = {
            "response_type": "code",
            "client_id": settings.operator_auth_auth0_ui_client_id,
            "redirect_uri": redirect_uri,
            "scope": settings.operator_auth_auth0_scope,
            "state": state,
        }
        if settings.operator_auth_auth0_audience:
            params["audience"] = settings.operator_auth_auth0_audience
        if settings.operator_auth_auth0_organization:
            params["organization"] = settings.operator_auth_auth0_organization
        if settings.operator_auth_auth0_connection:
            params["connection"] = settings.operator_auth_auth0_connection
        return f"{_auth0_base_url()}/authorize?{urlencode(params)}"

    if normalized == "azure_ad":
        if not azure_ad_browser_login_enabled():
            raise ProviderConfigurationError("Azure AD browser login is not enabled")
        if not nonce:
            raise ProviderConfigurationError("Azure AD browser login requires a nonce")
        discovery = await _azure_ad_discovery_document()
        params = {
            "response_type": "code",
            "client_id": settings.operator_auth_azure_ad_ui_client_id,
            "redirect_uri": redirect_uri,
            "scope": _azure_ad_scope(),
            "state": state,
            "nonce": nonce,
        }
        return f"{str(discovery['authorization_endpoint'])}?{urlencode(params)}"

    raise ProviderConfigurationError(f"Provider '{provider}' does not support browser login")


async def start_device_authorization(provider: str) -> DeviceAuthorizationStart:
    normalized = str(provider or "").strip().lower()
    if normalized == "auth0":
        if not auth0_device_login_enabled():
            raise ProviderConfigurationError("Auth0 CLI device login is not enabled")
        payload = {
            "client_id": settings.operator_auth_auth0_cli_client_id,
        }
        if settings.operator_auth_auth0_cli_client_secret:
            payload["client_secret"] = settings.operator_auth_auth0_cli_client_secret
        if settings.operator_auth_auth0_audience:
            payload["audience"] = settings.operator_auth_auth0_audience
        if settings.operator_auth_auth0_scope:
            payload["scope"] = settings.operator_auth_auth0_scope
        response = await _http_post_form(f"{_auth0_base_url()}/oauth/device/code", payload)
        if response.status_code >= 400:
            raise ProviderConfigurationError("Auth0 device authorization could not be started")
        data = response.json()
        return DeviceAuthorizationStart(
            provider="auth0",
            device_code=str(data["device_code"]),
            user_code=str(data["user_code"]),
            verification_uri=str(data["verification_uri"]),
            verification_uri_complete=(
                None
                if data.get("verification_uri_complete") is None
                else str(data.get("verification_uri_complete"))
            ),
            expires_in=int(data.get("expires_in") or 0),
            interval=int(data.get("interval") or 5),
        )

    if normalized == "azure_ad":
        if not azure_ad_device_login_enabled():
            raise ProviderConfigurationError("Azure AD CLI device login is not enabled")
        discovery = await _azure_ad_discovery_document()
        response = await _http_post_form(
            str(discovery["device_authorization_endpoint"]),
            {
                "client_id": settings.operator_auth_azure_ad_cli_client_id,
                "scope": _azure_ad_scope(),
            },
        )
        if response.status_code >= 400:
            raise ProviderConfigurationError("Azure AD device authorization could not be started")
        data = response.json()
        return DeviceAuthorizationStart(
            provider="azure_ad",
            device_code=str(data["device_code"]),
            user_code=str(data["user_code"]),
            verification_uri=str(data["verification_uri"]),
            verification_uri_complete=(
                None
                if data.get("verification_uri_complete") is None
                else str(data.get("verification_uri_complete"))
            ),
            expires_in=int(data.get("expires_in") or 0),
            interval=int(data.get("interval") or 5),
        )

    raise ProviderConfigurationError(f"Provider '{provider}' does not support device login")


async def authenticate_oidc_authorization_code(
    provider: str,
    *,
    code: str,
    redirect_uri: str,
    nonce: str | None = None,
) -> AuthIdentity:
    normalized = str(provider or "").strip().lower()
    if normalized == "auth0":
        if not auth0_browser_login_enabled():
            raise ProviderConfigurationError("Auth0 browser login is not enabled")
        payload = {
            "grant_type": "authorization_code",
            "client_id": settings.operator_auth_auth0_ui_client_id,
            "client_secret": settings.operator_auth_auth0_ui_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        response = await _http_post_json(f"{_auth0_base_url()}/oauth/token", payload)
        if response.status_code >= 400:
            raise InvalidCredentialsError("Auth0 code exchange failed")
        data = response.json()
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise InvalidCredentialsError("Auth0 response did not include an access token")
        profile = await _http_get_json(
            f"{_auth0_base_url()}/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return _auth0_identity_from_profile(profile)

    if normalized == "azure_ad":
        if not azure_ad_browser_login_enabled():
            raise ProviderConfigurationError("Azure AD browser login is not enabled")
        if not nonce:
            raise ProviderConfigurationError("Azure AD browser login requires a nonce")
        discovery = await _azure_ad_discovery_document()
        payload = {
            "grant_type": "authorization_code",
            "client_id": settings.operator_auth_azure_ad_ui_client_id,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if settings.operator_auth_azure_ad_ui_client_secret:
            payload["client_secret"] = settings.operator_auth_azure_ad_ui_client_secret
        response = await _http_post_form(str(discovery["token_endpoint"]), payload)
        if response.status_code >= 400:
            raise InvalidCredentialsError("Azure AD code exchange failed")
        data = response.json()
        id_token = str(data.get("id_token") or "").strip()
        if not id_token:
            raise InvalidCredentialsError("Azure AD response did not include an id_token")
        return await _decode_azure_ad_id_token(
            id_token,
            client_id=settings.operator_auth_azure_ad_ui_client_id,
            expected_nonce=nonce,
        )

    raise ProviderConfigurationError(f"Provider '{provider}' does not support browser login")


async def authenticate_device_code(provider: str, device_code: str) -> AuthIdentity:
    normalized = str(provider or "").strip().lower()
    if normalized == "auth0":
        if not auth0_device_login_enabled():
            raise ProviderConfigurationError("Auth0 CLI device login is not enabled")
        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": settings.operator_auth_auth0_cli_client_id,
        }
        if settings.operator_auth_auth0_cli_client_secret:
            payload["client_secret"] = settings.operator_auth_auth0_cli_client_secret
        response = await _http_post_form(f"{_auth0_base_url()}/oauth/token", payload)
        if response.status_code >= 400:
            data = response.json()
            error = str(data.get("error") or "").strip().lower() if isinstance(data, dict) else ""
            if error in {"authorization_pending", "slow_down"}:
                raise DeviceAuthorizationPending("Waiting for Auth0 approval")
            if error in {"expired_token", "access_denied"}:
                raise DeviceAuthorizationExpired("The Auth0 device login expired or was denied")
            raise InvalidCredentialsError("Auth0 device authorization failed")
        data = response.json()
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise InvalidCredentialsError("Auth0 response did not include an access token")
        profile = await _http_get_json(
            f"{_auth0_base_url()}/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return _auth0_identity_from_profile(profile)

    if normalized == "azure_ad":
        if not azure_ad_device_login_enabled():
            raise ProviderConfigurationError("Azure AD CLI device login is not enabled")
        discovery = await _azure_ad_discovery_document()
        response = await _http_post_form(
            str(discovery["token_endpoint"]),
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": settings.operator_auth_azure_ad_cli_client_id,
            },
        )
        if response.status_code >= 400:
            data = response.json()
            error = str(data.get("error") or "").strip().lower() if isinstance(data, dict) else ""
            if error in {"authorization_pending", "slow_down"}:
                raise DeviceAuthorizationPending("Waiting for Azure AD approval")
            if error in {"expired_token", "authorization_declined", "bad_verification_code"}:
                raise DeviceAuthorizationExpired("The Azure AD device login expired or was denied")
            raise InvalidCredentialsError("Azure AD device authorization failed")
        data = response.json()
        id_token = str(data.get("id_token") or "").strip()
        if not id_token:
            raise InvalidCredentialsError("Azure AD response did not include an id_token")
        return await _decode_azure_ad_id_token(
            id_token,
            client_id=settings.operator_auth_azure_ad_cli_client_id,
        )

    raise ProviderConfigurationError(f"Provider '{provider}' does not support device login")


def upsert_principal(db: Session, identity: AuthIdentity) -> AuthPrincipal:
    principal = (
        db.query(AuthPrincipal)
        .filter(
            AuthPrincipal.provider == identity.provider,
            AuthPrincipal.subject_id == identity.subject_id,
        )
        .first()
    )
    now = utc_now()
    if principal is None:
        principal = AuthPrincipal(
            provider=identity.provider,
            subject_id=identity.subject_id,
            username=identity.username,
            display_name=identity.display_name,
            principal_type=identity.principal_type,
            groups_json=identity.normalized_groups(),
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(principal)
        db.flush()
        return principal

    principal.username = identity.username
    principal.display_name = identity.display_name
    principal.principal_type = identity.principal_type
    principal.groups_json = identity.normalized_groups()
    principal.last_seen_at = now
    principal.updated_at = now
    db.flush()
    return principal


def get_principal_by_id(db: Session, principal_id: int) -> AuthPrincipal | None:
    return db.query(AuthPrincipal).filter(AuthPrincipal.id == principal_id).first()


def list_principals(
    db: Session,
    *,
    provider: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuthPrincipal]:
    query = db.query(AuthPrincipal).order_by(AuthPrincipal.username.asc())
    if provider:
        query = query.filter(AuthPrincipal.provider == provider)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            (AuthPrincipal.username.ilike(pattern)) | (AuthPrincipal.display_name.ilike(pattern))
        )
    return query.offset(offset).limit(limit).all()


def list_role_bindings(db: Session, *, provider: str | None = None) -> list[AuthRoleBinding]:
    query = db.query(AuthRoleBinding).order_by(
        AuthRoleBinding.provider.asc(),
        AuthRoleBinding.binding_type.asc(),
        AuthRoleBinding.id.asc(),
    )
    if provider:
        query = query.filter(AuthRoleBinding.provider == provider)
    return query.all()


def get_role_binding(db: Session, binding_id: int) -> AuthRoleBinding | None:
    return db.query(AuthRoleBinding).filter(AuthRoleBinding.id == binding_id).first()


def create_role_binding(
    db: Session,
    *,
    provider: str,
    binding_type: str,
    role: str,
    principal_id: int | None,
    external_group: str | None,
    created_by: str | None,
) -> AuthRoleBinding:
    binding = AuthRoleBinding(
        provider=provider,
        binding_type=binding_type,
        role=role,
        principal_id=principal_id,
        external_group=(None if external_group is None else external_group.strip() or None),
        created_by=(None if created_by is None else created_by.strip() or None),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(binding)
    db.flush()
    return binding


def update_role_binding(
    db: Session,
    binding: AuthRoleBinding,
    *,
    role: str | None = None,
    external_group: str | None = None,
) -> AuthRoleBinding:
    if role is not None:
        binding.role = role
    if binding.binding_type == "group" and external_group is not None:
        binding.external_group = external_group.strip() or None
    binding.updated_at = utc_now()
    db.flush()
    return binding


def delete_role_binding(db: Session, binding: AuthRoleBinding) -> None:
    db.delete(binding)


def resolve_role_for_identity(
    db: Session,
    identity: AuthIdentity,
    principal: AuthPrincipal | None = None,
) -> tuple[str | None, AuthPrincipal | None]:
    if identity.provider == "local" and identity.is_superuser:
        return ("admin", None)

    principal = principal or upsert_principal(db, identity)

    explicit_binding = (
        db.query(AuthRoleBinding)
        .filter(
            AuthRoleBinding.provider == identity.provider,
            AuthRoleBinding.binding_type == "user",
            AuthRoleBinding.principal_id == principal.id,
        )
        .first()
    )
    if explicit_binding is not None:
        return (explicit_binding.role, principal)

    groups = identity.normalized_groups()
    if not groups:
        return (None, principal)

    group_bindings = (
        db.query(AuthRoleBinding)
        .filter(
            AuthRoleBinding.provider == identity.provider,
            AuthRoleBinding.binding_type == "group",
            AuthRoleBinding.external_group.in_(groups),
        )
        .all()
    )
    return (highest_role([binding.role for binding in group_bindings]), principal)


def build_auth_context(
    identity: AuthIdentity,
    role: str,
    *,
    principal: AuthPrincipal | None = None,
) -> AuthContext:
    return AuthContext(
        provider=identity.provider,
        subject_id=identity.subject_id,
        username=identity.username,
        display_name=identity.display_name or identity.username,
        groups=identity.normalized_groups(),
        role=role,
        principal_type=identity.principal_type,
        is_superuser=identity.is_superuser,
        permissions=permissions_for_role(role, is_superuser=identity.is_superuser),
        principal_id=(None if principal is None else principal.id),
    )


def build_login_context(db: Session, identity: AuthIdentity) -> AuthContext:
    role, principal = resolve_role_for_identity(db, identity)
    if role is None:
        raise AccessDeniedError("No Bakery role binding matches this user")
    return build_auth_context(identity, role, principal=principal)


def service_token_context() -> AuthContext:
    return AuthContext(
        provider="service",
        subject_id="service-token",
        username="service",
        display_name="Internal Service",
        groups=[],
        role="service",
        principal_type="service",
        permissions=permissions_for_role("service"),
    )


def create_session(db: Session, context: AuthContext, *, ttl_seconds: int) -> AuthContext:
    now = utc_now()
    context.session_id = secrets.token_urlsafe(32)
    context.expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
    db.add(
        AuthSession(
            session_id=context.session_id,
            provider=context.provider,
            subject_id=context.subject_id,
            username=context.username,
            display_name=context.display_name,
            role=context.role,
            principal_type=context.principal_type,
            principal_id=context.principal_id,
            is_superuser=context.is_superuser,
            groups_json=context.groups,
            permissions_json=context.permissions,
            expires_at=now + timedelta(seconds=ttl_seconds),
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()
    return context


def get_session(db: Session, session_id: str | None) -> AuthContext | None:
    if not session_id:
        return None
    session = db.query(AuthSession).filter(AuthSession.session_id == session_id).first()
    if session is None:
        return None
    if session.expires_at <= utc_now():
        db.delete(session)
        db.flush()
        return None
    return AuthContext(
        provider=session.provider,
        subject_id=session.subject_id,
        username=session.username,
        display_name=session.display_name,
        groups=list(session.groups_json or []),
        role=session.role,
        principal_type=session.principal_type,
        is_superuser=bool(session.is_superuser),
        permissions=list(session.permissions_json or []),
        principal_id=session.principal_id,
        session_id=session.session_id,
        expires_at=session.expires_at.isoformat(),
    )


def delete_session(db: Session, session_id: str | None) -> None:
    if not session_id:
        return
    session = db.query(AuthSession).filter(AuthSession.session_id == session_id).first()
    if session is not None:
        db.delete(session)
        db.flush()


def put_state(
    db: Session,
    *,
    kind: str,
    state_key: str,
    payload: dict[str, Any],
    ttl_seconds: int,
) -> None:
    existing = (
        db.query(AuthState)
        .filter(AuthState.kind == kind, AuthState.state_key == state_key)
        .first()
    )
    now = utc_now()
    expires_at = now + timedelta(seconds=ttl_seconds)
    if existing is None:
        existing = AuthState(
            kind=kind,
            state_key=state_key,
            payload_json=payload,
            expires_at=expires_at,
            created_at=now,
        )
        db.add(existing)
    else:
        existing.payload_json = payload
        existing.expires_at = expires_at
    db.flush()


def pop_state(db: Session, *, kind: str, state_key: str) -> dict[str, Any] | None:
    row = (
        db.query(AuthState)
        .filter(AuthState.kind == kind, AuthState.state_key == state_key)
        .first()
    )
    if row is None:
        return None
    payload = dict(row.payload_json or {})
    expired = row.expires_at <= utc_now()
    db.delete(row)
    db.flush()
    if expired:
        return None
    return payload


def rehydrate_session_context(
    db: Session,
    session_id: str | None,
) -> tuple[AuthContext | None, str | None]:
    stored = get_session(db, session_id)
    if stored is None:
        return (None, None)
    if stored.role == "service" or stored.principal_type == "service":
        return (stored, None)
    if stored.is_superuser and stored.provider == "local":
        stored.role = "admin"
        stored.permissions = permissions_for_role("admin", is_superuser=True)
        return (stored, None)

    identity = AuthIdentity(
        provider=stored.provider,
        subject_id=stored.subject_id,
        username=stored.username,
        display_name=stored.display_name,
        groups=stored.groups,
        principal_type=stored.principal_type,
        is_superuser=stored.is_superuser,
    )
    principal = None
    if stored.principal_id is not None:
        principal = get_principal_by_id(db, stored.principal_id)
    role, principal = resolve_role_for_identity(db, identity, principal=principal)
    if role is None:
        return (None, "No Bakery role binding matches this session")
    refreshed = build_auth_context(identity, role, principal=principal)
    refreshed.session_id = stored.session_id
    refreshed.expires_at = stored.expires_at
    return (refreshed, None)


def _is_public_path(path: str, method: str) -> bool:
    if method == "OPTIONS":
        return True
    public_paths = {
        "/",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/health",
        "/api/v1/settings",
        "/api/v1/auth/providers",
        "/api/v1/auth/login",
        "/api/v1/auth/oidc/login",
        "/api/v1/auth/oidc/callback",
        "/api/v1/auth/device/start",
        "/api/v1/auth/device/poll",
    }
    return path in public_paths or path.startswith("/assets/") or path.startswith("/static/")


def is_request_public(path: str, method: str) -> bool:
    return _is_public_path(path, method.upper())


async def require_auth_if_enabled(
    request: Request,
    session_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> AuthContext | None:
    if not settings.operator_auth_enabled:
        return None
    existing = getattr(request.state, "auth_context", None)
    if isinstance(existing, AuthContext):
        return existing
    if is_request_public(request.url.path, request.method):
        return None

    context: AuthContext | None = None
    bearer_value = request.headers.get("Authorization", "")
    service_token = request.headers.get("X-Auth-Token")
    if not service_token and bearer_value.lower().startswith("bearer "):
        service_token = bearer_value[7:].strip()
    if settings.operator_auth_service_token and service_token:
        if secrets.compare_digest(service_token, settings.operator_auth_service_token):
            context = service_token_context()

    if context is None:
        context, resolution_error = rehydrate_session_context(db, session_token)
        if context is None:
            if resolution_error:
                raise HTTPException(status_code=403, detail=resolution_error)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid session required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    request.state.auth_context = context
    return context


async def require_reader(
    context: AuthContext | None = Depends(require_auth_if_enabled),
) -> AuthContext:
    if context is None or not is_authorized_for_role(context, "reader"):
        raise HTTPException(status_code=403, detail="Reader access required")
    return context


async def require_operator(
    context: AuthContext | None = Depends(require_auth_if_enabled),
) -> AuthContext:
    if context is None or not is_authorized_for_role(context, "operator"):
        raise HTTPException(status_code=403, detail="Operator access required")
    return context


async def require_admin(
    context: AuthContext | None = Depends(require_auth_if_enabled),
) -> AuthContext:
    if context is None or not is_authorized_for_role(context, "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return context
