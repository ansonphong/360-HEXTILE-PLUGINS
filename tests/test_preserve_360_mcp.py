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
