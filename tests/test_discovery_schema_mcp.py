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
        target = urllib.parse.urlsplit(req.full_url)
        path = target.path
        method = req.get_method()
        calls.append((method, path, req.full_url))
        headers = {key.lower(): value for key, value in req.header_items()}
        assert headers["x-hextile-agent"] == "mcp"
        if path == "/api/agent/events":
            return _Response(b"{}")
        spec = payloads.get((method, path, target.query))
        if spec is None:
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


def _shader_connection() -> dict[str, Any]:
    ref = {"origin": "user", "shaderId": "aurora"}
    return {"view": "shader", "schema": 1, "mcp_enabled": True,
        "current_surface": {"kind": "shader_workshop", "shader": ref, "draft_state": "clean",
            "studio_surface_id": "ws-test", "project_context_witness": "test-witness",
            "base": {"kind": "saved", "working_revision": 1,
                "document_hash": "sha256:" + "a" * 64, "source_hash": "sha256:" + "b" * 64}},
        "shader_contract": {"revision": 1, "apply_policy": "mounted", "blockers": []},
        "shader_summary": {"name": "Aurora", "metadata_status": "available", "shader": ref,
            "draft_state": "clean", "save_state": "saved", "editable": True, "blockers": []}}


def test_shader_connection_is_one_compact_read_and_preserves_full_default() -> None:
    compact = _shader_connection()
    full = {"models": [{"id": "unrelated"}], "inventory": {"renders": []}, "current_surface": compact["current_surface"]}
    query = "include_nav=0&include_active_tool=0"
    server, _client, calls = _server({
        ("GET", "/api/agent/live-context", query + "&view=shader"): (200, json.dumps(compact).encode()),
        ("GET", "/api/agent/live-context", query): (200, json.dumps(full).encode()),
    })
    result = server.call_tool("get_live_context", {"view": "shader"})
    assert not result.get("isError") and json.loads(result["content"][0]["text"]) == compact
    assert len(_native_calls(calls)) == 1
    assert _native_calls(calls)[0][1] == "/api/agent/live-context"
    assert json.loads(server.call_tool("get_live_context", {})["content"][0]["text"]) == full
    assert _tool("get_live_context")["inputSchema"]["properties"]["view"]["enum"] == ["full", "shader"]


@pytest.mark.parametrize("payload", [
    {"inventory": {}, "models": []},  # old APP silently ignored the new query
    {**_shader_connection(), "shader_summary": {**_shader_connection()["shader_summary"], "editable": "yes"}},
    {**_shader_connection(), "current_surface": {**_shader_connection()["current_surface"], "source": "private GLSL"}},
    {**_shader_connection(), "shader_contract": {**_shader_connection()["shader_contract"], "inventory": []}},
    {**_shader_connection(), "shader_contract": {**_shader_connection()["shader_contract"], "apply_policy": []}},
    {**_shader_connection(), "shader_summary": {**_shader_connection()["shader_summary"], "draft_state": "bogus", "editable": False},
        "current_surface": {**_shader_connection()["current_surface"], "draft_state": "bogus"}},
    {**_shader_connection(), "shader_summary": {**_shader_connection()["shader_summary"], "editable": False,
        "shader": {"origin": "invalid", "shaderId": "aurora"}}, "current_surface": {
            **_shader_connection()["current_surface"], "shader": {"origin": "invalid", "shaderId": "aurora"}}},
])
def test_shader_connection_never_claims_success_for_old_or_invalid_metadata(payload: dict[str, Any]) -> None:
    server, _client, calls = _server({
        ("GET", "/api/agent/live-context"): (200, json.dumps(payload).encode()),
    })
    result = server.call_tool("get_live_context", {"view": "shader"})
    assert result["isError"] is True
    assert json.loads(result["content"][0]["text"])["kind"] == "unsupported"
    assert len(_native_calls(calls)) == 1  # no fallback inventory or source reads


def test_shader_connection_invalid_arguments_do_not_reach_app() -> None:
    server, _client, calls = _server({})
    for args in ({"view": "other"}, {"view": True}, {"view": "shader", "include_source": True},
                 {"view": "shader", "include_nav": "false"}):
        assert server.call_tool("get_live_context", args)["isError"] is True
    assert _native_calls(calls) == []


