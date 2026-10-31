"""Fake-opener HTTP tests for sequence Client methods and MCP tools/list.

No live APP, no GPU, no network.
"""

from __future__ import annotations

import io
import asyncio
import http.client
import importlib.util
import json
import jsonschema
import sys
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = ROOT / "mcp"
sys.path.insert(0, str(MCP_DIR))

from hextile_client import (  # noqa: E402
    LONG_OPERATION_TIMEOUT_S,
    Client,
    HextileClientError,
)
from hextile_mcp import HextileMcpServer  # noqa: E402

SEQUENCE_TOOLS = (
    "extract_sequence_video",
    "create_sequence",
    "start_sequence",
    "get_sequence",
    "list_sequences",
    "list_sequence_frames",
    "rename_sequence",
    "set_sequence_lifecycle",
    "set_sequence_tags",
    "get_sequence_tags",
    "stop_sequence",
)

# Full HextileConfig-shaped object (not a pipeline-only stub). Nested keys
# prove create_sequence emits the complete object, not a subset.
FULL_CONFIG: dict[str, Any] = {
    "pipeline": "realesrgan",
    "hextile": {
        "template": "Dodecahedron",
        "render_tiles": "all",
        "tile_input_width": 512,
        "tile_output_width": 512,
    },
    "diffusion": {
        "model": "realesrgan-x4plus",
        "seed": -1,
        "strength": 0.45,
        "guidance_scale": 7.5,
        "num_inference_steps": 20,
    },
    "input": {
        "format": "equirectangular",
        "mode": "sequence",
        "source": "file",
        "path": "/frames/stills",
        "width": 2048,
        "height": 1024,
    },
    "upscale": {
        "model": "realesrgan-x4plus",
        "scale_factor": 4,
        "tile_size": 0,
        "template": "",
    },
    "output": {
        "format": "equirectangular",
        "width": 8192,
        "height": 4096,
        "file_format": "PNG",
    },
    "prompt": {
        "global": "identity-check",
        "negative": "blurry",
        "directional": {"enabled": False},
    },
    "post_process": {"enabled": False, "hooks": []},
    "sequence": {"enabled": False},
}

BASE = "http://hextile.test"


class _Resp:
    status = 200

    def __init__(self, payload: Any = None) -> None:
        self._payload = {} if payload is None else payload

    def read(self, size: int = -1) -> bytes:
        data = json.dumps(self._payload).encode()
        return data if size < 0 else data[:size]

    def getcode(self) -> int:
        return 200

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _recorder(seen: dict[str, Any], payload: Any = None):
    def opener(req, timeout=None):  # noqa: ANN001
        seen["url"] = req.full_url
        seen["data"] = req.data
        seen["timeout"] = timeout
        seen["method"] = req.get_method()
        return _Resp(payload)

    return opener


def _client(seen: dict[str, Any], payload: Any = None) -> Client:
    return Client(base_url=BASE, opener=_recorder(seen, payload))


def _http_error_opener(code: int, msg: str):
    def opener(req, timeout=None):  # noqa: ANN001
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=code,
            msg=msg,
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(json.dumps({"detail": msg}).encode()),
        )

    return opener


def test_extract_sequence_video_posts_path_and_generate_timeout() -> None:
    seen: dict[str, Any] = {}
    _client(seen).extract_sequence_video("/clips/scene.mp4")
    assert seen["method"] == "POST"
    assert seen["url"] == f"{BASE}/api/sequences/extract-video"
    assert json.loads(seen["data"]) == {"video_path": "/clips/scene.mp4"}
    assert seen["timeout"] == LONG_OPERATION_TIMEOUT_S
    assert LONG_OPERATION_TIMEOUT_S == 300.0


def test_create_sequence_posts_full_config_lossless() -> None:
    seen: dict[str, Any] = {}
    _client(seen).create_sequence("/frames/stills", FULL_CONFIG, name="upres-folder")
    assert seen["method"] == "POST"
    assert seen["url"] == f"{BASE}/api/sequences/create"
    body = json.loads(seen["data"])
    assert body["folder_path"] == "/frames/stills"
    assert body["name"] == "upres-folder"
    assert body["config"] == FULL_CONFIG
    assert set(body["config"]) == set(FULL_CONFIG)
    assert body["config"]["hextile"]["template"] == "Dodecahedron"
    assert body["config"]["diffusion"]["model"] == "realesrgan-x4plus"
    assert body["config"]["input"] == FULL_CONFIG["input"]
    assert body["config"]["upscale"] == FULL_CONFIG["upscale"]


def test_start_sequence_quotes_id() -> None:
    seen: dict[str, Any] = {}
    sequence_id = "seq_a/b"
    _client(seen).start_sequence(sequence_id)
    quoted = urllib.parse.quote(sequence_id, safe="")
    assert quoted == "seq_a%2Fb"
    assert seen["method"] == "POST"
    assert seen["url"] == f"{BASE}/api/sequences/{quoted}/start"
    assert "/seq_a/b/" not in seen["url"]


