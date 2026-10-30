"""Preferences, storage, cache, and license through the real client and MCP dispatch.

Fixture HTTP only. Closed arguments are rejected before any native request.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from hextile_client import (  # noqa: E402
    Client,
    _CACHE_UNKNOWN,
    _PREFERENCE_BOOLS,
    _PREFERENCE_ENUMS,
    _SETTINGS_UNKNOWN,
)
from hextile_mcp import TOOLS, HextileMcpServer, _DESTRUCTIVE, _MUTATING, _READ_ONLY  # noqa: E402

_STATUS = (
    "get_app_preferences",
    "update_app_preferences",
    "get_storage_summary",
    "get_cache_buckets",
    "clear_disposable_cache",
    "get_license_status",
)
_READS = (
    "get_app_preferences",
    "get_storage_summary",
    "get_cache_buckets",
    "get_license_status",
)
_SECRET = "/home/secret/renders"
_TOKEN = "sk-secretvalue123"


class _Response:
    def __init__(self, raw: bytes, status: int = 200) -> None:
        self.raw = raw
        self.status = status
        self.headers = {}

    def read(self, amt: int = -1) -> bytes:
        if amt is None or amt < 0:
            return self.raw
        return self.raw[:amt]

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _server(payloads: dict) -> tuple[HextileMcpServer, Client, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def opener(req: Any, timeout: Any = None) -> _Response:
        target = urllib.parse.urlsplit(req.full_url)
        method = req.get_method()
        headers = {key.lower(): value for key, value in req.header_items()}
        assert headers["x-hextile-agent"] == "mcp"
        body = req.data
        calls.append({
            "method": method,
            "path": target.path,
            "query": target.query,
            "body": None if body is None else json.loads(body.decode("utf-8")),
        })
        if target.path == "/api/agent/events":
            return _Response(b"{}")
        spec = payloads.get((method, target.path, target.query))
        if spec is None:
            spec = payloads.get((method, target.path))
        if spec is None:
            raise AssertionError(f"unexpected {method} {target.path}?{target.query}")
        if spec == "down":
            raise urllib.error.URLError("timed out")
        status, raw = spec
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "native", {}, io.BytesIO(raw))
        return _Response(raw, status)

    client = Client(opener=opener)
    return HextileMcpServer(client=client), client, calls


def _native(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in calls if item["path"] != "/api/agent/events"]


def _tool(name: str) -> dict[str, Any]:
    return next(row for row in TOOLS if row["name"] == name)


def _text(result: dict[str, Any]) -> str:
    return result["content"][0]["text"]


def _payload(result: dict[str, Any]) -> Any:
    return json.loads(_text(result))


def _preferences(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {key: False for key in _PREFERENCE_BOOLS}
    for key, values in _PREFERENCE_ENUMS.items():
        payload[key] = sorted(values)[0]
    payload.update({
        "default_pipeline": "sdxl",
        "export_filename_prefix": "",
        "tile_history_keep_n": 0,
        "effective_default_pipeline": "sdxl",
        "output_folder": _SECRET,
        "creator": {"email": "person@example.com"},
        "hf_username": "secret-user",
        "eula_accepted_version": "9",
    })
    payload.update(overrides)
    return payload


def _storage() -> dict[str, Any]:
    return {
        "root": _SECRET,
        "active_root": _SECRET,
        "configured_root": _SECRET,
        "configured_root_available": False,
        "fallback_active": True,
        "is_default": False,
        "output_folder_is_default": False,
        "disk": {"free_gb": 1.5, "total_gb": 10, "path": _SECRET},
        "classes": [{
            "name": "cache",
            "display_name": "Cache",
            "path": _SECRET,
            "size_mb": 2,
            "file_count": 3,
            "protection": "mixed",
            "relocatable": False,
            "location": "external",
            "children": [{
                "name": "inspect_tiles",
                "display_name": "Inspect",
                "path": _SECRET,
                "size_mb": 0,
                "file_count": 0,
                "protection": "disposable",
            }],
        }],
    }


def _buckets() -> dict[str, Any]:
    return {
        "cache_dir": _SECRET,
        "user_data_dir": _SECRET,
        "total_size_mb": 2,
        "buckets": [{
            "name": "inspect_tiles",
            "display_name": "Inspect",
            "path": _SECRET,
            "size_mb": 2,
            "file_count": 1,
            "protection": "disposable",
        }],
    }


def _license(**overrides: Any) -> dict[str, Any]:
    data = {
        "activated": False,
        "tier": None,
        "dev_override": False,
        "access_state": "unlicensed",
        "access_source": None,
        "features": {"sequences_enabled": False, "max_activations": 0},
        "machine_id": "machine-secret",
        "machine_name": "studio-secret",
        "license_key_hint": "ABCD",
        "online_validated": False,
        "email": "person@example.com",
    }
    data.update(overrides)
    return {"success": True, "message": "ok", "data": data}


def test_status_tools_agree_on_names_schema_and_annotations() -> None:
    assert set(_READS) <= _READ_ONLY
    assert {"update_app_preferences", "clear_disposable_cache"} <= _MUTATING
    assert "clear_disposable_cache" in _DESTRUCTIVE
    assert "update_app_preferences" not in _DESTRUCTIVE
    server = HextileMcpServer(client=Client(opener=lambda *_a, **_k: None))
    for name in _STATUS:
        tool = _tool(name)
        assert tool["inputSchema"]["additionalProperties"] is False
        assert name in server._handlers
    update = _tool("update_app_preferences")
    assert update["inputSchema"]["required"] == ["changes"]
    changes = update["inputSchema"]["properties"]["changes"]
    assert changes["additionalProperties"] is False
    assert changes["minProperties"] == 1
    pipeline = changes["properties"]["default_pipeline"]["anyOf"][0]
    prefix = changes["properties"]["export_filename_prefix"]["anyOf"][0]
    assert pipeline == {"type": "string", "minLength": 1}
    assert prefix == {"type": "string"}
    assert "maxLength" not in json.dumps(changes)
    for schema in changes["properties"].values():
        assert {"type": "null"} in schema["anyOf"]
    assert "output_folder" not in changes["properties"]
    assert "bypass" not in changes["properties"]
    assert "force" not in changes["properties"]
    assert _tool("get_license_status")["inputSchema"]["properties"] == {}
    assert "tier" not in _tool("clear_disposable_cache")["inputSchema"]["properties"]
    listed = [row["name"] for row in TOOLS]
    anchor = listed.index("get_plugin_catalog")
    assert listed[anchor + 1:anchor + 7] == list(_STATUS)


def test_preference_roundtrip_preserves_false_bools_and_strips_private_fields() -> None:
    native = _preferences(mcp_enabled=False, show_chat_icon=False, tile_history_keep_n=4)
    server, client, calls = _server({("GET", "/api/settings"): (200, json.dumps(native).encode())})
    direct = client.get_app_preferences()
    via = _payload(server.call_tool("get_app_preferences", {}))
    assert direct == via
    assert via["mcp_enabled"] is False
    assert via["show_chat_icon"] is False
    assert via["tile_history_keep_n"] == 4
    assert via["effective_default_pipeline"] == "sdxl"
    assert "output_folder" not in via
    assert "creator" not in via
    assert "hf_username" not in via
    assert _SECRET not in json.dumps(via)
    assert _native(calls) == [{"method": "GET", "path": "/api/settings", "query": "", "body": None}] * 2


@pytest.mark.parametrize("changes", [
    {"vision_mode": "resident"},
    {"navigate_to_render_on_start": "render_details"},
    {"torch_compile_mode": "max-autotune"},
    {"sd35_quantization": "nf4"},
    {"default_pipeline": "flux"},
    {"export_filename_prefix": ""},
    {"tile_history_keep_n": 0},
    {"tile_history_keep_n": "all"},
    {"telemetry_enabled": True},
    {"error_reporting_enabled": False},
])
def test_preference_update_sends_only_the_partial_object(changes: dict[str, Any]) -> None:
    native = _preferences(**changes)
    server, _client, calls = _server({("PATCH", "/api/settings"): (200, json.dumps(native).encode())})
    result = server.call_tool("update_app_preferences", {"changes": changes})
    assert result["isError"] is False
    body = _payload(result)
    for key, value in changes.items():
        assert body[key] == value
    assert _native(calls)[0]["body"] == changes
    assert "output_folder" not in _native(calls)[0]["body"]


@pytest.mark.parametrize("changes", [
    {},
    {"tile_history_keep_n": "3"},
    {"tile_history_keep_n": 1.5},
    {"tile_history_keep_n": True},
    {"tile_history_keep_n": -1},
    {"mcp_enabled": 0},
    {"mcp_enabled": "false"},
    {"vision_mode": "always"},
    {"vision_mode": ["resident"]},
    {"vision_mode": {"mode": "resident"}},
    {"default_pipeline": ""},
    {"default_pipeline": "/home/uniqueposix/pipe"},
    {"mcp_enabled": ["no"]},
    {"output_folder": _SECRET},
    {"creator": {"email": "person@example.com"}},
])
def test_invalid_preference_changes_do_not_reach_settings(changes: dict[str, Any]) -> None:
    server, _client, calls = _server({})
    result = server.call_tool("update_app_preferences", {"changes": changes})
    assert result["isError"] is True
    assert _payload(result)["status_code"] == 422
    assert _native(calls) == []


def test_storage_and_cache_reads_keep_public_flags_and_drop_locators() -> None:
    server, client, calls = _server({
        ("GET", "/api/storage"): (200, json.dumps(_storage()).encode()),
        ("GET", "/api/storage", "refresh=true"): (200, json.dumps(_storage()).encode()),
        ("GET", "/api/cache/stats"): (200, json.dumps(_buckets()).encode()),
    })
    omitted = _payload(server.call_tool("get_storage_summary", {}))
    explicit = client.get_storage_summary(False)
    assert omitted == explicit
    assert omitted["is_default"] is False
    assert omitted["fallback_active"] is True
    assert omitted["configured_root_available"] is False
    assert omitted["classes"][0]["relocatable"] is False
    assert omitted["classes"][0]["children"][0]["name"] == "inspect_tiles"
    assert "path" not in omitted["classes"][0]
    assert "root" not in omitted
    assert "configured_root" not in omitted
    buckets = _payload(server.call_tool("get_cache_buckets", {}))
    assert buckets["total_size_mb"] == 2
    assert buckets["buckets"][0]["protection"] == "disposable"
    assert "cache_dir" not in buckets
    assert "path" not in buckets["buckets"][0]
    refreshed = server.call_tool("get_storage_summary", {"refresh": True})
    assert refreshed["isError"] is False
    queries = [item["query"] for item in _native(calls) if item["path"] == "/api/storage"]
    assert queries == ["", "", "refresh=true"]
    assert _SECRET not in _text(refreshed)


def test_license_status_uses_the_current_status_and_strips_identity() -> None:
    server, client, calls = _server({
        ("GET", "/api/license/status"): (200, json.dumps(_license()).encode()),
    })
    direct = client.get_license_status()
    via = _payload(server.call_tool("get_license_status", {}))
    assert direct == via
    assert via["activated"] is False
    assert via["tier"] is None
    assert via["access_source"] is None
    assert via["features"] == {"sequences_enabled": False, "max_activations": 0}
    assert via["online_validated"] is False
    assert "machine_id" not in via
    assert "license_key_hint" not in via
    assert "email" not in via
    assert "success" not in via
    assert [item["path"] for item in _native(calls)] == ["/api/license/status", "/api/license/status"]


@pytest.mark.parametrize("name,arguments", [
    ("get_app_preferences", None),
    ("get_app_preferences", []),
    ("get_app_preferences", {"output_folder": _SECRET}),
    ("get_app_preferences", {"token": _TOKEN}),
    ("get_storage_summary", {"refresh": None}),
    ("get_storage_summary", {"refresh": "true"}),
    ("get_storage_summary", {"tier": "PRO"}),
    ("get_cache_buckets", {"cache_dir": _SECRET}),
    ("get_license_status", {"tier": "PRO"}),
    ("get_license_status", {"machine_id": "machine-secret"}),
    ("update_app_preferences", None),
    ("update_app_preferences", []),
    ("update_app_preferences", {"changes": {"mcp_enabled": False}, "output_folder": _SECRET}),
    ("clear_disposable_cache", {"bucket": None}),
    ("clear_disposable_cache", {"bucket": []}),
    ("clear_disposable_cache", {"bucket": "a/b"}),
    ("clear_disposable_cache", {"bucket": ""}),
    ("clear_disposable_cache", {"force": True}),
])
def test_closed_arguments_reject_before_native_call(name: str, arguments: Any) -> None:
    server, _client, calls = _server({})
    direct = server.call_tool(name, arguments)
    assert direct["isError"] is True
    assert _payload(direct)["status_code"] == 422
    rpc = server.handle_rpc({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert rpc["result"]["isError"] is True
    assert _payload(rpc["result"])["status_code"] == 422
    assert _SECRET not in _text(direct)
    assert _TOKEN not in _text(rpc["result"])
    assert _native(calls) == []


def test_omitted_arguments_default_for_zero_arg_reads() -> None:
    server, _client, calls = _server({
        ("GET", "/api/settings"): (200, json.dumps(_preferences()).encode()),
        ("GET", "/api/cache/stats"): (200, json.dumps(_buckets()).encode()),
        ("GET", "/api/license/status"): (200, json.dumps(_license()).encode()),
    })
    for name in ("get_app_preferences", "get_cache_buckets", "get_license_status"):
        response = server.handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name},
        })
        assert response["result"]["isError"] is False
    assert [item["path"] for item in _native(calls)] == [
        "/api/settings", "/api/cache/stats", "/api/license/status",
    ]


def test_malformed_success_hides_private_bodies() -> None:
    secret_body = json.dumps({"output_folder": _SECRET, "token": _TOKEN}).encode()
    server, _client, calls = _server({
        ("GET", "/api/settings"): (200, secret_body),
        ("GET", "/api/storage"): (200, b"not-json " + _SECRET.encode()),
        ("GET", "/api/cache/stats"): (200, secret_body),
        ("GET", "/api/license/status"): (200, json.dumps({"success": True, "data": {"machine_id": _SECRET}}).encode()),
        ("PATCH", "/api/settings"): (200, b"not-json " + _SECRET.encode()),
        ("POST", "/api/cache/clear"): (200, secret_body),
    })
    for name in _READS:
        result = server.call_tool(name, {})
        assert result["isError"] is True
        error = _payload(result)
        assert error["status_code"] == 502
        assert _SECRET not in _text(result)
        assert _TOKEN not in _text(result)
    updated = server.call_tool("update_app_preferences", {"changes": {"show_chat_icon": False}})
    cleared = server.call_tool("clear_disposable_cache", {})
    for result, kind in ((updated, "settings_outcome_unknown"), (cleared, "cache_outcome_unknown")):
        error = _payload(result)
        assert error["kind"] == kind
        assert "Do not replay" in error["error"]
        assert _SECRET not in _text(result)
    assert len(_native(calls)) == 6


_LEGACY_CLEAR_REPORTED = "Cache clear reported an error; private details omitted."


def test_clear_reports_partial_protected_and_live_owner_without_replay() -> None:
    partial = {
        "cleared": ["inspect_tiles"],
        "skipped_protected": ["360_lora_history"],
        "errors": ["postprocess: Permission denied: /home/secret/cache"],
        "error_details": [{"bucket": "postprocess", "code": "os_error", "reason": "clear failed"}],
    }
    legacy = {
        "cleared": [],
        "skipped_protected": [],
        "errors": ["batch_work: owner holds /home/secret/batch"],
    }
    live = {
        "cleared": [],
        "skipped_protected": [],
        "errors": ["batch_work: owner holds /home/secret/batch"],
        "error_details": [{
            "bucket": "batch_work", "code": "live_owner", "reason": "live owner refused the clear",
        }],
    }
    server, _client, calls = _server({
        ("POST", "/api/cache/clear"): (200, json.dumps(partial).encode()),
        ("POST", "/api/cache/clear/360_lora_history"): (
            403, b'{"detail":"\'360_lora_history\' is a protected bucket containing creative work"}',
        ),
        ("POST", "/api/cache/clear/not_a_real_bucket"): (400, b'{"detail":"Unknown cache bucket: not_a_real_bucket"}'),
        ("POST", "/api/cache/clear/batch_work"): (200, json.dumps(live).encode()),
        ("POST", "/api/cache/clear/postprocess"): (200, json.dumps(legacy).encode()),
    })
    partial_result = server.call_tool("clear_disposable_cache", {})
    assert partial_result["isError"] is True
    partial_body = _payload(partial_result)
    assert partial_body["cleared"] == ["inspect_tiles"]
    assert partial_body["skipped_protected"] == ["360_lora_history"]
    assert partial_body["errors"] == [{"bucket": "postprocess", "code": "os_error", "reason": "clear failed"}]
    assert "/home/secret" not in _text(partial_result)
    protected = server.call_tool("clear_disposable_cache", {"bucket": "360_lora_history"})
    assert _payload(protected)["status_code"] == 403
    assert "protected bucket" in _payload(protected)["error"]
    unknown = server.call_tool("clear_disposable_cache", {"bucket": "not_a_real_bucket"})
    assert _payload(unknown)["status_code"] == 400
    assert "Unknown cache bucket" in _payload(unknown)["error"]
    owned = _payload(server.call_tool("clear_disposable_cache", {"bucket": "batch_work"}))
    assert owned["errors"][0]["code"] == "live_owner"
    legacy_result = _payload(server.call_tool("clear_disposable_cache", {"bucket": "postprocess"}))
    assert legacy_result["errors"] == [{"reported": _LEGACY_CLEAR_REPORTED}]
    assert "/home/secret" not in json.dumps(legacy_result)
    assert [item["path"] for item in _native(calls)] == [
        "/api/cache/clear",
        "/api/cache/clear/360_lora_history",
        "/api/cache/clear/not_a_real_bucket",
        "/api/cache/clear/batch_work",
        "/api/cache/clear/postprocess",
    ]


def test_lost_acknowledgement_is_unknown_and_is_not_retried() -> None:
    server, _client, calls = _server({
        ("PATCH", "/api/settings"): "down",
        ("POST", "/api/cache/clear/inspect_tiles"): "down",
    })
    updated = server.call_tool("update_app_preferences", {"changes": {"show_chat_icon": True}})
    cleared = server.call_tool("clear_disposable_cache", {"bucket": "inspect_tiles"})
    assert _payload(updated)["kind"] == "settings_outcome_unknown"
    assert _payload(updated)["error"] == _SETTINGS_UNKNOWN
    assert _payload(cleared)["kind"] == "cache_outcome_unknown"
    assert _payload(cleared)["error"] == _CACHE_UNKNOWN
    assert _native(calls) == [
        {"method": "PATCH", "path": "/api/settings", "query": "", "body": {"show_chat_icon": True}},
        {"method": "POST", "path": "/api/cache/clear/inspect_tiles", "query": "", "body": None},
    ]


def test_mcp_disable_is_one_native_patch_and_cannot_bypass_revoke() -> None:
    native = _preferences(mcp_enabled=False)
    disable, _client, disable_calls = _server({
        ("PATCH", "/api/settings"): (200, json.dumps(native).encode()),
    })
    result = disable.call_tool("update_app_preferences", {"changes": {"mcp_enabled": False}})
    assert result["isError"] is False
    assert _payload(result)["mcp_enabled"] is False
    assert _native(disable_calls) == [{
        "method": "PATCH", "path": "/api/settings", "query": "", "body": {"mcp_enabled": False},
    }]
    blocked, _client, blocked_calls = _server({
        ("PATCH", "/api/settings"): (403, b'{"detail":{"code":"mcp_disabled"}}'),
    })
    denied = blocked.call_tool("update_app_preferences", {"changes": {"mcp_enabled": True}})
    error = _payload(denied)
    assert error["kind"] == "mcp_disabled"
    assert error["status_code"] == 403
    assert _native(blocked_calls) == [{
        "method": "PATCH", "path": "/api/settings", "query": "", "body": {"mcp_enabled": True},
    }]


_LONG_PREFIX = "p" * 257
_LONG_PIPELINE = "q" * 129
_PRIVATE_COMPONENTS = (
    "uniqueposix",
    "uniquewin",
    "uniquewinfwd",
    "uniqueunc",
    "uniquefile",
    "uniquesecretvalue12",
    "PRIVATE_COMPONENT_SENTINEL",
)


def test_long_native_preference_strings_roundtrip() -> None:
    native = _preferences(
        default_pipeline=_LONG_PIPELINE,
        export_filename_prefix=_LONG_PREFIX,
        effective_default_pipeline=_LONG_PIPELINE,
    )
    server, client, calls = _server({
        ("GET", "/api/settings"): (200, json.dumps(native).encode()),
        ("PATCH", "/api/settings"): (200, json.dumps(native).encode()),
    })
    read = client.get_app_preferences()
    assert read["default_pipeline"] == _LONG_PIPELINE
    assert read["export_filename_prefix"] == _LONG_PREFIX
    assert read["effective_default_pipeline"] == _LONG_PIPELINE
    changes = {"default_pipeline": _LONG_PIPELINE, "export_filename_prefix": _LONG_PREFIX}
    updated = _payload(server.call_tool("update_app_preferences", {"changes": changes}))
    assert updated["default_pipeline"] == _LONG_PIPELINE
    assert updated["export_filename_prefix"] == _LONG_PREFIX
    assert _native(calls)[1]["body"] == changes


def test_selected_null_is_forwarded_and_the_snapshot_stays_non_null() -> None:
    mixed = {"show_chat_icon": False, "vision_mode": None, "export_filename_prefix": None}
    every_null = {
        "show_chat_icon": None,
        "vision_mode": None,
        "default_pipeline": None,
        "export_filename_prefix": None,
        "tile_history_keep_n": None,
    }
    snapshot = _preferences(show_chat_icon=False)
    server, _client, calls = _server({
        ("PATCH", "/api/settings"): (200, json.dumps(snapshot).encode()),
    })
    mixed_result = _payload(server.call_tool("update_app_preferences", {"changes": mixed}))
    assert _native(calls)[0]["body"] == mixed
    assert mixed_result["show_chat_icon"] is False
    assert mixed_result["vision_mode"] == snapshot["vision_mode"]
    assert mixed_result["export_filename_prefix"] == ""
    assert None not in mixed_result.values()
    null_result = _payload(server.call_tool("update_app_preferences", {"changes": every_null}))
    assert _native(calls)[1]["body"] == every_null
    assert None not in null_result.values()
    assert null_result["tile_history_keep_n"] == 0


def test_success_false_license_is_not_current_entitlement() -> None:
    denied = _license()
    denied["success"] = False
    denied["message"] = "/home/uniqueposix/license uniquesecretvalue12"
    denied["data"]["machine_id"] = "uniqueidentity"
    denied["data"]["email"] = "uniqueidentity@example.com"
    server, _client, calls = _server({
        ("GET", "/api/license/status"): (200, json.dumps(denied).encode()),
    })
    result = server.call_tool("get_license_status", {})
    text = _text(result)
    assert result["isError"] is True
    assert _payload(result)["status_code"] == 502
    assert "License status is malformed" in text
    for secret in ("uniqueposix", "uniquesecretvalue12", "uniqueidentity", "machine_id"):
        assert secret not in text
    assert len(_native(calls)) == 1


def test_typed_bucket_names_are_malformed() -> None:
    numeric_top = _buckets()
    numeric_top["buckets"][0]["name"] = 12
    numeric_top["buckets"][0]["path"] = "/home/uniqueposix/cache"
    bool_top = _buckets()
    bool_top["buckets"][0]["name"] = True
    bool_top["buckets"][0]["path"] = "/home/uniqueposix/cache"
    numeric_child = _storage()
    numeric_child["classes"][0]["children"][0]["name"] = 7
    numeric_child["classes"][0]["children"][0]["path"] = "/home/uniqueposix/child"
    bool_child = _storage()
    bool_child["classes"][0]["children"][0]["name"] = False
    bool_child["classes"][0]["children"][0]["path"] = "/home/uniqueposix/child"
    cases = (
        ("/api/cache/stats", numeric_top, "get_cache_buckets"),
        ("/api/cache/stats", bool_top, "get_cache_buckets"),
        ("/api/storage", numeric_child, "get_storage_summary"),
        ("/api/storage", bool_child, "get_storage_summary"),
    )
    for path, payload, tool in cases:
        server, _client, calls = _server({("GET", path): (200, json.dumps(payload).encode())})
        result = server.call_tool(tool, {})
        assert result["isError"] is True
        assert _payload(result)["status_code"] == 502
        assert "uniqueposix" not in _text(result)
        assert "TypeError" not in _text(result)
        assert len(_native(calls)) == 1


def test_unhashable_clear_code_is_not_a_success() -> None:
    payload = {
        "cleared": [],
        "skipped_protected": [],
        "errors": ["postprocess: /home/uniqueposix/cache"],
        "error_details": [{
            "bucket": "postprocess", "code": ["os_error"], "reason": "clear failed",
        }],
    }
    server, _client, calls = _server({
        ("POST", "/api/cache/clear"): (200, json.dumps(payload).encode()),
    })
    result = server.call_tool("clear_disposable_cache", {})
    assert result["isError"] is True
    assert "uniqueposix" not in _text(result)
    assert "unhashable" not in _text(result)
    assert "TypeError" not in _text(result)
    assert len(_native(calls)) == 1


def test_unhashable_storage_location_is_malformed() -> None:
    payload = _storage()
    payload["classes"][0]["location"] = ["root"]
    payload["classes"][0]["path"] = "/home/uniqueposix/class"
    server, _client, _calls = _server({
        ("GET", "/api/storage"): (200, json.dumps(payload).encode()),
    })
    result = server.call_tool("get_storage_summary", {})
    assert result["isError"] is True
    assert _payload(result)["status_code"] == 502
    assert "uniqueposix" not in _text(result)
    assert "TypeError" not in _text(result)


def test_legacy_clear_text_hides_full_locator_components() -> None:
    public = "https://360hextile.com/docs/cache"
    errors = [
        "protected bucket has no clear path",
        "Permission denied: /home/uniqueposix/cache",
        "Permission denied: C:\\Users\\uniquewin\\cache",
        "Permission denied: C:/Users/uniquewinfwd/cache",
        "Permission denied: \\\\server\\uniqueunc\\cache",
        "Permission denied: file:///home/uniquefile/cache",
        f"refused {public} see /home/uniqueposix/nested",
        "token sk-uniquesecretvalue12",
        "[path]ome/uniqueposix/cache",
        f"see {public}",
        "Permission denied: '/home/example/Folder PRIVATE_COMPONENT_SENTINEL/cache'",
        "Permission denied: 'C:\\Users\\Example\\Folder PRIVATE_COMPONENT_SENTINEL\\cache'",
        "Permission denied: '\\\\server\\Folder PRIVATE_COMPONENT_SENTINEL\\cache'",
        "Permission denied: 'file:///home/example/Folder PRIVATE_COMPONENT_SENTINEL/cache'",
        "[path] PRIVATE_COMPONENT_SENTINEL[path]",
    ]
    server, client, _calls = _server({
        ("POST", "/api/cache/clear"): (200, json.dumps({
            "cleared": ["inspect_tiles"],
            "skipped_protected": ["360_lora_history"],
            "errors": errors,
        }).encode()),
    })
    direct = client.clear_disposable_cache()
    via = server.call_tool("clear_disposable_cache", {})
    assert via["isError"] is True
    body = _payload(via)
    assert direct == body
    assert body["cleared"] == ["inspect_tiles"]
    assert body["skipped_protected"] == ["360_lora_history"]
    assert len(body["errors"]) == len(errors)
    assert body["errors"] == [{"reported": _LEGACY_CLEAR_REPORTED} for _item in errors]
    rendered = json.dumps(body)
    for component in _PRIVATE_COMPONENTS:
        assert component not in rendered
    assert public not in rendered
    assert "Permission denied:" not in rendered
    assert "[path]" not in rendered
