"""HTTP client for bakeryctl."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from bakery.schemas import (
    AuthMeResponse,
    AuthProviderResponse,
    CollectionJobCreateRequest,
    CollectionJobResponse,
    DeviceAuthorizationPollRequest,
    DeviceAuthorizationPollResponse,
    DeviceAuthorizationStartRequest,
    DeviceAuthorizationStartResponse,
    MonitorBootstrapCredentialResponse,
    MonitorEventResponse,
    MonitorRouteInventoryResponse,
    MonitorSummaryResponse,
    OperationAnalyticsResponse,
    ReportOverviewResponse,
    SessionResponse,
    TicketBacklogResponse,
    ProviderAnalyticsResponse,
)
from cli.session import SessionStore, StoredSession


class BakeryClientError(RuntimeError):
    """Base CLI client error."""


@dataclass
class ProviderInfo:
    name: str
    label: str
    login_mode: str
    cli_login_mode: str
    browser_login: bool = False
    device_login: bool = False
    password_login: bool = False


@dataclass
class LoginResult:
    session_id: str
    username: str
    expires_at: str
    provider: str
    role: str
    display_name: str | None = None
    is_superuser: bool = False
    permissions: list[str] | None = None


@dataclass
class DeviceAuthorizationStart:
    provider: str
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None
    expires_in: int
    interval: int


@dataclass
class AuthMeResult:
    username: str
    display_name: str | None
    provider: str
    role: str
    principal_type: str
    principal_id: int | None
    is_superuser: bool
    permissions: list[str]
    groups: list[str]
    expires_at: str | None = None


class BakeryClient:
    """Simple sync client for Bakery operator APIs."""

    def __init__(
        self,
        base_url: str,
        service_token: str | None = None,
        *,
        session_store: SessionStore | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token or ""
        self.session_store = session_store or SessionStore()
        self.session = None if self.service_token else self.session_store.get(self.base_url)
        self.headers: dict[str, str] = {}
        if self.service_token:
            self.headers["X-Auth-Token"] = self.service_token

    def _cookies(self, *, use_session: bool = True) -> dict[str, str] | None:
        if self.service_token or not use_session or not self.session:
            return None
        return {"session_token": self.session.session_id}

    def _extract_error(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and "detail" in data:
            return str(data["detail"])
        return response.text.strip() or response.reason_phrase or f"HTTP {response.status_code}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        use_session: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path}"
        response = httpx.request(
            method=method,
            url=url,
            headers=self.headers,
            cookies=self._cookies(use_session=use_session),
            json=json,
            params=params,
            timeout=30.0,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            raise BakeryClientError(self._extract_error(response))
        if not response.content:
            return {}
        return response.json()

    def _validate_model(self, payload: Any, model: type[BaseModel], context: str) -> BaseModel:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise BakeryClientError(f"{context}: {exc}") from exc

    def _validate_list(self, payload: Any, model: type[BaseModel], context: str) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            raise BakeryClientError(context)
        validated: list[dict[str, Any]] = []
        for item in payload:
            record = self._validate_model(item, model, context)
            validated.append(record.model_dump(mode="json", by_alias=True))
        return validated

    def get_auth_providers(self) -> list[ProviderInfo]:
        payload = self._request("GET", "/api/v1/auth/providers", use_session=False)
        items = self._validate_list(payload, AuthProviderResponse, "Invalid auth provider response")
        return [ProviderInfo(**item) for item in items]

    def login(self, provider: str, username: str, password: str) -> LoginResult:
        payload = self._request(
            "POST",
            "/api/v1/auth/login",
            json={"provider": provider, "username": username, "password": password},
            use_session=False,
        )
        session = self._validate_model(payload, SessionResponse, "Invalid login response")
        stored = StoredSession(
            session_id=session.session_id,
            username=session.username,
            expires_at=session.expires_at,
            provider=session.provider,
            role=session.role,
            display_name=session.display_name,
            is_superuser=session.is_superuser,
            permissions=session.permissions,
        )
        self.session_store.save(self.base_url, stored)
        self.session = stored
        return LoginResult(**stored.to_dict())

    def start_device_login(self, provider: str) -> DeviceAuthorizationStart:
        payload = self._request(
            "POST",
            "/api/v1/auth/device/start",
            json=DeviceAuthorizationStartRequest(provider=provider).model_dump(mode="json"),
            use_session=False,
        )
        response = self._validate_model(
            payload,
            DeviceAuthorizationStartResponse,
            "Invalid device-start response",
        )
        return DeviceAuthorizationStart(**response.model_dump(mode="json"))

    def poll_device_login(self, provider: str, device_code: str) -> DeviceAuthorizationPollResponse:
        payload = self._request(
            "POST",
            "/api/v1/auth/device/poll",
            json=DeviceAuthorizationPollRequest(
                provider=provider,
                device_code=device_code,
            ).model_dump(mode="json"),
            use_session=False,
        )
        response = self._validate_model(
            payload,
            DeviceAuthorizationPollResponse,
            "Invalid device-poll response",
        )
        if response.session is not None:
            stored = StoredSession(
                session_id=response.session.session_id,
                username=response.session.username,
                expires_at=response.session.expires_at,
                provider=response.session.provider,
                role=response.session.role,
                display_name=response.session.display_name,
                is_superuser=response.session.is_superuser,
                permissions=response.session.permissions,
            )
            self.session_store.save(self.base_url, stored)
            self.session = stored
        return response

    def logout(self) -> bool:
        had_session = self.session is not None
        try:
            self._request("POST", "/api/v1/auth/logout")
        except BakeryClientError:
            pass
        self.session_store.delete(self.base_url)
        self.session = None
        return had_session

    def whoami(self) -> AuthMeResult:
        payload = self._request("GET", "/api/v1/auth/me")
        response = self._validate_model(payload, AuthMeResponse, "Invalid auth/me response")
        return AuthMeResult(**response.model_dump(mode="json"))

    def report_overview(self, **params: Any) -> dict[str, Any]:
        payload = self._request("GET", "/api/v1/reports/overview", params=params)
        response = self._validate_model(payload, ReportOverviewResponse, "Invalid overview report")
        return response.model_dump(mode="json")

    def report_monitors(self, **params: Any) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/reports/monitors", params=params)
        return self._validate_list(payload, MonitorSummaryResponse, "Invalid monitor report")

    def report_monitor_events(self, **params: Any) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/reports/monitor-events", params=params)
        return self._validate_list(payload, MonitorEventResponse, "Invalid monitor-event report")

    def report_routes(self, **params: Any) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/reports/routes", params=params)
        return self._validate_list(payload, MonitorRouteInventoryResponse, "Invalid route report")

    def report_providers(self, **params: Any) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/reports/providers", params=params)
        return self._validate_list(payload, ProviderAnalyticsResponse, "Invalid provider report")

    def report_operations(self, **params: Any) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/reports/operations", params=params)
        return self._validate_list(payload, OperationAnalyticsResponse, "Invalid operations report")

    def report_backlog(self, **params: Any) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/reports/backlog", params=params)
        return self._validate_list(payload, TicketBacklogResponse, "Invalid backlog report")

    def queue_job(
        self,
        *,
        monitor_uuid: str,
        collector_type: str,
        parameters: dict[str, Any] | None,
        reason: str | None,
    ) -> dict[str, Any]:
        request = CollectionJobCreateRequest(
            monitor_uuid=monitor_uuid,
            collector_type=collector_type,
            parameters=parameters or {},
            reason=reason,
        )
        payload = self._request(
            "POST",
            "/api/v1/collection-jobs",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        response = self._validate_model(payload, CollectionJobResponse, "Invalid collection-job response")
        return response.model_dump(mode="json")

    def list_jobs(self, **params: Any) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/collection-jobs", params=params)
        return self._validate_list(payload, CollectionJobResponse, "Invalid collection-job list")

    def get_job(self, job_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/v1/collection-jobs/{job_id}")
        response = self._validate_model(payload, CollectionJobResponse, "Invalid collection-job detail")
        return response.model_dump(mode="json")

    def requeue_job(self, job_id: str) -> dict[str, Any]:
        payload = self._request("POST", f"/api/v1/collection-jobs/{job_id}/requeue", json={})
        response = self._validate_model(payload, CollectionJobResponse, "Invalid collection-job response")
        return response.model_dump(mode="json")

    def rotate_bootstrap(self, monitor_id: str) -> dict[str, Any]:
        payload = self._request("PUT", f"/api/v1/admin/monitors/{monitor_id}/bootstrap-credential", json={})
        response = self._validate_model(
            payload,
            MonitorBootstrapCredentialResponse,
            "Invalid bootstrap-credential response",
        )
        return response.model_dump(mode="json")
