"""Stdio executor: sequential tools/call replies are never dropped."""

from __future__ import annotations

import io
import json
import queue
import select
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "mcp" / "hextile_mcp.py"


def test_render_wait_returns_on_terminal_status_and_rejects_bad_duration(monkeypatch) -> None:  # noqa: ANN001
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    for name in ("get_status", "shader_get_output_job", "get_shader_sequence", "audio_get_preparation"):
        tool = next(row for row in hextile_mcp.TOOLS + hextile_mcp.SHADER_EXTENSION_TOOLS
                    if row["name"] == name)
        assert tool["inputSchema"]["properties"]["wait_s"] == {
            "type": "integer", "minimum": 0, "maximum": 25, "default": 0}
        assert "Pass wait_s 25 instead of calling again." in tool["description"]

    now = [0.0]
    seen = []

    class Event:
        def is_set(self):
            return False

        def wait(self, seconds):
            now[0] += seconds
            return False

    class Client:
        def get_status(self, run_id, timeout=None):  # noqa: ANN001
            seen.append(run_id)
            return {"run_id": run_id, "status": "running" if len(seen) == 1 else "failed"}

    server = hextile_mcp.HextileMcpServer(client=Client())
    server._wait_shutdown = Event()
    monkeypatch.setattr(hextile_mcp, "time", SimpleNamespace(monotonic=lambda: now[0]))
    result = server._get_status({"run_id": "run_1", "wait_s": 25})
    assert result["status"] == "failed" and result["waited_s"] == 1
    assert seen == ["run_1", "run_1"]
    server.client.get_status = lambda run_id, timeout=None: {"run_id": run_id, "status": "crashed"}
    assert server._get_status({"run_id": "run_1", "wait_s": 25})["waited_s"] == 0
    for bad in (-1, 26, 1.5, "1", True):
        assert server.call_tool("get_status", {"run_id": "run_1", "wait_s": bad})["isError"] is True
    assert len(seen) == 2
    refusal = json.loads(server.call_tool("get_status", {"run_id": "run_1", "wait_s": 26})["content"][0]["text"])
    assert refusal["code"] == "invalid_arguments"
    assert refusal["next_step"] == "Pass wait_s as an integer from 0 to 25."


def test_waited_s_includes_reread_time_and_omits_missing_state_progress(monkeypatch) -> None:  # noqa: ANN001
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    now = [0.0]
    notifications = []
    calls = []

    class Event:
        def is_set(self):
            return False

        def wait(self, seconds):
            now[0] += seconds
            return False

    class Client:
        def get_status(self, run_id, timeout=None):  # noqa: ANN001
            calls.append(run_id)
            if len(calls) == 2:
                now[0] += 0.23
                return {"run_id": run_id}
            return {"run_id": run_id, "status": "running"}

    server = hextile_mcp.HextileMcpServer(client=Client(), notify=notifications.append)
    server._wait_shutdown = Event()
    server._wait_progress.token = "progress-1"
    monkeypatch.setattr(hextile_mcp, "time", SimpleNamespace(monotonic=lambda: now[0]))
    result = server._get_status({"run_id": "run_1", "wait_s": 25})
    assert result["waited_s"] == 1.2
    assert calls == ["run_1", "run_1"]
    assert notifications == []


def test_slow_reread_returns_last_good_read_within_cap() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    timeouts = []

    class Client:
        def get_status(self, run_id, timeout=None):  # noqa: ANN001
            timeouts.append(timeout)
            if timeout is not None:
                time.sleep(timeout)
                raise hextile_mcp.HextileClientError("timed out", kind="app_down")
            return {"run_id": run_id, "status": "running"}

    server = hextile_mcp.HextileMcpServer(client=Client())
    before = threading.active_count()
    for _ in range(3):
        started = time.monotonic()
        result = server._get_status({"run_id": "run_1", "wait_s": 2})
        assert time.monotonic() - started <= 2.3
        assert result["status"] == "running" and 1.9 <= result["waited_s"] <= 2.3
    assert threading.active_count() == before
    assert timeouts[0::2] == [None] * 3 and all(0 < t <= 1.05 for t in timeouts[1::2])


