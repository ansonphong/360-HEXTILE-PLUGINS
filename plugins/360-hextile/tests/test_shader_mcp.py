"""Shader MCP tools use the named v2 doors and bounded receipts."""

from __future__ import annotations

import json
import base64
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


def _inspector_capabilities():
    return {"native_render": {"contract": "native-render/1", "stills": {}, "sequences": {},
                              "shader_preview": {"profile": "shader-export-preview/2"}}}


def _inspector_ready(request_id):
    digest = "sha256:" + "a" * 64
    return {"request_id": request_id, "state": "ready", "status": "completed", "progress": None, "error": None,
        "width": 2048, "height": 1024, "stride": 6144, "size": 2048 * 1024 * 3,
        "sha256": digest, "format": "rgb8-srgb-top-origin", "profile": "shader-export-preview/2",
        "mode": "still", "supersampling": 1.5, "physical_width": 3072, "physical_height": 1536,
        "index": 0, "time": "0/1", "frame_rate": {"num": 24, "den": 1}, "sample": None,
        "output": {"projection": "equirectangular", "pan": 0, "tilt": 0, "roll": 0},
        "document_hash": digest, "source_hash": digest, "resource_manifest_hash": None}


def test_sequence_input_capture_is_typed_private_and_recovers_original_ticket(monkeypatch):
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    tool = next(row for row in SHADER_EXTENSION_TOOLS if row['name'] == 'shader_capture_sequence_input')
    digest = 'sha256:' + 'a' * 64
    request_id = '7e720fa5-192b-47da-a705-ab3b5ddc979e'
    owner = {'request_id': request_id, 'shader': {'origin': 'user', 'shaderId': 'aurora'},
        'project_context_witness': 'w', 'studio_surface_id': 'surface', 'expected_edit_sequence': 1,
        'base': {'kind': 'saved', 'working_revision': 1, 'document_hash': digest, 'source_hash': digest}}
    jsonschema.validate(owner, tool['inputSchema'])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**owner, 'input_sample': {}}, tool['inputSchema'])
    calls = []
    native = {'contract': 'native-render/1', 'stills': {}, 'sequences': {'shader': {
        'input_snapshot': {'contract': 'shader-sequence-input/1'}}}}
    client = Client()
    monkeypatch.setattr(client, 'get_capabilities', lambda: {'native_render': native})
    def post(method, path, body=None, **kwargs):
        calls.append((method, path, body))
        return {'request_id': request_id, 'state': 'pending'}
    monkeypatch.setattr(client, 'request_json', post)
    assert client.capture_shader_sequence_input(owner) == {'request_id': request_id, 'state': 'pending'}
    assert calls == [('POST', '/api/shaders/agent-operations/output/sequence-input', owner)]
    for result in ({'request_id': request_id, 'state': 'pending', 'input_sample': {}},
                   {'request_id': 'different', 'state': 'pending'}):
        monkeypatch.setattr(client, 'request_json', lambda *a, row=result, **kw: row)
        with pytest.raises(HextileClientError) as unknown:
            client.capture_shader_sequence_input(owner)
        assert unknown.value.kind == 'shader_output_outcome_unknown'
        assert unknown.value.receipt['request_id'] == request_id
    for malformed in ({}, {'shader': []}, {'shader': {'input_snapshot': []}}):
        monkeypatch.setattr(client, 'get_capabilities', lambda: {'native_render': {**native, 'sequences': malformed}})
        with pytest.raises(HextileClientError) as refused:
            client.capture_shader_sequence_input(owner)
        assert refused.value.status_code == 501


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
    preview = {**owner, "mode": "still", "width": 2048, "height": 1024,
               "output": {"projection": "equirectangular", "pan": 0, "tilt": 0, "roll": 0}}
    jsonschema.validate(preview, descriptor("shader_request_preview")["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**preview, "output": {**preview["output"], "path": "C:/pixels.png"}},
                            descriptor("shader_request_preview")["inputSchema"])
    still = {**owner, "profile": "shader-linear-rgba-exr/1",
             "output": {"width": 2048, "height": 1024, "output_path": "D:/Temp/test.exr"}}
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
    monkeypatch.setattr(client, "get_capabilities", _inspector_capabilities)
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
    assert "Reduced display attachment" in result["content"][1]["text"]


def test_raster_still_and_dome_exr_preflight_use_native_contract(monkeypatch) -> None:
    digest = "sha256:" + "a" * 64
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    owner = {"request_id": request_id, "shader": {"origin": "user", "shaderId": "aurora"},
             "project_context_witness": "w", "base": {"kind": "saved", "working_revision": 1,
             "document_hash": digest, "source_hash": digest},
             "studio_surface_id": "surface", "expected_edit_sequence": 1}
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    schema = next(tool["inputSchema"] for tool in SHADER_EXTENSION_TOOLS
                  if tool["name"] == "shader_preflight_still_export")
    raster = {**owner, "profile": "shader-raster-still/1",
              "output": {"projection": "equirectangular", "encoding": "jpg",
                         "width": 2048, "height": 1024,
                         "output_path": "D:\\Stills\\Orbit.épreuve.JPEG"},
              "allow_unpreviewed_revision": True}
    dome_exr = {**owner, "profile": "shader-linear-rgba-exr/1",
                "output": {"projection": "fulldome", "width": 2048, "height": 2048,
                           "fov_deg": 180, "pan": 0, "tilt": 0, "roll": 0,
                           "output_path": "D:\\Stills\\dôme.final.EXR"}}
    jsonschema.validate(raster, schema)
    jsonschema.validate(dome_exr, schema)
    seen: list[tuple[str, Any]] = []
    client = Client(opener=lambda *_a, **_kw: pytest.fail("native request_json is injected"))
    monkeypatch.setattr(client, "get_capabilities", lambda: {"native_render": {
        "contract": "native-render/1", "sequences": {},
        "stills": {"shader-raster-still/1": {}, "shader-linear-rgba-exr/1": {}}}})
    def reply(method, path, body=None, **kwargs):
        seen.append((path, body))
        return {"request_id": request_id, "state": "pending"}
    monkeypatch.setattr(client, "request_json", reply)
    assert client.preflight_shader_still(raster)["state"] == "pending"
    assert seen[-1][1]["allow_unpreviewed_revision"] is True
    assert client.preflight_shader_still(dome_exr)["state"] == "pending"
    for output in ({**raster["output"], "quality_if_jpg": 91},
                   {**raster["output"], "width": 4096, "height": 1024},
                   {**dome_exr["output"], "width": 1024},
                   {**raster["output"], "output_path": "D:\\Stills\\CON.jpg"},
                   {**raster["output"], "output_path": "D:\\Stills\\Orbit.jpg "},
                   {**raster["output"], "output_path": "D:\\Stills\\Orbit.png"}):
        with pytest.raises(HextileClientError):
            client.preflight_shader_still({**(raster if "encoding" in output else dome_exr),
                                           "output": output})
    assert len(seen) == 2
    job = {"job_id": "b" * 32, "state": "completed", "progress": 1.0,
           "idempotency_key": request_id,
           "output": {"projection": "equirectangular", "width": 2048, "height": 1024,
                      "encoding": "jpg", "file": "Orbit.épreuve.JPEG"}}
    monkeypatch.setattr(client, "request_json", lambda *_a, **_kw: {
        "request_id": request_id, "profile": "shader-raster-still/1",
        "job": job, "state": "completed", "output_name": "Orbit.épreuve.JPEG",
        "output_path": "D:\\Stills\\Orbit.épreuve.JPEG"})
    result = client.get_shader_output_job({"shader": owner["shader"], "project_context_witness": "w",
                                           "request_id": request_id, "profile": "shader-raster-still/1"})
    assert result["job"]["output"]["file"] == "Orbit.épreuve.JPEG"
    assert result["output_name"] == "Orbit.épreuve.JPEG"
    for leaf in ("CON.jpg", "Orbit.jpg ", "Orbit.png", "nested/Orbit.jpg"):
        monkeypatch.setattr(client, "request_json", lambda *_a, value=leaf, **_kw: {
            "request_id": request_id, "profile": "shader-raster-still/1",
            "job": {**job, "output": {**job["output"], "file": value}},
            "state": "completed"})
        with pytest.raises(HextileClientError):
            client.get_shader_output_job({"shader": owner["shader"], "project_context_witness": "w",
                                          "request_id": request_id, "profile": "shader-raster-still/1"})
    legacy_job = {**job, "output": {"projection": "fulldome", "diameter": 1024,
                                    "fov_deg": 180, "pan": 0, "tilt": 0, "roll": 0,
                                    "file": "domes/job_old.png"}}
    monkeypatch.setattr(client, "request_json", lambda *_a, **_kw: {
        "request_id": request_id, "profile": "dome-png/1", "job": legacy_job,
        "state": "completed"})
    assert client.get_shader_output_job({"shader": owner["shader"], "project_context_witness": "w",
                                         "request_id": request_id, "profile": "dome-png/1"})["job"]["output"]["file"] == "domes/job_old.png"
    exr_args = {"shader": owner["shader"], "project_context_witness": "w",
                "request_id": request_id, "profile": "shader-linear-rgba-exr/1"}
    for leaf in ("dôme.final.EXR", "final.exr"):
        exr_job = {"job_id": "b" * 32, "state": "completed", "progress": 1.0,
                   "profile": "shader-linear-rgba-exr/1", "output": leaf}
        monkeypatch.setattr(client, "request_json", lambda *_a, row=exr_job, **_kw: {
            "request_id": request_id, "profile": "shader-linear-rgba-exr/1",
            "job": row, "state": "completed"})
        assert client.get_shader_output_job(exr_args)["job"]["output"] == leaf
        assert client.stop_shader_output_job(exr_args)["job"]["output"] == leaf
    for leaf in ("CON.exr", "nested/final.exr", "final.exr ", "final.png"):
        monkeypatch.setattr(client, "request_json", lambda *_a, value=leaf, **_kw: {
            "request_id": request_id, "profile": "shader-linear-rgba-exr/1",
            "job": {**exr_job, "output": value}, "state": "completed"})
        with pytest.raises(HextileClientError):
            client.get_shader_output_job(exr_args)


def test_shader_preview_binary_transport_requires_explicit_image_opt_in() -> None:
    shader = {"origin": "user", "shaderId": "aurora"}
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    args = {"shader": shader, "project_context_witness": "w", "request_id": request_id}
    seen = []
    class Reply(io.BytesIO):
        def __init__(self, data, content_type):
            super().__init__(data)
            self.headers = {"Content-Type": content_type, "X-Hextile-Preview-Request-ID": request_id,
                            "X-Hextile-Preview-Attachment": "reduced-display/1"}
            self.status = 200
        def getcode(self):
            return 200
    def opener(request, timeout=None):
        seen.append(request)
        if "image=true" in request.full_url:
            png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lL8AAAAASUVORK5CYII=")
            return Reply(png, "image/png")
        return Reply(json.dumps(_inspector_ready(request_id)).encode(), "application/json")
    client = Client(opener=opener)
    metadata = client.get_shader_preview(args)
    assert metadata["state"] == "ready" and seen[-1].headers["X-hextile-agent"] == "mcp"
    image = client.get_shader_preview({**args, "image": True})
    assert isinstance(image, bytes) and image.startswith(b"\x89PNG")
    assert "image=true" in seen[-1].full_url


@pytest.mark.parametrize("saved_recipe", [False, True])
def test_full_quality_preview_contract_binds_exact_samples_and_refuses_wrong_recipe(monkeypatch, saved_recipe):
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    descriptor = next(row for row in SHADER_EXTENSION_TOOLS if row["name"] == "shader_request_preview")
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    digest = "sha256:" + "a" * 64
    sample = {"start_time": {"num": "10", "den": "1"}, "end_time": {"num": "11", "den": "1"},
              "frame_rate": {"num": 30000, "den": 1001}, "frame_count": 30, "index": 29}
    request = {"request_id": request_id, "shader": {"origin": "user", "shaderId": "aurora"},
        "project_context_witness": "w", "base": {"kind": "saved", "working_revision": 1,
        "document_hash": digest, "source_hash": digest}, "studio_surface_id": "surface", "expected_edit_sequence": 1,
        "mode": "sequence", "width": 4096, "height": 4096, "sequence_sample": sample,
        "output": {"projection": "fulldome_angular", "diameter": 4096, "fov_deg": 180,
                   "pan": 0, "tilt": 0, "roll": 0, "supersampling": 1.5}}
    if saved_recipe:
        request['saved_sequence'] = {'sequence_id': 'seq_' + 'b' * 32, 'recipe_hash': digest}
    jsonschema.validate(request, descriptor["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({key: value for key, value in request.items() if key != "sequence_sample"}, descriptor["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**request, "mode": "still"}, descriptor["inputSchema"])
    client = Client()
    def capabilities():
        result = _inspector_capabilities()
        result['native_render']['sequences']['shader'] = {'recovery': {'profile': 'shader-sequence-recovery/1'}}
        return result
    monkeypatch.setattr(client, "get_capabilities", capabilities)
    calls = []
    def reply(method, path, body=None, **kwargs):
        calls.append((method, path, body))
        return {"request_id": request_id, "state": "pending"}
    monkeypatch.setattr(client, "request_json", reply)
    assert client.request_shader_preview(request)["request_id"] == request_id
    assert calls[-1][2] == request
    for patch in ({"height": 2048}, {"sequence_sample": {**sample, "index": 30}},
                  {"sequence_sample": {**sample, "frame_count": 29}}, {"sequence_sample": None},
                  {"output": {**request["output"], "supersampling": float("inf")}}):
        with pytest.raises(HextileClientError):
            client.request_shader_preview({**request, **patch})
    assert len(calls) == 1  # Invalid settings never cross mutation admission.
    ready = {**_inspector_ready(request_id), "mode": "sequence", "width": 4096, "height": 4096,
        "stride": 4096 * 3, "size": 4096 * 4096 * 3, "physical_width": 6144, "physical_height": 6144,
        "index": 29, "time": "329029/30000", "frame_rate": sample["frame_rate"], "sample": sample,
        "output": {key: value for key, value in request["output"].items() if key != "supersampling"}}
    args = {key: request[key] for key in ("request_id", "shader", "project_context_witness")}
    monkeypatch.setattr(client, "request_json", lambda *a, **kw: ready)
    assert client.get_shader_preview(args) == ready
    for patch in ({"index": 28}, {"time": "11/1"}, {"supersampling": 1}, {"width": 512},
                  {"lease": "private"}, {"intent_sha256": "a" * 64}, {"size": 10 ** 20}):
        monkeypatch.setattr(client, "request_json", lambda *a, row={**ready, **patch}, **kw: row)
        with pytest.raises(HextileClientError):
            client.get_shader_preview(args)
    monkeypatch.setattr(client, "get_capabilities", lambda: {"native_render": {
        "contract": "native-render/1", "stills": {}, "sequences": {}}})
    with pytest.raises(HextileClientError) as unavailable:
        client.request_shader_preview(request)
    assert unavailable.value.status_code == 501
    pending_cancel = {"request_id": request_id, "released": False, "status": "cancel_pending", "cleanup": "pending"}
    monkeypatch.setattr(client, "request_json", lambda *a, **kw: pending_cancel)
    assert client.release_shader_preview(args) == pending_cancel
    monkeypatch.setattr(client, "request_json", lambda *a, **kw: {**pending_cancel, "lease": "private"})
    with pytest.raises(HextileClientError) as malformed:
        client.release_shader_preview(args)
    assert malformed.value.receipt == {"request_id": request_id}


def test_native_preview_timing_and_estimate_are_bounded_and_original_request_bound(monkeypatch):
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    sample = {"start_time": {"num": "0", "den": "1"}, "end_time": {"num": "1", "den": "1"},
              "frame_rate": {"num": 24, "den": 1}, "frame_count": 24, "index": 0}
    timing = {"profile": "shader-render-timing/1", "startup_ms": 2000,
              "frame_work_ms": 500, "history_replay_ms": 0, "history_frame_count": 0}
    estimate = {"profile": "shader-render-estimate/1", "basis": "preview", "approximate": True,
                "frame_count": 24, "remaining_frames": 24, "total_ms": 14000,
                "remaining_ms": 14000, "sample_count": 1, "includes_output": False}
    ready = {**_inspector_ready(request_id), "mode": "sequence", "sample": sample,
             "timing": timing, "estimate": estimate}
    args = {"request_id": request_id, "shader": {"origin": "user", "shaderId": "aurora"},
            "project_context_witness": "w"}
    client = Client("http://127.0.0.1:9")
    monkeypatch.setattr(client, "request_json", lambda *a, **kw: ready)
    assert client.get_shader_preview(args) == ready
    for patch in ({"timing": {**timing, "frame_work_ms": float("nan")}},
                  {"timing": {**timing, "startup_ms": True}},
                  {"timing": {**timing, "path": "private"}},
                  {"estimate": {**estimate, "total_ms": 48000, "remaining_ms": 48000}},
                  {"estimate": {**estimate, "frame_count": 25}},
                  {"estimate": {**estimate, "includes_output": True}},
                  {"estimate": {**estimate, "basis": "saved_frames"}}):
        monkeypatch.setattr(client, "request_json", lambda *a, row={**ready, **patch}, **kw: row)
        with pytest.raises(HextileClientError):
            client.get_shader_preview(args)
    old = {key: value for key, value in ready.items() if key not in {"timing", "estimate"}}
    monkeypatch.setattr(client, "request_json", lambda *a, **kw: old)
    assert "estimate" not in client.get_shader_preview(args)


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
    monkeypatch.setattr(client, "get_capabilities", _inspector_capabilities)
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    shader = {"origin": "user", "shaderId": "aurora"}
    digest = "sha256:" + "a" * 64
    owner = {"request_id": request_id, "shader": shader, "project_context_witness": "w",
             "base": {"kind": "saved", "working_revision": 1,
                      "document_hash": digest, "source_hash": digest},
             "studio_surface_id": "surface", "expected_edit_sequence": 1}
    preview = {**owner, "mode": "still", "width": 2048, "height": 1024,
               "output": {"projection": "equirectangular", "pan": 0, "tilt": 0, "roll": 0}}
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
    schema = descriptor["inputSchema"]
    # Hosts that collapse oneOf were hiding New/Paste arguments. The named tool lists them flat.
    assert "oneOf" not in schema
    assert set(schema["properties"]) >= {
        "request_id", "project_context_witness", "action", "template_id", "space", "source", "title"}
    assert schema["properties"]["template_id"]["const"] == "hx_starter"
    jsonschema.validate(paste, schema)
    jsonschema.validate({"request_id": request_id, "project_context_witness": "w", "action": "new",
                         "template_id": "hx_starter", "space": "direction_360"}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**paste, "source": ""}, schema)
    closed = Client(opener=lambda *_a, **_k: pytest.fail("exclusive variants do not reach HTTP"))
    for wrong in ({**paste, "template_id": "hx_starter"},
                  {**paste, "action": "new"},
                  {"request_id": request_id, "project_context_witness": "w", "action": "new", "source": "void main(){}"}):
        with pytest.raises(HextileClientError):
            closed.create_shader_asset(wrong)
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