def test_shader_connection_disconnected_app_is_not_a_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Client()
    calls = []
    def unavailable(method: str, path: str, **_kwargs: Any) -> Any:
        calls.append((method, path))
        if path == "/api/agent/events":
            return {}
        raise HextileClientError("APP unavailable", kind="network")
    monkeypatch.setattr(client, "request_json", unavailable)
    result = HextileMcpServer(client=client).call_tool("get_live_context", {"view": "shader"})
    assert result["isError"] is True
    assert calls == [("GET", "/api/agent/mcp-status")]


def test_shader_connection_keeps_external_mcp_enabled_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Client()
    calls = []
    def native(method: str, path: str, **_kwargs: Any) -> Any:
        calls.append((method, path))
        if path == "/api/agent/events":
            return {}
        if path == "/api/agent/mcp-status":
            return {"enabled": True}
        assert path == "/api/agent/live-context"
        return _shader_connection()
    monkeypatch.setattr(client, "request_json", native)
    result = HextileMcpServer(client=client).call_tool("get_live_context", {"view": "shader"})
    assert result["isError"] is False
    assert [call for call in calls if call[1] != "/api/agent/events"] == [
        ("GET", "/api/agent/mcp-status"), ("GET", "/api/agent/live-context")]


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


def _ui_schema(**overrides: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "mode_id": "sdxl",
        "display_name": "SDXL",
        "type": "tiled",
        "description": "tiled diffusion",
        "icon": "MagicWand",
        "product_surface": "dropdown",
        "capabilities": {
            "supports_lora": True,
            "supports_controlnet": True,
            "supports_sequence": True,
            "requires_template": True,
            "supports_post_process": True,
            "min_resolution": [512, 512],
            "max_resolution": [2048, 1024],
        },
        "tabs": [{
            "id": "diffusion",
            "label": "Diffusion",
            "icon": "Sliders",
            "fields": [{
                "id": "steps",
                "type": "slider",
                "label": "Steps",
                "default": 20,
                "required": True,
                "condition": {"field": "advanced", "value": True},
            }],
        }],
    }
    schema.update(overrides)
    return schema


def test_config_schema_query_and_processor_schema_pass_through() -> None:
    index = {"models": ["HextileConfig", "PromptSettings"], "revision": 1}
    page = {
        "model": "PromptSettings",
        "schema": {
            "type": "object",
            "title": "PromptSettings",
            "properties": {"global": {"type": "string", "title": "Global"}},
            "required": ["global"],
            "$defs": {"Inner": {"type": "object"}},
            "$ref": "#/$defs/Inner",
        },
    }
    processor = _ui_schema()
    server, client, calls = _server({
        ("GET", "/api/workflows/config-schema", ""): (200, json.dumps(index).encode()),
        ("GET", "/api/workflows/config-schema", "model=PromptSettings"): (200, json.dumps(page).encode()),
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
    assert direct == page
    assert direct["schema"]["properties"]["global"]["title"] == "Global"
    assert "global_" not in direct["schema"]["properties"]
    assert "global_" not in direct["schema"].get("required", [])
    listed = server.call_tool("get_config_schema", {})
    assert listed["isError"] is False
    assert json.loads(listed["content"][0]["text"]) == index
    via_tool = server.call_tool("get_config_schema", {"model": "PromptSettings"})
    assert json.loads(via_tool["content"][0]["text"]) == page
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
            "label": "Installed in /home/phong/private/plugins",
            "summary": "Installed at C:\\Users\\phong\\private",
            "site": "Docs https://example.com",
            "guide": "http://example.com/docs/guide",
            "portal": "HTTPS://example.com/api/plugins",
            "blurb": "Docs https://example.com Open /create/shader plugins/shader/plugin.json",
            "alert": "Docs https://example.com see /home/phong/private/plugins",
            "alert_win": "Docs https://example.com see C:\\Users\\phong\\private",
            "alert_unc": "Docs https://example.com \\\\server\\share",
            "alert_file": "Docs https://example.com file:///home/phong/private",
            "docs": "/api/plugins/catalog",
            "note": "Open /create/shader or /api/plugins/catalog",
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
            "diagnostics": [
                {"path": "\\\\server\\share\\plugin.json", "reason": "unreadable"},
                {"reason": "Installed in /home/phong/private/plugins"},
            ],
        }],
        "diagnostics": [{"path": "file:/mnt/private/plugin.json", "reason": "unreadable"}],
    }
    processors = {"processors": [{
        "mode_id": "sdxl",
        "display_name": "Docs https://example.com",
        "type": "tiled",
        "description": "Installed in /home/phong/private/plugins",
        "fresh_admission": False,
        "fresh_admission_reason": "see C:\\Users\\phong\\private",
        "weights": "/mnt/private/weights",
    }]}
    server, client, calls = _server({
        ("GET", "/api/processors"): (200, json.dumps(processors).encode()),
        ("GET", "/api/plugins/catalog"): (200, json.dumps(catalog).encode()),
    })
    listed = client.list_processors()
    assert listed == {"processors": [{
        "mode_id": "sdxl",
        "display_name": "Docs https://example.com",
        "type": "tiled",
        "fresh_admission": False,
    }]}
    via = json.loads(server.call_tool("list_processors", {})["content"][0]["text"])
    assert via == listed
    got = json.loads(server.call_tool("get_plugin_catalog", {})["content"][0]["text"])
    encoded = json.dumps(got)
    assert "/mnt/private" not in encoded
    assert "/home/phong/private" not in encoded
    assert "C:\\Users" not in encoded and "C:\\\\Users" not in encoded
    assert "installed_root" not in encoded
    assert "server" not in encoded
    assert "file:" not in encoded
    assert "label" not in got["packages"][0]
    assert "summary" not in got["packages"][0]
    assert "alert" not in got["packages"][0]
    assert "alert_win" not in got["packages"][0]
    assert "alert_unc" not in got["packages"][0]
    assert "alert_file" not in got["packages"][0]
    assert got["packages"][0]["site"] == "Docs https://example.com"
    assert got["packages"][0]["guide"] == "http://example.com/docs/guide"
    assert got["packages"][0]["portal"] == "HTTPS://example.com/api/plugins"
    assert got["packages"][0]["blurb"] == (
        "Docs https://example.com Open /create/shader plugins/shader/plugin.json"
    )
    assert got["packages"][0]["docs"] == "/api/plugins/catalog"
    assert got["packages"][0]["note"] == "Open /create/shader or /api/plugins/catalog"
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
    assert all("/home/phong" not in json.dumps(item) for item in got["packages"][0]["diagnostics"])
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