def test_slow_first_read_with_wait_uses_normal_timeout() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    timeouts = []

    class Client:
        def get_status(self, run_id, timeout=None):  # noqa: ANN001
            timeouts.append(timeout)
            time.sleep(1.2)
            return {"run_id": run_id, "status": "completed"}

    server = hextile_mcp.HextileMcpServer(client=Client())
    result = server._get_status({"run_id": "run_1", "wait_s": 1})
    assert result["status"] == "completed" and result["waited_s"] >= 1.2
    assert timeouts == [None]


def test_wait_returns_immediately_for_unknown_render_state() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    for status in (None, "future_native_state"):
        calls = []

        class Client:
            def get_status(self, run_id, timeout=None):  # noqa: ANN001
                calls.append(run_id)
                return {"run_id": run_id, "status": status}

        server = hextile_mcp.HextileMcpServer(client=Client())
        result = server._get_status({"run_id": "run_1", "wait_s": 25})
        assert result["status"] == status and result["waited_s"] == 0
        assert calls == ["run_1"]


def test_waited_reads_keep_client_request_headers(monkeypatch) -> None:  # noqa: ANN001
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp
    from hextile_client import Client

    now = [0.0]
    seen = []

    class Event:
        def is_set(self):
            return False

        def wait(self, seconds):
            now[0] += seconds
            return False

    class Response:
        status = 200

        def __init__(self, status):
            self.status_value = status

        def read(self, size=-1):
            return json.dumps({"status": self.status_value}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

    def opener(req, timeout=None):  # noqa: ANN001
        seen.append(req.get_header("X-hextile-copilot-token"))
        return Response("running" if len(seen) == 1 else "completed")

    client = Client(base_url="http://hextile.test", opener=opener)
    server = hextile_mcp.HextileMcpServer(client=client)
    server._wait_shutdown = Event()
    monkeypatch.setattr(hextile_mcp, "time", SimpleNamespace(monotonic=lambda: now[0]))
    with client.request_headers({"X-Hextile-Copilot-Token": "child-secret"}):
        result = server._get_status({"run_id": "run_1", "wait_s": 2})
    assert result["status"] == "completed"
    assert seen == ["child-secret", "child-secret"]


def test_sequential_tools_call_replies_not_dropped() -> None:
    expected = list(range(1, 13))
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdin is not None and proc.stdout is not None
    seen: list[int] = []
    try:
        for call_id in expected:
            proc.stdin.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": call_id,
                        "method": "tools/call",
                        "params": {
                            "name": "get_guide",
                            "arguments": {"name": "index"},
                        },
                    }
                )
                + "\n"
            )
            proc.stdin.flush()
            ready, _, _ = select.select([proc.stdout], [], [], 5)
            assert ready, f"no reply for id={call_id}"
            row = json.loads(proc.stdout.readline())
            seen.append(row.get("id"))
    finally:
        proc.stdin.close()
        proc.wait(timeout=5)
    assert seen == expected


def test_control_lane_replies_while_ordinary_call_is_blocked(monkeypatch) -> None:  # noqa: ANN001
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    class FakeServer:
        notify = None
        client = type("FakeClient", (), {})()

        def start_activity_sender(self) -> None:
            pass

        def flush_activity(self) -> None:
            pass

        def handle_rpc(self, msg):  # noqa: ANN001
            name = msg["params"]["name"]
            if name == "list_workflows":
                time.sleep(0.2)
            return {"jsonrpc": "2.0", "id": msg["id"], "result": {"name": name}}

    rows = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_workflows", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_status", "arguments": {"run_id": "run_1"}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_seed_job", "arguments": {"job_id": "seed_1"}}},
        *({"jsonrpc": "2.0", "id": index, "method": "tools/call",
           "params": {"name": name, "arguments": {}}}
          for index, name in enumerate(("get_shader_sequence", "control_shader_sequence",
                                        "get_fractal_sequence", "control_fractal_sequence",
                                        "get_fractal_request", "shader_get_output_job",
                                        "shader_stop_output_job"), start=4)),
    ]
    stdin = io.StringIO("".join(json.dumps(row) + "\n" for row in rows))
    stdout = io.StringIO()
    monkeypatch.setattr(hextile_mcp, "HextileMcpServer", FakeServer)
    monkeypatch.setattr(hextile_mcp.sys, "stdin", stdin)
    monkeypatch.setattr(hextile_mcp.sys, "stdout", stdout)

    assert hextile_mcp.main() == 0
    replies = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert {row["id"] for row in replies} == set(range(1, 11))
    assert [row["id"] for row in replies][-1] == 1


