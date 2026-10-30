"""Cross-repo discovery contract through the real client and MCP dispatch.

Fixture HTTP only. Schema documents pass through; list and catalog responses
are projected. Extra keys are rejected before the native read.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from hextile_client import Client, HextileClientError  # noqa: E402
from hextile_mcp import (  # noqa: E402
    TOOL_NAMES,
    TOOLS,
    HextileMcpServer,
    _MUTATING,
    _READ_ONLY,
)

_DISCOVERY = (
    "get_config_schema",
    "list_processors",
    "get_processor_schema",
    "get_plugin_catalog",
)
_MARKER = "PARTIAL_SCHEMA_MARKER"


class _Response:
    def __init__(self, raw: bytes, status: int = 200) -> None:
        self.raw = raw
        self.status = status

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


def _server(payloads: dict[tuple[str, str], tuple[int, bytes]]) -> tuple[HextileMcpServer, Client, list[tuple[str, str, str]]]:
    calls: list[tuple[str, str, str]] = []

    def opener(req: Any, timeout: Any = None) -> _Response:
        path = urllib.parse.urlsplit(req.full_url).path
        method = req.get_method()
        calls.append((method, path, req.full_url))
        headers = {key.lower(): value for key, value in req.header_items()}
        assert headers["x-hextile-agent"] == "mcp"
        if path == "/api/agent/events":
            return _Response(b"{}")
        spec = payloads.get((method, path))
        if spec is None:
            raise AssertionError(f"unexpected {method} {path}")
        status, body = spec
        if status >= 400:
            raise urllib.error.HTTPError(
                req.full_url, status, "native", {}, io.BytesIO(body),
            )
        return _Response(body, status)

    client = Client(opener=opener)
    return HextileMcpServer(client=client), client, calls


def _native_calls(calls: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    return [item for item in calls if item[1] != "/api/agent/events"]


def _tool(name: str) -> dict[str, Any]:
    return next(row for row in TOOLS if row["name"] == name)


def test_discovery_tools_are_closed_read_only_and_dispatched() -> None:
    assert {
        "get_config_schema", "list_processors", "get_processor_schema", "get_plugin_catalog",
    } <= set(TOOL_NAMES)
    assert set(_DISCOVERY) <= _READ_ONLY
    assert not set(_DISCOVERY) & _MUTATING
    for name in _DISCOVERY:
        tool = _tool(name)
        assert tool["annotations"] == {"readOnlyHint": True, "destructiveHint": False}
        assert tool["inputSchema"]["additionalProperties"] is False
        assert name in HextileMcpServer(client=Client(opener=lambda *_a, **_k: None))._handlers
    capabilities = _tool("get_capabilities")
    assert capabilities["inputSchema"]["properties"] == {}
    assert capabilities["inputSchema"]["additionalProperties"] is False
    assert "get_shader_context" in _READ_ONLY
    assert "get_shader_parameters" in _READ_ONLY
    assert "set_shader_parameter" in _MUTATING
    assert "register_animation" not in TOOL_NAMES
    assert "create_animation" not in TOOL_NAMES


def test_extra_keys_never_reach_discovery_routes() -> None:
    server, _client, calls = _server({})
    for name, args in (
        ("get_config_schema", {"model": "PromptSettings", "extra": True}),
        ("list_processors", {"mode": "sdxl"}),
        ("get_processor_schema", {"pipeline_id": "sdxl", "validate": True}),
        ("get_plugin_catalog", {"installed_root": "/mnt/private"}),
        ("get_processor_schema", {"pipeline_id": "sdxl/validate"}),
        ("get_processor_schema", {}),
    ):
        result = server.call_tool(name, args)
        assert result["isError"] is True
        payload = json.loads(result["content"][0]["text"])
        assert payload["status_code"] == 422
    assert _native_calls(calls) == []


def test_config_schema_query_and_processor_schema_pass_through() -> None:
    schema = {
        "model": "PromptSettings",
        "schema": {
            "properties": {"global": {"type": "string"}},
            "$defs": {"Inner": {"type": "object"}},
            "$ref": "#/$defs/Inner",
        },
    }
    processor = {
        "type": "object",
        "properties": {"steps": {"$ref": "#/$defs/Steps"}},
        "$defs": {"Steps": {"type": "integer"}},
    }
    server, client, calls = _server({
        ("GET", "/api/workflows/config-schema"): (200, json.dumps(schema).encode()),
        ("GET", "/api/processors/sdxl/schema"): (200, json.dumps(processor).encode()),
        ("GET", "/api/workflows/capabilities"): (200, json.dumps({
            "workflow_api_version": 1,
            "native_render": {
                "contract": "native-render/1",
                "shader_raster_policy": {"profile": "shader-raster-policy/1"},
            },
        }).encode()),
    })
    direct = client.get_config_schema("PromptSettings")
    assert direct == schema
    assert "global_" not in json.dumps(direct)
    listed = server.call_tool("get_config_schema", {})
    assert listed["isError"] is False
    assert json.loads(listed["content"][0]["text"]) == schema
    via_tool = server.call_tool("get_config_schema", {"model": "PromptSettings"})
    assert json.loads(via_tool["content"][0]["text"]) == schema
    queried = [url for method, path, url in calls if path == "/api/workflows/config-schema"]
    assert any("model=PromptSettings" in url for url in queried)
    assert any("model=" not in urllib.parse.urlsplit(url).query for url in queried)
    got = server.call_tool("get_processor_schema", {"pipeline_id": "sdxl"})
    assert json.loads(got["content"][0]["text"]) == processor
    caps = server.call_tool("get_capabilities", {})
    body = json.loads(caps["content"][0]["text"])
    assert body["native_render"]["contract"] == "native-render/1"
    assert body["native_render"]["shader_raster_policy"]["profile"] == "shader-raster-policy/1"
    assert client.get_processor_schema("sdxl") == processor


def test_processor_native_404_and_oversize_keep_no_partial_schema() -> None:
    huge = (b'{"' + _MARKER.encode() + b'":true}' + b" " * (256 * 1024))
    server, client, calls = _server({
        ("GET", "/api/processors/missing/schema"): (
            404, b'{"detail":"Processor \'missing\' not found"}',
        ),
        ("GET", "/api/processors/huge/schema"): (200, huge),
        ("GET", "/api/plugins/catalog"): (200, huge),
    })
    missing = server.call_tool("get_processor_schema", {"pipeline_id": "missing"})
    assert missing["isError"] is True
    text = missing["content"][0]["text"]
    payload = json.loads(text)
    assert payload["status_code"] == 404
    assert "not found" in text
    assert all("/validate" not in url and "/unload" not in url for _m, _p, url in calls)
    with pytest.raises(HextileClientError) as oversize:
        client.get_processor_schema("huge")
    assert oversize.value.status_code == 413
    assert str(oversize.value) == "schema_too_large"
    assert _MARKER not in str(oversize.value)
    assert _MARKER not in (oversize.value.body or "")
    catalog = server.call_tool("get_plugin_catalog", {})
    assert catalog["isError"] is True
    catalog_payload = json.loads(catalog["content"][0]["text"])
    assert catalog_payload["status_code"] == 413
    assert "response_too_large" in catalog["content"][0]["text"]
    assert _MARKER not in catalog["content"][0]["text"]


def test_processor_list_and_plugin_catalog_drop_private_locators() -> None:
    catalog = {
        "packages": [{
            "id": "hextile.shader",
            "enabled": False,
            "installed_root": "/mnt/private/plugins/shader",
            "snapshot_digest": "digest-ok",
            "capability_key": "shader",
            "contributions": [{
                "route": "/create/shader",
                "source": "plugins/shader/plugin.json",
                "available": False,
                "reason": "unsupported",
                "animation": {"runtime": "closed", "can_request_sample": False},
            }],
            "diagnostics": [{"path": "\\\\server\\share\\plugin.json", "reason": "unreadable"}],
        }],
        "diagnostics": [{"path": "file:/mnt/private/plugin.json", "reason": "unreadable"}],
    }
    processors = {"processors": [{
        "mode_id": "sdxl",
        "display_name": "SDXL",
        "type": "tiled",
        "description": "/mnt/private/should-drop",
        "fresh_admission": False,
        "weights": "/mnt/private/weights",
    }]}
    server, client, calls = _server({
        ("GET", "/api/processors"): (200, json.dumps(processors).encode()),
        ("GET", "/api/plugins/catalog"): (200, json.dumps(catalog).encode()),
    })
    listed = client.list_processors()
    assert listed == {"processors": [{
        "mode_id": "sdxl",
        "display_name": "SDXL",
        "type": "tiled",
        "fresh_admission": False,
    }]}
    via = json.loads(server.call_tool("list_processors", {})["content"][0]["text"])
    assert via == listed
    got = json.loads(server.call_tool("get_plugin_catalog", {})["content"][0]["text"])
    encoded = json.dumps(got)
    assert "/mnt/private" not in encoded
    assert "installed_root" not in encoded
    assert "server" not in encoded
    assert "file:" not in encoded
    row = got["packages"][0]["contributions"][0]
    assert row["route"] == "/create/shader"
    assert row["source"] == "plugins/shader/plugin.json"
    assert row["available"] is False
    assert row["reason"] == "unsupported"
    assert row["animation"]["runtime"] == "closed"
    assert row["animation"]["can_request_sample"] is False
    assert got["packages"][0]["snapshot_digest"] == "digest-ok"
    assert got["packages"][0]["capability_key"] == "shader"
    assert got["packages"][0]["diagnostics"][0]["reason"] == "unreadable"
    assert got["diagnostics"][0]["reason"] == "unreadable"
    assert [path for _method, path, _url in _native_calls(calls)] == [
        "/api/processors", "/api/processors", "/api/plugins/catalog",
    ]


def test_master_switch_blocks_discovery_before_the_schema_read(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def urlopen(req: Any, timeout: Any = None) -> _Response:
        path = urllib.parse.urlsplit(req.full_url).path
        calls.append(path)
        assert path == "/api/agent/mcp-status"
        return _Response(b'{"enabled": false}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    result = HextileMcpServer(client=Client()).call_tool("get_config_schema", {})
    assert result["isError"] is True
    assert calls == ["/api/agent/mcp-status"]
    assert "disabled" in result["content"][0]["text"].lower()