def test_stop_sequence_quotes_id() -> None:
    seen: dict[str, Any] = {}
    sequence_id = "seq id"
    _client(seen).stop_sequence(sequence_id)
    quoted = urllib.parse.quote(sequence_id, safe="")
    assert quoted == "seq%20id"
    assert seen["method"] == "POST"
    assert seen["url"] == f"{BASE}/api/sequences/{quoted}/stop"


def test_get_sequence_gets_quoted_id() -> None:
    seen: dict[str, Any] = {}
    sequence_id = "seq_a/b"
    _client(seen).get_sequence(sequence_id)
    quoted = urllib.parse.quote(sequence_id, safe="")
    assert seen["method"] == "GET"
    assert seen["url"] == f"{BASE}/api/sequences/{quoted}"
    assert seen["data"] is None


def test_list_sequences_default_lifecycle_active() -> None:
    seen: dict[str, Any] = {}
    _client(seen).list_sequences()
    assert seen["method"] == "GET"
    assert seen["url"] == f"{BASE}/api/sequences/?lifecycle_status=active"


def test_list_sequences_passes_lifecycle_status() -> None:
    seen: dict[str, Any] = {}
    _client(seen).list_sequences("archived")
    assert seen["method"] == "GET"
    assert seen["url"] == f"{BASE}/api/sequences/?lifecycle_status=archived"


def test_extract_sequence_video_402_is_hextile_client_error() -> None:
    client = Client(
        base_url=BASE,
        opener=_http_error_opener(402, "Payment Required"),
    )
    with pytest.raises(HextileClientError) as ei:
        client.extract_sequence_video("/v.mp4")
    assert ei.value.status_code == 402


def test_create_sequence_400_is_hextile_client_error() -> None:
    client = Client(
        base_url=BASE,
        opener=_http_error_opener(400, "Bad Request"),
    )
    with pytest.raises(HextileClientError) as ei:
        client.create_sequence("/frames/stills", FULL_CONFIG)
    assert ei.value.status_code == 400


def test_mcp_tools_list_includes_sequence_names() -> None:
    server = HextileMcpServer(client=Client(opener=lambda *a, **k: None))
    resp = server.handle_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    assert resp is not None
    names = [t["name"] for t in resp["result"]["tools"]]
    for name in SEQUENCE_TOOLS:
        assert name in names


@pytest.mark.parametrize(('tool', 'args', 'method', 'suffix', 'body'), [
    ('rename_sequence', {'name': '  A new name  '}, 'PATCH', 'name', {'name': 'A new name'}),
    ('set_sequence_lifecycle', {'status': 'archived'}, 'PATCH', 'status', {'status': 'archived'}),
    ('set_sequence_tags', {'tag_ids': ['tag_a', 'tag_b']}, 'PUT', 'tags', ['tag_a', 'tag_b']),
])
def test_sequence_metadata_tools_use_native_operations(tool, args, method, suffix, body):
    seen = {}
    recorder = _recorder(seen, {'sequence_id': 'seq/a b', 'name': 'A new name'})
    def opener(request, timeout=None):
        return _Resp() if '/api/agent/events' in request.full_url else recorder(request, timeout)
    server = HextileMcpServer(client=Client(base_url=BASE, opener=opener))
    result = server.call_tool(tool, {'sequence_id': 'seq/a b', **args})
    assert not result.get('isError')
    assert seen['method'] == method
    assert seen['url'].endswith(f'/api/sequences/seq%2Fa%20b/{suffix}')
    assert json.loads(seen['data']) == body
    listed = server.handle_rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
    definition = next(t for t in listed['result']['tools'] if t['name'] == tool)
    assert definition['annotations']['readOnlyHint'] is False
    jsonschema.validate({'sequence_id': 'seq/a b', **args}, definition['inputSchema'])


@pytest.mark.parametrize(('tool', 'args'), [
    ('rename_sequence', {'name': '   '}),
    ('rename_sequence', {'name': 'x' * 121}),
    ('set_sequence_lifecycle', {'status': 'deleted'}),
    ('set_sequence_tags', {'tag_ids': 'tag_a'}),
])
def test_sequence_metadata_tools_reject_invalid_values_without_http(tool, args):
    seen = {}
    def opener(request, timeout=None):
        if '/api/agent/events' not in request.full_url:
            seen['url'] = request.full_url
        return _Resp()
    result = HextileMcpServer(client=Client(base_url=BASE, opener=opener)).call_tool(tool, {'sequence_id': 'seq_test', **args})
    assert result.get('isError') and not seen


def test_sequence_tag_read_recovers_selected_ids_without_mutation():
    seen = {}
    assert _client(seen, {'tags': [{'tag_id': 'tag_a'}]}).get_sequence_tags('seq/a')['tags'][0]['tag_id'] == 'tag_a'
    assert seen['method'] == 'GET' and seen['url'].endswith('/api/sequences/seq%2Fa/tags')