def test_wait_keeps_cancel_and_ping_responsive_and_eof_interrupts(monkeypatch) -> None:  # noqa: ANN001
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    started = threading.Event()

    class Client:
        def get_status(self, run_id, timeout=None):  # noqa: ANN001
            started.set()
            return {"run_id": run_id, "status": "running"}

        def cancel_run(self, run_id):  # noqa: ANN001
            return {"run_id": run_id, "status": "cancelled"}

    server = hextile_mcp.HextileMcpServer(client=Client())

    class Input:
        def __init__(self):
            self.lines = queue.Queue()

        def readline(self):
            return self.lines.get()

        def send(self, row):  # noqa: ANN001
            self.lines.put(json.dumps(row) + "\n")

    stdin, stdout = Input(), io.StringIO()
    monkeypatch.setattr(hextile_mcp, "HextileMcpServer", lambda: server)
    monkeypatch.setattr(hextile_mcp.sys, "stdin", stdin)
    monkeypatch.setattr(hextile_mcp.sys, "stdout", stdout)
    thread = threading.Thread(target=hextile_mcp.main)
    thread.start()

    def call(call_id, name, arguments):  # noqa: ANN001
        stdin.send({"jsonrpc": "2.0", "id": call_id, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments}})

    def replies():
        return {row["id"]: row for line in stdout.getvalue().splitlines()
                if (row := json.loads(line)).get("id") is not None}

    try:
        call(1, "get_status", {"run_id": "run_1", "wait_s": 25})
        assert started.wait(1)
        call(2, "get_status", {"run_id": "run_2", "wait_s": 25})
        call(3, "cancel_run", {"run_id": "run_1"})
        stdin.send({"jsonrpc": "2.0", "id": 4, "method": "ping", "params": {}})
        deadline = time.monotonic() + 1.5
        while not {2, 3, 4} <= replies().keys() and time.monotonic() < deadline:
            time.sleep(0.01)
        rows = replies()
        assert {2, 3, 4} <= rows.keys()
        assert json.loads(rows[2]["result"]["content"][0]["text"])["waited_s"] == 0
        assert rows[3]["result"]["isError"] is False
        assert 1 not in rows
        eof_at = time.monotonic()
        stdin.lines.put("")
        thread.join(timeout=1.9)
        assert not thread.is_alive() and time.monotonic() - eof_at < 2
        assert 1 in replies()
    finally:
        if thread.is_alive():
            stdin.lines.put("")
            thread.join(timeout=3)


def test_eof_during_slow_reread_exits_within_two_seconds(monkeypatch) -> None:  # noqa: ANN001
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    reread_started = threading.Event()

    class Client:
        def get_status(self, run_id, timeout=None):  # noqa: ANN001
            if timeout is not None:
                reread_started.set()
                time.sleep(timeout)
                raise hextile_mcp.HextileClientError("timed out", kind="app_down")
            return {"run_id": run_id, "status": "running"}

    server = hextile_mcp.HextileMcpServer(client=Client())

    class Input:
        def __init__(self):
            self.lines = queue.Queue()

        def readline(self):
            return self.lines.get()

    stdin, stdout = Input(), io.StringIO()
    monkeypatch.setattr(hextile_mcp, "HextileMcpServer", lambda: server)
    monkeypatch.setattr(hextile_mcp.sys, "stdin", stdin)
    monkeypatch.setattr(hextile_mcp.sys, "stdout", stdout)
    thread = threading.Thread(target=hextile_mcp.main)
    thread.start()
    try:
        stdin.lines.put(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                    "params": {"name": "get_status", "arguments": {"run_id": "run_1", "wait_s": 25}}}) + "\n")
        assert reread_started.wait(3)
        eof_at = time.monotonic()
        stdin.lines.put("")
        thread.join(timeout=1.9)
        assert not thread.is_alive() and time.monotonic() - eof_at < 2
        reply = json.loads(stdout.getvalue().splitlines()[0])
        assert reply["id"] == 1 and json.loads(reply["result"]["content"][0]["text"])["status"] == "running"
    finally:
        if thread.is_alive():
            stdin.lines.put("")
            thread.join(timeout=3)