def _assert_closed_failure(result: dict[str, Any], secret: str) -> None:
    assert result["isError"] is True
    text = result["content"][0]["text"]
    payload = json.loads(text)
    assert payload["status_code"] == 422
    assert payload["error"] == "Unexpected arguments"
    assert secret not in text


def test_discovery_rejects_private_and_non_object_arguments_before_native_read() -> None:
    secret = "sk-secretvalue123"
    server, _client, calls = _server({
        ("GET", "/api/workflows"): (200, b'[{"id":"quick-scout"}]'),
        ("GET", "/api/workflows/config-schema", ""): (200, b'{"models":["PromptSettings"]}'),
        ("GET", "/api/processors"): (200, b'{"processors":[]}'),
        ("GET", "/api/plugins/catalog"): (200, b'{"packages":[]}'),
    })
    for name in _DISCOVERY:
        for arguments in ([], None, {"token": secret}, {"actor": secret, "operation_id": secret}):
            _assert_closed_failure(server.call_tool(name, arguments), secret)
            for wire in (arguments,):
                response = server.handle_rpc({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": wire},
                })
                _assert_closed_failure(response["result"], secret)
    _assert_closed_failure(
        server.call_tool("get_config_schema", {"model": "PromptSettings", "token": secret}),
        secret,
    )
    _assert_closed_failure(
        server.handle_rpc({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_processor_schema", "arguments": {"pipeline_id": "sdxl", "token": secret}},
        })["result"],
        secret,
    )
    assert _native_calls(calls) == []

    omitted = server.handle_rpc({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "get_plugin_catalog"},
    })
    assert omitted["result"]["isError"] is False
    empty = server.handle_rpc({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "list_processors", "arguments": {}},
    })
    assert empty["result"]["isError"] is False
    index = server.call_tool("get_config_schema", {})
    assert index["isError"] is False
    assert json.loads(index["content"][0]["text"]) == {"models": ["PromptSettings"]}
    other = server.call_tool("list_workflows", {"token": secret, "actor": secret})
    assert other["isError"] is False
    assert secret not in other["content"][0]["text"]
    coerced = server.call_tool("list_workflows", [])
    assert coerced["isError"] is False
    assert [path for _method, path, _url in _native_calls(calls)] == [
        "/api/plugins/catalog",
        "/api/processors",
        "/api/workflows/config-schema",
        "/api/workflows",
        "/api/workflows",
    ]


