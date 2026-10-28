"""Shader preservation survives typed MCP admission and bounded receipt projection."""
from pathlib import Path
import sys

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))
import hextile_client as client
import hextile_mcp as server


OUTPUT = dict(projection="fulldome_angular", diameter=1024, fov_deg=200,
              pan=20, tilt=30, roll=-10, preserve_360=True,
              preserve_360_profile="shader-dome-from-360/1")


def test_shader_preview_schema_and_client_retain_versioned_mode():
    jsonschema.validate(OUTPUT, server._SHADER_SEQUENCE_OUTPUT)
    args = dict(mode="still", width=1024, height=1024, output=OUTPUT)
    assert client._valid_preview_selection(args)
    assert client._valid_raster_still_output({**OUTPUT, "encoding": "png", "output_path": "D:/render.png"})
    assert client._valid_linear_exr_output({key: value for key, value in
        {**OUTPUT, "width": 1024, "height": 1024, "output_path": "D:/render.exr"}.items() if key != "diameter"})


@pytest.mark.parametrize("patch", [dict(preserve_360=1), dict(preserve_360=False),
    dict(preserve_360_profile="unknown/2")])
def test_invalid_modes_refused(patch):
    output = {**OUTPUT, **patch}
    assert not client._valid_preview_selection(dict(mode="still", width=1024, height=1024, output=output))


def test_equirectangular_rejects_preservation():
    output = dict(projection="equirectangular", pan=0, tilt=0, roll=0, preserve_360=True)
    assert not client._valid_preview_selection(dict(mode="still", width=2048, height=1024, output=output))


def test_status_projection_keeps_original_mode_for_recovery():
    value = client._native_sequence_fields(dict(producer="shader", accepted_settings={"output": OUTPUT}))
    assert value["accepted_settings"]["output"] == OUTPUT


def test_shader_status_top_level_output_keeps_mode(monkeypatch):
    api = client.Client()
    sid = "seq_" + "a" * 32
    monkeypatch.setattr(api, "get_json", lambda *args, **kwargs:
        dict(sequence_id=sid, status="completed", output=OUTPUT))
    assert api.get_shader_sequence(sid)["output"] == OUTPUT


def test_exr_job_status_retains_checked_accepted_mode():
    args = dict(request_id="a" * 32, profile="shader-linear-rgba-exr/1")
    receipt = dict(request_id=args["request_id"], profile=args["profile"],
        job=dict(job_id="b" * 32, state="completed", progress=1, profile=args["profile"],
                 output="render.exr", accepted_settings=dict(output=OUTPUT)))
    assert client._shader_output_receipt("get_job", args, receipt) == receipt


def test_preservation_requires_advertised_peer_support(monkeypatch):
    api = client.Client()
    native = dict(contract="native-render/1", sequences={}, stills={})
    monkeypatch.setattr(api, "get_capabilities", lambda: dict(native_render=native))
    with pytest.raises(client.HextileClientError) as error:
        api._require_native_render(preservation=True)
    assert error.value.status_code == 501
    native["shader_dome_preservation"] = dict(field="preserve_360", profiles=["shader-dome-from-360/1"])
    api._require_native_render(preservation=True)


def test_public_dome_preflight_forwards_preservation(monkeypatch):
    api = client.Client()
    digest = "sha256:" + "a" * 64
    args = dict(shader=dict(origin="user", shaderId="saved"), project_context_witness="w",
        request_id="550e8400-e29b-41d4-a716-446655440000", studio_surface_id="surface",
        expected_edit_sequence=0,
        base=dict(kind="saved", working_revision=1, document_hash=digest, source_hash=digest),
        profile="dome-png/1", output=OUTPUT)
    seen = []
    monkeypatch.setattr(api, "get_capabilities", lambda: dict(native_render=dict(
        contract="native-render/1", stills={"dome-png/1": {}}, sequences={}, shader_dome_preservation=dict(
            field="preserve_360", profiles=["shader-dome-from-360/1"]))))
    def reply(method, path, body=None, **kwargs):
        seen.append(body)
        return dict(request_id=args["request_id"], state="pending")
    monkeypatch.setattr(api, "request_json", reply)
    assert api.preflight_shader_still(args)["state"] == "pending"
    assert seen[0]["output"] == OUTPUT


@pytest.mark.parametrize("preflight", [True, False])
@pytest.mark.parametrize("enabled", [True, False])
def test_deferred_sequence_preservation_requires_peer_before_post(monkeypatch, preflight, enabled):
    api = client.Client()
    digest = "sha256:" + "a" * 64
    output = OUTPUT if enabled else {key: value for key, value in
        {**OUTPUT, "preserve_360": False}.items() if key != "preserve_360_profile"}
    body = dict(shader_ref=dict(origin="user", id="saved"), project_context_witness="w",
        idempotency_key="original", name="Dome", working_revision=1, document_hash=digest,
        source_hash=digest, width=1024, height=1024, output=output, seed=0,
        frame_rate=dict(num=30, den=1), frame_count=30,
        start_time=dict(num="0", den="1"), end_time=dict(num="1", den="1"),
        publication_mode="deferred")
    monkeypatch.setattr(api, "get_capabilities", lambda: dict(native_render=dict(
        contract="native-render/1", sequences={}, stills={})))
    posts = []
    monkeypatch.setattr(api, "post_json", lambda *args, **kwargs: posts.append(args))
    with pytest.raises(client.HextileClientError) as error:
        api._shader_sequence_post(body, preflight=preflight)
    assert error.value.status_code == 501
    assert posts == []