def test_internal_meta_headers_and_activity_suppression() -> None:
    # Kept in the agent-focused file because this is the canonical proxy contract.
    sys.path.insert(0, str(ROOT / "mcp"))
    from hextile_mcp import HextileMcpServer

    seen: list[tuple[str, str | None, str | None]] = []

    class FakeClient:
        internal_mode = True

        def request_headers(self, headers):  # noqa: ANN001
            class C:
                def __enter__(self_nonlocal):
                    seen.append(("headers", headers.get("X-Hextile-Copilot-Token"), headers.get("X-Hextile-Op")))

                def __exit__(self_nonlocal, *args):
                    return None

            return C()

        def get_status(self, run_id, timeout=None):
            seen.append(("status", run_id, None))
            return {"run_id": run_id, "status": "running"}

        def post_activity(self, _envelope):
            raise AssertionError("internal mode must suppress activity")

    server = HextileMcpServer(client=FakeClient(), child_token="child-secret")
    response = server.handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "get_status",
                "arguments": {"run_id": "run_1", "actor": "external"},
                "_meta": {"hextile_op": "op_1"},
            },
        }
    )
    assert response is not None and response["result"]["isError"] is False
    assert seen == [("headers", "child-secret", "op_1"), ("status", "run_1", None)]


def test_mcp_activity_minilog_projects_only_confirmed_safe_facts() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    from hextile_mcp import HextileMcpServer

    class FakeClient:
        def __init__(self):
            self.events = []

        def request_json(self, method, path):  # noqa: ANN001
            assert (method, path) == ("GET", "/api/agent/mcp-status")
            return {"enabled": True}

        def post_activity(self, envelope):  # noqa: ANN001
            self.events.append(envelope)

    client = FakeClient()
    server = HextileMcpServer(client=client, child_token="")
    server.client_name = "Codex <private-host-name>"
    server._handlers["get_status"] = lambda _args: {"run_id": "run_1", "status": "running"}
    server._handlers["shader_edit"] = lambda _args: {"status": "pending", "ticket_id": "ticket_1"}
    server._handlers["save_workflow"] = lambda _args: {"id": "new_workflow", "document": "secret-document"}
    server._handlers["get_shader_parameters"] = lambda _args: {
        "witness": {"shader": {"shaderId": "aurora"}}, "source": "secret-source"}
    server._handlers["get_render_config"] = lambda _args: {"config": "secret-config"}
    server._handlers["run_workflow"] = lambda _args: {"run_id": "run_2", "prompt": "secret-prompt"}
    server._handlers["create_sequence"] = lambda _args: {"sequence_id": "seq_1", "source": "secret-source"}
    server._handlers["start_batch"] = lambda _args: {"job_id": "batch_1", "prompt": "secret-prompt"}

    assert server.call_tool("get_status", {"run_id": "run_1"})["isError"] is False
    assert server.call_tool("shader_edit", {"shader_id": "aurora", "request_id": "req-1",
                                            "edits": [{"op": "set", "address": ["parameters", "fog"],
                                                       "value": "secret-value"}]})["isError"] is False
    assert server.call_tool("save_workflow", {"id": "new_workflow", "document": {"prompt": "secret-prompt"}})["isError"] is False
    assert server.call_tool("get_shader_parameters", {})["isError"] is False
    assert server.call_tool("get_render_config", {"render_id": "render_1"})["isError"] is False
    assert server.call_tool("run_workflow", {})["isError"] is False
    assert server.call_tool("create_sequence", {})["isError"] is False
    assert server.call_tool("start_batch", {})["isError"] is False
    assert [row.get("outcome") for row in client.events if row["phase"] == "succeeded"] == [
        None, "pending", "saved", None, None, None, None, None]
    assert client.events[0]["subject"] == {"kind": "run", "id": "run_1"}
    assert client.events[2]["subject"] == {"kind": "shader", "id": "aurora"}
    assert "ticket_id" not in client.events[3]
    assert client.events[4]["subject"] == {"kind": "workflow", "id": "new_workflow"}
    assert client.events[6]["subject"] == {"kind": "shader"}
    assert client.events[7]["subject"] == {"kind": "shader", "id": "aurora"}
    assert client.events[8]["subject"] == {"kind": "render", "id": "render_1"}
    assert client.events[9]["subject"] == {"kind": "render", "id": "render_1"}
    assert client.events[10]["subject"] == {"kind": "workflow"}
    assert client.events[11]["subject"] == {"kind": "run", "id": "run_2"}
    assert client.events[12]["subject"] == {"kind": "app"}
    assert client.events[13]["subject"] == {"kind": "sequence", "id": "seq_1"}
    assert client.events[14]["subject"] == {"kind": "app"}
    assert client.events[15]["subject"] == {"kind": "batch", "id": "batch_1"}
    assert all(row["client_name"] == "Codex" for row in client.events)
    assert all("secret" not in json.dumps(row) and "private" not in json.dumps(row) for row in client.events)


