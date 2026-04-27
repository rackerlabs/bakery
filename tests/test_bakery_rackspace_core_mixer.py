from __future__ import annotations

import httpx
import pytest

from bakery.config import settings
from bakery.mixer.rackspace_core import RackspaceCoreMixer


@pytest.mark.asyncio
async def test_create_ticket_resolves_named_values_to_numeric_ids(monkeypatch: pytest.MonkeyPatch):
    mixer = RackspaceCoreMixer()
    calls: list[list[dict[str, object]]] = []

    async def _fake_execute(query_set: list[dict[str, object]]):
        calls.append(query_set)
        first = query_set[0]
        class_name = first.get("class")
        load_arg = first.get("load_arg")

        if class_name == "Ticket.Queue" and isinstance(load_arg, dict):
            return [{"result": [{"id": 472, "name": "Support Queue"}]}]

        if class_name == "Ticket.Queue" and load_arg == 472:
            return [
                {
                    "result": [
                        {
                            "id": 472,
                            "name": "Support Queue",
                            "subcategories": [[{"id": 29158, "name": "Monitoring"}]],
                            "sources": [{"id": 12, "name": "RunBook"}],
                            "severities": [
                                {"id": 1, "name": "Standard"},
                                {"id": 2, "name": "Urgent"},
                                {"id": 3, "name": "Emergency"},
                            ],
                        }
                    ]
                }
            ]

        if class_name == "Account.Account":
            assert first.get("args") == [472, 29158, 12, 2, "test subject", "test body"]
            return [{"result": {"load_value": "260309-12345"}}]

        raise AssertionError(f"Unexpected query_set: {query_set}")

    monkeypatch.setattr(mixer, "_execute_query", _fake_execute)

    result = await mixer._create_ticket(
        {
            "account_number": "10",
            "queue": "Support Queue",
            "subcategory": "Monitoring",
            "source": "poundcake",
            "severity": "warning",
            "subject": "test subject",
            "body": "test body",
        }
    )

    assert result["success"] is True
    assert result["ticket_id"] == "260309-12345"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_create_ticket_attaches_resolved_core_device(monkeypatch: pytest.MonkeyPatch):
    mixer = RackspaceCoreMixer()
    calls: list[list[dict[str, object]]] = []

    async def _fake_execute(query_set: list[dict[str, object]]):
        calls.append(query_set)
        first = query_set[0]
        class_name = first.get("class")
        load_arg = first.get("load_arg")

        if class_name == "Ticket.Queue" and isinstance(load_arg, dict):
            return [{"result": [{"id": 472, "name": "Support Queue"}]}]

        if class_name == "Ticket.Queue" and load_arg == 472:
            return [
                {
                    "result": [
                        {
                            "id": 472,
                            "name": "Support Queue",
                            "subcategories": [[{"id": 29158, "name": "Monitoring"}]],
                            "sources": [{"id": 12, "name": "RunBook"}],
                            "severities": [{"id": 2, "name": "Urgent"}],
                        }
                    ]
                }
            ]

        if class_name == "Account.Account" and first.get("method") == "addTicket":
            return [{"result": {"number": "260309-12345"}}]

        if class_name == "Account.Account" and "attributes" in first:
            return [
                {
                    "result": [
                        {
                            "computers": {
                                "attribute": "computers",
                                "subattributes": {
                                    "472292": {
                                        "name": "472292-storage01",
                                        "nickname": "storage01",
                                        "status.name": "Online/Complete",
                                    }
                                },
                            }
                        }
                    ]
                }
            ]

        if class_name == "Ticket.Ticket" and first.get("method") == "addComputer":
            assert first.get("args") == [472292]
            assert first.get("keyword_args") == {"check_for_dr": True}
            return [{"result": {"attached": True}}]

        raise AssertionError(f"Unexpected query_set: {query_set}")

    monkeypatch.setattr(mixer, "_execute_query", _fake_execute)

    result = await mixer._create_ticket(
        {
            "account_number": "10",
            "queue": "Support Queue",
            "subcategory": "Monitoring",
            "source": "poundcake",
            "severity": "warning",
            "subject": "test subject",
            "body": "test body",
            "device_context": {"name": "472292-storage01"},
        }
    )

    assert result["success"] is True
    assert result["data"]["device_attachment"]["attached"] is True
    assert calls[-1][0]["method"] == "addComputer"


