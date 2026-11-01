"""Optional render_route stays native until discovery marks the route available."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from hextile_client import Client, HextileClientError, _checked_render_route, _shader_output_receipt  # noqa: E402
from hextile_mcp import SHADER_EXTENSION_TOOLS, _SHADER_SEQUENCE_REQUEST  # noqa: E402

NAMES = (
    "shader_preflight_still_export", "shader_export_still", "shader_request_preview",
)
ROUTE = {
    "profile": "shader-render-route/1",
    "route": "webgl-display-native-encode",
}


def _tool(name: str) -> dict:
    return next(row for row in SHADER_EXTENSION_TOOLS if row["name"] == name)


def test_named_tools_keep_render_route_optional_and_native_by_omission():
    for name in NAMES:
        schema = _tool(name)["inputSchema"]
        assert "render_route" in schema["properties"]
        assert "render_route" not in schema["required"]
        assert "shader_render_produce" in _tool(name)["description"]
    sequence = _SHADER_SEQUENCE_REQUEST
    assert "render_route" in sequence["properties"]
    assert "render_route" not in sequence["required"]
    assert _checked_render_route(ROUTE)
    assert _checked_render_route({**ROUTE, "path": "D:/frames/a.png"}) is False
    browser = {"profile": "shader-render-route/1", "route": "webgl-browser-encode-backend",
               "browser_codec": {"format": "png"}}
    assert _checked_render_route(browser)
    assert _checked_render_route({**browser, "browser_codec": {"format": "jpeg"}}) is False


def test_unavailable_webgl_route_refuses_before_a_fixture_can_enable_it():
    client = Client.__new__(Client)
    client.get_capabilities = lambda: {"native_render": {
        "contract": "native-render/1", "sequences": {}, "stills": {},
        "render_routes": [{"route": "webgl-display-native-encode", "available": False,
                           "reason": "no_capable_client"}],
    }}
    with pytest.raises(HextileClientError) as refused:
        client._require_native_render(render_route=ROUTE)
    assert refused.value.status_code == 409
    assert str(refused.value) == "no_capable_client"
    client._require_native_render(render_route=None)
    client._require_native_render(render_route={"profile": "shader-render-route/1", "route": "native"})


def test_still_receipt_accepts_a_bounded_route_and_keeps_the_legacy_job_shape():
    job = {"job_id": "a" * 32, "state": "processing", "progress": 0,
           "idempotency_key": "req", "output": None}
    args = {"request_id": "req", "profile": "dome-png/1", "shader": {"origin": "user", "shaderId": "probe"}}
    legacy = {"request_id": "req", "profile": "dome-png/1", "state": "processing", "job": job}
    assert _shader_output_receipt("still", args, legacy)["job"] == job
    routed = {**job, "render_route": {"profile": "shader-render-route/1", "route": "webgl-raw-float"},
              "producer_state": "issued", "published_cursor": 0}
    assert _shader_output_receipt("still", args, {**legacy, "job": routed})["job"]["published_cursor"] == 0
    leaked = {**routed, "render_route": {**routed["render_route"], "destination": "D:/secret.exr"}}
    with pytest.raises(HextileClientError):
        _shader_output_receipt("still", args, {**legacy, "job": leaked})


def _display_report():
    return {'profile': 'shader-webgl-display-processing/1', 'actual': 'gpu',
            'kernel_sha256': 'a' * 64, 'reason': None, 'cpu_repair_rows': 0,
            'float_readback_bytes': 0, 'display_readback_bytes': 32, 'packed_rgb_bytes': 24,
            'owned_gpu_bytes': 256, 'owned_host_calculated_bytes': 64, 'frame_index': 0}


def test_optional_display_work_receipt_survives_still_get_stop_and_sequence_projection():
    from hextile_client import _native_sequence_fields
    report = _display_report()
    job = {'job_id': 'a' * 32, 'state': 'processing', 'progress': 0,
           'idempotency_key': 'req', 'output': None,
           'render_route': {'profile': 'shader-render-route/1', 'route': 'webgl-display-native-encode'},
           'display_processing': report}
    args = {'request_id': 'req', 'profile': 'dome-png/1', 'shader': {'origin': 'user', 'shaderId': 'probe'}}
    receipt = {'request_id': 'req', 'profile': 'dome-png/1', 'state': 'processing', 'job': job}
    for operation in ('still', 'get_job', 'stop_job'):
        assert _shader_output_receipt(operation, args, receipt)['job']['display_processing'] == report
    assert _native_sequence_fields({'producer': 'shader', 'width': 4, 'height': 2,
                                   'display_processing': report})['display_processing'] == report
    changed = {**report, 'private_path': 'D:/private'}
    with pytest.raises(HextileClientError):
        _shader_output_receipt('get_job', args, {**receipt, 'job': {**job, 'display_processing': changed}})


def test_preview_work_receipt_is_bounded_and_legacy_absence_remains_valid():
    from hextile_client import _valid_display_processing
    value = {'request_id': 'req', 'state': 'pending', 'status': 'completed', 'progress': None, 'error': None,
             'display_processing': _display_report()}
    assert _shader_output_receipt('get_preview', {'request_id': 'req'}, value) == value
    legacy = {key: field for key, field in value.items() if key != 'display_processing'}
    assert _shader_output_receipt('get_preview', {'request_id': 'req'}, legacy) == legacy
    assert _valid_display_processing(_display_report(), width=4, height=2)
    for changed in ({'kernel_sha256': 'private'}, {'packed_rgb_bytes': 25}, {'float_readback_bytes': True}):
        assert not _valid_display_processing({**_display_report(), **changed}, width=4, height=2)