def test_shader_render_export_mcp_tool_chain() -> None:
    server = HextileMcpServer(client=Client(opener=lambda *a, **k: None))
    listed = server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert {"preflight_shader_sequence", "render_shader_sequence", "get_shader_sequence"} <= tools.keys()
    assert {"preflight_shader_sequence_export", "export_shader_sequence", "control_shader_sequence"} <= tools.keys()
    body = {"shader_ref": {"origin": "project", "id": "aurora"},
            "project_context_witness": "project-witness", "working_revision": 2,
            "document_hash": "sha256:" + "a" * 64, "source_hash": "sha256:" + "b" * 64,
            "idempotency_key": "native-001", "name": "Aurora", "frame_rate": {"num": 24, "den": 1},
            "frame_count": 48, "start_time": {"num": "0", "den": "1"},
            "end_time": {"num": "2", "den": "1"}, "width": 2048, "height": 1024,
            "seed": 7, "output": {"projection": "equirectangular", "pan": 0, "tilt": 0, "roll": 0},
            "publication_mode": "deferred"}
    for name in ("preflight_shader_sequence", "render_shader_sequence"):
        schema = tools[name]["inputSchema"]
        jsonschema.validate(body, schema)
        assert schema["additionalProperties"] is False
        assert tools[name]["annotations"]["readOnlyHint"] is (name == "preflight_shader_sequence")
        for bad in ({**body, "folder_export": {"destination_folder": "C:\\private"}},
                    {**body, "publication_mode": "automatic"},
                    {**body, "seed": float("inf")}):
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(bad, schema)
    assert tools["get_shader_sequence"]["annotations"]["readOnlyHint"] is True
    assert tools["preflight_shader_sequence_export"]["annotations"]["readOnlyHint"] is True
    assert tools["export_shader_sequence"]["annotations"]["readOnlyHint"] is False
    assert tools["control_shader_sequence"]["annotations"]["readOnlyHint"] is False
    with pytest.raises(HextileClientError):
        Client().preflight_shader_sequence({**body, "frame_count": 49})
    dome = {**body, "width": 2048, "height": 2048,
            "output": {"projection": "fulldome_angular", "diameter": 2048,
                       "fov_deg": 360, "pan": 0, "tilt": 0, "roll": 0}}
    jsonschema.validate(dome, tools["render_shader_sequence"]["inputSchema"])
    for bad in ({**dome, "output": {**dome["output"], "fov_deg": 361}},
                {**body, "start_time": {"num": "1", "den": "2"}}):
        with pytest.raises(HextileClientError):
            Client().render_shader_sequence(bad)
    guide = (ROOT / "skills" / "360-hextile" / "references" / "recipes.md").read_text(encoding="utf-8")
    import re
    example = json.loads(re.search(r"## Saved Shader native sequence.*?```json\n(.*?)\n```", guide, re.S).group(1))
    jsonschema.validate(example, tools["render_shader_sequence"]["inputSchema"])
    sys.path.insert(0, str(ROOT.parent / "360-HEXTILE-APP"))
    from backend.api.routes.shaders_pkg.sequences import SequenceRequest
    assert SequenceRequest.model_validate(example).publication_mode == "deferred"

    seen: list[Any] = []
    sid = "seq_" + "a" * 32
    digest = "sha256:" + "c" * 64
    attempt = "attempt_" + "c" * 32
    run_id = "d" * 32
    folder = {"sequence_id": sid, "destination_folder": "C:\\Chosen\\Frames", "format": "PNG"}
    jsonschema.validate(folder, tools["preflight_shader_sequence_export"]["inputSchema"])
    jsonschema.validate({**folder, "transaction_fingerprint": digest},
                        tools["export_shader_sequence"]["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**folder, "format": "JPG"},
                            tools["preflight_shader_sequence_export"]["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**folder, "quality_if_jpg": 90},
                            tools["preflight_shader_sequence_export"]["inputSchema"])
    for invalid in ({**folder, "format": "JPG"}, {**folder, "quality_if_jpg": 80},
                    {**folder, "format": "GIF"}):
        with pytest.raises(HextileClientError):
            Client().preflight_shader_sequence_export(invalid)
    for action in ("stop", "resume", "cancel_export", "retry_export"):
        args = {"sequence_id": sid, "action": action}
        if action == "stop":
            args["run_id"] = run_id
        if action.endswith("export"):
            args["attempt_id"] = attempt
        jsonschema.validate(args, tools["control_shader_sequence"]["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"sequence_id": sid, "action": "retry_export"},
                            tools["control_shader_sequence"]["inputSchema"])
    with pytest.raises(HextileClientError):
        Client().control_shader_sequence({"sequence_id": sid, "action": "retry_export"})
    class Response:
        status = 200
        def __init__(self, payload: Any) -> None:
            self.payload = payload
        def read(self) -> bytes:
            return json.dumps(self.payload).encode()
        def __enter__(self):
            return self
        def __exit__(self, *_exc: object) -> None:
            return None
    def opener(req: Any, timeout=None):
        seen.append(req)
        if req.full_url.endswith("/export/preflight"):
            return Response({"sequence_id": sid, "attempt_id": attempt,
                             "transaction_fingerprint": digest, "status": "ready",
                             "destination_folder": "C:\\private\\frames"})
        if req.full_url.endswith("/preflight"):
            return Response({"sequence_id": sid, "status": "ready", "request_hash": digest,
                             "private_path": "C:\\secret\\frames"})
        if req.full_url.endswith("/export"):
            return Response({"sequence_id": sid, "attempt_id": attempt,
                             "transaction_fingerprint": digest, "status": "queued",
                             "destination_folder": "C:\\private\\frames"})
        if req.full_url.endswith(("/stop", "/resume", "/export/cancel", "/export/retry")):
            return Response({"sequence_id": sid, "status": "queued", "path": "C:\\private",
                             "folder_export": {"attempt_id": attempt, "status": "queued"}})
        if req.get_method() == "POST":
            return Response({"sequence_id": sid, "status": "queued", "request_hash": digest,
                             "recipe_hash": digest})
        return Response({"sequence_id": sid, "status": "completed", "request_hash": digest,
                         "frames_completed": 48, "frame_count": 48,
                         "shader_source": {"source": "secret formula", "path": "C:\\secret"},
                         "folder_export": {"destination_folder": "C:\\secret", "status": "completed",
                                           "frames_completed": 48},
                         "error": "C:\\secret", "publication_attempts": [{"attempt_id": "attempt_" + "b" * 32,
                             "status": "completed", "destination_folder": "C:\\secret"}]})
    transport = Client(base_url=BASE, opener=opener)
    assert transport.preflight_shader_sequence(body) == {"sequence_id": sid, "status": "ready", "request_hash": digest}
    assert transport.render_shader_sequence(body)["request_hash"] == digest
    status_result = transport.get_shader_sequence(sid)
    assert status_result["frames_completed"] == 48
    assert status_result["folder_export"] == {"status": "completed", "frames_completed": 48}
    assert "C:\\secret" not in json.dumps(status_result) and "formula" not in json.dumps(status_result)
    assert [req.get_method() for req in seen] == ["POST", "POST", "GET"]
    assert [req.full_url for req in seen] == [f"{BASE}/api/shaders/sequences/preflight",
                                              f"{BASE}/api/shaders/sequences",
                                              f"{BASE}/api/shaders/sequences/{sid}"]
    assert all(req.get_header("X-hextile-project-witness") == "project-witness" for req in seen[:2])
    assert all(json.loads(req.data) == body for req in seen[:2])
    assert transport.preflight_shader_sequence_export(folder) == {
        "sequence_id": sid, "attempt_id": attempt, "transaction_fingerprint": digest, "status": "ready"}
    assert transport.export_shader_sequence({**folder, "transaction_fingerprint": digest})["status"] == "queued"
    assert transport.control_shader_sequence({"sequence_id": sid, "action": "cancel_export",
                                              "attempt_id": attempt})["attempt_id"] == attempt
    assert [req.full_url.rsplit("/api", 1)[-1] for req in seen[-3:]] == [
        f"/shaders/sequences/{sid}/export/preflight", f"/shaders/sequences/{sid}/export",
        f"/shaders/sequences/{sid}/export/cancel"]
    assert json.loads(seen[-1].data) == {"attempt_id": attempt}
    for action, suffix in (("stop", "/stop"), ("resume", "/resume"),
                           ("retry_export", "/export/retry")):
        arguments = {"sequence_id": sid, "action": action}
        if action == "stop":
            arguments["run_id"] = run_id
        if action == "retry_export":
            arguments["attempt_id"] = attempt
        assert transport.control_shader_sequence(arguments)["action"] == action
        assert seen[-1].full_url.endswith(suffix)
    lost = Client(opener=lambda *_a, **_kw: (_ for _ in ()).throw(urllib.error.URLError(TimeoutError())))
    with pytest.raises(HextileClientError) as uncertain:
        lost.render_shader_sequence(body)
    assert uncertain.value.kind == "shader_sequence_outcome_unknown"
    with pytest.raises(HextileClientError) as uncertain_export:
        lost.export_shader_sequence({**folder, "transaction_fingerprint": digest})
    assert uncertain_export.value.kind == "shader_sequence_outcome_unknown"
    assert "Chosen" not in str(uncertain_export.value)
    for bad in ({"sequence_id": sid, "status": 17},
                {"sequence_id": sid},
                {"sequence_id": "seq_" + "f" * 32, "status": "queued"}):
        malformed = Client(opener=lambda *_a, _bad=bad, **_kw: Response(_bad))
        for action_args in ({"sequence_id": sid, "action": "stop", "run_id": run_id},
                            {"sequence_id": sid, "action": "retry_export", "attempt_id": attempt}):
            with pytest.raises(HextileClientError) as control_unknown:
                malformed.control_shader_sequence(action_args)
            assert control_unknown.value.kind == "shader_sequence_outcome_unknown"
            assert "GET" in str(control_unknown.value)
    for bad in ({"sequence_id": sid, "attempt_id": attempt,
                 "transaction_fingerprint": digest, "status": 17},
                {"sequence_id": sid, "attempt_id": attempt,
                 "transaction_fingerprint": digest},
                {"sequence_id": "seq_" + "f" * 32, "attempt_id": attempt,
                 "transaction_fingerprint": digest, "status": "queued"}):
        malformed = Client(opener=lambda *_a, _bad=bad, **_kw: Response(_bad))
        with pytest.raises(HextileClientError) as export_unknown:
            malformed.export_shader_sequence({**folder, "transaction_fingerprint": digest})
        assert export_unknown.value.kind == "shader_sequence_outcome_unknown"
        assert "GET" in str(export_unknown.value)
    missing = Client(opener=_http_error_opener(404, "C:\\private\\formula"))
    with pytest.raises(HextileClientError) as unknown:
        missing.get_shader_sequence(sid)
    assert unknown.value.kind == "shader_sequence_outcome_unknown"
    assert "private" not in str(unknown.value)
    def stale_opener(req: Any, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 422, "Unprocessable", {},
                                     io.BytesIO(b'{"detail":{"code":"stale_document_hash","source":"C:\\\\private"}}'))
    with pytest.raises(HextileClientError) as stale:
        Client(opener=stale_opener).preflight_shader_sequence(body)
    assert stale.value.receipt == {"code": "stale_document_hash"}
    assert "private" not in str(stale.value) and "private" not in json.dumps(stale.value.receipt)
    with pytest.raises(HextileClientError) as refused:
        Client(opener=stale_opener).render_shader_sequence(body)
    assert refused.value.kind == "http" and refused.value.status_code == 422
    assert refused.value.receipt == {"code": "stale_document_hash"}

    # A lost or malformed response must not expose transport text or replay a render.
    private = "C:\\private\\shader-formula"
    for name, args in (("preflight_shader_sequence", body),
                       ("render_shader_sequence", body),
                       ("get_shader_sequence", {"sequence_id": sid})):
        for failure in (http.client.BadStatusLine(private), RuntimeError(private)):
            calls: list[Any] = []
            def broken(req: Any, timeout=None):
                if "/api/shaders/sequences" in req.full_url:
                    calls.append(req)
                raise failure
            result = HextileMcpServer(client=Client(opener=broken)).call_tool(name, args)
            payload = json.loads(result["content"][0]["text"])
            assert result["isError"] is True
            assert "shader-formula" not in json.dumps(result) and "trace" not in payload
            assert len(calls) == 1
            assert payload["kind"] == ("shader_sequence_outcome_unknown" if name == "render_shader_sequence" else "other")

    class Interrupted(Response):
        def read(self) -> bytes:
            raise http.client.IncompleteRead(private.encode())
    for name, args in (("preflight_shader_sequence", body),
                       ("render_shader_sequence", body),
                       ("get_shader_sequence", {"sequence_id": sid})):
        result = HextileMcpServer(client=Client(opener=lambda *_a, **_k: Interrupted({}))).call_tool(name, args)
        payload = json.loads(result["content"][0]["text"])
        assert "shader-formula" not in json.dumps(result) and "trace" not in payload
        assert payload["kind"] == ("shader_sequence_outcome_unknown" if name == "render_shader_sequence" else "other")

    class UnexpectedClient:
        def preflight_shader_sequence(self, _args: Any) -> Any:
            raise RuntimeError(private)
        render_shader_sequence = preflight_shader_sequence
        get_shader_sequence = preflight_shader_sequence
    for name, args in (("preflight_shader_sequence", body),
                       ("render_shader_sequence", body),
                       ("get_shader_sequence", {"sequence_id": sid})):
        result = HextileMcpServer(client=UnexpectedClient()).call_tool(name, args)
        payload = json.loads(result["content"][0]["text"])
        assert "shader-formula" not in json.dumps(result) and "trace" not in payload
        assert payload["kind"] == ("shader_sequence_outcome_unknown" if name == "render_shader_sequence" else "other")

    for status in (500, 503):
        calls: list[Any] = []
        def admitted_then_error(req: Any, timeout=None):
            if "/api/shaders/sequences" in req.full_url:
                calls.append(req)
            if req.get_method() == "POST":
                raise urllib.error.HTTPError(req.full_url, status, private, {}, io.BytesIO(private.encode()))
            return Response({"sequence_id": sid, "status": "queued", "request_hash": digest})
        recovery_server = HextileMcpServer(client=Client(opener=admitted_then_error))
        result = recovery_server.call_tool("render_shader_sequence", body)
        payload = json.loads(result["content"][0]["text"])
        assert result["isError"] is True and payload["kind"] == "shader_sequence_outcome_unknown"
        assert payload["receipt"] == {"status": "unknown"}
        assert "GET" in payload["error"] and "request_hash" in payload["error"]
        assert "shader-formula" not in json.dumps(result) and "trace" not in payload
        assert [req.get_method() for req in calls] == ["POST"]
        recovered = recovery_server.call_tool("get_shader_sequence", {"sequence_id": sid})
        assert json.loads(recovered["content"][0]["text"])["request_hash"] == digest
        assert [req.get_method() for req in calls] == ["POST", "GET"]
        preflight = recovery_server.call_tool("preflight_shader_sequence", body)
        preflight_error = json.loads(preflight["content"][0]["text"])
        assert preflight_error["kind"] == "http" and preflight_error["status_code"] == status

    sdk_spec = importlib.util.find_spec("mcp")
    if sdk_spec is not None and sdk_spec.origin is not None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        script = ("import sys; sys.path.insert(0, " + repr(str(MCP_DIR)) + "); "
                  "import hextile_mcp; original=hextile_mcp.HextileMcpServer; "
                  "hextile_mcp.HextileMcpServer=lambda: original(client=FakeClient(), child_token='test'); "
                  "raise SystemExit(hextile_mcp.main())")
        script = ("class FakeClient:\n"
                  "    def preflight_shader_sequence(self, args): return {'sequence_id':'" + sid + "','status':'ready','request_hash':'" + digest + "'}\n"
                  "    def render_shader_sequence(self, args): return {'sequence_id':'" + sid + "','status':'queued','request_hash':'" + digest + "'}\n"
                  "    def get_shader_sequence(self, sid): return {'sequence_id':sid,'status':'completed','frames_completed':48}\n"
                  "    def control_shader_sequence(self, args): return {'sequence_id':args['sequence_id'],'action':args['action'],'status':'queued'}\n"
                  "    def preflight_shader_sequence_export(self, args): return {'sequence_id':args['sequence_id'],'attempt_id':'" + attempt + "','transaction_fingerprint':'" + digest + "','status':'ready'}\n"
                  "    def export_shader_sequence(self, args): return {'sequence_id':args['sequence_id'],'attempt_id':'" + attempt + "','transaction_fingerprint':'" + digest + "','status':'queued'}\n"
                  + script)
        async def exercise_sdk() -> None:
            params = StdioServerParameters(command=sys.executable, args=["-c", script])
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    catalog = await session.list_tools()
                    assert {"preflight_shader_sequence", "render_shader_sequence", "get_shader_sequence",
                            "control_shader_sequence", "preflight_shader_sequence_export",
                            "export_shader_sequence"} <= {tool.name for tool in catalog.tools}
                    for name, args in (("preflight_shader_sequence", body), ("render_shader_sequence", body),
                                       ("get_shader_sequence", {"sequence_id": sid}),
                                       ("control_shader_sequence", {"sequence_id": sid, "action": "stop", "run_id": run_id}),
                                       ("preflight_shader_sequence_export", folder),
                                       ("export_shader_sequence", {**folder, "transaction_fingerprint": digest})):
                        result = await session.call_tool(name, args)
                        assert result.isError is False
                        assert json.loads(result.content[0].text)["sequence_id"] == sid
        asyncio.run(exercise_sdk())


@pytest.mark.parametrize('capture_id', [None, '7e720fa5-192b-47da-a705-ab3b5ddc979e'])
@pytest.mark.parametrize('processing', [None, 'auto', 'cpu'])
def test_native_shader_direct_inspect_continue_and_observed_stop(capture_id, processing) -> None:
    tools = {tool["name"]: tool for tool in HextileMcpServer(client=Client()).handle_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})["result"]["tools"]}
    digest = "sha256:" + "a" * 64
    sequence_id = "seq_" + "b" * 32
    run_id = "c" * 32
    folder = {"destination_folder": "C:\\chosen\\native", "format": "JPG", "quality_if_jpg": 91}
    request = {"shader_ref": {"origin": "project", "id": "aurora"},
               "project_context_witness": "project-witness", "working_revision": 2,
               "document_hash": digest, "source_hash": digest,
               "idempotency_key": "direct-1", "name": "Aurora",
               "frame_rate": {"num": 24, "den": 1}, "frame_count": 24,
               "start_time": {"num": "0", "den": "1"}, "end_time": {"num": "1", "den": "1"},
               "width": 2048, "height": 1024, "seed": 7, "supersampling": 1.25,
               "output": {"projection": "equirectangular", "pan": 0, "tilt": 0, "roll": 0},
               "folder_export": folder}
    if capture_id is not None:
        request['input_capture_id'] = capture_id
    if processing is not None:
        request['raster_policy'] = {'profile': 'shader-raster-policy/1', 'processing': processing}
        from hextile_client import validate_shader_sequence_request
        for level in (0, 6):
            png = {**request, 'folder_export': {**folder, 'format': 'PNG', 'quality_if_jpg': None},
                   'raster_policy': {**request['raster_policy'], 'png_compress_level': level}}
            jsonschema.validate(png, tools['render_shader_sequence']['inputSchema'])
            validate_shader_sequence_request(png)
        for invalid in (None, {**request['raster_policy'], 'png_compress_level': 0},
                        {**request['raster_policy'], 'processing': True}):
            with pytest.raises(HextileClientError):
                validate_shader_sequence_request({**request, 'raster_policy': invalid})
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate({**request, 'raster_policy': invalid}, tools['render_shader_sequence']['inputSchema'])
        with pytest.raises(HextileClientError):
            validate_shader_sequence_request({**request, 'folder_export': None, 'publication_mode': 'deferred'})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**request, 'input_sample': {}}, tools['render_shader_sequence']['inputSchema'])
    jsonschema.validate(request, tools["render_shader_sequence"]["inputSchema"])
    jsonschema.validate({"request": request}, tools["inspect_shader_sequence_output"]["inputSchema"])
    control = {"sequence_id": sequence_id, "action": "continue", "request": request,
               "inspection_fingerprint": digest}
    jsonschema.validate(control, tools["control_shader_sequence"]["inputSchema"])
    seen: list[Any] = []
    def opener(req: Any, timeout=None):
        seen.append(req)
        if req.full_url.endswith("/capabilities"):
            return _Resp({"native_render": {"contract": "native-render/1", "sequences": {'shader': {
                'input_snapshot': {'contract': 'shader-sequence-input/1'}}}, "stills": {},
                'shader_raster_policy': {'profile': 'shader-raster-policy/1'}}})
        if req.full_url.endswith("/inspect"):
            return _Resp({"status": "unfinished", "sequence_id": sequence_id,
                          "producer": "shader", "render_identity": digest, "recipe_hash": digest,
                          "destination_folder": folder["destination_folder"], "format": "JPG",
                          "quality_if_jpg": 91, "frames_completed": 7, "frame_count": 24,
                          "native_status": "incomplete", "publication_state": "direct",
                          "inspection_fingerprint": digest, "ownership_live": False})
        if req.full_url.endswith("/continue"):
            return _Resp({"sequence_id": sequence_id, "status": "queued", "run_id": run_id})
        if req.full_url.endswith("/stop"):
            return _Resp({"sequence_id": sequence_id, "status": "processing"})
        if req.get_method() == "GET":
            return _Resp({"sequence_id": sequence_id, "status": "processing",
                          "frames_completed": 7, "frame_count": 24, "ownership_live": True,
                          "render_observation": {"run_id": run_id, "revision": 3,
                                                 "phase": "checking", "checked_count": 2,
                                                 "check_total": 7, "verified_cursor": 0,
                                                 "durations_ms": [120], "sample_count": 1},
                          "continuation_receipt": {"key": request["idempotency_key"],
                                                   "request_hash": digest,
                                                   "inspection_fingerprint": digest, "run_id": run_id},
                          "accepted_settings": {"supersampling": 1.25, "frame_count": 24,
                                                "selected_resource_frames": [{"private": "resource"}]}})
        raise AssertionError(req.full_url)
    client = Client(base_url=BASE, opener=opener)
    inspected = client.inspect_shader_sequence_output({"request": request})
    assert inspected["inspection_fingerprint"] == digest
    assert "destination_folder" not in inspected
    accepted = client.control_shader_sequence(control)
    assert json.loads(seen[-1].data)['request'] == request
    assert accepted["run_id"] == run_id
    detail = client.get_shader_sequence(sequence_id)
    assert detail["frames_completed"] == 7
    assert detail["render_observation"]["verified_cursor"] == 0
    assert detail["render_observation"]["checked_count"] == 2
    assert detail["continuation_receipt"]["run_id"] == run_id
    assert detail["accepted_settings"] == {"supersampling": 1.25, "frame_count": 24}
    assert client.control_shader_sequence({"sequence_id": sequence_id, "action": "stop",
                                           "run_id": run_id})["run_id"] == run_id
    assert json.loads(seen[-1].data) == {"run_id": run_id}
    assert any(req.get_header("X-hextile-project-witness") == "project-witness"
               for req in seen if req.full_url.endswith(("/inspect", "/continue")))
    assert folder["destination_folder"] not in json.dumps(inspected)