def test_activity_refusal_carries_only_a_closed_reason_token() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    from hextile_client import HextileClientError
    from hextile_mcp import HextileMcpServer

    class FakeClient:
        def __init__(self):
            self.events = []

        def request_json(self, method, path):  # noqa: ANN001
            return {"enabled": True}

        def post_activity(self, envelope):  # noqa: ANN001
            self.events.append(envelope)

    client = FakeClient()
    server = HextileMcpServer(client=client, child_token="")
    bodies = iter([
        '{"detail": {"code": "attachment_not_ready", "message": "secret detail"}}',
        '{"detail": {"code": "Not A Token <secret>"}}',
    ])

    def refuse(_args):  # noqa: ANN001, ANN202
        raise HextileClientError("secret message", status_code=409, body=next(bodies))

    server._handlers["get_status"] = refuse
    assert server.call_tool("get_status", {"run_id": "run_1"})["isError"] is True
    assert server.call_tool("get_status", {"run_id": "run_1"})["isError"] is True
    failed = [row["error"]["message"] for row in client.events if row["phase"] == "failed"]
    assert failed == ["HTTP 409 attachment_not_ready", "HTTP 409"]
    assert all("secret" not in json.dumps(row) for row in client.events)


def test_describe_image_exact_body_timeout_and_text_only_result() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    from hextile_client import Client
    from hextile_mcp import HextileMcpServer

    seen = []

    class Response:
        status = 200

        def read(self):  # noqa: ANN201
            return json.dumps({
                "prompt": "A mountain at dusk", "mode": "crop",
                "image_signature": "sha256-test", "image_base64": "SHOULD_NOT_LEAK",
            }).encode()

        def __enter__(self):  # noqa: ANN201
            return self

        def __exit__(self, *args):  # noqa: ANN002, ANN201
            return None

    def opener(req, timeout):  # noqa: ANN001, ANN201
        seen.append((req.get_method(), req.full_url, json.loads(req.data), timeout))
        return Response()

    server = HextileMcpServer(client=Client(opener=opener), child_token="test")
    source = {"kind": "render_node", "render_id": "render_1", "node_id": "node_2"}
    crop = {"yaw": 15, "pitch": -10, "fov": 70}
    result = server.call_tool("describe_image", {"source": source, "crop": crop})
    assert result["isError"] is False
    assert seen == [(
        "POST", "http://127.0.0.1:8000/api/prompts/describe-source",
        {"source": source, "crop": crop}, 300.0,
    )]
    assert len(result["content"]) == 1 and result["content"][0]["type"] == "text"
    payload = json.loads(result["content"][0]["text"])
    assert payload == {
        "prompt": "A mountain at dusk", "source": source, "mode": "crop",
        "crop": crop, "image_signature": "sha256-test",
    }
    assert "SHOULD_NOT_LEAK" not in result["content"][0]["text"]

    for rejected in (
        {"source": {**source, "image_base64": "AA=="}},
        {"source": {"kind": "local_file", "path": "https://example.com/image.jpg"}},
        {"source": source, "crop": {**crop, "bitmap": "AA=="}},
        {"source": source, "image_base64": "AA=="},
    ):
        assert server.call_tool("describe_image", rejected)["isError"] is True
    assert len(seen) == 1