def test_workspace_refusal_and_unknown_outcome_keep_structured_fields(monkeypatch) -> None:
    from hextile_client import workspace_refusal
    secret = "C:\\Users\\secret\\shader.glsl"
    projected = workspace_refusal({
        "code": "provenance_protected",
        "message": "Protected provenance fields cannot change.",
        "recovery": "Preserve ai and adapted_source_hash.",
        "accepted": False,
        "files_preserved": True,
        "retry_unchanged": False,
        "next_action": "preserve_protected_bindings",
        "fields": ["$.provenance.ai", "$.provenance.adapted_source_hash", secret],
        "findings": [{"code": "provenance_protected", "field": "$.provenance.ai",
                      "message": "Protected provenance binding cannot change."}],
    })
    assert projected["code"] == "provenance_protected"
    assert projected["accepted"] is False and projected["retry_unchanged"] is False
    assert secret not in json.dumps(projected)
    assert projected["fields"] == ["$.provenance.ai", "$.provenance.adapted_source_hash"]
    client = Client(opener=lambda *_a, **_k: pytest.fail("transport failed before HTTP"))
    def broken(*_a, **_k):
        raise http.client.HTTPException("connection reset")
    monkeypatch.setattr(client, "request_json", broken)
    with pytest.raises(HextileClientError) as unknown:
        client._shader_workspace_request("POST", "/api/agent/shader-workspaces/open", {})
    assert unknown.value.kind == "workspace_outcome_unknown"
    assert unknown.value.receipt["code"] == "outcome_unknown"
    assert unknown.value.receipt["retry_unchanged"] is False
    assert unknown.value.receipt["recovery"] == (
        "Rediscover the current attachment before another attempt. Do not assume nothing changed.")
    secret = "C:\\Users\\secret\\shader.glsl"
    body = json.dumps({"detail": {
        "code": "provenance_protected",
        "message": "see " + secret,
        "fields": ["$.provenance.ai", "$.provenance." + secret],
        "accepted": False, "files_preserved": True, "retry_unchanged": False,
        "next_action": "preserve_protected_bindings",
    }})
    def leaked(*_a, **_k):
        raise HextileClientError(body, kind="http", status_code=409, body=body)
    monkeypatch.setattr(client, "request_json", leaked)
    with pytest.raises(HextileClientError) as refused:
        client._shader_workspace_request("POST", "/api/agent/shader-workspaces/h/updates", {})
    assert secret not in str(refused.value)
    assert secret not in json.dumps(refused.value.receipt)
    assert refused.value.receipt["code"] == "provenance_protected"
    assert refused.value.receipt["fields"] == ["$.provenance.ai"]



