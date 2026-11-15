---
name: shader
description: "Connect to the open Shader and inspect its lease, or edit a Shader package through shader_edit and register."
---

# 360 Hextile — Shader

## Connect / what Shader is open?

For a read-only connection or current-Shader question, first check that the
registered tool accepts `view`. If missing, report that the host tool registration
needs refresh/reconnect; do not send an unsupported field or call the full view.
Otherwise call `get_live_context(view="shader")` once. This read needs no
`get_capabilities` handshake. Use the tools already exposed by the host; do not
print the whole catalog or inspect DevTools just to discover the Shader.

The reply is the compact live Shader: `shader.origin`, `shader.shaderId`
(the same value as `shader.shader_id`), `title`, `writable`,
`project_context_witness`, `studio_surface_id`, `lease` (`holder` and
`generation`), `commit`, `revision`, `connected`, `mcp_enabled` and
`agent_open` (`policy`, `allow_force_open`, `blocked_for_session`). Report
those. `title` is the saved package title. Ask politely. Call
`shader_open_asset` only when the user wants another Shader on screen. It asks
the user; poll the request_id; never retry a dismissed request; ask in chat
instead. Use force only when the user asked for an agent-driven session. To
change another Shader without switching the view, edit it by id with
`shader_edit` or `open_shader_workspace`. A missing Shader means none is open. `connected: false` or
`shader: null` means the Workshop is empty. Call `shader_list_assets` with the
`project_context_witness` from that context. The list returns that witness.
APP down: “Launch 360 Hextile, then retry.” MCP disabled: enable MCP in APP Settings.

`open_shader_workspace` takes `shader_id` and `request_id` only. Do not send
`workspace_schema`. The package digest layout is in
[the authoring procedure](references/authoring.md). `shader_capture_sequence_input`
is optional for a Shader with no sequence input.

A successful connection is not a save and not permission to write. Only use
DevTools when the request needs visual or DOM inspection. Discovery does not
navigate, duplicate, edit, register, render or take screenshots.

## Export 8K equirect PNG at 2×

Call `get_live_context(view="shader")` once and keep `studio_surface_id`, the
witness, and the saved base. Every still needs that surface id, including
App – High precision. Then `shader_preflight_still_export`, then
`shader_export_still` with that preflight id.

Profile `shader-raster-still/1`. Output: `projection` `equirectangular`,
`encoding` `png`, `width` `8192`, `height` `4096`, `supersampling` `2`,
`output_path` the absolute PNG file. A still writes a file. A sequence writes
a folder: `preflight_shader_sequence` then `render_shader_sequence`, with
top-level `width`, `height`, `supersampling`, and
`folder_export.destination_folder`.

Omit `render_route` for App – High precision. Otherwise send
`{profile: "shader-render-route/1", route}` using
`webgl-display-native-encode`, `webgl-browser-encode-desktop`,
`webgl-browser-encode-backend`, or `webgl-raw-float`. The two browser routes
also send `browser_codec`: `{format: "png"}`, `{format: "jpeg", jpeg_quality}`
from 0.50 to 1.00, or `{format: "exr"}`. Equirect EXR uses profile
`shader-linear-rgba-exr/1` and omits `projection`. Window supersampling presets
are 1, 1.5, and 2. Any finite scale of at least 1 is sent through. Viewer –
High precision sequences are EXR.

## Edit, controls, diagnostics or output

Before any Shader change, read
[the authoring procedure](references/authoring.md). A package is `shader.json`,
`source.glsl`, `modules/**/*.glsl`, `provenance.json`, the referenced
`resources/` and `originals/` files, and an optional `cover.jpg`. `hexshader`
is 1.

`shader_edit` and the typed tools change one unit at a time.
`register_shader_update` saves the package digest. Read `merge`. Watch
`compile`. Send `seen` for a unit a human has edited. Only the human moves the
lease (Take control / Hand back). A `stale_lease` result means the human holds
the code, or the generation you sent is no longer current.

A Shader technique question is `get_guide(name="shader-cookbook")` and does not
open a Shader. Load only the guides the procedure names.

`shader_edit` addresses: a parameter is `["values","<parameter id>"]`, source is
`["code"]` with value `{"source.glsl":"...","<module path>":"..."}` (all files).
Personal tags for `shader_set_tags` are user-owned and no tool lists them; ask the
user. Write tools take `expected_working_digest` = `base.document_hash` (from
`shader_get_asset_state`); it defaults to that when omitted. A Sequence render
requires `seed`. Still export needs the Shader mounted; use `shader_open_asset` first.

Playback (`shader_control_clock` and `shader_step_frame`) is not an edit.
Changing bpm, speed, start, end or loop is an edit.

Never auto-install, restart or change host permissions. After an update, observe
the installed package, the registered tools and the running APP. A source checkout
alone proves no activation.

Human guides: https://360hextile.com/docs/create/shader and
https://360hextile.com/docs/user-guide/agent-mode.
For Workshop UI questions, call `search_docs` then `read_doc` on `create/shader`.