@pytest.mark.asyncio
async def test_add_comment_skips_ambiguous_core_device_match(
    monkeypatch: pytest.MonkeyPatch,
):
    mixer = RackspaceCoreMixer()
    calls: list[list[dict[str, object]]] = []

    async def _fake_execute(query_set: list[dict[str, object]]):
        calls.append(query_set)
        first = query_set[0]
        class_name = first.get("class")
        load_arg = first.get("load_arg")

        if class_name == "Ticket.Ticket" and load_arg == "260309-12345" and "attributes" in first:
            return [{"result": [{"queue": {"load_value": 472}}]}]

        if class_name == "Ticket.Queue" and load_arg == 472:
            return [
                {
                    "result": [
                        {
                            "id": 472,
                            "name": "Support Queue",
                            "subcategories": [],
                            "sources": [{"id": 12, "name": "RunBook"}],
                            "severities": [],
                        }
                    ]
                }
            ]

        if class_name == "Ticket.Ticket" and first.get("method") == "addMessage":
            return [{"result": [{"load_value": 123}]}]

        if class_name == "Account.Account" and "attributes" in first:
            return [
                {
                    "result": [
                        {
                            "computers": {
                                "attribute": "computers",
                                "subattributes": {
                                    "1001": {
                                        "name": "1001-storage01",
                                        "nickname": "storage01",
                                        "status.name": "Online/Complete",
                                    },
                                    "1002": {
                                        "name": "1002-storage01",
                                        "nickname": "storage01",
                                        "status.name": "Online/Complete",
                                    },
                                },
                            }
                        }
                    ]
                }
            ]

        raise AssertionError(f"Unexpected query_set: {query_set}")

    monkeypatch.setattr(mixer, "_execute_query", _fake_execute)

    result = await mixer._add_comment(
        {
            "ticket_id": "260309-12345",
            "comment": "[b]test[/b]",
            "account_number": "10",
            "device_context": {"name": "storage01"},
        }
    )

    assert result["success"] is True
    assert result["data"]["device_attachment"]["reason"] == "ambiguous_device_match"
    assert all(call[0].get("method") != "addComputer" for call in calls)


@pytest.mark.asyncio
async def test_create_ticket_does_not_fail_when_device_attachment_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    mixer = RackspaceCoreMixer()

    async def _fake_execute(query_set: list[dict[str, object]]):
        first = query_set[0]
        class_name = first.get("class")
        load_arg = first.get("load_arg")

        if class_name == "Ticket.Queue" and isinstance(load_arg, dict):
            return [{"result": [{"id": 472, "name": "Support Queue"}]}]

        if class_name == "Ticket.Queue" and load_arg == 472:
            return [
                {
                    "result": [
                        {
                            "id": 472,
                            "name": "Support Queue",
                            "subcategories": [[{"id": 29158, "name": "Monitoring"}]],
                            "sources": [{"id": 12, "name": "RunBook"}],
                            "severities": [{"id": 2, "name": "Urgent"}],
                        }
                    ]
                }
            ]

        if class_name == "Account.Account" and first.get("method") == "addTicket":
            return [{"result": {"number": "260309-12345"}}]

        if class_name == "Account.Account" and "attributes" in first:
            return [
                {
                    "result": [
                        {
                            "computers": {
                                "attribute": "computers",
                                "subattributes": {
                                    "472292": {
                                        "name": "472292-storage01",
                                        "nickname": "storage01",
                                        "status.name": "Online/Complete",
                                    }
                                },
                            }
                        }
                    ]
                }
            ]

        if class_name == "Ticket.Ticket" and first.get("method") == "addComputer":
            request = httpx.Request("POST", "https://example.invalid/ctkapi/query/")
            response = httpx.Response(500, request=request)
            raise httpx.HTTPStatusError("attach failed", request=request, response=response)

        raise AssertionError(f"Unexpected query_set: {query_set}")

    monkeypatch.setattr(mixer, "_execute_query", _fake_execute)

    result = await mixer._create_ticket(
        {
            "account_number": "10",
            "queue": "Support Queue",
            "subcategory": "Monitoring",
            "source": "poundcake",
            "severity": "warning",
            "subject": "test subject",
            "body": "test body",
            "device_context": {"name": "472292-storage01"},
        }
    )

    assert result["success"] is True
    assert result["data"]["device_attachment"]["attached"] is False
    assert "attach failed" in result["data"]["device_attachment"]["error"]


@pytest.mark.asyncio
async def test_close_ticket_uses_set_status_by_name(monkeypatch: pytest.MonkeyPatch):
    mixer = RackspaceCoreMixer()
    calls: list[list[dict[str, object]]] = []

    async def _fake_execute(query_set: list[dict[str, object]]):
        calls.append(query_set)
        return [{"result": {"ok": True}}]

    monkeypatch.setattr(mixer, "_execute_query", _fake_execute)

    result = await mixer._close_ticket({"ticket_id": "260309-12345", "status": "confirmed_solved"})

    assert result["success"] is True
    assert calls[0][0]["method"] == "setStatusByName"
    assert calls[0][0]["args"] == ["Confirm Solved"]
    assert calls[0][0]["keyword_args"] == {}