class _GateClient:
    """A client with no injected opener, so the external MCP-status gate runs."""

    def __init__(self, answers) -> None:  # noqa: ANN001
        self.answers = answers  # callable returning the status payload or raising
        self.status_calls = 0
        self.activity: list[tuple[str, str]] = []

    def request_json(self, method, path):  # noqa: ANN001, ANN201
        assert (method, path) == ("GET", "/api/agent/mcp-status")
        self.status_calls += 1
        return self.answers()

    def post_activity(self, envelope):  # noqa: ANN001, ANN201
        self.activity.append((envelope["tool"], envelope["phase"]))


def _gate_server(client, dispatched):  # noqa: ANN001, ANN202
    sys.path.insert(0, str(ROOT / "mcp"))
    from hextile_mcp import HextileMcpServer

    server = HextileMcpServer(client=client, child_token="")

    def handler(_args):  # noqa: ANN001, ANN202
        dispatched.append(1)
        if client_refusal:
            raise client_refusal[0]
        return {"run_id": "run_1", "status": "running"}

    client_refusal: list = []
    server._handlers["get_status"] = handler
    server._refusal = client_refusal
    return server


def test_external_gate_reuses_enabled_status_and_never_reuses_disabled() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    from hextile_client import HextileClientError

    state = {"enabled": False}
    client = _GateClient(lambda: {"enabled": state["enabled"]})
    dispatched: list[int] = []
    server = _gate_server(client, dispatched)
    call = lambda: server.call_tool("get_status", {"run_id": "run_1"})  # noqa: E731

    # Disabled: refused before activity or dispatch, and never reused.
    assert call()["isError"] is True and call()["isError"] is True
    assert client.status_calls == 2 and dispatched == [] and client.activity == []

    # Enabled: the first call checks, the second inside the window reuses the result.
    state["enabled"] = True
    assert call()["isError"] is False
    assert client.status_calls == 3 and len(dispatched) == 1
    state["enabled"] = False  # Settings flipped; the reuse window still holds.
    assert call()["isError"] is False
    assert client.status_calls == 3 and len(dispatched) == 2

    # A 403 mcp_disabled from the APP clears the reuse, so the next call checks again.
    server._refusal.append(HextileClientError("off", status_code=403, body='{"code": "mcp_disabled"}'))
    assert call()["isError"] is True
    assert server._mcp_enabled_until == 0.0
    server._refusal.clear()
    assert call()["isError"] is True  # re-checked: now disabled
    assert client.status_calls == 4


def test_external_gate_rechecks_after_the_reuse_window() -> None:
    client = _GateClient(lambda: {"enabled": True})
    server = _gate_server(client, [])
    assert server.call_tool("get_status", {})["isError"] is False
    server._mcp_enabled_until = time.monotonic() - 1
    assert server.call_tool("get_status", {})["isError"] is False
    assert client.status_calls == 2


def test_activity_sender_posts_in_order_and_flushes_on_exit() -> None:
    client = _GateClient(lambda: {"enabled": True})
    server = _gate_server(client, [])
    server.start_activity_sender()
    server.call_tool("get_status", {})
    server.call_tool("get_status", {})
    server.flush_activity()
    phases = [phase for _tool, phase in client.activity]
    assert len(phases) >= 4 and phases[0] == "started"
    assert phases.index("started", 1) > 1  # call 1 finished before call 2 started
    assert server._activity_queue is None


def test_external_gate_fails_closed_on_bad_status() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    from hextile_client import HextileClientError

    def raising(error):  # noqa: ANN001, ANN202
        def answer():  # noqa: ANN202
            raise error
        return answer

    for answer in (lambda: {}, lambda: {"enabled": 1}, lambda: {"enabled": "true"}, lambda: [], lambda: None,
                   raising(OSError("offline")), raising(HextileClientError("down", status_code=503))):
        client = _GateClient(answer)
        dispatched: list[int] = []
        server = _gate_server(client, dispatched)
        result = server.call_tool("get_status", {"run_id": "run_1"})
        assert result["isError"] is True
        assert client.status_calls == 1 and dispatched == [] and client.activity == []


