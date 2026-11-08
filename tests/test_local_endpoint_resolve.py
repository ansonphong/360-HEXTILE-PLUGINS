"""The shipped resolver reads local-endpoint.json and does not assume port 8000."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from hextile_client import (  # noqa: E402
    ENDPOINT_UNVERIFIED,
    UNSUPPORTED_CONNECTIVITY,
    Client,
    HextileClientError,
    _PREFERENCE_UPDATE_FIELDS,
    _SETTINGS_UNKNOWN,
    resolve_local_endpoint,
)
from hextile_mcp import HextileMcpServer  # noqa: E402

INSTANCE = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
OTHER = "bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _record(port: int = 8123, instance: str = INSTANCE, **extra: object) -> dict:
    data = {
        "desired_port": port,
        "actual_port": port,
        "host": "127.0.0.1",
        "generation": 2,
        "instance_id": instance,
        "pid": 7,
        "receipts": [],
    }
    data.update(extra)
    return data


def _write(directory: Path, payload: object) -> None:
    (directory / "local-endpoint.json").write_text(json.dumps(payload), encoding="utf-8")


def _reachable(host: str, port: int) -> bool:
    assert (host, port) == ("127.0.0.1", 8123)
    return True


def test_bootstrap_dir_ignores_an_untrusted_base_string(tmp_path: Path) -> None:
    _write(tmp_path, _record(base="http://127.0.0.1:8000", url="http://10.1.2.3:9", origin="http://127.0.0.1:8000"))
    result = resolve_local_endpoint(
        environ={"HEXTILE_BOOTSTRAP_DIR": str(tmp_path), "APPDATA": r"C:\Users\Other\AppData\Roaming"},
        trusted_instance_id=INSTANCE,
        probe_reachability=_reachable,
        query_appdata=lambda: pytest.fail("bootstrap dir must not query APPDATA"),
        translate_windows_path=lambda _path: pytest.fail("bootstrap dir must not translate"),
    )
    assert result.status == "ok"
    assert result.base == "http://127.0.0.1:8123"
    assert result.base != "http://127.0.0.1:8000"
    assert result.instance_id == INSTANCE
    assert result.generation == 2


def test_base_string_alone_is_not_port_8000(tmp_path: Path) -> None:
    _write(tmp_path, {"base": "http://127.0.0.1:8000", "url": "http://127.0.0.1:8000", "origin": "http://127.0.0.1:8000"})
    result = resolve_local_endpoint(
        environ={"HEXTILE_BOOTSTRAP_DIR": str(tmp_path)},
        probe_reachability=lambda *_args: pytest.fail("an unverified file must not connect"),
    )
    assert result.status == ENDPOINT_UNVERIFIED
    assert result.base is None


def test_unverified_file_refuses_8000(tmp_path: Path) -> None:
    _write(tmp_path, _record(port=8000))
    missing = resolve_local_endpoint(
        environ={"HEXTILE_BOOTSTRAP_DIR": str(tmp_path / "absent")},
        probe_reachability=lambda *_args: pytest.fail("missing file must not connect"),
    )
    foreign = resolve_local_endpoint(
        environ={"HEXTILE_BOOTSTRAP_DIR": str(tmp_path)},
        trusted_instance_id=OTHER,
        probe_reachability=lambda *_args: pytest.fail("foreign identity must not connect"),
    )
    _write(tmp_path, _record(port=8000, host="10.1.2.3", base="http://127.0.0.1:8000"))
    invalid = resolve_local_endpoint(
        environ={"HEXTILE_BOOTSTRAP_DIR": str(tmp_path)},
        trusted_instance_id=INSTANCE,
        probe_reachability=lambda *_args: pytest.fail("a non-loopback record must not connect"),
    )
    assert missing.status == foreign.status == invalid.status == ENDPOINT_UNVERIFIED
    assert missing.base is None and foreign.base is None and invalid.base is None


def test_one_wslpath_translation_of_one_windows_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    leaf = tmp_path / "360-hextile"
    leaf.mkdir()
    _write(leaf, _record())
    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(list(args))

        class Completed:
            returncode = 0
            stdout = ""

        if args[0] == "cmd.exe":
            assert args == ["cmd.exe", "/d", "/c", "echo %APPDATA%"]
            Completed.stdout = "C:\\Users\\Phong\\AppData\\Roaming\r\n"
            return Completed()
        if args[0] == "wslpath":
            assert args == ["wslpath", "-u", "C:\\Users\\Phong\\AppData\\Roaming\\360-hextile"]
            Completed.stdout = str(leaf) + "\n"
            return Completed()
        raise AssertionError(args)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = resolve_local_endpoint(
        environ={},
        trusted_instance_id=INSTANCE,
        probe_reachability=_reachable,
    )
    assert result.status == "ok"
    assert result.base == "http://127.0.0.1:8123"
    assert [item[0] for item in calls] == ["cmd.exe", "wslpath"]


def test_appdata_env_translates_once_and_does_not_query(tmp_path: Path) -> None:
    leaf = tmp_path / "360-hextile"
    leaf.mkdir()
    _write(leaf, _record())
    seen: list[str] = []

    def translate(path: str) -> str:
        seen.append(path)
        return str(leaf)

    result = resolve_local_endpoint(
        environ={"APPDATA": r"C:\Users\Phong\AppData\Roaming"},
        trusted_instance_id=INSTANCE,
        translate_windows_path=translate,
        query_appdata=lambda: pytest.fail("an absolute Windows APPDATA must not query cmd.exe"),
        probe_reachability=_reachable,
    )
    assert result.status == "ok"
    assert seen == ["C:\\Users\\Phong\\AppData\\Roaming\\360-hextile"]
    assert result.base == "http://127.0.0.1:8123"


def test_relative_multiple_and_non_leaf_paths_are_unverified(tmp_path: Path) -> None:
    decoy = tmp_path / "local-endpoint.json"
    decoy.write_text(json.dumps(_record(port=8000)), encoding="utf-8")
    queries: list[str] = []

    def query() -> str:
        queries.append("query")
        return "not-a-windows-path\nC:\\Users\\Other\\AppData\\Roaming\n"

    multiple = resolve_local_endpoint(
        environ={},
        query_appdata=query,
        translate_windows_path=lambda _path: pytest.fail("multiple results must not be translated"),
        probe_reachability=lambda *_args: pytest.fail("must not connect"),
    )
    relative = resolve_local_endpoint(
        environ={},
        query_appdata=lambda: "Roaming",
        translate_windows_path=lambda _path: pytest.fail("a relative path must not be translated"),
        probe_reachability=lambda *_args: pytest.fail("must not connect"),
    )
    wrong_leaf = resolve_local_endpoint(
        environ={"APPDATA": r"C:\Users\Phong\AppData\Roaming"},
        translate_windows_path=lambda _path: str(tmp_path),
        query_appdata=lambda: pytest.fail("must not query"),
        probe_reachability=lambda *_args: pytest.fail("must not connect"),
    )
    assert multiple.status == relative.status == wrong_leaf.status == ENDPOINT_UNVERIFIED
    assert multiple.base is None and relative.base is None and wrong_leaf.base is None
    assert queries == ["query"]
    assert decoy.is_file()


def test_unsupported_connectivity_does_not_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, _record(port=8123))
    calls: list[tuple] = []

    def connect(address, timeout=None):
        calls.append((address, timeout))
        raise OSError("closed")

    monkeypatch.setattr(socket, "create_connection", connect)
    result = resolve_local_endpoint(
        environ={"HEXTILE_BOOTSTRAP_DIR": str(tmp_path)},
        trusted_instance_id=INSTANCE,
    )
    assert result.status == UNSUPPORTED_CONNECTIVITY
    assert result.base is None
    assert calls == [(("127.0.0.1", 8123), 0.4)]


def test_follow_record_does_not_open_8000(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, {"base": "http://127.0.0.1:8000"})
    monkeypatch.delenv("HEXTILE_MCP_CHILD_TOKEN", raising=False)
    monkeypatch.setenv("HEXTILE_BOOTSTRAP_DIR", str(tmp_path))
    opened: list[object] = []
    client = Client(follow_record=True, opener=lambda *args, **_kwargs: opened.append(args))
    with pytest.raises(HextileClientError) as caught:
        client.get_json("/api/agent/mcp-status")
    assert caught.value.kind == ENDPOINT_UNVERIFIED
    assert opened == []
    assert client.base_url != "http://127.0.0.1:8000"
    server = HextileMcpServer()
    assert server.internal_mode is False
    assert server.client.base_url != "http://127.0.0.1:8000"
    assert server.client.endpoint_resolution is not None
    assert server.client.endpoint_resolution.status == ENDPOINT_UNVERIFIED


def test_port_is_not_a_preference_and_uncertain_writes_do_not_replay() -> None:
    assert "port" not in _PREFERENCE_UPDATE_FIELDS
    assert "actual_port" not in _PREFERENCE_UPDATE_FIELDS
    assert "Do not replay" in _SETTINGS_UNKNOWN
