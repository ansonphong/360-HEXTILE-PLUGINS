"""search_docs and read_doc: closed read-only tools over the public docs routes.

Fixture HTTP only. Bad arguments are rejected before any docs request.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from hextile_client import Client, HextileClientError  # noqa: E402
from hextile_mcp import TOOLS, HextileMcpServer  # noqa: E402


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


def _text(result: dict[str, Any]) -> str:
    return result["content"][0]["text"]


def _payload(result: dict[str, Any]) -> Any:
    return json.loads(_text(result))


def _listed() -> dict[str, dict[str, Any]]:
    server = HextileMcpServer(client=Client(opener=lambda *_a, **_k: None))
    response = server.handle_rpc({
        "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
    })
    return {row["name"]: row for row in response["result"]["tools"]}


def test_docs_tools_are_closed_read_only() -> None:
    listed = _listed()
    defined = {row["name"]: row for row in TOOLS}
    for name, required in (("search_docs", ["query"]), ("read_doc", ["path"])):
        for source in (listed, defined):
            tool = source[name]
            schema = tool["inputSchema"]
            assert schema["type"] == "object"
            assert schema["additionalProperties"] is False
            assert schema["required"] == required
            assert tool["annotations"] == {"readOnlyHint": True, "destructiveHint": False}
        assert name in defined and defined[name] is listed[name]
    search = listed["search_docs"]["inputSchema"]
    read = listed["read_doc"]["inputSchema"]
    assert set(search["properties"]) == {"query", "limit"}
    assert search["properties"]["query"]["minLength"] == 1
    assert search["properties"]["query"]["maxLength"] == 200
    assert search["properties"]["limit"] == {"type": "integer", "minimum": 1, "maximum": 10}
    assert set(read["properties"]) == {"path", "section"}
    assert read["properties"]["path"]["minLength"] == 1
    assert read["properties"]["path"]["maxLength"] == 200
    assert read["properties"]["section"]["maxLength"] == 200
    jsonschema.validate({"query": "shader"}, search)
    jsonschema.validate({"query": "shader", "limit": 1}, search)
    jsonschema.validate({"path": "create/shader"}, read)
    jsonschema.validate({"path": "create/shader", "section": "workshop"}, read)
    for schema, args in (
        (search, {}),
        (search, {"query": ""}),
        (search, {"query": "x" * 201}),
        (search, {"query": "shader", "limit": True}),
        (search, {"query": "shader", "limit": 0}),
        (search, {"query": "shader", "limit": 11}),
        (search, {"query": "shader", "extra": 1}),
        (read, {}),
        (read, {"path": ""}),
        (read, {"path": "x" * 201}),
        (read, {"path": "create/shader", "section": "x" * 201}),
        (read, {"path": "create/shader", "url": "https://example"}),
    ):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(args, schema)


@pytest.mark.parametrize("name,arguments", [
    ("search_docs", {}),
    ("search_docs", {"query": ""}),
    ("search_docs", {"query": "x" * 201}),
    ("search_docs", {"query": 1}),
    ("search_docs", {"query": "shader", "limit": True}),
    ("search_docs", {"query": "shader", "limit": False}),
    ("search_docs", {"query": "shader", "limit": 0}),
    ("search_docs", {"query": "shader", "limit": 11}),
    ("search_docs", {"query": "shader", "limit": "5"}),
    ("search_docs", {"query": "shader", "limit": 1.5}),
    ("search_docs", {"query": "shader", "url": "https://360hextile.com"}),
    ("search_docs", None),
    ("read_doc", {}),
    ("read_doc", {"path": ""}),
    ("read_doc", {"path": "x" * 201}),
    ("read_doc", {"path": 1}),
    ("read_doc", {"path": "create/shader", "section": 1}),
    ("read_doc", {"path": "create/shader", "section": "x" * 201}),
    ("read_doc", {"path": "create/shader", "anchor": "top"}),
    ("read_doc", None),
])
def test_docs_argument_validation_rejects_before_native_call(name: str, arguments: Any) -> None:
    server, _client, calls = _server({})
    result = server.call_tool(name, arguments)
    assert result["isError"] is True
    payload = _payload(result)
    assert payload["kind"] == "other"
    assert payload["status_code"] == 422
    assert _native(calls) == []


def test_docs_client_builds_search_and_read_queries() -> None:
    search_body = {"version": "docs-1", "results": []}
    read_body = {
        "version": "docs-1", "path": "create/shader", "title": "Shader",
        "url": "https://360hextile.com/docs/create/shader",
        "markdown": "Workshop", "truncated": False, "outline": [],
    }
    server, client, calls = _server({
        ("GET", "/api/docs/search", "q=shader+agent&limit=3"): (200, json.dumps(search_body).encode()),
        ("GET", "/api/docs/search", "q=shader"): (200, json.dumps(search_body).encode()),
        ("GET", "/api/docs/read", "path=create%2Fshader&section=workshop"): (200, json.dumps(read_body).encode()),
        ("GET", "/api/docs/read", "path=create%2Fshader"): (200, json.dumps(read_body).encode()),
    })
    assert client.search_docs("shader agent", 3) == search_body
    assert _payload(server.call_tool("search_docs", {"query": "shader"})) == search_body
    assert client.read_doc("create/shader", "workshop") == read_body
    assert _payload(server.call_tool("read_doc", {"path": "create/shader"})) == read_body
    native = _native(calls)
    assert [(item["method"], item["path"], item["query"]) for item in native] == [
        ("GET", "/api/docs/search", "q=shader+agent&limit=3"),
        ("GET", "/api/docs/search", "q=shader"),
        ("GET", "/api/docs/read", "path=create%2Fshader&section=workshop"),
        ("GET", "/api/docs/read", "path=create%2Fshader"),
    ]


def test_docs_http_errors_use_public_status_mapping() -> None:
    server, client, calls = _server({
        ("GET", "/api/docs/read", "path=missing"): (
            404, b'{"detail":{"code":"docs_not_found","message":"Unknown documentation path"}}',
        ),
        ("GET", "/api/docs/search", "q=..."): (
            422, b'{"detail":{"code":"invalid_query","message":"query is empty"}}',
        ),
        ("GET", "/api/docs/search", "q=shader"): (
            503, b'{"detail":{"code":"docs_snapshot_unavailable","message":"snapshot missing"}}',
        ),
        ("GET", "/api/docs/read", "path=create%2Fshader"): "down",
    })
    with pytest.raises(HextileClientError) as missing:
        client.read_doc("missing")
    assert str(missing.value) == "docs_not_found"
    assert missing.value.status_code == 404
    assert missing.value.kind == "http"
    with pytest.raises(HextileClientError) as invalid:
        client.search_docs("...")
    assert str(invalid.value) == "invalid_query"
    assert invalid.value.status_code == 422
    with pytest.raises(HextileClientError) as unavailable:
        client.search_docs("shader")
    assert str(unavailable.value) == "docs_snapshot_unavailable"
    assert unavailable.value.status_code == 503
    with pytest.raises(HextileClientError) as down:
        client.read_doc("create/shader")
    assert down.value.kind == "app_down"
    via_tool = server.call_tool("read_doc", {"path": "missing"})
    assert via_tool["isError"] is True
    assert _payload(via_tool)["error"] == "docs_not_found"
    assert _payload(via_tool)["status_code"] == 404
    assert [item["path"] for item in _native(calls)] == [
        "/api/docs/read",
        "/api/docs/search",
        "/api/docs/search",
        "/api/docs/read",
        "/api/docs/read",
    ]