def test_v2_saved_output_owner_and_bundle_receipt_round_trip(monkeypatch) -> None:
    monkeypatch.setattr("hextile_client.Path", PurePosixPath)
    digest = "sha256:" + "a" * 64
    request_id = "7e720fa5-192b-47da-a705-ab3b5ddc979e"
    shader = {"origin": "user", "shaderId": "aurora"}
    owner = {"request_id": request_id, "shader": shader, "project_context_witness": "w",
             "studio_surface_id": "surface", "base": {"kind": "saved", "working_revision": 1,
                 "document_hash": digest, "source_hash": digest}}
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    descriptor = lambda name: next(tool for tool in SHADER_EXTENSION_TOOLS if tool["name"] == name)
    for name, extra in (
            ("shader_request_preview", {"mode": "still", "width": 4, "height": 2,
                "output": {"projection": "equirectangular", "pan": 0, "tilt": 0, "roll": 0}}),
            ("shader_preflight_still_export", {"profile": "png-master/1",
                "output": {"width": 4, "height": 2}}),
            ("shader_export_still", {"profile": "png-master/1", "preflight_request_id": request_id}),
            ("shader_capture_sequence_input", {}),
            ("shader_export_bundle", {"expected_looks": [], "expected_provenance_hash": None})):
        jsonschema.validate({**owner, **extra}, descriptor(name)["inputSchema"])
    client = Client(opener=lambda *_a, **_k: pytest.fail("request_json is injected"))
    destination = "D:/Temp/frame.hexshader"
    bundle = {**owner, "expected_looks": [], "expected_provenance_hash": None,
              "output_path": destination}
    receipt = {"request_id": request_id, "state": "saved", "stack": "v2",
               "output_name": "frame.hexshader", "output_path": destination,
               "resource_count": 0, "resource_bytes": 0}
    monkeypatch.setattr(client, "request_json", lambda *a, **k: receipt)
    assert client.export_shader_bundle(bundle) == receipt
    recovery = {"schema": 1, "request_id": request_id, "scope": "output",
                "operation": "shader_export_bundle", "project_context_witness": "w",
                "shader": shader, "state": "saved", "receipt": receipt}
    monkeypatch.setattr(client, "request_json", lambda *a, **k: recovery)
    assert client.get_shader_operation({"request_id": request_id, "project_context_witness": "w",
                                        "shader": shader, "scope": "output"}) == recovery


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
    surface = {"current_surface": {"kind": "shader_workshop",
        "owner_id": "owner", "owner_generation": 1, "viewer_generation": 2, "source_epoch": 3,
        "shader": {"origin": "user", "shaderId": "aurora"}}}
    def reply(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        if path.endswith("/live-context"):
            return surface
        if path.endswith("/playback"):
            return {"delivery": "delivered"}
        return {"schema": 1, "request_id": body["request_id"], "state": "pending",
                "operation": "shader_set_capture"}
    monkeypatch.setattr(client, "request_json", reply)
    target = {"shader": {"origin": "user", "shaderId": "aurora"},
              "project_context_witness": "witness", "studio_surface_id": "surface",
              "request_id": "7e720fa5-192b-47da-a705-ab3b5ddc979e",
              "expected_edit_sequence": 3}
    assert client.set_shader_capture({**target, "action": "live_seed", "seed": 7})["state"] == "pending"
    assert calls[-1][1].endswith("/capture")
    playback = {key: target[key] for key in ("shader", "project_context_witness", "request_id")}
    assert client.control_shader_clock({**playback, "action": "play"})["state"] == "applied"
    assert calls[-1][1:] == ("/api/shaders/aurora/playback",
                           {"origin": "user", "action": "play", "request_id": target["request_id"]}, {})
    assert client.control_shader_clock({**playback, "action": "seek", "time": 2.5})["state"] == "applied"
    assert calls[-1][2]["time"] == 2.5
    assert not any(path.endswith("/live-context") for _, path, *_ in calls)
    owner = {"owner_id": "owner", "owner_generation": 1, "viewer_generation": 2, "source_epoch": 3}
    step_schema = next(tool for tool in SHADER_EXTENSION_TOOLS if tool["name"] == "shader_step_frame")["inputSchema"]
    assert "owner" in step_schema["required"] and step_schema["additionalProperties"] is False
    assert client.step_shader_frame({**playback, "direction": 1, "owner": owner})["state"] == "applied"
    assert calls[-2][0] == "GET" and calls[-2][1] == "/api/agent/live-context"
    assert "view" not in calls[-2][3]["params"]
    assert calls[-1][2] == {"origin": "user", "action": "step", "request_id": target["request_id"], "direction": 1}
    assert "owner" not in calls[-1][2]
    with pytest.raises(HextileClientError) as stale:
        client.step_shader_frame({**playback, "direction": 1, "owner": {**owner, "owner_generation": 9}})
    assert stale.value.status_code == 409 and stale.value.receipt == {
        "code": "owner_changed",
        "message": "The mounted Shader preview owner changed. Read the current surface before stepping.",
        "next_step": "get_live_context"}
    assert calls[-1][1].endswith("/live-context")
    def down(method, path, body=None, **kwargs):
        if path.endswith("/live-context"):
            raise HextileClientError("down", kind="app_down")
        return {"delivery": "delivered"}
    monkeypatch.setattr(client, "request_json", down)
    with pytest.raises(HextileClientError) as transport:
        client.step_shader_frame({**playback, "direction": 1, "owner": owner})
    assert transport.value.kind == "app_down"
    with pytest.raises(HextileClientError):
        client.control_shader_clock({**playback, "action": "reanchor", "bpm": 120})
    with pytest.raises(HextileClientError):
        client.step_shader_frame({**playback, "direction": 1})
    with pytest.raises(HextileClientError):
        client.step_shader_frame({**playback, "direction": 0, "owner": owner})
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
        "changes": {"text": {"author": "Artist"}}}
    jsonschema.validate(proposal, next(tool for tool in SHADER_EXTENSION_TOOLS
                                       if tool["name"] == "shader_propose_credits")["inputSchema"])
    assert client.propose_shader_credits(proposal)["state"] == "pending"
    assert calls[-1][2] == proposal
    assert client.research_shader_sources({**target, "source_url": "https://example.com"})["pages"] == []
    with pytest.raises(HextileClientError):
        client.propose_shader_credits({**proposal, "changes": {"author": "Artist"}})
    with pytest.raises(HextileClientError):
        client.propose_shader_credits({**proposal, "changes": {"distribution": {}}})


def test_credit_changes_match_package_keys() -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    schema = next(tool for tool in SHADER_EXTENSION_TOOLS if tool["name"] == "shader_propose_credits")["inputSchema"]
    changes = schema["properties"]["changes"]
    assert set(changes["properties"]) == {
        "licenses_append", "contributor", "contribution", "record", "retained", "lineage", "text"}
    assert changes["minProperties"] == 1 and changes["additionalProperties"] is False
    ref = {"origin": "user", "shaderId": "aurora"}
    proposal = {"shader": ref, "project_context_witness": "wit",
        "request_id": "7e720fa5-192b-47da-a705-ab3b5ddc979e",
        "base": {"kind": "saved", "working_revision": 1, "document_hash": "sha256:" + "a" * 64,
                 "source_hash": "sha256:" + "b" * 64},
        "working_digest": None, "expected_provenance_hash": None,
        "changes": {"text": {"author": "Artist"}}}
    jsonschema.validate(proposal, schema)
    client = Client("http://127.0.0.1:9")
    for rejected in ({"author": "Artist"}, {"distribution": {}}, {}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**proposal, "changes": rejected}, schema)
        with pytest.raises(HextileClientError):
            client.propose_shader_credits({**proposal, "changes": rejected})


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


def test_register_forwards_digest_lease_and_seen(monkeypatch) -> None:
    digest = "sha256:" + "ab" * 32
    seen = [{"address": ["parameters", "fog"], "human": 1}]
    args = {"shader_id": "aurora", "request_id": "req-register", "digest": digest,
            "lease": {"holder": "agent", "generation": 0}, "seen": seen}
    jsonschema.validate(args, _schema("register_shader_update")["inputSchema"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**args, "handle": "workspace_1"}, _schema("register_shader_update")["inputSchema"])
    saved = {"save": "saved", "merge": [{"op": "set", "address": ["parameters", "fog"],
                                         "outcome": "kept", "value": 0.2}],
             "lease": {"holder": "agent", "generation": 0}, "commit": 3, "revision": 4}
    sent = {}
    client = Client("http://127.0.0.1:9")

    def request_json(method, path, body=None, **kwargs):
        sent["method"] = method
        sent["path"] = path
        sent["body"] = body
        return saved

    monkeypatch.setattr(client, "request_json", request_json)
    registered = client.register_shader_update(args)
    assert registered["merge"] == [{"op": "set", "address": ["parameters", "fog"],
                                    "outcome": "kept", "value": 0.2}]
    assert "kept_count" not in registered
    assert sent == {"method": "POST", "path": "/api/shaders/aurora/register",
                    "body": {"request_id": "req-register", "digest": digest,
                             "lease": args["lease"], "seen": seen}}
    with pytest.raises(HextileClientError):
        client.register_shader_update({**args, "seen": [{"address": "parameters.fog", "human": 1}]})