def test_request_marker_is_unoverridable_and_private_token_is_backend_checked() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    from hextile_client import Client
    from hextile_mcp import HextileMcpServer

    seen = []

    class Response:
        status = 200

        def read(self):  # noqa: ANN201
            return b'{"run_id":"run_1","status":"running"}'

        def __enter__(self):  # noqa: ANN201
            return self

        def __exit__(self, *args):  # noqa: ANN002, ANN201
            return None

    def opener(req, timeout):  # noqa: ANN001, ANN201
        headers = {key.lower(): value for key, value in req.header_items()}
        seen.append((req.full_url, headers))
        assert headers["x-hextile-agent"] == "mcp"
        if headers.get("x-hextile-copilot-token") == "fake":
            raise urllib.error.HTTPError(req.full_url, 403, "forbidden", {}, io.BytesIO(b'{"detail":"mcp_disabled"}'))
        return Response()

    client = Client(opener=opener, internal_mode=True)
    with client.request_headers({"X-Hextile-Agent": "unmarked"}):
        client.request_json("GET", "/test", headers={"x-hextile-agent": "unmarked"})

    real = HextileMcpServer(client=client, child_token="real")
    assert real.call_tool("get_status", {"run_id": "run_1"})["isError"] is False
    assert seen[-1][1]["x-hextile-copilot-token"] == "real"
    assert all(not url.endswith("/api/agent/mcp-status") for url, _ in seen)

    fake = HextileMcpServer(client=client, child_token="fake")
    denied = fake.call_tool("get_status", {"run_id": "run_1"})
    assert denied["isError"] is True
    assert seen[-1][1]["x-hextile-copilot-token"] == "fake"
    assert seen[-1][1]["x-hextile-agent"] == "mcp"


def test_heartbeat_is_queued_off_the_stdio_thread() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    from hextile_mcp import HextileMcpServer

    posted: list[dict] = []

    class SlowClient:
        def post_activity(self, envelope):  # noqa: ANN001, ANN201
            time.sleep(0.5)
            posted.append(envelope)

    server = HextileMcpServer(client=SlowClient(), child_token="")
    server.internal_mode = False
    server.start_activity_sender()
    started = time.monotonic()
    server._emit_heartbeat()
    assert time.monotonic() - started < 0.2  # The reply is not held by the activity post.
    server.flush_activity()
    assert [row["kind"] for row in posted] == ["heartbeat"]


def test_recorded_unchanged_edit_recovers_through_get_shader_update() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_client

    value = {"save": "unchanged", "results": [], "commit": 1, "revision": 1, "changed": False}
    assert hextile_client._saved_result(dict(value))["save"] == "unchanged"


# ── Audio preparation status reuses _wait_read and the control lane (T8g.1) ─────────────────

class _AudioPreparations:
    """audio_preparation(receipt, release=, timeout=) answering a scripted state sequence."""

    def __init__(self, states, delay=0.0) -> None:  # noqa: ANN001
        self.states, self.delay, self.calls = list(states), delay, []
        self.started = threading.Event()

    def audio_preparation(self, receipt, *, release=False, timeout=None):  # noqa: ANN001, ANN201
        self.calls.append((receipt, release, timeout))
        self.started.set()
        if release:
            return {"receipt_id": receipt, "state": "cancelled"}
        if timeout is not None and self.delay:
            time.sleep(timeout)
            raise RuntimeError("timed out")
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {"receipt_id": receipt, **({} if state is None else {"state": state})}


def test_audio_preparation_wait_returns_on_terminal_or_unknown_state(monkeypatch) -> None:  # noqa: ANN001
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    now = [0.0]

    class Event:
        def is_set(self):
            return False

        def wait(self, seconds):
            now[0] += seconds
            return False

    monkeypatch.setattr(hextile_mcp, "time", SimpleNamespace(monotonic=lambda: now[0]))
    receipt = "r" * 24
    for states, reads, waited in ((["pending", "ready"], 2, 1), (["pending", "error"], 2, 1),
                                  (["cancelled"], 1, 0), (["future_native_state"], 1, 0), ([None], 1, 0)):
        client = _AudioPreparations(states)
        server = hextile_mcp.HextileMcpServer(client=client)
        server._wait_shutdown = Event()
        result = server._audio_get_preparation({"receipt": receipt, "wait_s": 25})
        assert result["waited_s"] == waited and len(client.calls) == reads, states
        assert client.calls[0] == (receipt, False, None)  # first read at the normal timeout; wait_s never sent
    client = _AudioPreparations(["pending"])
    server = hextile_mcp.HextileMcpServer(client=client)
    assert server._wait_lock.acquire(blocking=False)  # another wait is running: answer at once
    try:
        assert server._audio_get_preparation({"receipt": receipt, "wait_s": 25})["waited_s"] == 0
    finally:
        server._wait_lock.release()
    for bad in (-1, 26, 1.5, "1", True):
        refusal = json.loads(server.call_tool("audio_get_preparation",
                                              {"receipt": receipt, "wait_s": bad})["content"][0]["text"])
        assert refusal["code"] == "invalid_arguments" and refusal["next_step"], bad
    assert len(client.calls) == 1