def test_native_saved_frame_estimate_projection_drops_untrusted_fields():
    from hextile_client import _native_sequence_fields
    estimate = {"profile": "shader-render-estimate/1", "basis": "saved_frames", "approximate": True,
                "frame_count": 24, "remaining_frames": 17, "total_ms": 26000,
                "remaining_ms": 17000, "sample_count": 7, "includes_output": True}
    data = {"producer": "shader", "render_estimate": estimate}
    assert _native_sequence_fields(data)["render_estimate"] == estimate
    for patch in ({"total_ms": float("inf")}, {"remaining_frames": 25}, {"sample_count": True},
                  {"private_lease": "hidden"}, {"basis": "preview"}):
        assert _native_sequence_fields({**data, "render_estimate": {**estimate, **patch}})["render_estimate"] is None
    assert _native_sequence_fields({**data, "render_estimate": None})["render_estimate"] is None
    assert "render_estimate" not in _native_sequence_fields({"producer": "shader"})


def test_native_render_new_semantics_require_advertised_contract() -> None:
    body = {"shader_ref": {"origin": "user", "id": "known"},
            "project_context_witness": "w", "working_revision": 1,
            "document_hash": "sha256:" + "a" * 64, "source_hash": "sha256:" + "b" * 64,
            "idempotency_key": "one", "name": "One", "frame_rate": {"num": 1, "den": 1},
            "frame_count": 1, "start_time": {"num": "0", "den": "1"},
            "end_time": {"num": "1", "den": "1"}, "width": 1024, "height": 512,
            "seed": 0, "output": {"projection": "equirectangular", "pan": 0, "tilt": 0, "roll": 0},
            "folder_export": {"destination_folder": "/chosen", "format": "PNG"}}
    seen: list[str] = []
    def old_peer(req: Any, timeout=None):
        seen.append(req.full_url)
        return _Resp({"capabilities": []})
    client = Client(base_url=BASE, opener=old_peer)
    with pytest.raises(HextileClientError) as error:
        client.render_shader_sequence(body)
    assert error.value.status_code == 501
    assert seen == [f"{BASE}/api/workflows/capabilities"]
    capture = {"producer": "mounted_shader_writer", "requires_finished_frame": True,
               "caller_supplied_packets": False, "allow_unpreviewed_revision": True}
    native = {"contract": "native-render/1", "sequences": {}, "stills": {},
              "still_capture": capture}
    assert _client({}, {"native_render": native}).get_capabilities()["native_render"]["still_capture"] == capture