def test_changed_kept_rows_stay_and_unchanged_kept_rows_are_omitted(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    changed = {"op": "set", "address": ["parameters", "fog"], "outcome": "kept",
               "before": 0.1, "value": 0.4, "human": 3}
    unchanged = {"op": "set", "address": ["parameters", "gain"], "outcome": "kept",
                 "before": 1, "value": 1, "human": 2}
    created = {"op": "create", "address": ["parameters", "haze"], "outcome": "kept", "value": 0.5}
    body = _saved_body()
    body["merge"] = [changed, unchanged, created]
    monkeypatch.setattr(client, "request_json", lambda *args, **kwargs: body)
    saved = client.get_shader_update(_package_args())
    assert saved["kept_count"] == 1
    assert saved["merge"] == [changed, created]
    assert saved["merge"][0]["address"] == ["parameters", "fog"]
    assert saved["merge"][0]["outcome"] == "kept"
    assert saved["merge"][0]["human"] == 3


def test_conflict_and_skipped_rows_keep_bounded_source(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    glsl = "void hxMain() {\n  gl_FragColor = vec4(1.0);\n}\n" * 8
    skipped = {"op": "set", "address": ["code"], "outcome": "skipped",
               "value": {"source.glsl": glsl}}
    conflict = {"op": "set", "address": ["code"], "outcome": "lost_to_human", "human": 4,
                "before": {"source.glsl": glsl}, "value": {"source.glsl": glsl + "\n"}}
    rewritten = {"op": "set", "address": ["code"], "outcome": "rewritten",
                 "value": {"source.glsl": glsl}}
    body = _saved_body()
    body["merge"] = [skipped, conflict, rewritten]
    monkeypatch.setattr(client, "request_json", lambda *args, **kwargs: body)
    saved = client.get_shader_update(_package_args())
    assert saved["merge"][0]["value"]["source.glsl"] == glsl
    assert saved["merge"][1]["before"]["source.glsl"] == glsl
    assert saved["merge"][1]["value"]["source.glsl"] == glsl + "\n"
    assert saved["merge"][1]["human"] == 4
    digest = saved["merge"][2]["value"]["files"][0]
    assert digest["path"] == "source.glsl" and digest["bytes"] == len(glsl.encode("utf-8"))
    assert glsl not in json.dumps(saved["merge"][2])
    huge = "void hxMain() {\n" + ("x" * 70000)
    body["merge"] = [{"op": "set", "address": ["code"], "outcome": "skipped",
                      "value": {"source.glsl": huge}}]
    with pytest.raises(HextileClientError) as caught:
        client.get_shader_update(_package_args())
    assert "Malformed Shader merge report" in str(caught.value)
    assert "xxx" not in str(caught.value)


def test_native_shader_extension_routes_are_explicit_and_closed() -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS

    names = {tool["name"] for tool in SHADER_EXTENSION_TOOLS}
    assert {"shader_list_assets", "shader_get_history", "shader_get_looks",
            "shader_get_project_conventions"} <= names
    assert "shader_get_proposal" not in names
    assert "shader_get_workspace" not in names
    assert "shader_stop_workspace" not in names
    assert "shader_recheck_update" not in names
    assert "shader_edit" in {tool["name"] for tool in TOOLS}
    assert "shader_edit" not in names
    assert {"shader_get_asset_state", "shader_rename_asset", "shader_delete_asset",
            "shader_open_asset", "shader_create_asset", "shader_fork_asset",
            "shader_duplicate_asset",
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

    def reply(method, path, payload):
        sent.append((method, path, payload))
        if path.endswith("/delete"):
            return {"stack": "v2", "deleted": True, "shader_id": ref["shaderId"], "origin": ref["origin"]}
        return {"request_id": request_id,
                "operation": "shader_save_as" if path.endswith("/save-as") else "shader_open_asset",
                "state": "applied"}

    monkeypatch.setattr(client, "request_json", reply)
    assert client.delete_shader_asset(body)["deleted"] is True
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
    as_copy = {**save, "title": "A copy"}
    assert client.save_shader_as(as_copy)["state"] == "applied"
    assert sent[-1] == ("POST", "/api/shaders/agent-operations/save-as", as_copy)
    with pytest.raises(HextileClientError):
        client.save_shader_as({**as_copy, "title": ""})


def test_rename_and_delete_receipts_match_route_bodies(monkeypatch) -> None:
    """The route body is the receipt. A request id, an extra operation, or the wrong target is not success."""
    client = Client("http://127.0.0.1:9")
    request_id = "b5897a63-59a1-4d8f-aecb-36ba083fc1ea"
    ref = {"origin": "user", "shaderId": "aurora"}
    project = {"origin": "project", "shaderId": "aurora"}
    digest = "sha256:" + "a" * 64
    base = {"kind": "saved", "working_revision": 1, "document_hash": digest, "source_hash": digest}
    rename = {"request_id": request_id, "shader": ref, "project_context_witness": "wit",
              "base": base, "expected_working_digest": digest, "title": "Renamed",
              "library_intent": "saved", "confirmation_scope": {"operation": "rename", "shader": ref}}
    removal = {key: value for key, value in rename.items() if key != "title"}
    removal["confirmation_scope"] = {"operation": "delete", "shader": ref}
    lease = {"holder": "agent", "generation": 0}
    renamed = {"stack": "v2", "shader_id": "aurora", "title": "Renamed", "tags": ["e2e"],
               "revision": 9, "commit": 9, "digest": digest, "lease": lease}
    deleted = {"stack": "v2", "deleted": True, "shader_id": "aurora", "origin": "user"}
    replies = {"rename": renamed, "delete": deleted}

    def reply(method, path, payload=None, **kwargs):
        if path.endswith("/rename"):
            return replies["rename"]
        if path.endswith("/delete"):
            return replies["delete"]
        raise AssertionError(path)

    monkeypatch.setattr(client, "request_json", reply)
    assert client.rename_shader_asset(rename)["title"] == "Renamed"
    assert client.delete_shader_asset(removal)["origin"] == "user"

    def reject(kind, body, call):
        replies[kind] = body
        with pytest.raises(HextileClientError) as caught:
            call()
        assert caught.value.kind == "shader_operation_outcome_unknown"

    reject("rename", {"request_id": request_id, "state": "saved"}, lambda: client.rename_shader_asset(rename))
    reject("rename", {**renamed, "operation": "shader_library_commit"}, lambda: client.rename_shader_asset(rename))
    reject("rename", {**renamed, "origin": "user"}, lambda: client.rename_shader_asset(rename))
    reject("rename", {**renamed, "title": "Other"}, lambda: client.rename_shader_asset(rename))
    reject("rename", {**renamed, "shader_id": "other"}, lambda: client.rename_shader_asset(rename))
    replies["rename"] = renamed
    reject("delete", {"request_id": request_id, "operation": "shader_delete_asset", "state": "saved"},
           lambda: client.delete_shader_asset(removal))
    reject("delete", {**deleted, "origin": "project"}, lambda: client.delete_shader_asset(removal))
    reject("delete", {**deleted, "shader_id": "other"}, lambda: client.delete_shader_asset(removal))
    reject("delete", {**deleted, "operation": "delete"}, lambda: client.delete_shader_asset(removal))
    project_delete = {**removal, "shader": project,
                      "confirmation_scope": {"operation": "delete", "shader": project}}
    reject("delete", deleted, lambda: client.delete_shader_asset(project_delete))
    replies["delete"] = {"stack": "v2", "deleted": True, "shader_id": "aurora", "origin": "project"}
    assert client.delete_shader_asset(project_delete)["origin"] == "project"


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


def test_duplicate_saved_shader_posts_once_and_recovers_the_source_request(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    sent = []
    request_id = "b5897a63-59a1-4d8f-aecb-36ba083fc1ea"
    shader = {"origin": "user", "shaderId": "source"}
    base = {"kind": "saved", "working_revision": 3, "document_hash": "sha256:" + "a" * 64,
            "source_hash": "sha256:" + "b" * 64}
    body = {"request_id": request_id, "project_context_witness": "wit", "shader": shader, "base": base,
            "destination_origin": "project"}
    digest = "sha256:" + "d" * 64
    saved = {"schema": 1, "request_id": request_id, "operation": "shader_duplicate_asset", "state": "saved",
             "shader": shader, "project_context_witness": "wit", "receipt": {
                 "shader": {"origin": "project", "shaderId": "shader_copy"}, "working_revision": 1,
                 "document_hash": digest, "source_hash": digest, "manifest_hash": digest, "placement": "placed"}}
    refused = {"schema": 1, "request_id": request_id, "operation": "shader_duplicate_asset", "state": "refused",
               "shader": shader, "project_context_witness": "wit", "error": {"message": "Source Shader is not saved"}}
    unknown_created = {"schema": 1, "request_id": request_id, "operation": "shader_duplicate_asset",
                       "state": "unknown", "shader": shader, "project_context_witness": "wit",
                       "created": {"shader": {"origin": "project", "shaderId": "shader_copy"},
                                   "working_revision": 1, "document_hash": digest, "source_hash": digest,
                                   "manifest_hash": digest}, "placement": "unavailable"}
    unknown = {key: value for key, value in unknown_created.items() if key not in {"created", "placement"}}
    mode = {"kind": "saved"}

    def reply(method, path, payload=None, **kwargs):
        sent.append((method, path, payload))
        if path.endswith("/duplicate") and mode["kind"] == "lost":
            raise HextileClientError("lost", kind="app_down", status_code=503)
        return {"saved": saved, "refused": refused, "created": unknown_created, "unknown": unknown,
                "thin": {"request_id": request_id, "operation": "shader_duplicate_asset"},
                "schema_bool": {**saved, "schema": True},
                "schema_float": {**saved, "schema": 1.0}}[mode["kind"]]

    monkeypatch.setattr(client, "request_json", reply)
    mode["kind"] = "lost"
    with pytest.raises(HextileClientError) as lost:
        client.duplicate_shader_asset(body)
    mode["kind"] = "saved"
    assert lost.value.kind == "shader_operation_outcome_unknown"
    assert lost.value.receipt == {"request_id": request_id, "shader": shader}
    assert sent == [("POST", "/api/shaders/agent-operations/duplicate", body)]
    assert client.get_shader_operation({"request_id": request_id, "project_context_witness": "wit",
                                        "shader": shader})["receipt"]["placement"] == "placed"
    assert client.duplicate_shader_asset(body)["receipt"]["shader"]["shaderId"] == "shader_copy"
    assert [item[1] for item in sent].count("/api/shaders/agent-operations/duplicate") == 2
    with pytest.raises(HextileClientError):
        client.duplicate_shader_asset({**body, "destination_origin": "builtin"})
    with pytest.raises(HextileClientError):
        client.duplicate_shader_asset({**body, "actor": "human"})
    with pytest.raises(HextileClientError) as bad_origin:
        client.duplicate_shader_asset({**body, "shader": {"origin": {"shelf": "user"}, "shaderId": "source"}})
    assert bad_origin.value.status_code == 422
    with pytest.raises(HextileClientError) as bad_destination:
        client.duplicate_shader_asset({**body, "destination_origin": ["project"]})
    assert bad_destination.value.status_code == 422
    assert [item[1] for item in sent].count("/api/shaders/agent-operations/duplicate") == 2
    mode["kind"] = "refused"
    assert client.duplicate_shader_asset(body)["state"] == "refused"
    assert client.get_shader_operation({"request_id": request_id, "project_context_witness": "wit",
                                        "shader": shader})["state"] == "refused"
    mode["kind"] = "created"
    assert client.get_shader_operation({"request_id": request_id, "project_context_witness": "wit",
                                        "shader": shader})["placement"] == "unavailable"
    mode["kind"] = "unknown"
    assert client.duplicate_shader_asset(body)["state"] == "unknown"
    mode["kind"] = "thin"
    with pytest.raises(HextileClientError) as thin:
        client.duplicate_shader_asset(body)
    assert thin.value.kind == "shader_operation_outcome_unknown"
    with pytest.raises(HextileClientError) as thin_status:
        client.get_shader_operation({"request_id": request_id, "project_context_witness": "wit", "shader": shader})
    assert thin_status.value.kind == "other"
    for kind, schema in (("schema_bool", True), ("schema_float", 1.0)):
        mode["kind"] = kind
        with pytest.raises(HextileClientError) as bad_schema:
            client.duplicate_shader_asset(body)
        assert bad_schema.value.kind == "shader_operation_outcome_unknown"
        with pytest.raises(HextileClientError) as bad_status:
            client.get_shader_operation({"request_id": request_id, "project_context_witness": "wit",
                                        "shader": shader})
        assert bad_status.value.kind == "other"


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
    rename_digest = "sha256:" + "d" * 64
    renamed = {"stack": "v2", "shader_id": "aurora", "title": "Renamed", "tags": ["night"],
               "revision": 2, "commit": 4, "digest": rename_digest,
               "lease": {"holder": "agent", "generation": 0}}

    def reply(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        if path.endswith("/rename"):
            return renamed
        if body:
            return {"request_id": body["request_id"], "state": "applied"}
        if path.endswith("/asset-state"):
            return {"schema": 1, "shader": {"origin": "user", "shaderId": "aurora"},
                    "project_context_witness": "wit", "status": "saved", "provenance": "saved",
                    "base": {}, "capability": {}, "writable": False, "save_state": "saved"}
        return {"state": "applied"}

    monkeypatch.setattr(client, "request_json", reply)
    ref = {"origin": "user", "shaderId": "aurora"}
    assert client.get_shader_asset_state({"shader": ref, "project_context_witness": "wit"})["status"] == "saved"
    request_id = "b5897a63-59a1-4d8f-aecb-36ba083fc1ea"
    base = {"kind": "saved", "working_revision": 1, "document_hash": "sha256:" + "a" * 64,
            "source_hash": "sha256:" + "b" * 64}
    body = {"request_id": request_id, "shader": ref, "project_context_witness": "wit",
            "base": base, "expected_working_digest": "sha256:" + "c" * 64, "title": "Renamed",
            "confirmation_scope": {"operation": "rename", "shader": ref}}
    assert client.rename_shader_asset(body) == renamed
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


def test_list_shader_assets_omits_an_absent_witness(monkeypatch) -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    tool = next(item for item in SHADER_EXTENSION_TOOLS if item["name"] == "shader_list_assets")
    assert "project_context_witness" not in tool["inputSchema"].get("required", [])
    assert tool["description"].endswith(
        "Omit the witness to discover it; the reply carries the current project_context_witness.")
    client = Client("http://127.0.0.1:9")
    calls = []
    reply = {"schema": 1, "project_context_witness": "live", "project": {},
             "entries": [], "next_cursor": None}

    def fake(method, path, body=None, **kwargs):
        calls.append((method, path, kwargs.get("params")))
        return reply

    monkeypatch.setattr(client, "request_json", fake)
    assert client.list_shader_assets({})["project_context_witness"] == "live"
    assert calls == [("GET", "/api/shaders/agent-operations/assets", {})]
    assert client.list_shader_assets({"project_context_witness": "wit", "shelf": "user"})["entries"] == []
    assert calls[1][2] == {"project_context_witness": "wit", "shelf": "user"}
    with pytest.raises(HextileClientError) as bad:
        client.list_shader_assets({"project_context_witness": ""})
    assert bad.value.status_code == 422
    with pytest.raises(HextileClientError) as missing:
        client.get_shader_project_conventions({})
    assert "project_context_witness" in str(missing.value)



def test_compile_ok_matches_status(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")

    def compile_of(profile: dict[str, Any]) -> dict[str, Any]:
        fresh = _saved_body(compile={"revision": 4, "profiles": [profile]})
        monkeypatch.setattr(client, "request_json", lambda *args, fresh=fresh, **kwargs: fresh)
        return client.get_shader_update(_package_args())

    assert compile_of({"profile": "webgl2", "status": "passed", "program_identity": "prog", "ok": True})["compile"]["profiles"][0]["ok"] is True
    assert compile_of({"profile": "webgl2", "status": "failed", "program_identity": None, "ok": False})["compile"]["profiles"][0]["ok"] is False
    pending = compile_of({"profile": "webgl2", "status": "pending", "program_identity": None, "ok": None})
    assert pending["compile_note"] == "compile pending; poll get_shader_update"
    quiet = compile_of({"profile": "dome", "status": "not_observed", "program_identity": None, "ok": None})
    assert "compile_note" not in quiet
    for bad in (
        {"profile": "webgl2", "status": "passed", "program_identity": "prog", "ok": None},
        {"profile": "webgl2", "status": "passed", "program_identity": "prog"},
        {"profile": "webgl2", "status": "failed", "program_identity": None, "ok": None},
        {"profile": "webgl2", "status": "failed", "program_identity": None, "ok": True},
        {"profile": "webgl2", "status": "passed", "program_identity": "prog", "ok": False},
    ):
        fresh = _saved_body(compile={"revision": 4, "profiles": [bad]})
        monkeypatch.setattr(client, "request_json", lambda *args, fresh=fresh, **kwargs: fresh)
        with pytest.raises(HextileClientError) as caught:
            client.get_shader_update(_package_args())
        assert "Malformed compile report" in str(caught.value)


def test_register_digest_covers_workspace_text_only() -> None:
    authoring = (ROOT / "skills" / "shader" / "references" / "authoring.md").read_text(encoding="utf-8")
    snippet, after = authoring.split("```python", 1)[1].split("```", 1)
    assert "def package_digest" in snippet
    note = after.strip().split("\n\n", 1)[0]
    for member in ("shader.json", "provenance.json", "source.glsl", "modules"):
        assert member in note
    assert "does not cover" in note and "resources" in note and "originals" in note


def test_shader_recheck_update_is_absent() -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS, TOOL_NAMES
    listed = {tool["name"] for tool in TOOLS + SHADER_EXTENSION_TOOLS}
    assert "shader_recheck_update" not in listed
    assert not hasattr(Client, "recheck_shader_update")
    assert "shader_edit" in TOOL_NAMES


def test_live_shader_context_accepts_v2_and_refuses_the_old_compact_shape(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")
    v2 = {"view": "shader", "stack": "v2", "connected": True, "mcp_enabled": True,
          "shader": {"origin": "user", "shader_id": "aurora"},
          "lease": {"holder": "agent", "generation": 0}, "commit": 1, "revision": 1}
    monkeypatch.setattr(client, "get_json", lambda *args, **kwargs: v2)
    assert client.get_live_context(view="shader") == v2
    old = {"view": "shader", "schema": 1, "mcp_enabled": True, "current_surface": {},
           "shader_contract": {}, "shader_summary": {}}
    monkeypatch.setattr(client, "get_json", lambda *args, **kwargs: old)
    with pytest.raises(HextileClientError) as caught:
        client.get_live_context(view="shader")
    assert caught.value.kind == "unsupported"



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
    procedure = (ROOT / "skills" / "shader" / "references" / "authoring.md").read_text(encoding="utf-8")
    for phrase in (
        "provenance.json", "lineage", "retained_credits", "ai_assistance",
        "distribution", "permission to distribute", "human_only", "proposed",
    ):
        assert phrase in guide
        assert phrase in procedure


def test_attribution_guides_teach_limits_and_typed_proposal() -> None:
    from hextile_mcp import load_guide

    guide = load_guide("best-practices")["markdown"]
    skill = (ROOT / "skills" / "shader" / "references" / "authoring.md").read_text(encoding="utf-8")
    assert "64 KiB" in guide and "256 KiB" in guide
    assert "depth at most 2" in guide or "depth 2" in guide
    assert "30 seconds" in guide and "four" in guide
    assert "do not claim a page was read" in guide.lower() or "when it was not" in guide
    assert "proposed" in guide and "human_only" in guide
    assert "64 KiB" in skill and "256 KiB" in skill
    assert "depth at most 2" in skill
    assert "30 seconds" in skill and "four" in skill
    assert "do not claim a page was read" in skill.lower()
    assert "Register saves. Read merge to see what was kept." in skill
    assert "stale_lease" in skill
    assert "Take control" in skill and "Hand back" in skill
    assert "comes back skipped" in skill


def test_stale_lease_and_human_only_keep_next_step(monkeypatch) -> None:
    from hextile_client import validate_shader_workspace
    args = {"shader_id": "aurora", "request_id": "req-register",
            "digest": "sha256:" + "ab" * 32, "lease": {"holder": "agent", "generation": 0}}
    jsonschema.validate(args, _schema("register_shader_update")["inputSchema"])
    validate_shader_workspace("register", args)
    cases = (
        (409, "stale_lease", "The human holds the code and can hand it back.",
         "Hand the code back, then register again."),
        (403, "human_only", "Credits require human review.", "Propose credits for the Credits card."),
    )
    for status, code, message, next_step in cases:
        sent = {}

        def capture(method, path, body=None, **kwargs):
            sent["body"] = body
            raw = json.dumps({"detail": {"code": code, "message": message, "next_step": next_step}})
            raise HextileClientError(message, status_code=status, body=raw, kind="http")

        client = Client("http://127.0.0.1:9")
        monkeypatch.setattr(client, "request_json", capture)
        with pytest.raises(HextileClientError) as refused:
            client.register_shader_update(args)
        assert refused.value.kind == "http"
        assert refused.value.status_code == status
        assert refused.value.receipt["code"] == code
        assert refused.value.receipt["message"] == message
        assert refused.value.receipt["next_step"] == next_step
        assert sent["body"]["digest"] == args["digest"]
        assert sent["body"]["lease"] == args["lease"]


def _parameter_witness() -> dict[str, Any]:
    return {"studio_surface_id": "surface", "project_context_witness": "wit",
            "shader": {"origin": "user", "shaderId": "aurora"},
            "base": {"working_revision": 1, "manifest_hash": None,
                     "document_hash": "sha256:" + "ab" * 32,
                     "source_hash": "sha256:" + "cd" * 32},
            "edit_sequence": 7}





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






def _board_candidate(ident: str) -> dict[str, Any]:
    return {
        "candidate_id": ident,
        "complete_candidate": {"source": "x", "values": {}, "capture_defaults": {},
                               "output": {}, "space": "direction_360", "extensions": {}},
        "explanation": "One look",
    }


def _variation_board(count: int) -> dict[str, Any]:
    base = {**_proposal()["base"], "frozen_capture_hash": "sha256:" + "ef" * 32}
    return {"kind": "shader_variation_board", "board_id": "board-1", "base": base,
            "candidates": [_board_candidate(f"row-{index}") for index in range(count)]}











def _lease() -> dict[str, Any]:
    return {"holder": "agent", "generation": 0}


def _package_args(**extra: Any) -> dict[str, Any]:
    body = {"shader_id": "aurora", "request_id": "req-1"}
    body.update(extra)
    return body


def _merge_row(**extra: Any) -> dict[str, Any]:
    row = {"op": "set", "address": ["parameters", "fog"], "outcome": "kept", "value": 0.2}
    row.update(extra)
    return row


def _open_body(**extra: Any) -> dict[str, Any]:
    body = {"lease": _lease(), "commit": 1, "revision": 2}
    body.update(extra)
    return body


def _saved_body(**extra: Any) -> dict[str, Any]:
    body = {"save": "saved", "merge": [_merge_row()], "not_adopted": [],
            "lease": _lease(), "commit": 3, "revision": 4,
            "compile": {"revision": 4, "profiles": [
                {"profile": "preview", "status": "pending", "program_identity": None}]}}
    body.update(extra)
    return body


def _edit_body() -> dict[str, Any]:
    return {"save": "saved", "results": [
        _merge_row(outcome="lost_to_human", human=2, before=0.1, value=0.4)],
            "commit": 5, "revision": 6}


def test_package_tool_schemas_are_closed() -> None:
    opened = _schema("open_shader_workspace")["inputSchema"]
    registered = _schema("register_shader_update")["inputSchema"]
    got = _schema("get_shader_update")["inputSchema"]
    edited = _schema("shader_edit")["inputSchema"]
    package = _package_args()
    digest = "sha256:" + "ab" * 32
    edit = _package_args(edits=[{"op": "set", "address": ["parameters", "fog"], "value": 0.2}],
                         lease=_lease(), seen=[{"address": ["parameters", "fog"], "human": 1}])
    delete = _package_args(edits=[{"op": "delete", "address": ["parameters", "fog"]}])
    for schema, args in ((opened, package), (got, package),
                         (registered, {**package, "digest": digest, "lease": _lease()}),
                         (edited, edit), (edited, delete)):
        assert schema["additionalProperties"] is False
        jsonschema.validate(args, schema)
    for schema in (opened, got, registered, edited):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**package, "handle": "workspace_1"}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_package_args(shader_id="bad id"), opened)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_package_args(edits=[]), edited)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_package_args(edits=[{"op": "set", "address": "parameters.fog", "value": 1}]), edited)
    for op in ("set", "create", "reshape"):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_package_args(edits=[{"op": op, "address": ["parameters", "fog"]}]), edited)
        jsonschema.validate(_package_args(edits=[{"op": op, "address": ["parameters", "fog"], "value": 1}]), edited)


def _capture(monkeypatch, reply):
    sent = []
    client = Client("http://127.0.0.1:9")

    def request_json(method, path, body=None, **kwargs):
        sent.append((method, path, body))
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(client, "request_json", request_json)
    return client, sent


def test_open_posts_only_the_request_id_and_returns_the_lease(monkeypatch) -> None:
    client, sent = _capture(monkeypatch, _open_body(not_adopted=[
        {"address": ["parameters", "fog"], "outcome": "not_adopted", "value": 1}]))
    result = client.open_shader_workspace(_package_args())
    assert sent == [("POST", "/api/shaders/aurora/workspace", {"request_id": "req-1"})]
    assert result["lease"] == _lease()
    assert result["not_adopted"][0]["outcome"] == "not_adopted"
    again, second = _capture(monkeypatch, _open_body())
    again.open_shader_workspace(_package_args())
    again.open_shader_workspace(_package_args())
    assert len(second) == 2 and second[0][2] == second[1][2]


def test_shader_edit_posts_the_batch_and_keeps_lost_to_human(monkeypatch) -> None:
    args = _package_args(edits=[{"op": "delete", "address": ["parameters", "fog"]}],
                         lease=_lease(), seen=[{"address": ["parameters", "fog"], "human": 2}])
    client, sent = _capture(monkeypatch, _edit_body())
    result = client.shader_edit(args)
    assert sent[0][0] == "POST" and sent[0][1] == "/api/shaders/aurora/agent/edits"
    assert sent[0][2]["edits"] == args["edits"]
    assert sent[0][2]["seen"] == args["seen"]
    assert sent[0][2]["lease"] == _lease()
    assert result["results"][0]["outcome"] == "lost_to_human"
    assert result["results"][0]["human"] == 2
    with pytest.raises(HextileClientError):
        client.shader_edit(_package_args(edits=[{"op": "set", "address": ["parameters", "fog"]}]))


def test_get_reads_the_recorded_save_and_prepare_failure(monkeypatch) -> None:
    client, sent = _capture(monkeypatch, _saved_body())
    saved = client.get_shader_update(_package_args())
    assert sent == [("GET", "/api/shaders/aurora/updates/req-1", None)]
    assert saved["save"] == "saved" and saved["compile"]["profiles"][0]["status"] == "pending"
    failed, _calls = _capture(monkeypatch, {"prepare": "failed", "diagnostics": [{"line": 1}]})
    assert failed.register_shader_update({**_package_args(), "digest": "sha256:" + "ab" * 32,
                                          "lease": _lease()})["prepare"] == "failed"


def test_package_results_refuse_malformed_bodies(monkeypatch) -> None:
    for reply, needle in (
        ({"commit": 1, "revision": 2}, "Malformed Shader open result"),
        ({"save": "saved", "merge": [], "commit": 1, "revision": 2}, "Malformed Shader save result"),
        ({"save": "saved", "results": [], "commit": 1}, "Malformed Shader edit result"),
        ({"prepare": "failed"}, "Malformed prepare failure"),
    ):
        client, _sent = _capture(monkeypatch, reply)
        with pytest.raises(HextileClientError) as caught:
            if "results" in reply or set(reply) == {"save", "results", "commit"}:
                client.shader_edit(_package_args(edits=[{"op": "delete", "address": ["modules", "fog.glsl"]}]))
            elif "prepare" in reply or "merge" in reply:
                client.register_shader_update({**_package_args(), "digest": "sha256:" + "ab" * 32, "lease": _lease()})
            else:
                client.open_shader_workspace(_package_args())
        assert needle in str(caught.value)
        assert caught.value.kind == "other"


def test_package_transport_keeps_unknown_upgrade_and_typed_refusal(monkeypatch) -> None:
    down = HextileClientError("offline", kind="app_down")
    client, sent = _capture(monkeypatch, down)
    with pytest.raises(HextileClientError) as unknown:
        client.open_shader_workspace(_package_args())
    assert unknown.value.kind == "workspace_outcome_unknown"
    assert len(sent) == 1
    missing = HextileClientError("missing", status_code=404, body=json.dumps({"detail": "Not Found"}), kind="http")
    client, _sent = _capture(monkeypatch, missing)
    with pytest.raises(HextileClientError) as upgrade:
        client.open_shader_workspace(_package_args())
    assert upgrade.value.kind == "upgrade"
    client, _sent = _capture(monkeypatch, {})
    with pytest.raises(HextileClientError) as empty:
        client.register_shader_update({**_package_args(), "digest": "sha256:" + "ab" * 32, "lease": _lease()})
    assert empty.value.kind == "other"
    assert "Malformed Shader save result" in str(empty.value)


_SHIPPED_HEADER = re.compile(r"/\*@hextile-shader\n.*?\*/\n", re.S)


def _playable_recipe() -> tuple[list[str], dict[str, Any]]:
    guide = (ROOT / "skills/360-hextile/references/recipes.md").read_text(encoding="utf-8")
    playable = guide.split("## Recipe I — Playable Shaders:", 1)[1]
    playable = playable.split("\n# Inspect an exact full-quality", 1)[0]
    sources = re.findall(r"```glsl\n(.*?)```", playable, re.S)
    recipe_j = playable.split("## Recipe J — Playable Shaders:", 1)[1]
    document = json.loads(re.search(r"```json\n(.*?)```", recipe_j, re.S).group(1))
    return sources, document


def test_playable_recipes_match_shipped_sources_and_bound_contracts() -> None:
    # The guide keeps the shipped GLSL bodies and a shader.json the package schema admits.
    app = ROOT.parents[2] / "360-HEXTILE-APP"
    sys.path.insert(0, str(app))
    from plugins.shader.backend.package.schema import validate_shader

    examples = json.loads((app / "plugins/shader/frontend/convention-examples.json").read_text(encoding="utf-8"))
    sources, document = _playable_recipe()
    shipped = [_SHIPPED_HEADER.sub("", row["candidate"]["source"], count=1) for row in examples]
    assert sources == shipped
    assert validate_shader(document)["hexshader"] == 1
    assert document["meta"]["title"] == "Enter blast"
    assert document["controls"]["camera"] is None
    assert "vec3 ro = hxCameraPosition;" in sources[0]
    assert "vec3 rd = hxCameraDirection(hx.direction);" in sources[0]
    assert "hxParam_glow" in sources[1] and "BLAST" in sources[1]


@pytest.mark.parametrize("variant", ["held", "instant", "orphan", "default_one", "bad_kind"])
def test_playable_recipe_variants_use_real_intrinsic_admission(variant: str) -> None:
    sys.path.insert(0, str(ROOT.parents[2] / "360-HEXTILE-APP"))
    from plugins.shader.backend.package.schema import PackageError, validate_shader

    _, document = _playable_recipe()
    document = deepcopy(document)
    modulator = next(iter(document["modulators"].values()))
    if variant == "held":
        modulator.update(mode="held", attack=0.2, release=0.6)
    elif variant == "instant":
        modulator["attack"] = 0
    elif variant == "orphan":
        modulator["input"] = "missing_gate"
    elif variant == "default_one":
        document["controls"]["channels"]["blast_press"]["default"] = 1
    else:
        modulator["kind"] = "not-envelope"

    if variant in {"held", "instant"}:
        validate_shader(document)
    else:
        with pytest.raises(PackageError):
            validate_shader(document)


def test_playable_tool_guidance_preserves_legacy_authority_and_no_new_controls() -> None:
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    workspace = _schema("open_shader_workspace")["description"]
    assert "shader_id and request_id" in workspace
    assert "lease, commit and revision" in workspace
    assert "recorded result" in workspace
    from hextile_mcp import load_guide
    detail = load_guide("workflow-schema", detail=True)["markdown"]
    assert "conventions/1" in detail and "modulation/2" in detail
    assert "hxCameraDirection(vec3 canonicalDirection)" in detail
    assert "never arms Interact" in detail
    assert not {"propose_shader", "shader_get_proposal", "shader_save_asset"} & {tool["name"] for tool in TOOLS}
    assert not {"press_key", "set_pose", "arm_interact", "save_project_convention"} & {tool["name"] for tool in TOOLS}
    source = (ROOT / "skills/360-hextile/SKILL.md").read_text(encoding="utf-8")
    fragment = (ROOT / "codex/AGENTS-fragment.md").read_text(encoding="utf-8")
    assert fragment.split("-->\n\n", 1)[1] == source.split("\n---\n", 1)[1].lstrip("\n")
    catalog_text = json.dumps(TOOLS + SHADER_EXTENSION_TOOLS)
    for obsolete in ("source grant", "Capture and Apply consent", "Trusted Local Full Access",
                     "human Fractal grant", "session selected and follow_ready", "Follow and whole-source"):
        assert obsolete not in catalog_text
    assert all("lease_id" not in row["inputSchema"].get("properties", {}) for row in TOOLS + SHADER_EXTENSION_TOOLS)


@pytest.mark.parametrize('level,processing', [(0, 'auto'), (6, 'cpu')])
def test_raster_policy_schema_peer_gate_and_strict_effective_receipts(monkeypatch, level, processing):
    from hextile_client import _native_sequence_fields, _shader_output_receipt, _RASTER_PROFILES
    from hextile_mcp import SHADER_EXTENSION_TOOLS
    schemas = {row['name']: row['inputSchema'] for row in SHADER_EXTENSION_TOOLS}
    key = '7e720fa5-192b-47da-a705-ab3b5ddc979e'
    digest = 'sha256:' + 'a' * 64
    policy = {'profile': 'shader-raster-policy/1', 'processing': processing, 'png_compress_level': level}
    preview_policy = {key: value for key, value in policy.items() if key != 'png_compress_level'}
    owner = {'request_id': key, 'shader': {'origin': 'user', 'shaderId': 'aurora'},
        'project_context_witness': 'w', 'base': {'kind': 'saved', 'working_revision': 1,
        'document_hash': digest, 'source_hash': digest}, 'studio_surface_id': 'surface', 'expected_edit_sequence': 1}
    output = {'projection': 'equirectangular', 'width': 2048, 'height': 1024, 'encoding': 'png',
              'output_path': 'D:/Stills/policy.png', 'raster_policy': policy}
    args = {**owner, 'profile': 'shader-raster-still/1', 'output': output}
    schema = schemas['shader_preflight_still_export']
    jsonschema.validate(args, schema)
    preview = {**owner, 'mode': 'still', 'width': 2048, 'height': 1024, 'output': {
        'projection': 'equirectangular', 'pan': 0, 'tilt': 0, 'roll': 0, 'raster_policy': preview_policy}}
    jsonschema.validate(preview, schemas['shader_request_preview'])
    for invalid in [None, {**policy, 'png_compress_level': True}, {**policy, 'extra': True}]:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**args, 'output': {**output, 'raster_policy': invalid}}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**preview, 'output': {**preview['output'], 'raster_policy': policy}},
                            schemas['shader_request_preview'])
    client = Client()
    caps = _inspector_capabilities()
    caps['native_render']['stills'] = {'shader-raster-still/1': {}}
    monkeypatch.setattr(client, 'get_capabilities', lambda: caps)
    post = mock.Mock(return_value={'request_id': key, 'state': 'pending'})
    monkeypatch.setattr(client, 'request_json', post)
    with pytest.raises(HextileClientError) as old_peer:
        client.preflight_shader_still(args)
    assert old_peer.value.status_code == 501 and not post.called
    caps['native_render']['shader_raster_policy'] = {'profile': 'shader-raster-policy/1'}
    client.preflight_shader_still(args)
    assert post.call_args.args[2]['output']['raster_policy'] == policy
    execution = {'profile': policy['profile'], 'requested_processing': processing, 'actual_processing': 'cpu',
        'reason': 'forced_cpu' if processing == 'cpu' else 'gpu_unqualified', 'profiles': _RASTER_PROFILES}
    ready = {**_inspector_ready(key), 'raster_policy': preview_policy, 'raster_execution': execution}
    assert _shader_output_receipt('get_preview', {'request_id': key}, ready) == ready
    for changed in (None, {**execution, 'actual_processing': 'gpu'}, {**execution, 'secret': 'private'},
                    {**execution, 'profiles': {**_RASTER_PROFILES, 'area': 'unknown/1'}}):
        with pytest.raises(HextileClientError):
            _shader_output_receipt('get_preview', {'request_id': key}, {**ready, 'raster_execution': changed})
    native_execution = {'profile': policy['profile'], 'requested_processing': 'auto',
        'actual_processing': 'retained_native', 'reason': 'unreviewed', 'profiles': dict(_RASTER_PROFILES),
        'gpu_qualified': False, 'production_activated': False, 'repair_fraction': 0}
    if processing == 'auto':
        native_ready = {**ready, 'raster_execution': native_execution}
        assert _shader_output_receipt('get_preview', {'request_id': key}, native_ready) == native_ready
    else:
        with pytest.raises(HextileClientError):
            _shader_output_receipt('get_preview', {'request_id': key}, {**ready, 'raster_execution': native_execution})
    stored_native = {**native_execution, 'gpu_qualified': True, 'production_activated': True}
    if processing == 'auto':
        stored_ready = {**ready, 'raster_execution': stored_native}
        assert _shader_output_receipt('get_preview', {'request_id': key}, stored_ready) == stored_ready
    else:
        with pytest.raises(HextileClientError):
            _shader_output_receipt('get_preview', {'request_id': key}, {**ready, 'raster_execution': stored_native})
    for forged in ({**native_execution, 'actual_processing': 'cpu', 'reason': 'cpu_fallback', 'gpu_qualified': True},
                   {**native_execution, 'actual_processing': 'gpu'},
                   {**native_execution, 'gpu_qualified': 'yes'},
                   {**native_execution, 'secret': True}):
        with pytest.raises(HextileClientError):
            _shader_output_receipt('get_preview', {'request_id': key}, {**ready, 'raster_execution': forged})
    job = {'job_id': 'b' * 32, 'state': 'completed', 'progress': 1,
           'idempotency_key': key, 'output': {key: value for key, value in output.items() if key != 'output_path'}}
    job['output'].update(file='policy.png', raster_execution=execution)
    result = {'request_id': key, 'profile': args['profile'], 'job': job,
              'state': 'completed', 'output_name': 'policy.png', 'output_path': output['output_path']}
    assert _shader_output_receipt('get_job', args, result) == result
    with pytest.raises(HextileClientError):
        _shader_output_receipt('get_job', args, {**result, 'job': {**job,
            'output': {**job['output'], 'raster_execution': None}}})
    pending = {key: ready[key] for key in ('request_id', 'state', 'status', 'progress', 'error', 'raster_policy')}
    pending.update(state='pending', status='running', raster_execution=None)
    assert _shader_output_receipt('get_preview', {'request_id': key}, pending) == pending
    settings = {'raster_policy': policy, 'raster_profiles': _RASTER_PROFILES}
    projected = _native_sequence_fields({'producer': 'shader', 'accepted_settings': settings,
        'raster_execution': execution, 'storage': {'layout': 'direct', 'ownership': 'generated',
        'encoding': {'format': 'PNG', 'quality_if_jpg': None, 'png_compress_level': level}}})
    assert projected['accepted_settings']['raster_policy'] == policy
    assert projected['accepted_settings']['raster_profiles'] == _RASTER_PROFILES
    assert projected['raster_execution'] == execution
    assert projected['storage']['encoding']['png_compress_level'] == level
    assert 'destination_intent' not in projected['accepted_settings']
    for pending in [None, execution]:
        live = _native_sequence_fields({'producer': 'shader', 'accepted_settings': settings,
            'raster_execution': pending, 'folder_export': {'format': 'PNG'}})
        assert live['accepted_settings']['raster_policy'] == policy
        assert live['raster_execution'] == pending
    if processing == 'auto':
        native_projected = _native_sequence_fields({'producer': 'shader', 'accepted_settings': settings,
            'raster_execution': native_execution, 'storage': {'layout': 'direct', 'ownership': 'generated',
            'encoding': {'format': 'PNG', 'quality_if_jpg': None, 'png_compress_level': level}}})
        assert native_projected['raster_execution'] == native_execution
        stored_projected = _native_sequence_fields({'producer': 'shader', 'accepted_settings': settings,
            'raster_execution': stored_native, 'storage': {'layout': 'direct', 'ownership': 'generated',
            'encoding': {'format': 'PNG', 'quality_if_jpg': None, 'png_compress_level': level}}})
        assert stored_projected['raster_execution'] == stored_native
    else:
        dropped = _native_sequence_fields({'producer': 'shader', 'accepted_settings': settings,
            'raster_execution': native_execution, 'folder_export': {'format': 'PNG'}})
        assert 'raster_execution' not in dropped


