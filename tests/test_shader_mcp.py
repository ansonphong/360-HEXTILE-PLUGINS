"""get_shader_context and propose_shader are thin proxies, not apply or import."""

from __future__ import annotations

import json
import ast
import http.client
import hashlib
import importlib.util
import io
import re
import asyncio
import urllib.error
from copy import deepcopy

import jsonschema
import sys
from pathlib import Path, PurePosixPath
from typing import Any
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from hextile_client import Client, HextileClientError  # noqa: E402
from hextile_mcp import TOOLS, HextileMcpServer  # noqa: E402


def _schema(name: str) -> dict[str, Any]:
    return next(tool for tool in TOOLS if tool["name"] == name)


def test_shader_output_extensions_use_closed_profiles_and_image_block(monkeypatch) -> None:
    # The MCP host may be Linux while the APP owns Windows-native paths.
    monkeypatch.setattr("hextile_client.Path", PurePosixPath)
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    descriptor = lambda name: next(item for item in SHADER_EXTENSION_TOOLS if item["name"] == name)
    names = {item["name"] for item in SHADER_EXTENSION_TOOLS}
    expected = {"shader_request_preview", "shader_get_preview", "shader_release_preview",
                "shader_preflight_still_export", "shader_export_still", "shader_get_output_job",
                "shader_stop_output_job", "shader_export_bundle", "shader_export_to_project"}
    assert expected <= names
    shader = {"origin": "user", "shaderId": "aurora"}
    digest = "sha256:" + "a" * 64
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    owner = {"request_id": request_id, "shader": shader, "project_context_witness": "w",
             "base": {"kind": "saved", "working_revision": 1,
                      "document_hash": digest, "source_hash": digest},
             "studio_surface_id": "surface", "expected_edit_sequence": 1}
    preview = {**owner, "output": {"projection": "equirectangular", "pan": 0, "tilt": 0, "roll": 0}}
    jsonschema.validate(preview, descriptor("shader_request_preview")["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**preview, "output": {**preview["output"], "path": "C:/pixels.png"}},
                            descriptor("shader_request_preview")["inputSchema"])
    still = {**owner, "profile": "shader-linear-rgba-exr/1",
             "output": {"width": 2048, "height": 1024, "output_path": "D:/Temp/test.png"}}
    jsonschema.validate(still, descriptor("shader_preflight_still_export")["inputSchema"])
    jsonschema.validate({key: value for key, value in still.items() if key != "output"} |
                        {"preflight_request_id": request_id},
                        descriptor("shader_export_still")["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({key: value for key, value in still.items() if key not in {"output", "profile"}} |
                            {"preflight_request_id": request_id},
                            descriptor("shader_export_still")["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**still, "destination": "C:/pixels.exr"},
                            descriptor("shader_preflight_still_export")["inputSchema"])
    calls = []
    client = Client(opener=lambda *_a, **_k: pytest.fail("request_json is injected"))
    def reply(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        return {"request_id": request_id, "state": "pending"}
    monkeypatch.setattr(client, "request_json", reply)
    assert client.request_shader_preview(preview)["state"] == "pending"
    assert calls[-1][1].endswith("/output/preview")
    assert client.preflight_shader_still(still)["state"] == "pending"
    assert calls[-1][1].endswith("/output/still/preflight")
    applied = {"schema": 1, "request_id": request_id, "operation": "shader_capture_output",
               "state": "applied", "shader": shader, "project_context_witness": "w",
               "transition": {"from_edit_sequence": 1, "to_edit_sequence": 1,
                              "from_base": {**{key: preview["base"][key] for key in
                                               ("working_revision", "document_hash", "source_hash")},
                                            "manifest_hash": digest},
                              "to_base": {**{key: preview["base"][key] for key in
                                             ("working_revision", "document_hash", "source_hash")},
                                          "manifest_hash": digest}}}
    monkeypatch.setattr(client, "request_json", lambda *_a, **_k: applied)
    assert client.request_shader_preview(preview)["state"] == "applied"
    monkeypatch.setattr(client, "request_json", reply)
    with pytest.raises(HextileClientError):
        client.preflight_shader_still({**still, "output": {**still["output"], "path": "C:/pixels.exr"}})
    with pytest.raises(HextileClientError):
        client.preflight_shader_still({**still, "profile": ["png-master/1"]})
    for destination in (r"C:\out\frame.hexshader", "C:/out/frame.hexshader",
                        r"\\server\share\frame.hexshader", "/data/frame.hexshader"):
        bundle = {**owner, "output_path": destination, "expected_looks": [], "expected_provenance_hash": None}
        saved = {"request_id": request_id, "state": "saved", "output_name": "frame.hexshader",
                 "output_path": destination, "resource_count": 0, "resource_bytes": 0}
        monkeypatch.setattr(client, "request_json", lambda *a, row=saved, **k: row)
        assert client.export_shader_bundle(bundle) == saved
        project = {**owner, "destination_project": destination.rsplit("/", 1)[0] if "/" in destination else destination.rsplit("\\", 1)[0]}
        copied = {"request_id": request_id, "state": "accepted", "shader_id": "copied", "target_name": "Project",
                  "destination_project": project["destination_project"]}
        monkeypatch.setattr(client, "request_json", lambda *a, row=copied, **k: row)
        assert client.export_shader_to_project(project) == copied
        monkeypatch.setattr(client, "request_json", lambda *a, row={**saved, "output_path": "relative.hexshader"}, **k: row)
        with pytest.raises(HextileClientError): client.export_shader_bundle(bundle)
        monkeypatch.setattr(client, "request_json", lambda *a, row={**copied, "destination_project": "relative"}, **k: row)
        with pytest.raises(HextileClientError): client.export_shader_to_project(project)
    for relative in ("relative/file.hexshader", r"C:file.hexshader", r"\file.hexshader"):
        with pytest.raises(HextileClientError): client.export_shader_bundle({**bundle, "output_path": relative})
        with pytest.raises(HextileClientError): client.export_shader_to_project({**project, "destination_project": relative})
        with pytest.raises(HextileClientError): client.preflight_shader_still({**still, "output": {**still["output"], "output_path": relative}})
    image_args = {"shader": shader, "project_context_witness": "w", "request_id": request_id, "image": True}
    monkeypatch.setattr(client, "request_shader_preview_image", lambda *_a: b"\x89PNG\r\n\x1a\nFAKE")
    result = HextileMcpServer(client=client).call_tool("shader_get_preview", image_args)
    assert result["content"][0]["type"] == "image" and result["content"][0]["mimeType"] == "image/png"
    assert all(block["type"] != "text" for block in result["content"])


def test_shader_preview_binary_transport_requires_explicit_image_opt_in() -> None:
    shader = {"origin": "user", "shaderId": "aurora"}
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    args = {"shader": shader, "project_context_witness": "w", "request_id": request_id}
    seen = []
    class Reply(io.BytesIO):
        def __init__(self, data, content_type):
            super().__init__(data)
            self.headers = {"Content-Type": content_type}
            self.status = 200
        def getcode(self):
            return 200
    def opener(request, timeout=None):
        seen.append(request)
        if "image=true" in request.full_url:
            return Reply(b"\x89PNG\r\n\x1a\nFAKE", "image/png")
        return Reply(json.dumps({"request_id": request_id, "state": "ready", "width": 2,
                                 "height": 1, "sha256": "sha256:" + "a" * 64,
                                 "format": "rgb8-srgb-top-origin"}).encode(), "application/json")
    client = Client(opener=opener)
    metadata = client.get_shader_preview(args)
    assert metadata["state"] == "ready" and seen[-1].headers["X-hextile-agent"] == "mcp"
    image = client.get_shader_preview({**args, "image": True})
    assert isinstance(image, bytes) and image.startswith(b"\x89PNG")
    assert "image=true" in seen[-1].full_url


def test_known_shader_output_job_recovers_through_disabled_mcp_proxy(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    calls = []
    def reply(method, path, body=None, **kwargs):
        calls.append((method, path))
        if path == "/api/agent/mcp-status":
            return {"enabled": False}
        return {"request_id": request_id, "profile": "png-master/1", "publication": "unknown",
                "job": {"id": "a" * 32, "shader_ref": {"origin": "user", "shaderId": "aurora"},
                        "state": "completed", "progress": 1.0, "output_identity": None}}
    monkeypatch.setattr(client, "request_json", reply)
    server = HextileMcpServer(client=client)
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    args = {"request_id": request_id, "shader": {"origin": "user", "shaderId": "aurora"},
            "project_context_witness": "w", "profile": "png-master/1"}
    result = server.call_tool("shader_get_output_job", args)
    assert result["isError"] is False and calls == [("GET", "/api/shaders/agent-operations/output/jobs/" + request_id)]
    server.call_tool("shader_stop_output_job", args)
    assert calls[-1] == ("POST", "/api/shaders/agent-operations/output/jobs/" + request_id + "/stop")
    assert server.call_tool("shader_request_preview", {})["isError"] is True
    assert calls[-1] == ("GET", "/api/agent/mcp-status")


def test_shader_output_receipts_refuse_wrong_identity_and_private_fields(monkeypatch) -> None:
    client = Client(opener=lambda *_a, **_k: pytest.fail("request_json is injected"))
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    shader = {"origin": "user", "shaderId": "aurora"}
    digest = "sha256:" + "a" * 64
    owner = {"request_id": request_id, "shader": shader, "project_context_witness": "w",
             "base": {"kind": "saved", "working_revision": 1,
                      "document_hash": digest, "source_hash": digest},
             "studio_surface_id": "surface", "expected_edit_sequence": 1}
    preview = {**owner, "output": {"projection": "equirectangular", "pan": 0, "tilt": 0, "roll": 0}}
    replies = [{"request_id": "wrong-id", "state": "pending"},
               {"request_id": request_id, "state": "pending", "private_path": "D:/secret"},
               {"request_id": request_id, "state": "saved"},
               {"request_id": request_id, "state": "pending", "padding": "x" * 32768}]
    calls = []
    def reply(method, path, body=None, **kwargs):
        calls.append((method, path))
        return replies.pop(0)
    monkeypatch.setattr(client, "request_json", reply)
    for _ in range(4):
        with pytest.raises(HextileClientError) as error:
            client.request_shader_preview(preview)
        assert error.value.kind == "shader_output_outcome_unknown"
    assert len(calls) == 4
    job = {"id": "a" * 32, "shader_ref": shader, "state": "completed",
           "progress": 1.0, "output_identity": None}
    replies[:] = [{"request_id": request_id, "profile": "dome-png/1", "job": job},
                 {"request_id": request_id, "profile": "png-master/1",
                  "job": {**job, "private_path": "D:/secret"}},
                 {"request_id": request_id, "profile": "png-master/1",
                  "job": {**job, "progress": "done"}}]
    for _ in range(3):
        with pytest.raises(HextileClientError):
            client.get_shader_output_job({"request_id": request_id, "shader": shader,
                                          "project_context_witness": "w", "profile": "png-master/1"})
    assert len(calls) == 7


def test_shader_create_paste_is_closed_and_uses_creation_status(monkeypatch) -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    descriptor = next(item for item in SHADER_EXTENSION_TOOLS if item["name"] == "shader_create_asset")
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    paste = {"request_id": request_id, "project_context_witness": "w", "action": "paste",
             "source": "// λ\r\nvoid main(){}\n"}
    jsonschema.validate(paste, descriptor["inputSchema"])
    for wrong in ({**paste, "template_id": "hx_starter"},
                  {**paste, "source": ""},
                  {**paste, "action": "new"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(wrong, descriptor["inputSchema"])
    client = Client(opener=lambda *_a, **_k: pytest.fail("request_json is injected"))
    calls = []
    def reply(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        return {"schema": 1, "request_id": request_id, "operation": "shader_create_asset",
                "scope": "creation", "state": "saved", "project_context_witness": "w",
                "receipt": {"shader": {"origin": "user", "shaderId": "shader_created"},
                            "working_revision": 1, "document_hash": "sha256:" + "a" * 64,
                            "source_hash": "sha256:" + "b" * 64, "manifest_hash": None}}
    monkeypatch.setattr(client, "request_json", reply)
    result = client.create_shader_asset(paste)
    assert result["scope"] == "creation" and "source" not in result
    status = client.get_shader_operation({"request_id": request_id,
        "project_context_witness": "w", "scope": "creation"})
    assert status["scope"] == "creation" and calls[-1][3]["params"]["scope"] == "creation"
    assert "origin" not in calls[-1][3]["params"]


def test_shader_output_original_status_refuses_private_result(monkeypatch) -> None:
    client = Client(opener=lambda *_a, **_k: pytest.fail("request_json is injected"))
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    shader = {"origin": "user", "shaderId": "aurora"}
    args = {"request_id": request_id, "project_context_witness": "w", "shader": shader,
            "scope": "output"}
    monkeypatch.setattr(client, "request_json", lambda *_a, **_k: {
        "schema": 1, "request_id": request_id, "scope": "output", "operation": "shader_export_bundle",
        "project_context_witness": "w", "shader": shader, "state": "saved",
        "receipt": {"request_id": request_id, "state": "saved", "private_path": "D:/secret"}})
    with pytest.raises(HextileClientError):
        client.get_shader_operation(args)


def test_resource_and_library_extensions_have_closed_explicit_transport(monkeypatch) -> None:
    # The MCP host may be Linux while the APP owns Windows-native paths.
    monkeypatch.setattr("hextile_client.Path", PurePosixPath)
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    names = {item["name"] for item in SHADER_EXTENSION_TOOLS}
    assert {"shader_stage_resource", "shader_set_resource", "shader_get_library_organization",
            "shader_organize_library", "shader_set_tags", "shader_set_project_conventions"} <= names
    descriptor = lambda name: next(item for item in SHADER_EXTENSION_TOOLS if item["name"] == name)
    ref = {"origin": "user", "shaderId": "aurora"}
    digest = "sha256:" + "a" * 64
    base = {"kind": "saved", "working_revision": 1, "document_hash": digest, "source_hash": digest}
    target = {"shader": ref, "project_context_witness": "w", "base": base, "expected_working_digest": digest}
    source = {"kind": "local_path", "paths": ["D:/frames/1.png", "D:/frames/2.png"], "fps_num": 24, "fps_den": 1}
    stage = {**target, "source": source}
    jsonschema.validate(stage, descriptor("shader_stage_resource")["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**stage, "path": "C:/private.png"}, descriptor("shader_stage_resource")["inputSchema"])
    client = Client("http://127.0.0.1:9")
    calls = []
    def reply(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        if path.endswith("/resources/stage"):
            return {"schema": 1, "shader": ref, "project_context_witness": "w", "staged_token": "stage",
                    "frames": [{"index": 0, "sha256": digest, "width": 2, "height": 2},
                               {"index": 1, "sha256": digest, "width": 2, "height": 2}],
                    "frame_count": 2, "canonical_hash": None, "estimated_bytes": 100, "expires_in": 300}
        if method == "GET":
            return {"schema": 1, "project_context_witness": "w", "origin": "user", "status": "ready",
                    "revision": "b" * 64, "folders": [], "assigned_shader_ids": [], "next_cursor": None}
        return {"schema": 1, "request_id": body["request_id"], "operation":
                "shader_set_resource" if path.endswith("/resources/set") else "shader_organize_library",
                "state": "saved", "project_context_witness": "w"}
    monkeypatch.setattr(client, "request_json", reply)
    assert len(client.stage_shader_resource(stage)["frames"]) == 2
    assert calls[-1][1].endswith("/resources/stage")
    for native in (r"C:\frames\one.png", "C:/frames/one.png", r"\\server\share\one.png", "/frames/one.png"):
        assert client.stage_shader_resource({**stage, "source": {"kind": "local_path", "path": native}})["frame_count"] == 2
        assert calls[-1][2]["source"]["path"] == native
    for relative in ("frames/one.png", r"C:one.png", r"\one.png"):
        with pytest.raises(HextileClientError): client.stage_shader_resource({**stage, "source": {"kind": "local_path", "path": relative}})
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    mutation = {**target, "request_id": request_id, "action": "attach", "slot_id": "input1",
                "staged_token": "stage", "library_intent": "saved",
                "confirmation_scope": {"operation": "shader_set_resource", "shader": ref}}
    jsonschema.validate(mutation, descriptor("shader_set_resource")["inputSchema"])
    assert client.set_shader_resource(mutation)["state"] == "saved"
    assert calls[-1][1].endswith("/resources/set")
    assert client.get_shader_library_organization({"project_context_witness": "w", "origin": "user"})["revision"] == "b" * 64
    assert calls[-1][1].endswith("/library/organization")
    with pytest.raises(HextileClientError):
        client.set_shader_resource({**mutation, "path": "C:/private.png"})


def test_organization_tags_and_conventions_forward_only_native_closed_actions(monkeypatch) -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    descriptor = lambda name: next(item for item in SHADER_EXTENSION_TOOLS if item["name"] == name)
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    session_id = "c63dffab-15b2-4752-9f54-729cf3922b09"
    revision = "a" * 64
    org = {"request_id": request_id, "project_context_witness": "w", "origin": "user",
           "library_session_id": session_id, "expected_revision": revision,
           "command": {"kind": "moveShaders", "shaderIds": ["aurora", "borealis"], "folderId": None}}
    jsonschema.validate(org, descriptor("shader_organize_library")["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**org, "command": {**org["command"], "shaderIds": ["aurora", "aurora"]}},
                            descriptor("shader_organize_library")["inputSchema"])
    tags = {"request_id": request_id, "project_context_witness": "w", "command": {
        "kind": "setShaderTag", "shader": {"origin": "user", "shaderId": "aurora"},
        "tagId": "favorite", "assigned": True}}
    conventions = {"request_id": request_id, "project_context_witness": "w",
                   "expected_digest": revision, "profiles": [], "default_profile_id": None}
    jsonschema.validate(tags, descriptor("shader_set_tags")["inputSchema"])
    jsonschema.validate(conventions, descriptor("shader_set_project_conventions")["inputSchema"])
    calls = []
    client = Client("http://127.0.0.1:9")
    def reply(method, path, body=None, **kwargs):
        calls.append((method, path, body))
        operation = {"organize": "shader_organize_library", "tags": "shader_set_tags",
                     "project-conventions": "shader_set_project_conventions"}[path.rsplit("/", 1)[-1]]
        return {"schema": 1, "request_id": body["request_id"], "operation": operation, "state": "saved"}
    monkeypatch.setattr(client, "request_json", reply)
    assert client.organize_shader_library(org)["state"] == "saved"
    assert client.set_shader_tags(tags)["state"] == "saved"
    assert client.set_shader_project_conventions(conventions)["state"] == "saved"
    assert [path for _, path, _ in calls] == ["/api/shaders/agent-operations/library/organize",
        "/api/shaders/agent-operations/library/tags", "/api/shaders/agent-operations/project-conventions"]
    with pytest.raises(HextileClientError):
        client.organize_shader_library({**org, "path": "/private"})


def test_shader_authoring_actions_have_closed_named_transport(monkeypatch) -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    names = {tool["name"] for tool in SHADER_EXTENSION_TOOLS}
    assert {"shader_set_capture", "shader_control_clock", "shader_step_frame"} <= names
    client = Client("http://127.0.0.1:9")
    calls = []
    monkeypatch.setattr(client, "request_json", lambda method, path, body=None, **kwargs:
                        calls.append((method, path, body, kwargs)) or
                        {"schema": 1, "request_id": body["request_id"], "state": "pending",
                         "operation": {"capture": "shader_set_capture", "clock": "shader_control_clock",
                                       "frame-step": "shader_step_frame"}[path.rsplit("/", 1)[-1]]})
    target = {"shader": {"origin": "user", "shaderId": "aurora"},
              "project_context_witness": "witness", "studio_surface_id": "surface",
              "request_id": "7e720fa5-192b-47da-a705-ab3b5ddc979e",
              "expected_edit_sequence": 3}
    assert client.set_shader_capture({**target, "action": "live_seed", "seed": 7})["state"] == "pending"
    assert calls[-1][1].endswith("/capture")
    assert client.control_shader_clock({**target, "action": "align"})["state"] == "pending"
    assert calls[-1][1].endswith("/clock")
    assert client.step_shader_frame({**target, "direction": 1, "owner": {"owner_id": "view",
        "owner_generation": 1, "viewer_generation": 2, "source_epoch": 3}})["state"] == "pending"
    assert calls[-1][1].endswith("/frame-step")
    with pytest.raises(HextileClientError):
        client.set_shader_capture({**target, "action": "live_seed", "seed": 7, "actor": "human"})


def test_credits_metadata_and_research_transport_are_closed(monkeypatch) -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    names = {tool["name"] for tool in SHADER_EXTENSION_TOOLS}
    assert {"shader_get_credits", "shader_propose_credits", "shader_research_sources"} <= names
    ref = {"origin": "user", "shaderId": "aurora"}
    target = {"shader": ref, "project_context_witness": "wit"}
    read = {**target, "section": "sources", "cursor": 0, "limit": 16}
    jsonschema.validate(read, next(tool for tool in SHADER_EXTENSION_TOOLS
                                   if tool["name"] == "shader_get_credits")["inputSchema"])
    calls = []
    client = Client("http://127.0.0.1:9")
    monkeypatch.setattr(client, "request_json", lambda method, path, body=None, **kwargs:
                        calls.append((method, path, body, kwargs)) or
                        ({"schema": 1, "target": ref, "section": "sources", "sources": [],
                          "provenance_hash": None, "base": {}, "working_digest": None}
                         if method == "GET" else {"schema": 1, "state": "pending", "request_id": body["request_id"]}
                         if path.endswith("/credits/proposals") else {"schema": 1, "pages": []}))
    assert client.get_shader_credits(read)["sources"] == []
    assert calls[-1][1].endswith("/credits")
    from uuid import uuid4
    proposal = {**target, "request_id": str(uuid4()), "base": {"kind": "saved", "working_revision": 1,
        "document_hash": "sha256:" + "a" * 64, "source_hash": "sha256:" + "b" * 64},
        "working_digest": "sha256:" + "c" * 64, "expected_provenance_hash": None,
        "changes": {"author": "Artist"}}
    jsonschema.validate(proposal, next(tool for tool in SHADER_EXTENSION_TOOLS
                                       if tool["name"] == "shader_propose_credits")["inputSchema"])
    assert client.propose_shader_credits(proposal)["state"] == "pending"
    assert calls[-1][2] == proposal
    assert client.research_shader_sources({**target, "source_url": "https://example.com"})["pages"] == []
    with pytest.raises(HextileClientError):
        client.propose_shader_credits({**proposal, "changes": {"distribution": {}}})


def test_credits_text_chunk_transport_is_closed_and_forwards_utf8_offset(monkeypatch) -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    descriptor = next(tool for tool in SHADER_EXTENSION_TOOLS if tool["name"] == "shader_get_credits")
    ref = {"origin": "user", "shaderId": "aurora"}
    text_ref = "ct1:sha256:" + "a" * 64 + ":notices:0:license_text"
    args = {"shader": ref, "project_context_witness": "witness", "section": "text", "text_ref": text_ref, "offset_utf8": 4096}
    jsonschema.validate(args, descriptor["inputSchema"])
    client = Client("http://127.0.0.1:9")
    seen = {}
    def reply(method, path, body=None, **kwargs):
        seen.update(method=method, path=path, params=kwargs["params"])
        return {"schema": 1, "target": ref, "provenance_hash": "sha256:" + "a" * 64,
                "section": "text", "text_ref": text_ref, "offset_utf8": 4096,
                "text": "é", "total_bytes": 4098, "next_offset_utf8": None,
                "base": {"kind": "saved", "working_revision": 1,
                         "document_hash": "sha256:" + "b" * 64, "source_hash": "sha256:" + "c" * 64},
                "working_digest": "sha256:" + "d" * 64}
    monkeypatch.setattr(client, "request_json", reply)
    assert client.get_shader_credits(args)["text"] == "é"
    assert seen["params"]["text_ref"] == text_ref and seen["params"]["offset_utf8"] == 4096
    with pytest.raises(HextileClientError):
        client.get_shader_credits({**args, "path": "/tmp/private"})
    monkeypatch.setattr(client, "request_json", lambda *a, **k: {**reply("GET", "", params={}), "raw_provenance": {}})
    with pytest.raises(HextileClientError):
        client.get_shader_credits(args)


def test_credits_distribution_summary_is_closed_without_raw_rights(monkeypatch) -> None:
    ref = {"origin": "builtin", "shaderId": "hx_starter"}
    args = {"shader": ref, "project_context_witness": "wit"}
    page = {"schema": 1, "target": ref, "section": "sources", "sources": [],
            "provenance_hash": "sha256:" + "a" * 64,
            "original_source_hash": "sha256:" + "b" * 64,
            "distribution": {"schema": 1, "rights": "declared", "source_hash": "sha256:" + "c" * 64,
                             "original_sha256": None, "licenses_total": 2, "has_opaque_fields": True}}
    client = Client("http://127.0.0.1:9")
    monkeypatch.setattr(client, "request_json", lambda *a, **k: page)
    assert client.get_shader_credits(args)["distribution"]["licenses_total"] == 2
    monkeypatch.setattr(client, "request_json", lambda *a, **k: {**page,
        "distribution": {**page["distribution"], "raw_licenses": ["private"]}})
    with pytest.raises(HextileClientError):
        client.get_shader_credits(args)


def test_register_forwards_typed_source_proposal_without_changing_digest(monkeypatch) -> None:
    args = _workspace_register()
    source_proposal = {"schema": 1, "expected_provenance_hash": None, "sources": [{"kind": "append",
        "row": {"author": "Adapter", "license_status": "unknown",
                "evidence": {"basis": "observed", "note": "source"}}}]}
    args["source_proposal"] = source_proposal
    jsonschema.validate(args, _schema("register_shader_update")["inputSchema"])
    sent = {}
    client = Client("http://127.0.0.1:9")
    monkeypatch.setattr(client, "_shader_workspace_request", lambda method, path, body=None:
                        sent.update(body=body) or {"handle": args["handle"], "change_id": args["change_id"],
                        "content_digest": args["content_digest"], "generation": 1, "candidate_id": "candidate"})
    client.register_shader_update(args)
    assert sent["body"]["source_proposal"] == source_proposal
    assert sent["body"]["content_digest"] == args["content_digest"]
    with pytest.raises(HextileClientError):
        client.register_shader_update({**args, "source_proposal": {**source_proposal, "sources": [
            {"kind": "remove", "index": 0}]}})


def test_native_shader_extension_routes_are_explicit_and_closed() -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS

    names = {tool["name"] for tool in SHADER_EXTENSION_TOOLS}
    assert {"shader_list_assets", "shader_get_history", "shader_get_looks",
            "shader_get_project_conventions"} <= names
    assert {"shader_get_proposal", "shader_get_workspace", "shader_recheck_update",
            "shader_stop_workspace"} <= names
    assert {"shader_get_asset_state", "shader_rename_asset", "shader_delete_asset",
            "shader_open_asset", "shader_save_asset", "shader_create_asset", "shader_fork_asset",
            "shader_save_as", "shader_import_bundle", "shader_get_operation"} <= names
    assert {"shader_save_look", "shader_apply_look", "shader_rename_look", "shader_delete_look",
            "shader_checkpoint", "shader_restore_revision", "shader_copy_revision",
            "shader_history_retention"} <= names
    assert "shader_apply_mutation" not in names
    server = HextileMcpServer(client=mock.Mock())
    listed = server.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert names <= {tool["name"] for tool in listed["result"]["tools"]}
    assert names <= set(server._handlers)
    for tool in SHADER_EXTENSION_TOOLS:
        assert tool["inputSchema"]["additionalProperties"] is False
        assert not {"actor", "mutation", "authority_ticket", "path"} & set(tool["inputSchema"]["properties"])


def test_named_history_client_forwards_closed_intent_and_keeps_unknown_request(monkeypatch):
    from hextile_client import Client, HextileClientError
    client = Client("http://127.0.0.1:9")
    request_id = "b5897a63-59a1-4d8f-aecb-36ba083fc1ea"
    shader = {"origin": "user", "shaderId": "aurora"}
    base = {"kind": "saved", "working_revision": 2,
            "document_hash": "sha256:" + "a" * 64, "source_hash": "sha256:" + "b" * 64}
    args = {"request_id": request_id, "shader": shader, "project_context_witness": "wit",
            "base": base, "expected_working_digest": "sha256:" + "c" * 64,
            "library_intent": "saved",
            "confirmation_scope": {"operation": "shader_checkpoint_save", "shader": shader},
            "action": "save", "title": "Before"}
    sent = []
    monkeypatch.setattr(client, "request_json", lambda method, path, body:
                        sent.append((method, path, body)) or {"request_id": request_id,
                            "operation": "shader_checkpoint_save", "state": "saved"})
    assert client.shader_checkpoint(args)["state"] == "saved"
    assert sent == [("POST", "/api/shaders/agent-operations/checkpoint", args)]
    with pytest.raises(HextileClientError):
        client.shader_checkpoint({**args, "confirmation_scope": {"operation": "shader_checkpoint_remove", "shader": shader}})
    with pytest.raises(HextileClientError):
        client.shader_checkpoint({**args, "mutation": {"kind": "checkpoint_save"}})


def test_delete_shader_asset_forwards_exact_intent_and_recovers_unknown(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    request_id = "b5897a63-59a1-4d8f-aecb-36ba083fc1ea"
    ref = {"origin": "user", "shaderId": "aurora"}
    body = {"request_id": request_id, "shader": ref, "project_context_witness": "wit",
            "base": {"kind": "saved", "working_revision": 1,
                     "document_hash": "sha256:" + "a" * 64, "source_hash": "sha256:" + "b" * 64},
            "expected_working_digest": "sha256:" + "c" * 64,
            "library_intent": "saved", "confirmation_scope": {"operation": "delete", "shader": ref}}
    sent = []
    monkeypatch.setattr(client, "request_json", lambda method, path, payload:
                        sent.append((method, path, payload)) or {"request_id": request_id,
                            "operation": "shader_save_asset" if path.endswith("/save") else
                                         "shader_save_as" if path.endswith("/save-as") else "shader_open_asset",
                            "state": "applied"})
    assert client.delete_shader_asset(body)["state"] == "applied"
    assert sent == [("POST", "/api/shaders/agent-operations/delete", body)]
    with pytest.raises(HextileClientError):
        client.delete_shader_asset({**body, "confirmation_scope": {"operation": "rename", "shader": ref}})
    mounted = {"request_id": request_id, "shader": ref, "project_context_witness": "wit",
               "studio_surface_id": "surface", "expected_edit_sequence": 2,
               "target": {"origin": "builtin", "shaderId": "hx_starter"}}
    assert client.open_shader_asset(mounted)["state"] == "applied"
    assert sent[-1] == ("POST", "/api/shaders/agent-operations/open", mounted)
    with pytest.raises(HextileClientError):
        client.open_shader_asset({**mounted, "target": ref})
    save = {key: value for key, value in mounted.items() if key != "target"}
    assert client.save_shader_asset(save)["state"] == "applied"
    assert sent[-1] == ("POST", "/api/shaders/agent-operations/save", save)
    with pytest.raises(HextileClientError):
        client.save_shader_asset({**save, "shader": {"origin": "builtin", "shaderId": "hx_starter"}})
    as_copy = {**save, "title": "A copy"}
    assert client.save_shader_as(as_copy)["state"] == "applied"
    assert sent[-1] == ("POST", "/api/shaders/agent-operations/save-as", as_copy)
    with pytest.raises(HextileClientError):
        client.save_shader_as({**as_copy, "title": ""})


def test_native_new_and_fork_forward_only_closed_creation(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    sent = []
    monkeypatch.setattr(client, "request_json", lambda method, path, body:
                        sent.append((method, path, body)) or {"request_id": body["request_id"],
                            "operation": "shader_create_asset" if body["action"] == "new" else "shader_fork_asset",
                            "state": "saved", "receipt": {"shader": {"origin": "user", "shaderId": "result"}}})
    common = {"request_id": "b5897a63-59a1-4d8f-aecb-36ba083fc1ea",
              "project_context_witness": "wit"}
    new = {**common, "action": "new", "template_id": "hx_starter"}
    assert client.create_shader_asset(new)["state"] == "saved"
    assert sent[-1] == ("POST", "/api/shaders/agent-operations/create", new)
    with pytest.raises(HextileClientError):
        client.create_shader_asset({**new, "template_id": "arbitrary"})
    fork = {**common, "action": "fork", "shader": {"origin": "user", "shaderId": "source"},
            "expected_document_hash": "sha256:" + "a" * 64}
    assert client.fork_shader_asset(fork)["state"] == "saved"
    assert sent[-1] == ("POST", "/api/shaders/agent-operations/create", fork)
    with pytest.raises(HextileClientError):
        client.fork_shader_asset({**fork, "actor": "human"})


def test_import_bundle_uses_only_selected_grant_and_closed_receipt(monkeypatch) -> None:
    # The MCP host may be Linux while the APP owns Windows-native paths.
    monkeypatch.setattr("hextile_client.Path", PurePosixPath)
    client = Client("http://127.0.0.1:9")
    digest = "sha256:" + "b" * 64
    args = {"request_id": "b5897a63-59a1-4d8f-aecb-36ba083fc1ea", "project_context_witness": "wit",
            "input_path": "D:/task/input.hexshader", "collision_intent": "fork"}
    receipt = {"schema": 1, "request_id": args["request_id"], "operation": "shader_import_bundle",
        "scope": "creation", "state": "saved", "project_context_witness": "wit", "receipt": {
            "shader": {"origin": "user", "shaderId": "imported"}, "working_revision": 1,
            "document_hash": digest, "source_hash": digest, "manifest_hash": None, "bundle_sha256": digest}}
    calls = []
    def reply(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        return receipt
    monkeypatch.setattr(client, "request_json", reply)
    assert client.import_shader_bundle(args) == receipt
    assert calls[-1][:3] == ("POST", "/api/shaders/agent-operations/import-bundle", args)
    assert client.import_shader_bundle({**args, "bundle_sha256": digest}) == receipt
    for native in (r"C:\task\input.hexshader", "C:/task/input.hexshader", r"\\server\share\input.hexshader", "/data/input.hexshader"):
        assert client.import_shader_bundle({**args, "input_path": native}) == receipt
        assert calls[-1][2]["input_path"] == native
    for relative in ("input.hexshader", r"C:input.hexshader", r"\input.hexshader"):
        with pytest.raises(HextileClientError): client.import_shader_bundle({**args, "input_path": relative})
    assert client.get_shader_operation({"request_id": args["request_id"], "scope": "creation",
        "project_context_witness": "wit"}) == receipt
    for changed in ({"input_path": "relative.hexshader"}, {"collision_intent": "replace"},
                    {"grant_id": "obsolete"}, {"shader": {"origin": "user", "shaderId": "dummy"}},
                    {"bundle_sha256": "sha256:" + "c" * 64}):
        with pytest.raises(HextileClientError): client.import_shader_bundle({**args, **changed})
    for change in ({"request_id": "another"}, {"project_context_witness": "another"},
                   {"scope": "asset"}, {"receipt": {**receipt["receipt"], "private": True}}):
        monkeypatch.setattr(client, "request_json", lambda *a, row={**receipt, **change}, **k: row)
        with pytest.raises(HextileClientError): client.import_shader_bundle(args)


def test_native_shader_extension_transport_and_unknown_outcome(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    calls = []
    monkeypatch.setattr(client, "request_json", lambda method, path, body=None, **kwargs:
                        calls.append((method, path, body, kwargs)) or
                        ({"request_id": body["request_id"], "state": "applied"} if body else
                         {"schema": 1, "shader": {"origin": "user", "shaderId": "aurora"},
                          "project_context_witness": "wit", "status": "saved", "provenance": "saved",
                          "base": {}, "capability": {}, "writable": False, "save_state": "saved"}
                         if path.endswith("/asset-state") else {"state": "applied"}))
    ref = {"origin": "user", "shaderId": "aurora"}
    assert client.get_shader_asset_state({"shader": ref, "project_context_witness": "wit"})["status"] == "saved"
    request_id = "b5897a63-59a1-4d8f-aecb-36ba083fc1ea"
    base = {"kind": "saved", "working_revision": 1, "document_hash": "sha256:" + "a" * 64,
            "source_hash": "sha256:" + "b" * 64}
    body = {"request_id": request_id, "shader": ref, "project_context_witness": "wit",
            "base": base, "expected_working_digest": "sha256:" + "c" * 64, "title": "Renamed"}
    assert client.rename_shader_asset(body) == {"request_id": request_id, "state": "applied"}
    assert calls[0][1].endswith("/asset-state")
    assert calls[1][1].endswith("/rename")
    assert calls[1][2] == body
    assert client.get_shader_operation({"request_id": request_id, "shader": ref,
                                        "project_context_witness": "wit"}) == {"state": "applied"}
    assert calls[2][1].endswith("/operations/" + request_id)
    with pytest.raises(HextileClientError) as error:
        client.rename_shader_asset({**body, "actor": "human"})
    assert error.value.status_code == 422
    with pytest.raises(HextileClientError) as wrong_version:
        client.rename_shader_asset({**body, "request_id": "00000000-0000-1000-8000-000000000000"})
    assert wrong_version.value.status_code == 422
    monkeypatch.setattr(client, "request_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        HextileClientError("connection lost", kind="app_down")))
    with pytest.raises(HextileClientError) as unknown:
        client.rename_shader_asset(body)
    assert unknown.value.kind == "shader_operation_outcome_unknown"
    assert unknown.value.receipt == {"request_id": request_id}


def test_native_shader_discovery_transport_rejects_unbounded_results(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    calls = []
    monkeypatch.setattr(client, "request_json", lambda method, path, body=None, **kwargs:
                        calls.append((method, path, kwargs)) or
                        ({"schema": 1, "project_context_witness": "wit", "digest": None,
                          "writable": False, "profiles": []} if path.endswith("/project-conventions")
                         else {"schema": 1, "shader": {"origin": "user", "shaderId": "aurora"},
                               "project_context_witness": "wit", "kind": "revisions",
                               "entries": [], "next_cursor": None} if path.endswith("/history")
                         else {"schema": 1, "shader": {"origin": "user", "shaderId": "aurora"},
                               "project_context_witness": "wit", "provenance": "saved",
                               "entries": []} if path.endswith("/looks")
                         else {"schema": 1, "project_context_witness": "wit", "project": {},
                               "entries": [], "next_cursor": None}))
    assert client.list_shader_assets({"project_context_witness": "wit", "shelf": "user"})["entries"] == []
    assert calls[0][1].endswith("/assets")
    assert calls[0][2]["params"]["shelf"] == "user"
    ref = {"shader": {"origin": "user", "shaderId": "aurora"}, "project_context_witness": "wit"}
    assert client.get_shader_history(ref)["entries"] == []
    assert calls[1][1].endswith("/history")
    assert client.get_shader_looks(ref)["entries"] == []
    assert calls[2][1].endswith("/looks")
    assert client.get_shader_project_conventions({"project_context_witness": "wit"})["schema"] == 1
    assert calls[3][1].endswith("/project-conventions")
    with pytest.raises(HextileClientError):
        client.list_shader_assets({"project_context_witness": "wit", "limit": 1000})
    with pytest.raises(HextileClientError):
        client.get_shader_history({**ref, "kind": "source"})
    monkeypatch.setattr(client, "request_json", lambda *_args, **_kwargs:
                        {"schema": 1, "entries": [{}] * 51})
    with pytest.raises(HextileClientError):
        client.list_shader_assets({"project_context_witness": "wit"})


def test_native_shader_recovery_transport_before_registration_and_closed_stop(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    calls = []
    handle = "workspace_1"
    witness = "wit"
    attachment = {"handle": handle, "generation": 0, "attachment_state": "attached",
                  "studio_surface_id": "surface", "mount_generation": "mount", "project_context_witness": witness,
                  "base": {}}

    def request_json(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        if path.endswith("/attachment"):
            return attachment
        if path.endswith("/shader-proposals/spt_" + "a" * 32):
            return {"ticket_id": "spt_" + "a" * 32, "ready": False,
                    "project_context_witness": witness, "lease_id": "private"}
        if method == "DELETE":
            return {**attachment, "attachment_state": "stopped"}
        raise AssertionError(path)

    monkeypatch.setattr(client, "request_json", request_json)
    status = client.get_shader_workspace_status({"handle": handle, "project_context_witness": witness})
    assert status["receipt"] is None and status["attachment"]["generation"] == 0
    assert [call[1] for call in calls] == [f"/api/agent/shader-workspaces/{handle}/attachment"]
    proposal = client.get_shader_proposal_status({"ticket_id": "spt_" + "a" * 32,
                                                   "project_context_witness": witness})
    assert proposal["ready"] is False
    assert "lease_id" not in proposal
    assert calls[-1][3]["headers"]["X-Hextile-Project-Witness"] == witness
    stopped = client.stop_shader_workspace({"handle": handle, "generation": 0,
        "studio_surface_id": "surface", "project_context_witness": witness})
    assert stopped["attachment_state"] == "stopped"
    assert calls[-1][2] == {"generation": 0, "studio_surface_id": "surface",
                            "project_context_witness": witness}
    with pytest.raises(HextileClientError):
        client.stop_shader_workspace({"handle": handle, "generation": 0,
            "studio_surface_id": "surface", "project_context_witness": witness,
            "action": "take_control"})
    with pytest.raises(HextileClientError):
        client.get_shader_proposal_status({"ticket_id": "cpr_" + "a" * 32,
                                           "project_context_witness": witness})
    monkeypatch.setattr(client, "request_json", lambda *_args, **_kwargs:
                        (_ for _ in ()).throw(HextileClientError("lost reply", kind="app_down")))
    with pytest.raises(HextileClientError) as unknown:
        client.stop_shader_workspace({"handle": handle, "generation": 0,
            "studio_surface_id": "surface", "project_context_witness": witness})
    assert unknown.value.kind == "workspace_outcome_unknown"
    assert unknown.value.receipt == {"handle": handle}


def test_native_shader_recheck_uses_same_candidate_and_source_free_status(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    handle = "workspace_1"
    change_id = handle + ":1"
    digest = "sha256:" + "a" * 64
    calls = []
    attachment = {"handle": handle, "generation": 1, "attachment_state": "attached",
                  "studio_surface_id": "surface", "project_context_witness": "wit",
                  "candidate_id": "candidate", "change_id": change_id}
    receipt = {"handle": handle, "change_id": change_id, "candidate_id": "candidate",
               "generation": 1, "content_digest": digest, "check_attempt": 0,
               "studio_surface_id": "surface", "project_context_witness": "wit",
               "save": "not_saved", "prepare": "passed", "raw_log": "private"}

    def request_json(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        if path.endswith("/attachment"):
            return attachment
        if method == "GET" and path.endswith("/updates/" + handle + "%3A1"):
            return receipt
        if method == "POST" and path.endswith("/recheck"):
            return {key: value for key, value in {**receipt, "check_attempt": 1,
                                                  "diagnostics": [{"message": "private"}]}.items()
                    if key != "raw_log"}
        raise AssertionError(path)

    monkeypatch.setattr(client, "request_json", request_json)
    status = client.get_shader_workspace_status({"handle": handle, "project_context_witness": "wit"})
    assert status["receipt"]["candidate_id"] == "candidate"
    assert "raw_log" not in status["receipt"] and "source_diagnostics" not in status["receipt"]
    assert calls[1][3]["params"] == {"project_context_witness": "wit"}
    rechecked = client.recheck_shader_update({"handle": handle, "change_id": change_id,
        "generation": 1, "content_digest": digest, "studio_surface_id": "surface",
        "project_context_witness": "wit"})
    assert rechecked["candidate_id"] == "candidate" and rechecked["check_attempt"] == 1
    assert "diagnostics" not in rechecked
    assert calls[-1][2] == {"generation": 1, "content_digest": digest,
                            "studio_surface_id": "surface", "project_context_witness": "wit"}
    with pytest.raises(HextileClientError):
        client.recheck_shader_update({"handle": handle, "change_id": change_id,
            "generation": True, "content_digest": digest, "studio_surface_id": "surface",
            "project_context_witness": "wit"})


def test_native_shader_recovery_status_and_stop_bypass_only_disabled_preflight(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    calls = []
    handle = "workspace_1"
    witness = "wit"
    attachment = {"handle": handle, "generation": 0, "attachment_state": "attached",
                  "studio_surface_id": "surface", "project_context_witness": witness}

    def request_json(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        if path == "/api/agent/mcp-status":
            return {"enabled": False}
        if path.endswith("/attachment"):
            return attachment
        if path.endswith("/shader-proposals/spt_" + "a" * 32):
            return {"ticket_id": "spt_" + "a" * 32, "ready": False,
                    "project_context_witness": witness}
        if method == "DELETE":
            return {**attachment, "attachment_state": "stopped"}
        raise AssertionError(path)

    monkeypatch.setattr(client, "request_json", request_json)
    server = HextileMcpServer(client=client)
    proposal_args = {"ticket_id": "spt_" + "a" * 32, "project_context_witness": witness}
    assert server.call_tool("shader_get_proposal", proposal_args).get("isError") is not True
    assert server.call_tool("shader_get_workspace", {"handle": handle,
        "project_context_witness": witness}).get("isError") is not True
    assert server.call_tool("shader_stop_workspace", {"handle": handle, "generation": 0,
        "studio_surface_id": "surface", "project_context_witness": witness}).get("isError") is not True
    assert all(call[1] != "/api/agent/mcp-status" for call in calls)
    calls.clear()
    assert server.call_tool("shader_recheck_update", {}).get("isError") is True
    assert [call[1] for call in calls] == ["/api/agent/mcp-status"]
    calls.clear()
    assert server.call_tool("shader_get_workspace_unknown", {}).get("isError") is True
    assert [call[1] for call in calls] == ["/api/agent/mcp-status"]
    monkeypatch.setattr(client, "request_json", lambda *_args, **_kwargs:
                        {"schema": 1, "entries": [], "source": "private"})
    with pytest.raises(HextileClientError):
        client.list_shader_assets({"project_context_witness": "wit"})


def test_call_tool_allows_exact_shader_status_through_unavailable_preflight(monkeypatch) -> None:
    request_id = "b5897a63-59a1-4d8f-aecb-36ba083fc1ea"
    args = {"request_id": request_id, "shader": {"origin": "user", "shaderId": "aurora"},
            "project_context_witness": "wit"}
    status = {"request_id": request_id, "state": "applied"}

    for unavailable in ("disabled", "failure"):
        client = Client("http://127.0.0.1:9")
        calls = []

        def request_json(method, path, body=None, **kwargs):
            calls.append((method, path, body, kwargs))
            if path == "/api/agent/mcp-status":
                if unavailable == "failure":
                    raise HextileClientError("offline", kind="app_down")
                return {"enabled": False}
            if path.endswith("/operations/" + request_id):
                return status
            raise AssertionError(f"unexpected request: {method} {path}")

        monkeypatch.setattr(client, "request_json", request_json)
        server = HextileMcpServer(client=client)
        recovered = server.call_tool("shader_get_operation", args)
        assert recovered.get("isError") is not True
        assert calls == [("GET", f"/api/shaders/agent-operations/operations/{request_id}", None,
                          {"params": {"origin": "user", "shader_id": "aurora", "scope": "asset",
                                       "project_context_witness": "wit"}})]

        calls.clear()
        fresh_write = {**args, "base": {}, "expected_working_digest": "sha256:" + "c" * 64,
                       "title": "Renamed"}
        refused = server.call_tool("shader_rename_asset", fresh_write)
        assert refused["isError"] is True
        assert [call[1] for call in calls] == ["/api/agent/mcp-status"]

        calls.clear()
        unknown = server.call_tool("shader_get_operation_unknown", args)
        assert unknown["isError"] is True
        assert [call[1] for call in calls] == ["/api/agent/mcp-status"]


def test_served_best_practices_preserve_shader_credit_authority() -> None:
    from hextile_mcp import load_guide

    guide = load_guide("best-practices")["markdown"]
    skill = (ROOT / "skills" / "shader" / "SKILL.md").read_text(encoding="utf-8")
    for text in (guide, skill):
        assert "extensions.lineage" in text
        assert "extensions.retained_credits" in text
        assert "ai_assistance" in text
        assert "repair registrations" in text
        assert "v1 cannot edit provenance" in text
        assert "extensions.distribution" in text
        assert "permission to distribute" in text


def test_attribution_guides_teach_limits_and_typed_proposal() -> None:
    from hextile_mcp import load_guide

    guide = load_guide("best-practices")["markdown"]
    skill = (ROOT / "skills" / "shader" / "SKILL.md").read_text(encoding="utf-8")
    for text in (guide, skill):
        assert "64 KiB" in text and "256 KiB" in text
        assert "depth at most 2" in text or "depth 2" in text
        assert "30 seconds" in text and "four" in text
        assert "attribution_proposal" in text
        assert "Attribution wasn't added in this selection edit" in text
        assert "skip_optional" in text
        assert "reopen" in text and "v2" in text
        assert "do not claim a page was read" in text.lower() or "when it was not" in text


def test_attribution_wire_negotiation_and_exact_refusal_receipt(monkeypatch) -> None:
    open_args = {
        "shader": {"origin": "user", "shaderId": "aurora"},
        "project_context_witness": "witness",
        "studio_surface_id": "surface",
        "workspace_schema": 2,
        "attribution_schema": 1,
    }
    jsonschema.validate(open_args, _schema("open_shader_workspace")["inputSchema"])
    register_args = {
        "handle": "abc", "change_id": "abc:1", "expected_generation": 0,
        "content_digest": "sha256:" + "ab" * 32, "attribution_action": "skip_optional",
    }
    jsonschema.validate(register_args, _schema("register_shader_update")["inputSchema"])
    from hextile_client import validate_shader_workspace
    validate_shader_workspace("open", open_args)
    validate_shader_workspace("register", register_args)
    sent = {}

    def capture(method, path, body=None, **kwargs):
        sent["body"] = body
        detail = {
            "code": "attribution_required",
            "message": "Write the supplied provenance bytes and register again.",
            "recovery": "write_provenance_and_rehash",
            "attribution": {
                "schema": 1, "status": "replacement_required", "generation": 7,
                "content_digest": register_args["content_digest"],
                "provenance_utf8": "{\"extensions\":{}}",
                "provenance_sha256": "sha256:" + "cd" * 32,
            },
        }
        raw = json.dumps({"detail": detail}).encode("utf-8")
        assert len(raw) <= 65536
        raise HextileClientError(
            f"HTTP 409 POST {path}: {raw.decode()}", status_code=409, body=raw.decode(), kind="http")

    client = Client("http://127.0.0.1:9")
    monkeypatch.setattr(client, "request_json", capture)
    with pytest.raises(HextileClientError) as refused:
        client.register_shader_update(register_args)
    assert sent["body"]["attribution_action"] == "skip_optional"
    assert refused.value.receipt["code"] == "attribution_required"
    assert refused.value.receipt["attribution"]["provenance_utf8"] == "{\"extensions\":{}}"
    payload = __import__("hextile_mcp", fromlist=["error_payload"]).error_payload(refused.value)
    assert payload["receipt"]["attribution"]["status"] == "replacement_required"
    assert payload["receipt"]["attribution"]["provenance_utf8"].encode("utf-8") == b"{\"extensions\":{}}"


def _parameter_witness() -> dict[str, Any]:
    return {"studio_surface_id": "surface", "project_context_witness": "wit",
            "shader": {"origin": "user", "shaderId": "aurora"},
            "base": {"working_revision": 1, "manifest_hash": None,
                     "document_hash": "sha256:" + "ab" * 32,
                     "source_hash": "sha256:" + "cd" * 32},
            "edit_sequence": 7}


def test_shader_parameter_tool_schema_and_dispatch() -> None:
    get_tool = _schema("get_shader_parameters")
    set_tool = _schema("set_shader_parameter")
    assert get_tool["inputSchema"]["additionalProperties"] is False
    assert get_tool["annotations"]["readOnlyHint"] is True
    assert set_tool["annotations"]["readOnlyHint"] is False
    submit = {"operation": "submit", "client_request_id": "known_1",
              "witness": _parameter_witness(), "parameter_id": "cellCount", "value": 44}
    status = {"operation": "status", "client_request_id": "known_1"}
    for args in (submit, status):
        jsonschema.validate(args, set_tool["inputSchema"])
    tagged = {**submit, "witness": {**submit["witness"], "base": {
        "kind": "saved", "working_revision": 1,
        "document_hash": submit["witness"]["base"]["document_hash"],
        "source_hash": submit["witness"]["base"]["source_hash"]}}}
    jsonschema.validate(tagged, set_tool["inputSchema"])
    for args in ({**submit, "source": "secret"}, {**submit, "witness": {**submit["witness"], "edit_sequence": -1}},
                 {**submit, "witness": {**submit["witness"], "source_epoch": 1}},
                 {**status, "value": 44}, {**submit, "parameter_id": ""},
                 {**submit, "session_id": "model-chosen"}, {**status, "session_id": "model-chosen"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(args, set_tool["inputSchema"])
    client = mock.Mock()
    client.get_shader_parameters.return_value = {"witness": _parameter_witness(), "parameters": []}
    client.set_shader_parameter.return_value = {"status": "pending"}
    server = HextileMcpServer(client=client)
    assert server._get_shader_parameters({})["parameters"] == []
    assert server._set_shader_parameter(submit)["status"] == "pending"
    assert server._set_shader_parameter(status)["status"] == "pending"
    session_id = server.session_id
    assert session_id is not None
    client.get_shader_parameters.assert_called_once_with(session_id=session_id)
    client.set_shader_parameter.assert_any_call(submit, session_id=session_id)
    client.set_shader_parameter.assert_any_call(status, session_id=session_id)


def test_shader_parameter_client_transport_and_unknown_recovery() -> None:
    witness = _parameter_witness()
    submit = {"operation": "submit", "client_request_id": "known_1",
              "witness": witness, "parameter_id": "cellCount", "value": 44}
    status = {"operation": "status", "client_request_id": "known_1"}
    ticket_id = "123e4567-e89b-42d3-a456-426614174000"
    session_id = "123e4567-e89b-42d3-a456-426614174001"
    seen = []
    completion = {"applied": False}
    discovery = {"witness": witness, "writable": True, "parameters": [
        {"id": "cellCount", "type": "integer", "value": 32, "default": 32, "ui": {"min": 1, "max": 64}}]}

    class Response:
        status = 200
        def __init__(self, data: dict[str, Any]) -> None:
            self.data = data
        def read(self) -> bytes:
            return json.dumps(self.data).encode()
        def __enter__(self) -> "Response":
            return self
        def __exit__(self, *_exc: object) -> None:
            return None

    def opener(req: Any, timeout: Any = None) -> Response:
        seen.append(req)
        if req.full_url.endswith("/api/agent/shader-parameters"):
            return Response(discovery)
        if req.get_method() == "POST":
            return Response({"ok": True, "ticket_id": ticket_id,
                             "status": "applied" if completion["applied"] else "pending"})
        return Response({"ticket_id": ticket_id, "status": "applied", "parameter_id": "cellCount"})

    client = Client(opener=opener)
    assert client.get_shader_parameters(session_id=session_id)["parameters"][0]["value"] == 32
    assert client.set_shader_parameter(submit, session_id=session_id)["status"] == "pending"
    no_manifest = {**submit, "client_request_id": "known_2", "witness": {**witness, "base": {
        key: val for key, val in witness["base"].items() if key != "manifest_hash"}}}
    assert client.set_shader_parameter(no_manifest, session_id=session_id)["status"] == "pending"
    assert client.set_shader_parameter(status, session_id=session_id)["status"] == "applied"
    assert [req.get_method() for req in seen] == ["GET", "POST", "POST", "GET"]
    assert seen[1].full_url.endswith("/api/agent/shader-parameter")
    assert json.loads(seen[1].data) == {key: submit[key] for key in ("client_request_id", "witness", "parameter_id", "value")}
    assert seen[3].full_url.endswith("/api/agent/shader-parameter/requests/known_1")
    assert all(req.get_header("X-hextile-agent") == "mcp" for req in seen)
    assert all(req.get_header("X-hextile-mcp-session") == session_id for req in seen)

    # Original-ID replay/status reaches the native journal despite later owner/witness changes.
    completion["applied"] = True
    discovery.update(witness={**witness, "edit_sequence": 8})
    assert client.set_shader_parameter(submit, session_id=session_id)["status"] == "applied"
    assert client.set_shader_parameter(status, session_id=session_id)["status"] == "applied"
    assert [req.get_method() for req in seen[-2:]] == ["POST", "GET"]
    assert json.loads(seen[-2].data) == json.loads(seen[1].data)
    assert all(req.get_header("X-hextile-mcp-session") == session_id for req in seen[-3:])

    old_seen = []
    def old_opener(req: Any, **_kw: Any) -> Response:
        old_seen.append(req)
        return Response({"witness": witness, "writable": True})
    old_app = Client(opener=old_opener)
    with pytest.raises(HextileClientError) as upgrade:
        old_app.set_shader_parameter(submit, session_id=session_id)
    assert upgrade.value.kind == "shader_parameter_outcome_unknown"
    assert [req.get_method() for req in old_seen] == ["POST"]

    with pytest.raises(HextileClientError):
        client.set_shader_parameter(submit, session_id="model-chosen")

    def lost_opener(req: Any, **_kw: Any) -> Response:
        if req.get_method() == "POST":
            raise urllib.error.URLError(TimeoutError())
        return Response(discovery)
    lost = Client(opener=lost_opener)
    with pytest.raises(HextileClientError) as uncertain:
        lost.set_shader_parameter(submit, session_id=session_id)
    assert uncertain.value.kind == "shader_parameter_outcome_unknown"
    assert uncertain.value.receipt == {"client_request_id": "known_1"}
    with mock.patch.object(client, "get_json", side_effect=HextileClientError("gone", kind="http", status_code=404)):
        with pytest.raises(HextileClientError) as missing:
            client.set_shader_parameter(status, session_id=session_id)
    assert missing.value.kind == "shader_parameter_outcome_unknown"
    with mock.patch.object(client, "post_json", side_effect=HextileClientError("stale_snapshot", kind="http", status_code=409)):
        with pytest.raises(HextileClientError) as stale:
            client.set_shader_parameter(submit, session_id=session_id)
    assert stale.value.status_code == 409
    assert stale.value.kind == "http"
    for bad in ({**submit, "value": float("inf")}, {**submit, "witness": {**witness, "edit_sequence": True}},
                {**submit, "witness": {**witness, "base": {"kind": "saved"}}},
                {**status, "value": 44}):
        with pytest.raises(HextileClientError):
            client.set_shader_parameter(bad, session_id=session_id)


def test_expression_timeline_mcp_schema_and_teaching() -> None:
    proposal = _proposal()
    proposal["modulation_edits"] = {"schema": 2, "edits": [
        {"op": "set_parameter_expression", "target": "shader.params.gain",
         "source_text": "T*2", "refs": {}},
        {"op": "set_timeline", "start": {"num": "0", "den": "1"},
         "end": {"num": "4", "den": "1"}, "loop": True}]}
    jsonschema.validate(proposal, _schema("propose_shader")["inputSchema"])
    typed_binding = {"source_id": "mod_" + "a" * 24, "target": "shader.params.mode",
                     "signature": {"kind": "enum", "unit": "unitless", "min": 0,
                                   "max": 2, "choices": [0, 1, 2]},
                     "mode": "range", "range_min": 0, "range_max": 2}
    mode_proposal = {**proposal, "modulation_edits": {"schema": 2, "edits": [
        {"op": "set_parameter_mode", "target": "shader.params.mode",
         "mode": "modulator", "binding": typed_binding}]}}
    jsonschema.validate(mode_proposal, _schema("propose_shader")["inputSchema"])
    sys.path.insert(0, str(ROOT.parent / "360-HEXTILE-APP"))
    from backend.modulation.contracts import _signature
    assert _signature(typed_binding["signature"], "binding.signature", typed=True)["choices"] == [0, 1, 2]
    for kind in ("int", "bool", "vec3", "ramp_color"):
        signature = {"kind": kind, "unit": "unitless", "min": 0, "max": 1}
        typed = {**mode_proposal, "modulation_edits": {"schema": 2, "edits": [
            {**mode_proposal["modulation_edits"]["edits"][0],
             "binding": {**typed_binding, "signature": signature}}]}}
        jsonschema.validate(typed, _schema("propose_shader")["inputSchema"])
        assert _signature(signature, "binding.signature", typed=True)["kind"] == kind
    for malformed in ({**typed_binding, "source_id": {"id": "mod_" + "a" * 24}},
                      {**typed_binding, "signature": {**typed_binding["signature"], "choices": []}}):
        bad = {**mode_proposal, "modulation_edits": {"schema": 2, "edits": [
            {**mode_proposal["modulation_edits"]["edits"][0], "binding": malformed}]}}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, _schema("propose_shader")["inputSchema"])
    with mock.patch.object(Client, "post_json", return_value={"ticket_id": "spt_1"}) as post:
        assert Client().propose_shader(proposal) == {"ticket_id": "spt_1"}
        assert Client().propose_shader(mode_proposal) == {"ticket_id": "spt_1"}
    assert [call.args for call in post.call_args_list] == [
        ("/api/agent/shader-proposals", proposal), ("/api/agent/shader-proposals", mode_proposal)]
    proposal_client = mock.Mock()
    proposal_client.propose_shader.return_value = {"ticket_id": "spt_mode", "kind": "shader_document_candidate"}
    assert HextileMcpServer(client=proposal_client)._propose_shader(mode_proposal)["ticket_id"] == "spt_mode"
    proposal_client.propose_shader.assert_called_once_with(mode_proposal)
    witness = {"studio_surface_id": "surface", "project_context_witness": "wit",
               "shader": {"origin": "user", "shaderId": "aurora"},
               "base": {"kind": "saved", "working_revision": 1,
                        "document_hash": "sha256:" + "ab" * 32,
                        "source_hash": "sha256:" + "cd" * 32},
               "owner_id": "owner", "owner_generation": 1,
               "viewer_generation": 2, "source_epoch": 3}
    control = _schema("control_shader_timeline")
    assert control["annotations"]["readOnlyHint"] is False
    submit = {"operation": "submit", "client_request_id": "known_1",
              "action": "seek", "time_seconds": 2.5, "witness": witness}
    status = {"operation": "status", "client_request_id": "known_1"}
    for args in (submit, status):
        jsonschema.validate(args, control["inputSchema"])
    for malformed in ({**submit, "action": "pause"},
                      {**status, "witness": witness},
                      {**submit, "witness": {**witness, "owner_generation": None}}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(malformed, control["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**submit, "time_seconds": float("inf")}, control["inputSchema"])
    seen = []
    client = mock.Mock()
    client.control_shader_timeline.side_effect = lambda args: seen.append(args) or {"status": "pending"}
    server = HextileMcpServer(client=client)
    assert server._control_shader_timeline(submit) == {"status": "pending"}
    assert server._control_shader_timeline(status) == {"status": "pending"}
    assert seen == [submit, status]
    from hextile_mcp import load_guide
    guide = load_guide("recipes")
    assert "set_parameter_expression" in str(guide)
    assert "control_shader_timeline" in str(guide)
    example = json.loads(re.search(r"## Shader scalar expression and mounted timeline.*?```json\n(.*?)\n```",
                                   guide["markdown"], re.S).group(1))
    jsonschema.validate(example, _schema("propose_shader")["inputSchema"])
    assert example["base"] == _proposal()["base"]
    assert example["modulation_edits"]["schema"] == 2
    assert "kind" not in example["base"]
    context_description = _schema("get_shader_context")["description"]
    assert "hx-math" in context_description and "parameter expression" in context_description
    assert "include_formula" in context_description and "include_source" in context_description
    for name in ("preflight_shader_sequence", "render_shader_sequence", "get_shader_sequence"):
        assert _schema(name)["inputSchema"]["additionalProperties"] is False
        assert name in guide["markdown"]

    class Response:
        status = 200
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload
        def read(self) -> bytes:
            return json.dumps(self.payload).encode()
        def __enter__(self) -> "Response":
            return self
        def __exit__(self, *_exc: object) -> None:
            return None

    wire = []
    def opener(req: Any, timeout: Any = None) -> Response:
        wire.append(req)
        return Response({"ok": True, "ticket_id": "123e4567-e89b-42d3-a456-426614174000", "status": "pending"} if req.get_method() == "POST"
                        else {"client_request_id": "known_1", "status": "applied", "ticket_id": "123e4567-e89b-42d3-a456-426614174000"})
    transport = Client(opener=opener)
    assert transport.control_shader_timeline(submit)["status"] == "pending"
    assert transport.control_shader_timeline(status)["status"] == "applied"
    assert [req.get_method() for req in wire] == ["POST", "GET"]
    assert wire[0].full_url.endswith("/api/agent/shader-timeline-control")
    assert json.loads(wire[0].data) == {key: value for key, value in submit.items() if key != "operation"}
    assert wire[1].full_url.endswith("/api/agent/shader-timeline-control/requests/known_1")
    assert all(req.get_header("X-hextile-agent") == "mcp" for req in wire)
    with pytest.raises(HextileClientError):
        transport.control_shader_timeline({**submit, "time_seconds": float("nan")})

    lost = Client(opener=lambda *_a, **_kw: (_ for _ in ()).throw(urllib.error.URLError(TimeoutError())))
    with pytest.raises(HextileClientError) as uncertain:
        lost.control_shader_timeline(submit)
    assert uncertain.value.kind == "shader_timeline_outcome_unknown"
    assert uncertain.value.receipt == {"client_request_id": "known_1"}
    missing = Client(opener=lambda req, timeout=None: (_ for _ in ()).throw(
        urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"detail":"outcome_unknown"}'))))
    with pytest.raises(HextileClientError) as expired:
        missing.control_shader_timeline(status)
    assert expired.value.kind == "shader_timeline_outcome_unknown"
    assert expired.value.receipt == {"client_request_id": "known_1", "status": "unknown"}

    private = r"C:\private\shader-formula"
    for code in (422, 500, 503):
        def broken(req: Any, timeout: Any = None) -> Any:
            raise urllib.error.HTTPError(req.full_url, code, private, {}, io.BytesIO(private.encode()))
        result = HextileMcpServer(client=Client(opener=broken)).call_tool("control_shader_timeline", submit)
        payload = json.loads(result["content"][0]["text"])
        assert result["isError"] is True and private not in json.dumps(result)
        assert payload["kind"] == ("shader_timeline_outcome_unknown" if code >= 500 else "http")
        if code >= 500:
            assert payload["receipt"]["client_request_id"] == "known_1"
    result = HextileMcpServer(client=Client(opener=lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError(private)))).call_tool(
        "control_shader_timeline", submit)
    assert private not in json.dumps(result) and "trace" not in json.dumps(result)
    assert json.loads(result["content"][0]["text"])["kind"] == "shader_timeline_outcome_unknown"
    raw_client = mock.Mock()
    raw_client.control_shader_timeline.side_effect = RuntimeError(private)
    result = HextileMcpServer(client=raw_client).call_tool("control_shader_timeline", submit)
    assert private not in json.dumps(result) and "trace" not in json.dumps(result)
    def polluted(req: Any, timeout: Any = None) -> Response:
        if req.get_method() == "GET":
            return Response({"ticket_id": "123e4567-e89b-42d3-a456-426614174000", "status": "applied",
                             "action": "seek", "source": private, "trace": private})
        return Response({"ok": True, "ticket_id": "123e4567-e89b-42d3-a456-426614174000",
                         "status": "pending", "source": private})
    clean = Client(opener=polluted)
    assert private not in json.dumps(clean.control_shader_timeline(submit))
    assert private not in json.dumps(clean.control_shader_timeline(status))
    def refused(req: Any, timeout: Any = None) -> Response:
        return Response({"ticket_id": "123e4567-e89b-42d3-a456-426614174000",
                         "status": "refused", "action": "seek", "reason": "preview_unavailable",
                         "source": private})
    assert Client(opener=refused).control_shader_timeline(status) == {
        "client_request_id": "known_1", "ticket_id": "123e4567-e89b-42d3-a456-426614174000",
        "status": "refused", "action": "seek", "reason": "preview_unavailable"}

    if importlib.util.find_spec("mcp") is not None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        script = ("import sys; sys.path.insert(0, " + repr(str(ROOT / "mcp")) + "); "
                  "import hextile_mcp; "
                  "original=hextile_mcp.HextileMcpServer; "
                  "hextile_mcp.HextileMcpServer=lambda: original(client=FakeClient(), child_token='test'); "
                  "raise SystemExit(hextile_mcp.main())")
        script = ("class FakeClient:\n"
                  "    def control_shader_timeline(self, args):\n"
                  "        return {'status':'applied','client_request_id':args['client_request_id']}\n"
                  + script)
        async def exercise_sdk() -> None:
            params = StdioServerParameters(command=sys.executable, args=["-c", script])
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    catalog = await session.list_tools()
                    assert any(tool.name == "control_shader_timeline" for tool in catalog.tools)
                    result = await session.call_tool("control_shader_timeline", status)
                    assert result.isError is False
                    assert json.loads(result.content[0].text)["status"] == "applied"
        asyncio.run(exercise_sdk())


_DOCTOR_ID = "123e4567-e89b-42d3-a456-426614174000"
_DOCTOR_REQUEST = {"request_id": _DOCTOR_ID, "origin": "builtin", "shader_id": "aurora",
                   "project_context_witness": "wit", "studio_surface_id": "surface"}


def test_shader_doctor_closed_tools_and_exact_poll() -> None:
    request_schema = _schema("request_shader_doctor")
    get_schema = _schema("get_shader_doctor")
    poll = {"request_id": _DOCTOR_ID, "project_context_witness": "wit"}
    jsonschema.validate(_DOCTOR_REQUEST, request_schema["inputSchema"])
    jsonschema.validate(poll, get_schema["inputSchema"])
    assert request_schema["annotations"]["readOnlyHint"] is False
    assert get_schema["annotations"]["readOnlyHint"] is True
    for schema, args in ((request_schema, _DOCTOR_REQUEST), (get_schema, poll)):
        assert schema["inputSchema"]["additionalProperties"] is False
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**args, "source": "private"}, schema["inputSchema"])

    seen: list[Any] = []

    class Response:
        status = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return json.dumps(self.payload).encode()

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    def opener(req: Any, timeout: Any = None) -> Response:
        seen.append(req)
        return Response({"request_id": _DOCTOR_ID, "status": "pending", "expires_at": 100})

    server = HextileMcpServer(client=Client(opener=opener))
    assert server._request_shader_doctor(_DOCTOR_REQUEST)["status"] == "pending"
    assert server._get_shader_doctor(poll)["request_id"] == _DOCTOR_ID
    assert [req.get_method() for req in seen] == ["POST", "GET"]
    assert json.loads(seen[0].data) == _DOCTOR_REQUEST
    assert seen[0].full_url.endswith("/api/agent/shader-doctor/requests")
    assert seen[1].full_url.endswith(f"/api/agent/shader-doctor/requests/{_DOCTOR_ID}?project_context_witness=wit")
    assert all(req.get_header("X-hextile-agent") == "mcp" for req in seen)


def test_shader_doctor_uncertain_post_preserves_id_without_retry() -> None:
    for failure in (urllib.error.URLError(TimeoutError("timed out")), http.client.RemoteDisconnected("lost")):
        seen: list[Any] = []

        def opener(req: Any, timeout: Any = None) -> Any:
            seen.append(req)
            raise failure

        with pytest.raises(HextileClientError) as caught:
            Client(opener=opener).request_shader_doctor(_DOCTOR_REQUEST)
        assert caught.value.kind == "shader_doctor_outcome_unknown"
        assert caught.value.receipt == {"request_id": _DOCTOR_ID}
        assert _DOCTOR_ID in str(caught.value)
        assert len(seen) == 1




def _proposal() -> dict[str, Any]:
    return {
        "kind": "shader_document_candidate", "explanation": "Enable mouse input",
        "base": {"shader": {"origin": "user", "shaderId": "aurora"},
                 "project_context_witness": "wit", "working_revision": 1,
                 "document_hash": "sha256:" + "ab" * 32,
                 "source_hash": "sha256:" + "cd" * 32, "manifest_hash": None},
        "modulation_edits": {"schema": 1, "edits": [
            {"op": "set_mouse_input", "value": {"schema": 1, "enabled": True, "abi": "hx-mouse/1"}}]},
    }


def _operations() -> list[dict[str, Any]]:
    source = {"id": "mod_" + "a" * 24}
    binding = {"id": "binding_" + "b" * 24}
    definition = {"label": "Pulse", "alias": "MOD1", "kind": "time", "enabled": True,
                  "source": "sin(2*pi*cycle)", "period_unit": "beats",
                  "settings": {"period": 4, "speed": 1, "phase": 0,
                               "output_min": -1, "output_max": 1, "duty": .5}}
    added_binding = {"source_id": {"ref": "pulse"}, "target": "gain", "enabled": True,
                     "signature": {"kind": "float", "unit": "scalar", "min": 0, "max": 1},
                     "mode": "range", "range_min": 0, "range_max": 1}
    return [
        {"op": "add_source", "definition": definition, "ref": "pulse"},
        {"op": "remove_source", "source": source},
        {"op": "set_label", "source": source, "label": "Wave"},
        {"op": "install_wave", "source": source, "wave": "Square (50%)"},
        {"op": "set_expression", "source": source, "source_text": "cycle"},
        {"op": "set_setting", "source": source, "setting": "period", "value": 2},
        {"op": "set_period_unit", "source": source, "period_unit": "seconds"},
        {"op": "set_click", "source": source, "button": "right", "mode": "toggle"},
        {"op": "rename_alias", "source": source, "alias": "customAlias"},
        {"op": "set_source_enabled", "source": source, "enabled": False},
        {"op": "add_binding", "binding": added_binding, "ref": "gain"},
        {"op": "update_binding", "binding": binding,
         "value": {**added_binding, "id": binding["id"], "source_id": source["id"]}},
        {"op": "remove_binding", "binding": binding},
        {"op": "set_binding_enabled", "binding": binding, "enabled": False},
        _proposal()["modulation_edits"]["edits"][0],
        {"op": "set_master_clock", "value": {"schema": 1, "bpm": 120, "speed": 1,
         "anchor": {"time": {"num": "0", "den": "1"}, "seconds": 0, "beats": 0}}},
    ]


def test_closed_modulation_catalog_and_existing_alternatives() -> None:
    schema = _schema("propose_shader")["inputSchema"]
    for operation in _operations():
        proposal = _proposal()
        proposal["modulation_edits"]["edits"] = [operation]
        jsonschema.validate(proposal, schema)
    for field, value in (("source_edit", {"from_utf16": 0, "to_utf16": 0,
                                         "expected_text": "", "replacement": "x"}),
                         ("complete_candidate", {"source": "x", "values": {}, "capture_defaults": {},
                          "output": {}, "space": "direction_360", "extensions": {}})):
        proposal = _proposal()
        del proposal["modulation_edits"]
        proposal[field] = value
        jsonschema.validate(proposal, schema)
    variants = schema["properties"]["modulation_edits"]["oneOf"][0]["properties"]["edits"]["items"]["oneOf"]
    assert {variant["properties"]["op"]["const"] for variant in variants} == {op["op"] for op in _operations()}


@pytest.mark.parametrize("change", ["xor", "none", "unknown", "partial", "foreign", "null",
                                     "count", "reference", "definition_id", "boolean"])
def test_modulation_schema_refuses_malformed_batches(change: str) -> None:
    proposal = _proposal()
    edit = proposal["modulation_edits"]["edits"][0]
    if change == "xor": proposal["source_edit"] = {}
    elif change == "none": del proposal["modulation_edits"]
    elif change == "unknown": edit["op"] = "arm"
    elif change == "partial": del edit["value"]["abi"]
    elif change == "foreign": edit["value"]["armed"] = True
    elif change == "null": proposal["modulation_edits"] = None
    elif change == "count": proposal["modulation_edits"]["edits"] *= 33
    elif change == "reference": proposal["modulation_edits"]["edits"] = [{"op": "remove_source", "source": "MOD1"}]
    elif change == "definition_id":
        proposal["modulation_edits"]["edits"] = [_operations()[0]]
        proposal["modulation_edits"]["edits"][0]["definition"]["id"] = "mod_" + "a" * 24
    elif change == "boolean": edit["value"]["enabled"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(proposal, _schema("propose_shader")["inputSchema"])


def test_client_transports_exact_typed_batch_and_explicit_formula_consent() -> None:
    client = Client()
    metadata = {"modulation": {"definitions": [{"id": "mod_" + "a" * 24, "alias": "MOD1"}],
                               "bindings": [], "mouse_input": {"schema": 1, "enabled": True, "abi": "hx-mouse/1"}}}
    with mock.patch.object(client, "get_json", return_value=metadata) as get:
        assert client.get_shader_context(origin="user", shader_id="aurora", project_context_witness="wit") == metadata
        assert get.call_args.kwargs["params"]["include_source"] == "false"
        assert get.call_args.kwargs["params"]["include_formula"] == "false"
        assert "source" not in metadata
        client.get_shader_context(origin="user", shader_id="aurora", project_context_witness="wit",
                                  include_source=True, include_formula=True)
        assert get.call_args.kwargs["params"]["include_source"] == "true"
        assert get.call_args.kwargs["params"]["include_formula"] == "true"
    proposal = _proposal()
    original = deepcopy(proposal)
    with mock.patch.object(client, "post_json", return_value={"ticket_id": "spt_abc"}) as post:
        client.propose_shader(proposal)
        assert post.call_args.args == ("/api/agent/shader-proposals", original)
        assert proposal == original
        for malformed in ({**proposal, "source_edit": {}}, {**proposal, "foreign": True},
                          {**proposal, "modulation_edits": {"schema": 1, "edits": [proposal["modulation_edits"]["edits"][0]] * 33}},
                          {**proposal, "modulation_edits": {"schema": 1, "edits": [{"op": "arm"}]}},
                          {**proposal, "modulation_edits": {"schema": 1, "edits": [{"op": "set_label", "source": {"id": "mod_" + "a" * 24}, "label": "x" * 65537}]}}):
            with pytest.raises(HextileClientError): client.propose_shader(malformed)
        assert post.call_count == 1

def test_shader_tool_schemas_cannot_import_delete_or_consume() -> None:
    for name in ("get_shader_context", "propose_shader"):
        schema = _schema(name)["inputSchema"]
        assert schema["additionalProperties"] is False
        assert not {"import", "delete", "accept", "consume", "config_partial", "path"} & set(schema["properties"])
    assert _schema("get_shader_context")["annotations"]["readOnlyHint"] is True
    assert _schema("propose_shader")["annotations"]["readOnlyHint"] is False
    assert _schema("propose_shader")["annotations"]["destructiveHint"] is False
    assert _schema("get_shader_context")["inputSchema"]["properties"]["include_source"]["default"] is False


def test_shader_client_calls_context_and_proposal_only() -> None:
    seen: list[Any] = []

    class Response:
        status = 200

        def read(self) -> bytes:
            return b'{"ticket_id":"spt_abc","kind":"shader_document_candidate","ready":true,"source":"secret"}'

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    def opener(req: Any, timeout: Any = None) -> Response:
        del timeout
        seen.append(req)
        return Response()

    client = Client(opener=opener)
    client.get_shader_context(
        origin="user", shader_id="aurora", project_context_witness="wit", include_source=False,
    )
    client.propose_shader(_proposal())
    assert [req.get_method() for req in seen] == ["GET", "POST"]
    assert seen[0].full_url.startswith("http://127.0.0.1:8000/api/agent/shader-context?")
    assert "include_source=false" in seen[0].full_url
    assert seen[0].get_header("X-hextile-agent") == "mcp"
    assert seen[0].get_header("X-hextile-project-witness") == "wit"
    assert seen[1].full_url == "http://127.0.0.1:8000/api/agent/shader-proposals"
    assert seen[1].get_header("X-hextile-agent") == "mcp"
    body = json.loads(seen[1].data)
    assert body["kind"] == "shader_document_candidate"
    assert all("imports" not in req.full_url and "consume" not in req.full_url for req in seen)
    with pytest.raises(HextileClientError):
        client.propose_shader({"kind": "config_partial", "config_partial": {"gain": 1}})
    with pytest.raises(HextileClientError):
        client.propose_shader({"kind": "shader_document_candidate", "base": {}, "consume": True})


def test_shader_handlers_return_context_and_ticket_identity() -> None:
    client = mock.Mock()
    client.get_shader_context.return_value = {"source_hash": "sha256:" + "ab" * 32, "manifest": {}}
    client.propose_shader.return_value = {
        "ticket_id": "spt_abc", "kind": "shader_document_candidate", "ready": True,
        "shader": {"origin": "user", "shaderId": "aurora"},
        "complete_candidate": {"source": "secret"},
    }
    server = HextileMcpServer(client=client)
    context = server._get_shader_context({
        "origin": "user", "shader_id": "aurora", "project_context_witness": "wit",
        "include_source": False,
    })
    assert context["manifest"] == {}
    client.get_shader_context.assert_called_once_with(
        origin="user", shader_id="aurora", project_context_witness="wit",
        include_source=False, include_formula=False, working_revision=None,
    )
    identity = server._propose_shader(_proposal())
    assert identity == {
        "ticket_id": "spt_abc", "kind": "shader_document_candidate",
        "shader": {"origin": "user", "shaderId": "aurora"}, "ready": False,
    }
    assert "complete_candidate" not in identity
    with pytest.raises(HextileClientError):
        server._propose_shader({"kind": "shader_document_candidate", "base": {}, "accept": True})
    with pytest.raises(HextileClientError):
        server._get_shader_context({
            "origin": "user", "shader_id": "aurora", "project_context_witness": "wit", "import": True,
        })


def _workspace_open() -> dict[str, Any]:
    return {"shader": {"origin": "project", "shaderId": "aurora"},
            "project_context_witness": "wit", "expected_working_revision": 1,
            "expected_document_hash": "sha256:" + "ab" * 32,
            "expected_source_hash": "sha256:" + "cd" * 32, "studio_surface_id": "surface"}


def _workspace_attachment() -> dict[str, Any]:
    body = _workspace_open()
    return {"handle": "sw_test", "generation": 0, "shader": body["shader"],
            "base": {"working_revision": 1, "document_hash": body["expected_document_hash"],
                     "source_hash": body["expected_source_hash"], "manifest_hash": None},
            "project_context_witness": "wit", "studio_surface_id": "surface",
            "files": {"source_path": "D:/project/workspace/source.glsl", "authoring_path": "D:/project/workspace/authoring.json"},
            "content_digest": "sha256:" + "ef" * 32, "schema": 1, "abi": "hx-shader/1",
            "available": True, "executable_capabilities": ["conventions/1"], "instructions": "observed APP instructions"}


def _workspace_register() -> dict[str, Any]:
    return {"handle": "sw_test", "change_id": "sw_test:1", "expected_generation": 0,
            "content_digest": "sha256:" + "ef" * 32}


def _workspace_receipt() -> dict[str, Any]:
    attachment = _workspace_attachment()
    return {key: value for key, value in {
        **attachment, **_workspace_register(), "generation": 1, "candidate_id": "candidate",
        "check_attempt": 0, "attachment_state": "attached", "prepare": "passed", "compile": "failed",
        "preview": "failed", "presentation": "pending", "save": "not_saved",
        "diagnostics": [{"phase": "compile", "severity": "error", "code": "compile",
                         "message": "x" * 2048, "file": "source.glsl", "line": 42, "column": 3}],
        "raw_log": "x" * 8192, "reason": {"code": "compile_failed", "message": "Repair native source"},
    }.items() if key not in {"files", "instructions", "expected_generation"}}


class _WorkspaceResponse:
    status = 200

    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body

    def read(self) -> bytes:
        return json.dumps(self.body).encode()

    def __enter__(self) -> "_WorkspaceResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def test_workspace_closed_schemas_and_transport_admission() -> None:
    cases = [("open_shader_workspace", _workspace_open()),
             ("register_shader_update", _workspace_register()),
             ("get_shader_update", {"handle": "sw_test", "change_id": "sw_test:1", "project_context_witness": "wit"})]
    client = Client(opener=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no HTTP")))
    for name, args in cases:
        schema = _schema(name)["inputSchema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) <= set(args)
        jsonschema.validate(args, schema)
        malformed = [{**args, "path": "D:/other"}, {key: value for key, value in args.items() if key != schema["required"][0]}]
        if name == "open_shader_workspace":
            adopted = {**args, "existing_workspace": {"action": "adopt", "expected_content_digest": "sha256:" + "ef" * 32}}
            jsonschema.validate(adopted, schema)
            malformed += [{**args, "shader": {**args["shader"], "path": "D:/other"}},
                          {**adopted, "existing_workspace": {**adopted["existing_workspace"], "force": True}},
                          {**args, "shader": {"origin": "builtin", "shaderId": "aurora"}},
                          {**args, "existing_workspace": None}, {**args, "expected_working_revision": True}]
        for body in malformed:
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(body, schema)
            with pytest.raises(HextileClientError):
                getattr(client, name)(body)


def test_workspace_requests_validate_with_live_app_closed_models() -> None:
    # Load the real route models without importing unrelated desktop/GPU owners.
    # This cross-service boundary catches a closed field or type drifting in APP.
    route = ROOT.parent / "360-HEXTILE-APP/backend/api/routes/agent_shader_workspaces.py"
    tree = ast.parse(route.read_text(encoding="utf-8"))
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module in {"typing", "pydantic"}]
    names = {"ClosedModel", "ShaderRef", "ExistingWorkspace", "OpenIn", "RegisterIn",
             "SourceEvidence", "SourceDigest", "SourceProfileLink", "SourceProfile",
             "SourceProfileRef", "SourceProfileV2", "SourceAvatar", "SourceProfileLinkV2", "SourceFields", "SourceAppend", "SourceChange", "SourceProposal"}
    assignments = {"Digest", "Name", "SurfaceId"}
    definitions = [node for node in tree.body if (isinstance(node, ast.ClassDef) and node.name in names)
                   or (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in assignments for target in node.targets))]
    namespace: dict[str, Any] = {"MAX_SAFE_GENERATION": 2**53 - 1}
    exec(compile(ast.Module(body=imports + definitions, type_ignores=[]), str(route), "exec"), namespace)
    for name in names:
        namespace[name].model_rebuild(_types_namespace=namespace)
    for model, body in ((namespace["OpenIn"], _workspace_open()),
                        (namespace["OpenIn"], {**_workspace_open(), "workspace_schema": 2}),
                        (namespace["OpenIn"], _workspace_open_v2()),
                        (namespace["RegisterIn"], {key: value for key, value in _workspace_register().items() if key != "handle"})):
        validated = model.model_validate(body).model_dump(exclude_unset=True)
        assert validated == body
        with pytest.raises(ValueError):
            model.model_validate({**body, "source": "forbidden GLSL JSON"})
    source_body = {key: value for key, value in _workspace_register().items() if key != "handle"}
    source_body["source_proposal"] = {"schema": 1, "expected_provenance_hash": None,
        "sources": [{"kind": "append", "row": {"author": "Adapter",
            "evidence": {"basis": "observed", "note": "source"}}}]}
    assert namespace["RegisterIn"].model_validate(source_body).model_dump(exclude_unset=True) == source_body
    with pytest.raises(ValueError):
        namespace["RegisterIn"].model_validate({**source_body, "source_proposal": {
            **source_body["source_proposal"], "sources": [{"kind": "append", "row": {
                "author": "Adapter", "evidence": {"basis": "observed", "note": "source", "private": True}}}]}})
    schema = namespace["OpenIn"].model_json_schema()
    public = _schema("open_shader_workspace")["inputSchema"]
    assert set(public["properties"]) == set(schema["properties"])
    assert set(public["required"]) == set(schema["required"])
    schema = namespace["RegisterIn"].model_json_schema()
    public = _schema("register_shader_update")["inputSchema"]
    assert set(public["properties"]) - {"handle"} == set(schema["properties"])


def test_workspace_http_identity_receipt_and_open_replay() -> None:
    seen: list[Any] = []
    attachment, receipt = _workspace_attachment(), _workspace_receipt()

    def opener(req: Any, timeout: Any = None) -> _WorkspaceResponse:
        seen.append((req, timeout))
        return _WorkspaceResponse(attachment if req.full_url.endswith("/open") else receipt)

    server = HextileMcpServer(client=Client(opener=opener, timeout=23))
    # Call handlers to isolate workspace transport from unrelated activity requests.
    assert server._open_shader_workspace(_workspace_open()) == attachment
    assert server._open_shader_workspace(_workspace_open()) == attachment
    assert server._register_shader_update(_workspace_register()) == receipt
    assert server._get_shader_update({"handle": "sw_test", "change_id": "sw_test:1", "project_context_witness": "wit"}) == receipt
    assert [timeout for _, timeout in seen] == [15.0, 15.0, 23, 23]
    assert [req.get_method() for req, _ in seen] == ["POST", "POST", "POST", "GET"]
    assert json.loads(seen[0][0].data) == json.loads(seen[1][0].data) == _workspace_open()
    assert json.loads(seen[2][0].data) == {key: value for key, value in _workspace_register().items() if key != "handle"}
    assert seen[2][0].full_url.endswith("/api/agent/shader-workspaces/sw_test/updates")
    assert seen[3][0].full_url.endswith("/sw_test/updates/sw_test%3A1?project_context_witness=wit")
    assert all(req.get_header("X-hextile-agent") == "mcp" for req, _ in seen)
    assert "files" not in receipt and "source" not in receipt
    assert receipt["diagnostics"][0]["line"] == 42 and len(receipt["raw_log"]) == 8192


@pytest.mark.parametrize("change_id", ["other:1", "sw_test:01", "sw_test:0", "sw_test:+1", "sw_test:1.0",
                                     "sw_test:١", "sw_test:9007199254740992", "sw_test:" + "9" * 10000])
def test_workspace_canonical_change_id_refuses_before_http(change_id: str) -> None:
    client = Client(opener=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no HTTP")))
    with pytest.raises(HextileClientError) as caught:
        client.register_shader_update({**_workspace_register(), "change_id": change_id})
    assert caught.value.status_code == 409
    with pytest.raises(HextileClientError):
        client.get_shader_update({"handle": "sw_test", "change_id": change_id, "project_context_witness": "wit"})


@pytest.mark.parametrize("generation", [True, -1, 1.0, 2**53 - 1])
def test_workspace_generation_is_bounded_safe_integer(generation: Any) -> None:
    with pytest.raises(HextileClientError):
        Client().register_shader_update({**_workspace_register(), "expected_generation": generation})


@pytest.mark.parametrize("status,code", [(409, "idempotency_conflict"), (409, "generation_conflict"),
    (409, "attachment_conflict"), (409, "attachment_not_ready"), (503, "attachment_unavailable"),
    (410, "receipt_expired"), (410, "workspace_expired"), (403, "authority"), (503, "capacity")])
def test_workspace_backend_refusals_preserve_bounded_details(status: int, code: str) -> None:
    detail = {"code": code, "message": "x" * 2048, "recovery": "Rediscover current authority"}

    def opener(req: Any, timeout: Any = None) -> Any:
        raise urllib.error.HTTPError(req.full_url, status, "refused", None,
                                     io.BytesIO(json.dumps({"detail": detail}).encode()))

    server = HextileMcpServer(client=Client(opener=opener))
    result = server.call_tool("register_shader_update", _workspace_register())
    assert result["isError"] is True
    error = json.loads(result["content"][0]["text"])
    assert error["status_code"] == status and error["receipt"] == detail
    assert "files" not in error and "source_path" not in result["content"][0]["text"]


@pytest.mark.parametrize("operation", ["open_shader_workspace", "register_shader_update"])
def test_workspace_lost_open_never_retries_or_claims_attachment(operation: str) -> None:
    for failure in (urllib.error.URLError(TimeoutError("timed out")), http.client.RemoteDisconnected("lost")):
        calls: list[Any] = []

        def opener(req: Any, timeout: Any = None) -> Any:
            calls.append(req)
            raise failure

        with pytest.raises(HextileClientError):
            getattr(Client(opener=opener), operation)(_workspace_open() if operation == "open_shader_workspace" else _workspace_register())
        assert len(calls) == 1
    for reply in ({"attachment_state": "attaching", "files": _workspace_attachment()["files"]},
                  {**_workspace_attachment(), "attachment_state": "stale"}):
        with pytest.raises(HextileClientError) as caught:
            Client(opener=lambda *_a, **_k: _WorkspaceResponse(reply)).open_shader_workspace(_workspace_open())
        assert caught.value.kind == "workspace_outcome_unknown"
        assert caught.value.receipt is None and caught.value.body is None

    class IncompleteResponse(_WorkspaceResponse):
        def read(self) -> bytes:
            return b'{"files":{"source_path":"D:/private/source.glsl"'

    with pytest.raises(HextileClientError) as caught:
        Client(opener=lambda *_a, **_k: IncompleteResponse({})).open_shader_workspace(_workspace_open())
    assert "D:/private" not in str(caught.value)
    assert caught.value.body is None and caught.value.receipt is None


def test_workspace_empty_registration_is_unknown() -> None:
    class EmptyBody:
        status = 200

        def read(self) -> bytes:
            return b"null"

        def __enter__(self) -> "EmptyBody":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    server = HextileMcpServer(client=Client(opener=lambda *_a, **_k: EmptyBody()))
    result = server.call_tool("register_shader_update", _workspace_register())
    assert result["isError"] is True
    assert json.loads(result["content"][0]["text"])["kind"] == "workspace_outcome_unknown"


def test_workspace_replay_and_history_are_app_owned() -> None:
    receipt = _workspace_receipt()
    observed: list[Any] = []

    def opener(req: Any, timeout: Any = None) -> _WorkspaceResponse:
        if req.full_url.endswith("/open"):
            return _WorkspaceResponse({**_workspace_attachment(), "generation": 9})
        body = json.loads(req.data)
        observed.append(body)
        # Retained original ID can replay after current generation advances.
        return _WorkspaceResponse(receipt)

    client = Client(opener=opener)
    assert client.open_shader_workspace(_workspace_open())["generation"] == 9
    assert client.register_shader_update(_workspace_register()) == receipt
    assert client.register_shader_update(_workspace_register()) == receipt
    assert observed[0] == observed[1]
    # Altered retained generation must reach APP's replay classifier, not be
    # relabelled by a proxy without the authoritative receipt history.
    client.register_shader_update({**_workspace_register(), "expected_generation": 1})
    assert observed[-1]["change_id"] == "sw_test:1"


def test_workspace_missing_route_is_actionable_without_rewriting_old_peer_error() -> None:
    def opener(req: Any, timeout: Any = None) -> Any:
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, io.BytesIO(b'{"detail":"Not Found"}'))

    with pytest.raises(HextileClientError) as caught:
        Client(opener=opener).open_shader_workspace(_workspace_open())
    assert caught.value.kind == "upgrade" and "Upgrade 360 Hextile" in str(caught.value)
    assert caught.value.body == '{"detail":"Not Found"}'


def _workspace_open_v2() -> dict[str, Any]:
    return {key: value for key, value in {**_workspace_open(), "workspace_schema": 2}.items()
            if key not in {"expected_working_revision", "expected_document_hash", "expected_source_hash"}}


def _workspace_attachment_v2(base: dict[str, Any]) -> dict[str, Any]:
    return {**_workspace_attachment(), "workspace_schema": 2, "schema": 2, "base": base,
            "workspace_root": "D:/project/workspace", "authoring_path": "D:/project/workspace/authoring.json",
            "files": [{"path": "lib/noise.glsl", "native_path": "D:/project/workspace/lib/noise.glsl"},
                      {"path": "source.glsl", "native_path": "D:/project/workspace/source.glsl"}]}


@pytest.mark.parametrize("base", [
    {"kind": "saved", "working_revision": 9, "document_hash": "sha256:" + "ab" * 32, "source_hash": "sha256:" + "cd" * 32},
    {"kind": "unaccepted", "authoring_digest": "sha256:" + "12" * 32},
])
def test_workspace_v2_open_preserves_exact_server_base_and_files(base: dict[str, Any]) -> None:
    attachment = _workspace_attachment_v2(base)
    seen = []

    def opener(req: Any, timeout: Any = None) -> _WorkspaceResponse:
        seen.append(json.loads(req.data))
        return _WorkspaceResponse(attachment)

    args = _workspace_open_v2() if base["kind"] == "unaccepted" else {**_workspace_open(), "workspace_schema": 2}
    jsonschema.validate(args, _schema("open_shader_workspace")["inputSchema"])
    assert HextileMcpServer(client=Client(opener=opener))._open_shader_workspace(args) == attachment
    assert seen == [args]


@pytest.mark.parametrize("patch", [{"workspace_schema": 1}, {"workspace_schema": True}, {"workspace_schema": None},
                                  {"workspace_schema": 3}, {"expected_source_hash": "sha256:" + "cd" * 32}])
def test_workspace_v2_open_closed_negotiation(patch: dict[str, Any]) -> None:
    args = {**_workspace_open_v2(), **patch}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(args, _schema("open_shader_workspace")["inputSchema"])
    with pytest.raises(HextileClientError):
        Client(opener=lambda *_a, **_k: pytest.fail("no HTTP")).open_shader_workspace(args)


@pytest.mark.parametrize("flag", [None, 0, 1, "true", {}, []])
def test_workspace_located_flag_is_closed_boolean(flag: Any) -> None:
    args = {"handle": "sw_test", "change_id": "sw_test:1", "project_context_witness": "wit", "include_source_diagnostics": flag}
    schema = _schema("get_shader_update")["inputSchema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["include_source_diagnostics"] == {"type": "boolean", "default": False}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(args, schema)
    with pytest.raises(HextileClientError):
        HextileMcpServer(client=Client(opener=lambda *_a, **_k: pytest.fail("no HTTP")))._get_shader_update(args)


@pytest.mark.parametrize("flag", [None, False, True])
def test_workspace_located_get_exact_url_and_granted_ack(flag: Any) -> None:
    args = {"handle": "sw_test", "change_id": "sw_test:1", "project_context_witness": "wit"}
    if flag is not None:
        args["include_source_diagnostics"] = flag
    receipt = _workspace_receipt()
    if flag is True:
        receipt["source_diagnostics"] = [{"phase": "compile", "severity": "error", "code": "compile",
                                          "message": "Unknown symbol", "logical_file": "lib/noise.glsl", "full_source_line": 4}]
    seen = []

    def opener(req: Any, timeout: Any = None) -> _WorkspaceResponse:
        seen.append(req.full_url)
        return _WorkspaceResponse(receipt)

    jsonschema.validate(args, _schema("get_shader_update")["inputSchema"])
    assert HextileMcpServer(client=Client(opener=opener))._get_shader_update(args) == receipt
    expected = "http://127.0.0.1:8000/api/agent/shader-workspaces/sw_test/updates/sw_test%3A1?project_context_witness=wit"
    assert seen == [expected + ("&include_source_diagnostics=true" if flag is True else "")]
    assert not {"files", "source", "complete_candidate", "ticket_id"} & receipt.keys()


@pytest.mark.parametrize("status,code,witness", [(403, "authority", "wit"), (409, "generation_conflict", "wit"),
                                                (409, "context_conflict", "wrong"), (409, "check_timeout", "wit")])
def test_workspace_located_get_preserves_revoked_stale_witness_deadline_refusal(status: int, code: str, witness: str) -> None:
    detail = {"code": code, "message": "Source diagnostic read refused", "recovery": "Rediscover current authority"}
    seen = []

    def opener(req: Any, timeout: Any = None) -> Any:
        seen.append(req)
        raise urllib.error.HTTPError(req.full_url, status, "refused", None, io.BytesIO(json.dumps({"detail": detail}).encode()))

    with pytest.raises(HextileClientError) as caught:
        HextileMcpServer(client=Client(opener=opener))._get_shader_update({"handle": "sw_test", "change_id": "sw_test:1",
            "project_context_witness": witness, "include_source_diagnostics": True})
    assert caught.value.status_code == status and caught.value.receipt == detail
    assert len(seen) == 1


@pytest.mark.parametrize("reply", [_workspace_receipt(), {**_workspace_receipt(), "source_diagnostics": None}])
def test_workspace_located_get_unsupported_legacy_200_refuses_without_downgrade(reply: dict[str, Any]) -> None:
    seen = []

    def opener(req: Any, timeout: Any = None) -> _WorkspaceResponse:
        seen.append(req.full_url)
        return _WorkspaceResponse(reply)

    with pytest.raises(HextileClientError) as caught:
        Client(opener=opener).get_shader_update({"handle": "sw_test", "change_id": "sw_test:1", "project_context_witness": "wit",
                                              "include_source_diagnostics": True})
    assert caught.value.kind == "upgrade" and "Upgrade" in str(caught.value) and "reconnect" in str(caught.value)
    assert len(seen) == 1 and seen[0].endswith("&include_source_diagnostics=true")


def test_workspace_v2_register_granted_diagnostics_repair_keeps_full_set_identity() -> None:
    # Transport fixture: APP alone owns the grant, frozen candidate and stale classifier.
    current = _workspace_receipt()
    seen = []

    def opener(req: Any, timeout: Any = None) -> _WorkspaceResponse:
        nonlocal current
        seen.append(req)
        if req.get_method() == "POST":
            body = json.loads(req.data)
            current = {**current, **body, "generation": body["expected_generation"] + 1,
                       "candidate_id": "candidate-" + body["change_id"]}
            return _WorkspaceResponse(current)
        if "sw_test%3A1?" in req.full_url and current["generation"] == 2:
            raise urllib.error.HTTPError(req.full_url, 409, "stale", None,
                                         io.BytesIO(b'{"detail":{"code":"generation_conflict"}}'))
        return _WorkspaceResponse({**current, "source_diagnostics": []})

    server = HextileMcpServer(client=Client(opener=opener))
    # Include an unused declared helper: even its edit changes the raw full-set digest.
    authoring = b'{"entry":"source.glsl","source_files":["lib/unused.glsl","source.glsl"]}'
    members = {"source.glsl": b"void main() {}", "lib/unused.glsl": b"float unused = broken;"}

    def digest() -> str:
        framed = b"360hextile.shader-workspace.v2\0" + len(authoring).to_bytes(8, "big") + authoring + len(members).to_bytes(4, "big")
        for path, raw in sorted(members.items(), key=lambda pair: pair[0].encode("utf-8")):
            name = path.encode("utf-8")
            framed += len(name).to_bytes(4, "big") + name + len(raw).to_bytes(8, "big") + raw
        return "sha256:" + hashlib.sha256(framed).hexdigest()

    first = {**_workspace_register(), "content_digest": digest()}
    assert server._register_shader_update(first)["content_digest"] == first["content_digest"]
    get = {"handle": "sw_test", "change_id": "sw_test:1", "project_context_witness": "wit", "include_source_diagnostics": True}
    assert server._get_shader_update(get)["source_diagnostics"] == []
    members["lib/unused.glsl"] = b"float unused = 0.0;"
    repaired = {**first, "change_id": "sw_test:2", "expected_generation": 1, "content_digest": digest()}
    assert first["content_digest"] != repaired["content_digest"]
    receipt = server._register_shader_update(repaired)
    assert receipt["content_digest"] == repaired["content_digest"] and receipt["candidate_id"] == "candidate-sw_test:2"
    with pytest.raises(HextileClientError) as caught:
        server._get_shader_update(get)
    assert caught.value.receipt == {"code": "generation_conflict"}
    assert server._get_shader_update({**get, "change_id": "sw_test:2"})["content_digest"] == repaired["content_digest"]
    assert [json.loads(req.data) for req in seen if req.get_method() == "POST"] == [
        {key: value for key, value in args.items() if key != "handle"} for args in (first, repaired)]


@pytest.mark.parametrize("available,executable", [(False, []), (True, []), (True, ["source-modules/1"])])
def test_workspace_v2_negotiated_capabilities_are_not_inferred_from_format_or_guides(available: bool, executable: list[str]) -> None:
    attachment = {**_workspace_attachment_v2({"kind": "unaccepted", "authoring_digest": "sha256:" + "12" * 32}),
                  "available": available, "recognized_capabilities": ["source-modules/1"], "executable_capabilities": executable}
    receipt = {**_workspace_receipt(), "base": attachment["base"]}
    if not available or "source-modules/1" not in executable:
        receipt.update(prepare="failed", compile="not_requested", preview="not_requested",
                       diagnostics=[{"phase": "prepare", "severity": "error", "code": "unsupported_capability",
                                     "message": "source-modules/1 is not executable"}])
    else:
        receipt.update(prepare="pending", compile="not_requested", preview="not_requested", diagnostics=[])
    calls = []

    def opener(req: Any, timeout: Any = None) -> _WorkspaceResponse:
        calls.append(req)
        return _WorkspaceResponse(attachment if req.full_url.endswith("/open") else receipt)

    server = HextileMcpServer(client=Client(opener=opener))
    assert server._open_shader_workspace(_workspace_open_v2()) == attachment
    assert server._register_shader_update(_workspace_register()) == receipt
    assert len(calls) == 2 and receipt["compile"] == "not_requested"  # No proxy compiler/execution claim.
    guidance = _schema("open_shader_workspace")["description"]
    assert "source-modules/1 execution requires APP available and executable_capabilities" in guidance
    assert "version numbers do not prove execution or installed host filesystem access" in guidance


def test_workspace_v2_old_peer_200_refuses_and_v1_remains_unchanged() -> None:
    seen = []

    def opener(req: Any, timeout: Any = None) -> _WorkspaceResponse:
        seen.append(json.loads(req.data))
        return _WorkspaceResponse(_workspace_attachment())

    server = HextileMcpServer(client=Client(opener=opener))
    assert server._open_shader_workspace(_workspace_open()) == _workspace_attachment()
    with pytest.raises(HextileClientError) as caught:
        server._open_shader_workspace({**_workspace_open(), "workspace_schema": 2})
    assert caught.value.kind == "upgrade" and "reconnect" in str(caught.value)
    assert seen == [_workspace_open(), {**_workspace_open(), "workspace_schema": 2}]


@pytest.mark.parametrize("status,detail", [(404, "Not Found"),
    (409, {"code": "workspace_version_required", "message": "Unsupported workspace schema", "recovery": "Upgrade and reconnect"})])
def test_workspace_v2_missing_or_unsupported_peer_refuses_once(status: int, detail: Any) -> None:
    calls = []

    def opener(req: Any, timeout: Any = None) -> Any:
        calls.append(json.loads(req.data))
        raise urllib.error.HTTPError(req.full_url, status, "unsupported", None, io.BytesIO(json.dumps({"detail": detail}).encode()))

    with pytest.raises(HextileClientError) as caught:
        HextileMcpServer(client=Client(opener=opener))._open_shader_workspace(_workspace_open_v2())
    assert calls == [_workspace_open_v2()]
    assert caught.value.kind == ("upgrade" if status == 404 else "http")
    assert caught.value.receipt == (detail if isinstance(detail, dict) else None)


@pytest.mark.parametrize("operation", ["open_shader_workspace", "register_shader_update"])
def test_workspace_v2_uncertain_mutations_do_not_replay_or_release_paths(operation: str) -> None:
    calls = []

    def opener(req: Any, timeout: Any = None) -> Any:
        calls.append(req)
        raise http.client.RemoteDisconnected("reply lost")

    args = _workspace_open_v2() if operation == "open_shader_workspace" else _workspace_register()
    server = HextileMcpServer(client=Client(opener=opener))
    handler = server._open_shader_workspace if operation == "open_shader_workspace" else server._register_shader_update
    with pytest.raises(HextileClientError) as caught:
        handler(args)
    assert caught.value.kind == "app_down" and caught.value.receipt is None  # Existing transport classification.
    assert len(calls) == 1


def _playable_recipe() -> tuple[list[str], dict[str, Any]]:
    guide = (ROOT / "skills/360-hextile/references/recipes.md").read_text(encoding="utf-8")
    shader_section = guide.split("## Recipe I — Playable Shaders:", 1)[1]
    sources = re.findall(r"```glsl\n(.*?)```", shader_section, re.S)
    extensions = json.loads(re.search(r"```json\n(.*?)```", shader_section, re.S).group(1))
    return sources, extensions


def test_playable_recipes_match_shipped_sources_and_bound_contracts() -> None:
    # These are the two accepted producer examples, not schema stubs. Read-only
    # admission checks keep a copied guide from teaching fields APP rejects.
    app = ROOT.parent / "360-HEXTILE-APP"
    sys.path.insert(0, str(app))
    from backend.modulation.conventions import validate_conventions
    from backend.modulation.contracts import validate_modulation

    examples = json.loads((app / "plugins/shader/frontend/convention-examples.json").read_text(encoding="utf-8"))
    sources, extensions = _playable_recipe()
    assert sources == [row["candidate"]["source"] for row in examples]
    assert extensions == examples[1]["candidate"]["extensions"]
    assert extensions["required_capabilities"] == ["conventions/1", "master-clock/1", "modulation/2"]
    manifest = json.loads(sources[1].split("/*@hextile-shader\n", 1)[1].split("\n*/", 1)[0])
    descriptors = [{"id": "shader.params." + p["id"], "kind": p["type"], "unit": "unitless",
                    "min": p["ui"]["min"], "max": p["ui"]["max"], "base": p["default"], "live": True} for p in manifest["parameters"]]
    validate_conventions(extensions["conventions"], descriptors)
    validate_modulation(extensions["modulation"], descriptors, extensions["master_clock"],
                        require_aliases=True, logical_inputs=extensions["conventions"])
    assert "vec3 ro = hxCameraPosition;" in sources[0]
    assert "vec3 rd = hxCameraDirection(hx.direction);" in sources[0]
    assert "hxParam_glow" in sources[1] and "BLAST" in sources[1]
    assert extensions["conventions"]["camera"] is None


@pytest.mark.parametrize("variant", ["held", "instant", "orphan", "default_one", "schema_one"])
def test_playable_recipe_variants_use_real_intrinsic_admission(variant: str) -> None:
    sys.path.insert(0, str(ROOT.parent / "360-HEXTILE-APP"))
    from backend.modulation.contracts import ContractError, validate_modulation_intrinsic

    _, extensions = _playable_recipe()
    definition = extensions["modulation"]["definitions"][0]
    if variant == "held":
        definition["mode"] = "held"
        definition["settings"].update(attack=0.2, release=0.6)
    elif variant == "instant":
        definition["settings"]["attack"] = 0
    elif variant == "orphan":
        definition["input_id"] = "missing_gate"
    elif variant == "default_one":
        extensions["conventions"]["channels"][1]["default"] = 1
    else:
        extensions["modulation"]["schema"] = 1

    def admit() -> None:
        validate_modulation_intrinsic(extensions["modulation"], extensions["master_clock"],
                                      require_aliases=True, logical_inputs=extensions["conventions"])

    if variant in {"held", "instant"}:
        admit()
    else:
        with pytest.raises(ContractError):
            admit()


def test_playable_tool_guidance_preserves_legacy_authority_and_no_new_controls() -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    context = _schema("get_shader_context")["description"]
    proposal = _schema("propose_shader")["description"]
    workspace = _schema("open_shader_workspace")["description"]
    assert "source-free" in context and "include_formula selects" in context
    assert "every Board row" in proposal and "preserve" in proposal
    assert "attested" in proposal and "envelope" in proposal
    assert "conventions/1" in workspace and "modulation/2" in workspace
    assert "hxCameraDirection(vec3 canonicalDirection)" in workspace
    assert "never arms Interact" in workspace
    operations = _schema("propose_shader")["inputSchema"]["properties"]["modulation_edits"]
    assert {variant["properties"]["schema"]["const"] for variant in operations["oneOf"]} == {1, 2}
    assert all(variant["additionalProperties"] is False for variant in operations["oneOf"])
    assert not {"press_key", "set_pose", "arm_interact", "save_project_convention"} & {tool["name"] for tool in TOOLS}
    source = (ROOT / "skills/360-hextile/SKILL.md").read_text(encoding="utf-8")
    fragment = (ROOT / "codex/AGENTS-fragment.md").read_text(encoding="utf-8")
    assert fragment.split("-->\n\n", 1)[1] == source.split("\n---\n", 1)[1].lstrip("\n")
    catalog_text = json.dumps(TOOLS + SHADER_EXTENSION_TOOLS)
    for obsolete in ("source grant", "Capture and Apply consent", "Trusted Local Full Access",
                     "human Fractal grant", "session selected and follow_ready", "Follow and whole-source"):
        assert obsolete not in catalog_text
    assert all("lease_id" not in row["inputSchema"].get("properties", {}) for row in TOOLS + SHADER_EXTENSION_TOOLS)