def test_audio_preparation_slow_reread_keeps_last_good_read_within_cap() -> None:
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    client = _AudioPreparations(["pending"], delay=1.0)
    server = hextile_mcp.HextileMcpServer(client=client)
    before = threading.active_count()
    started = time.monotonic()
    result = server._audio_get_preparation({"receipt": "r" * 24, "wait_s": 2})
    assert time.monotonic() - started <= 2.3
    assert result["state"] == "pending" and 1.9 <= result["waited_s"] <= 2.3
    assert threading.active_count() == before
    timeouts = [call[2] for call in client.calls]
    assert timeouts[0] is None and all(0 < t <= 1.5 for t in timeouts[1:])


def test_audio_preparation_wait_keeps_release_and_ping_responsive(monkeypatch) -> None:  # noqa: ANN001
    sys.path.insert(0, str(ROOT / "mcp"))
    import hextile_mcp

    client = _AudioPreparations(["pending"])
    server = hextile_mcp.HextileMcpServer(client=client)

    class Input:
        def __init__(self):
            self.lines = queue.Queue()

        def readline(self):
            return self.lines.get()

        def send(self, row):  # noqa: ANN001
            self.lines.put(json.dumps(row) + "\n")

    stdin, stdout = Input(), io.StringIO()
    monkeypatch.setattr(hextile_mcp, "HextileMcpServer", lambda: server)
    monkeypatch.setattr(hextile_mcp.sys, "stdin", stdin)
    monkeypatch.setattr(hextile_mcp.sys, "stdout", stdout)
    thread = threading.Thread(target=hextile_mcp.main)
    thread.start()

    def call(call_id, name, arguments):  # noqa: ANN001
        stdin.send({"jsonrpc": "2.0", "id": call_id, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments}})

    def replies():
        return {row["id"]: row for line in stdout.getvalue().splitlines()
                if (row := json.loads(line)).get("id") is not None}

    try:
        call(1, "audio_get_preparation", {"receipt": "r" * 24, "wait_s": 25})
        assert client.started.wait(1)
        call(2, "audio_get_preparation", {"receipt": "s" * 24, "wait_s": 25})
        call(3, "audio_release_preparation", {"receipt": "r" * 24})
        stdin.send({"jsonrpc": "2.0", "id": 4, "method": "ping", "params": {}})
        deadline = time.monotonic() + 1.5
        while not {2, 3, 4} <= replies().keys() and time.monotonic() < deadline:
            time.sleep(0.01)
        rows = replies()
        assert {2, 3, 4} <= rows.keys() and 1 not in rows
        assert json.loads(rows[2]["result"]["content"][0]["text"])["waited_s"] == 0
        assert json.loads(rows[3]["result"]["content"][0]["text"])["state"] == "cancelled"
        stdin.lines.put("")
        thread.join(timeout=1.9)
        assert not thread.is_alive() and 1 in replies()
    finally:
        if thread.is_alive():
            stdin.lines.put("")
            thread.join(timeout=3)


def test_audio_preparation_status_and_release_answer_with_mcp_disabled() -> None:
    client = _GateClient(lambda: {"enabled": False})
    server = _gate_server(client, [])
    answered = []
    for name in ("audio_get_preparation", "audio_release_preparation"):
        server._handlers[name] = lambda args, _name=name: answered.append(_name) or {"state": "cancelled"}
        assert server.call_tool(name, {"receipt": "r" * 24})["isError"] is False, name
    assert answered == ["audio_get_preparation", "audio_release_preparation"] and client.status_calls == 0
    assert server.call_tool("audio_prepare_resource", {})["isError"] is True and client.status_calls == 1