@pytest.mark.asyncio
async def test_close_ticket_defaults_to_confirm_solved(monkeypatch: pytest.MonkeyPatch):
    mixer = RackspaceCoreMixer()
    calls: list[list[dict[str, object]]] = []

    async def _fake_execute(query_set: list[dict[str, object]]):
        calls.append(query_set)
        return [{"result": {"ok": True}}]

    monkeypatch.setattr(settings, "bakery_rackspace_confirmed_solved_status", "confirmed solved")
    monkeypatch.setattr(mixer, "_execute_query", _fake_execute)

    result = await mixer._close_ticket({"ticket_id": "260309-12345"})

    assert result["success"] is True
    assert calls[0][0]["args"] == ["Confirm Solved"]


@pytest.mark.asyncio
async def test_close_ticket_falls_back_to_set_attribute_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
):
    mixer = RackspaceCoreMixer()
    calls: list[list[dict[str, object]]] = []

    async def _fake_execute(query_set: list[dict[str, object]]):
        calls.append(query_set)
        if len(calls) == 1:
            request = httpx.Request("POST", "https://example.invalid/ctkapi/query/")
            response = httpx.Response(500, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)
        return [{"result": {"ok": True}}]

    monkeypatch.setattr(mixer, "_execute_query", _fake_execute)

    result = await mixer._close_ticket({"ticket_id": "260309-12345", "status": "Solved"})

    assert result["success"] is True
    assert calls[0][0]["method"] == "setStatusByName"
    assert "set_attribute" in calls[1][0]


@pytest.mark.asyncio
async def test_add_comment_uses_add_message_with_numeric_source_id(
    monkeypatch: pytest.MonkeyPatch,
):
    mixer = RackspaceCoreMixer()
    calls: list[list[dict[str, object]]] = []

    async def _fake_execute(query_set: list[dict[str, object]]):
        calls.append(query_set)
        first = query_set[0]
        class_name = first.get("class")
        load_arg = first.get("load_arg")

        if class_name == "Ticket.Ticket" and load_arg == "260309-12345" and "attributes" in first:
            return [{"result": [{"queue": {"load_value": 472}}]}]

        if class_name == "Ticket.Queue" and load_arg == 472:
            return [
                {
                    "result": [
                        {
                            "id": 472,
                            "name": "Support Queue",
                            "subcategories": [],
                            "sources": [{"id": 12, "name": "RunBook"}],
                            "severities": [],
                        }
                    ]
                }
            ]

        if class_name == "Ticket.Ticket" and first.get("method") == "addMessage":
            assert first.get("args") == ["[b]test[/b]", 12]
            assert first.get("keyword_args") == {"private": True, "has_bbcode": True}
            return [{"result": [{"load_value": 123}]}]

        raise AssertionError(f"Unexpected query_set: {query_set}")

    monkeypatch.setattr(mixer, "_execute_query", _fake_execute)

    result = await mixer._add_comment(
        {
            "ticket_id": "260309-12345",
            "comment": "[b]test[/b]",
            "visibility": "internal",
        }
    )

    assert result["success"] is True
    assert calls[-1][0]["method"] == "addMessage"


@pytest.mark.asyncio
async def test_close_ticket_adds_close_notes_before_status_change(
    monkeypatch: pytest.MonkeyPatch,
):
    mixer = RackspaceCoreMixer()
    calls: list[list[dict[str, object]]] = []

    async def _fake_execute(query_set: list[dict[str, object]]):
        calls.append(query_set)
        first = query_set[0]
        class_name = first.get("class")
        load_arg = first.get("load_arg")

        if class_name == "Ticket.Ticket" and load_arg == "260309-12345" and "attributes" in first:
            return [{"result": [{"queue": {"load_value": 472}}]}]

        if class_name == "Ticket.Queue" and load_arg == 472:
            return [
                {
                    "result": [
                        {
                            "id": 472,
                            "name": "Support Queue",
                            "subcategories": [],
                            "sources": [{"id": 12, "name": "RunBook"}],
                            "severities": [],
                        }
                    ]
                }
            ]

        if class_name == "Ticket.Ticket" and first.get("method") == "addMessage":
            assert first.get("args") == ["[b]resolved[/b]", 12]
            assert first.get("keyword_args") == {"private": False, "has_bbcode": True}
            return [{"result": [{"load_value": 456}]}]

        if class_name == "Ticket.Ticket" and first.get("method") == "setStatusByName":
            assert first.get("args") == ["Confirm Solved"]
            return [{"result": {"ok": True}}]

        raise AssertionError(f"Unexpected query_set: {query_set}")

    monkeypatch.setattr(mixer, "_execute_query", _fake_execute)

    result = await mixer._close_ticket(
        {
            "ticket_id": "260309-12345",
            "status": "confirmed_solved",
            "close_notes": "[b]resolved[/b]",
        }
    )

    assert result["success"] is True
    assert calls[-1][0]["method"] == "setStatusByName"
