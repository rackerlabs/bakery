from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bakery.providers.github import GitHubProvider
from bakery.providers.jira import JiraProvider
from bakery.providers.pagerduty import PagerDutyProvider


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {}


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def patch(self, *args, **kwargs):
        return _Response()

    async def post(self, *args, **kwargs):
        return _Response()

    async def put(self, *args, **kwargs):
        return _Response()


@pytest.mark.asyncio
async def test_github_close_issue_adds_close_notes_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = GitHubProvider()
    add_comment = AsyncMock(return_value={"success": True, "ticket_id": "9"})
    monkeypatch.setattr(provider, "_add_comment", add_comment)
    monkeypatch.setattr("bakery.providers.github.httpx.AsyncClient", lambda *args, **kwargs: _Client())

    result = await provider._close_issue(
        {
            "owner": "rackerlabs",
            "repo": "poundcake",
            "ticket_id": "9",
            "close_notes": "Resolved after recovery.",
        }
    )

    assert result["success"] is True
    add_comment.assert_awaited_once()


@pytest.mark.asyncio
async def test_jira_close_issue_adds_close_notes_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = JiraProvider()
    add_comment = AsyncMock(return_value={"success": True, "ticket_id": "OPS-9"})
    monkeypatch.setattr(provider, "_add_comment", add_comment)
    monkeypatch.setattr("bakery.providers.jira.httpx.AsyncClient", lambda *args, **kwargs: _Client())

    result = await provider._close_issue(
        {
            "ticket_id": "OPS-9",
            "close_notes": {"type": "doc", "version": 1, "content": []},
        }
    )

    assert result["success"] is True
    add_comment.assert_awaited_once()


@pytest.mark.asyncio
async def test_pagerduty_close_incident_adds_close_note(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = PagerDutyProvider()
    add_note = AsyncMock(return_value={"success": True, "ticket_id": "PD-9"})
    monkeypatch.setattr(provider, "_add_note", add_note)
    monkeypatch.setattr(
        "bakery.providers.pagerduty.httpx.AsyncClient",
        lambda *args, **kwargs: _Client(),
    )

    result = await provider._close_incident(
        {
            "ticket_id": "PD-9",
            "from_email": "alerts@example.com",
            "close_notes": "Resolved automatically.",
        }
    )

    assert result["success"] is True
    add_note.assert_awaited_once()