def test_malformed_open_result_does_not_echo_paths(monkeypatch) -> None:
    client = Client("http://127.0.0.1:9")

    def request_json(method, path, body=None, **kwargs):
        return {"commit": 1, "revision": 2, "note": "D:/project/secret.glsl"}

    monkeypatch.setattr(client, "request_json", request_json)
    with pytest.raises(HextileClientError) as caught:
        client.open_shader_workspace({"shader_id": "aurora", "request_id": "req-open"})
    assert caught.value.kind == "other"
    assert "Malformed Shader open result" in str(caught.value)
    assert "D:/project" not in str(caught.value)


def test_v2_receipts_compile_credits_and_named_fields(monkeypatch) -> None:
    monkeypatch.setattr("hextile_client.Path", PurePosixPath)
    digest = "sha256:" + "b" * 64
    request_id = "b5897a63-59a1-4d8f-aecb-36ba083fc1ea"
    ref = {"origin": "user", "shaderId": "aurora"}
    client = Client("http://127.0.0.1:9")
    imported = {"schema": 1, "request_id": request_id, "operation": "shader_import_bundle",
                "scope": "creation", "state": "saved", "project_context_witness": "wit",
                "receipt": {"stack": "v2", "shader": {"origin": "user", "shaderId": "imported"},
                            "working_revision": 3, "document_hash": digest, "bundle_sha256": digest}}
    monkeypatch.setattr(client, "request_json", lambda *a, **k: imported)
    args = {"request_id": request_id, "project_context_witness": "wit",
            "input_path": "D:/task/input.hexshader", "collision_intent": "fork", "bundle_sha256": digest}
    assert client.import_shader_bundle(args)["receipt"]["stack"] == "v2"
    assert client.get_shader_operation({"request_id": request_id, "scope": "creation",
                                        "project_context_witness": "wit"})["state"] == "saved"

    base = {"kind": "saved", "working_revision": 1, "document_hash": digest, "source_hash": digest}
    rename = {"request_id": request_id, "shader": ref, "project_context_witness": "wit", "base": base,
              "expected_working_digest": digest, "title": "Renamed",
              "confirmation_scope": {"operation": "rename", "shader": ref}, "library_intent": "saved"}
    renamed = {"stack": "v2", "shader_id": "aurora", "title": "Renamed", "tags": ["e2e"],
               "revision": 9, "commit": 9, "digest": digest, "lease": {"holder": "agent", "generation": 0}}
    monkeypatch.setattr(client, "request_json", lambda *a, **k: renamed)
    landed = client.rename_shader_asset(rename)
    assert landed["title"] == "Renamed" and landed["shader_id"] == "aurora" and "operation" not in landed
    deleted = {"stack": "v2", "deleted": True, "shader_id": "aurora", "origin": "user"}
    monkeypatch.setattr(client, "request_json", lambda *a, **k: deleted)
    removal = {key: value for key, value in rename.items() if key != "title"}
    removal["confirmation_scope"] = {"operation": "delete", "shader": ref}
    assert client.delete_shader_asset(removal)["deleted"] is True

    glsl = "void hxMain() {\n  gl_FragColor = vec4(1.0);\n}\n" * 8
    pending = _saved_body(compile={"revision": 4, "profiles": [
        {"profile": "webgl2", "status": "pending", "program_identity": None, "ok": None},
        {"profile": "dome", "status": "not_observed", "program_identity": None, "ok": None}]})
    pending["merge"] = [
        {"op": "set", "address": ["code"], "outcome": "lost_to_human", "human": 1,
         "value": {"source.glsl": glsl}},
        _merge_row()]
    monkeypatch.setattr(client, "request_json", lambda *a, **k: pending)
    saved = client.get_shader_update(_package_args())
    assert saved["compile_note"] == "compile pending; poll get_shader_update"
    assert "kept_count" not in saved
    assert [row["outcome"] for row in saved["merge"]] == ["lost_to_human", "kept"]
    assert saved["merge"][0]["value"]["source.glsl"] == glsl
    quiet = _saved_body(compile={"revision": 4, "profiles": [
        {"profile": "dome", "status": "not_observed", "program_identity": None, "ok": None}]})
    monkeypatch.setattr(client, "request_json", lambda *a, **k: quiet)
    assert "compile_note" not in client.get_shader_update(_package_args())

    page = {"schema": 1, "target": ref, "section": "sources", "sources": [],
            "provenance_hash": digest, "author": None, "attribution": None, "license": "MIT",
            "automatic_credit": True, "cursor": 0, "total": 0, "next_cursor": None,
            "protected_distribution_present": True, "has_opaque_fields": False,
            "original": "originals/" + "ab" * 32 + ".glsl",
            "distribution": {"rights": "declared", "code": digest, "original": None, "licenses_total": 1},
            "attribution_schema": 2,
            "host_profile": {"source": "none", "state": "missing", "automatic_credit": False,
                             "profile": None, "frozen": None},
            "base": base, "working_digest": None}
    monkeypatch.setattr(client, "request_json", lambda *a, **k: page)
    assert client.get_shader_credits({"shader": ref, "project_context_witness": "wit"})["distribution"]["code"] == digest
    monkeypatch.setattr(client, "request_json", lambda *a, **k: {**page, "distribution": {**page["distribution"], "raw_licenses": []}})
    with pytest.raises(HextileClientError):
        client.get_shader_credits({"shader": ref, "project_context_witness": "wit"})

    opened = _open_body(workspace_path="D:/shaders/aurora/workspace")
    monkeypatch.setattr(client, "request_json", lambda *a, **k: opened)
    assert client.open_shader_workspace(_package_args())["workspace_path"].endswith("workspace")

    with pytest.raises(HextileClientError) as titled:
        client.create_shader_asset({"request_id": request_id, "project_context_witness": "wit",
                                    "action": "new", "template_id": "hx_starter", "title": "Nope"})
    assert "title is not accepted for action new" in str(titled.value)
    with pytest.raises(HextileClientError) as limited:
        client.list_shader_assets({"project_context_witness": "wit", "shelf": "user", "limit": 999})
    assert "limit must be an integer from 1 to 50" in str(limited.value)
    with pytest.raises(HextileClientError) as duplicated:
        client.duplicate_shader_asset({"request_id": "not-a-uuid", "project_context_witness": "wit",
                                       "shader": ref, "base": {}})
    assert "invalid request_id" in str(duplicated.value) and "base" in str(duplicated.value)
    with pytest.raises(HextileClientError) as slotted:
        client.set_shader_resource({"shader": ref, "project_context_witness": "wit", "request_id": request_id,
                                    "base": base, "expected_working_digest": digest, "action": "remove"})
    assert "missing slot_id" in str(slotted.value)

    look = {"request_id": request_id, "shader": ref, "project_context_witness": "wit", "base": base,
            "expected_working_digest": digest, "library_intent": "saved", "look_id": "look_1",
            "expected_look_envelope_hash": digest,
            "confirmation_scope": {"operation": "shader_apply_look", "shader": ref}}
    fat = {"schema": 1, "request_id": request_id, "operation": "shader_apply_look", "state": "saved",
           "shader": ref, "receipt": {"results": [
               _merge_row(),
               {"op": "set", "address": ["code"], "outcome": "rewritten", "value": {"source.glsl": glsl}}]}}
    monkeypatch.setattr(client, "request_json", lambda *a, **k: fat)
    applied = client.apply_shader_look(look)
    assert "kept_count" not in applied["receipt"]
    assert applied["receipt"]["results"][0]["outcome"] == "kept"
    assert applied["receipt"]["results"][1]["value"]["files"][0]["bytes"] == len(glsl.encode("utf-8"))
    assert "void hxMain" not in json.dumps(applied)

    from hextile_mcp import SHADER_EXTENSION_TOOLS
    described = {tool["name"]: tool["description"] for tool in TOOLS + SHADER_EXTENSION_TOOLS}
    assert "workspace_schema" in described["open_shader_workspace"]
    assert "render_observation.run_id" in described["control_shader_sequence"]
    assert "shader_checkpoint_save" in described["shader_checkpoint"]
    assert "operation rename" in described["shader_rename_asset"]
    assert "operation delete" in described["shader_delete_asset"]
    assert "slot_id is required" in described["shader_set_resource"]
    assert "title is accepted only for action paste" in described["shader_create_asset"]
    skill = (ROOT / "skills" / "shader" / "SKILL.md").read_text(encoding="utf-8")
    authoring = (ROOT / "skills" / "shader" / "references" / "authoring.md").read_text(encoding="utf-8")
    assert "current_surface" in skill and "shader_capture_sequence_input" in skill
    assert "hexshader-package-1" in authoring and "def package_digest" in authoring
    assert "render_observation.run_id" in authoring
    assert "sequence_input_unsupported" in authoring