def test_malformed_discovery_success_is_not_a_schema() -> None:
    secret = "/home/phong/private/plugins"
    page = {
        "model": "PromptSettings",
        "schema": {"type": "object", "properties": {"global": {"$ref": "#/$defs/Inner"}}},
    }
    ui = _ui_schema()
    cases: list[tuple[str, dict[str, Any], str, Any]] = [
        ("get_config_schema", {}, "/api/workflows/config-schema", None),
        ("get_config_schema", {}, "/api/workflows/config-schema", []),
        ("get_config_schema", {}, "/api/workflows/config-schema", {"error": secret}),
        ("get_config_schema", {}, "/api/workflows/config-schema", {"models": ["9bad"]}),
        ("get_config_schema", {"model": "PromptSettings"}, "/api/workflows/config-schema", {"error": secret}),
        ("get_config_schema", {"model": "PromptSettings"}, "/api/workflows/config-schema", page | {"model": "OtherModel"}),
        ("get_config_schema", {"model": "PromptSettings"}, "/api/workflows/config-schema",
         {"model": "PromptSettings", "schema": {"error": secret}}),
        ("get_processor_schema", {"pipeline_id": "sdxl"}, "/api/processors/sdxl/schema", None),
        ("get_processor_schema", {"pipeline_id": "sdxl"}, "/api/processors/sdxl/schema", []),
        ("get_processor_schema", {"pipeline_id": "sdxl"}, "/api/processors/sdxl/schema", {"error": secret}),
        ("get_processor_schema", {"pipeline_id": "sdxl"}, "/api/processors/sdxl/schema", _ui_schema(mode_id="other")),
        ("get_processor_schema", {"pipeline_id": "sdxl"}, "/api/processors/sdxl/schema",
         _ui_schema(tabs=[{"id": "diffusion", "fields": [{"id": "steps", "condition": secret}]}])),
        ("list_processors", {}, "/api/processors", None),
        ("list_processors", {}, "/api/processors", []),
        ("list_processors", {}, "/api/processors", {"error": secret}),
        ("list_processors", {}, "/api/processors", {"processors": [{"mode_id": "sdxl"}], "error": secret}),
        ("get_plugin_catalog", {}, "/api/plugins/catalog", None),
        ("get_plugin_catalog", {}, "/api/plugins/catalog", []),
        ("get_plugin_catalog", {}, "/api/plugins/catalog", {"error": secret}),
        ("get_plugin_catalog", {}, "/api/plugins/catalog", {"packages": [secret]}),
        ("get_plugin_catalog", {}, "/api/plugins/catalog", {"packages": [], "error": secret}),
    ]
    for name, args, path, body in cases:
        server, client, calls = _server({("GET", path): (200, json.dumps(body).encode())})
        result = server.call_tool(name, args)
        assert result["isError"] is True, name
        text = result["content"][0]["text"]
        assert json.loads(text)["status_code"] == 502
        assert secret not in text
        assert [item[1] for item in _native_calls(calls)] == [path]
        with pytest.raises(HextileClientError) as exc:
            if name == "get_config_schema":
                client.get_config_schema(args.get("model"))
            elif name == "get_processor_schema":
                client.get_processor_schema(args["pipeline_id"])
            elif name == "list_processors":
                client.list_processors()
            else:
                client.get_plugin_catalog()
        assert exc.value.status_code == 502
        assert secret not in str(exc.value)
        assert secret not in (exc.value.body or "")
    positive, direct, _calls = _server({
        ("GET", "/api/workflows/config-schema", "model=PromptSettings"): (200, json.dumps(page).encode()),
        ("GET", "/api/processors/sdxl/schema"): (200, json.dumps(ui).encode()),
    })
    assert direct.get_config_schema("PromptSettings") == page
    assert positive.call_tool("get_processor_schema", {"pipeline_id": "sdxl"})["isError"] is False
    assert json.loads(positive.call_tool("get_processor_schema", {"pipeline_id": "sdxl"})["content"][0]["text"]) == ui