def test_sequence_frame_page_is_bounded_and_redacts_private_data():
    seen = {}
    client = _client(seen, {'page': 1, 'page_size': 2, 'total_frames': 2, 'total_pages': 1,
                            'frames': [{'index': 0, 'status': 'completed', 'output_file': 'output/a.png',
                                        'source_file': 'C:/private/a.png', 'content_sha256': 'secret'},
                                       {'index': 1, 'status': 'failed', 'error_message': 'C:/private'}]})
    result = client.list_sequence_frames('seq_a', page_size=2)
    assert result['frames'] == [{'index': 0, 'status': 'completed',
                                'output_handle': '/api/sequences/seq_a/frame-output/0'},
                               {'index': 1, 'status': 'failed'}]
    assert seen['url'].endswith('/api/sequences/seq_a/frames?page=1&page_size=2')
    for page, size in ((0, 2), (1, 101), (True, 2)):
        with pytest.raises(HextileClientError):
            client.list_sequence_frames('seq_a', page, size)
    response = HextileMcpServer(client=client).handle_rpc(
        {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
    tools = {tool['name']: tool for tool in response['result']['tools']}
    jsonschema.validate({'sequence_id': 'seq_a', 'page_size': 100}, tools['list_sequence_frames']['inputSchema'])


def test_bounded_sequence_summary_and_run_controls():
    seen = {}
    sid, run_id = 'seq_' + 'a' * 32, 'b' * 32
    client = _client(seen, {'sequence_id': sid, 'status': 'processing', 'run_id': run_id,
                            'source_folder': 'C:/private', 'frames': [{'source_file': 'secret'}],
                            'frame_rate': {'num': 30000, 'den': 1001, 'hash': 'private'}})
    summary = client.get_sequence_summary(sid)
    assert summary == {'sequence_id': sid, 'status': 'processing', 'run_id': run_id,
                       'frame_rate': {'num': 30000, 'den': 1001}}
    assert seen['url'].endswith(f'/{sid}?include_frames=false')
    for action, method in (('resume', client.resume_sequence), ('retry-failed', client.retry_sequence_failed_frames),
                           ('stop', client.stop_sequence)):
        method(sid, run_id)
        assert seen['url'].endswith(f'/{sid}/{action}') and json.loads(seen['data']) == {'run_id': run_id}
    with pytest.raises(HextileClientError):
        client.resume_sequence(sid, 'stale')


def test_only_derived_summary_and_run_fenced_stop_bypass_disabled_gate():
    class DisabledClient:
        _opener = None
        def request_json(self, *args, **kwargs):
            return {'enabled': False}
        def get_sequence_summary(self, sid):
            return {'sequence_id': sid, 'status': 'processing'}
        def stop_sequence(self, sid, run_id=None):
            return {'sequence_id': sid, 'status': 'cancelled'}
    server = HextileMcpServer(client=DisabledClient())
    sid, run_id = 'seq_' + 'a' * 32, 'b' * 32
    for name, args in [('get_sequence', {'sequence_id': sid}),
                       ('stop_sequence', {'sequence_id': sid, 'run_id': run_id})]:
        assert not server.call_tool(name, args).get('isError', False)
    for name, args in [('get_sequence', {'sequence_id': 'seq_legacy'}),
                       ('stop_sequence', {'sequence_id': sid}),
                       ('resume_sequence', {'sequence_id': sid, 'run_id': run_id}),
                       ('list_sequence_frames', {'sequence_id': sid})]:
        assert server.call_tool(name, args)['isError']
