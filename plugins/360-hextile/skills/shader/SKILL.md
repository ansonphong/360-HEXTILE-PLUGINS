---
name: shader
description: "Connect to the open Shader and inspect it, or edit a My Library Shader (or a Built-in in dev mode) by id with shader_edit, which saves each edit."
---

# 360 Hextile — Shader

## How to work fast

- Orient with one read: `get_live_context(view="shader")`.
- Act by `shader_id` with `shader_edit` (one call can batch several edits), no open step, no Save; it saves itself.
- 403 `No document is open` or `connected: false`: never poll it; ask the user to open a document or the Shader Workshop.
- Lost reply: resend the same request with the same `request_id`.

## Top 20

`W`, `B`, `S`, `U` and `L` are defined in `get_guide(name="recipes")` (longer examples: `recipes-detail`). Edits are `shader_edit {"shader_id":"<id>","request_id":"<unique>","edits":[..]}`; when an edit needs the lease, `lease` is a top-level field next to `edits`, never inside an edit: `{"shader_id":"S","request_id":"U","lease":{"holder":"agent","generation":0},"edits":[..]}`. Copy `lease` from `get_live_context` (on screen) or `open_shader_workspace` (any Shader).

1. What Shader is open → `get_live_context(view="shader")`.
2. Rename dropdown options → `{"op":"set","address":["parameters","<id>","option_labels"],"value":{"0":"A","1":"B"}}` — ids and option values from `get_shader_parameters`.
3. Change a label, range, default, step or help → `["parameters","<id>","label"|"min"|"max"|"default"|"step"|"help"]` — send min and max together.
4. Set a value → `{"op":"set","address":["values","<id>"],"value":0.7}`.
5. Edit the code → read every file with `shader_get_asset_state {..,"include":["source"]}`, then `["code"]` with every file and top-level `"lease":L` — a compile error returns `file:line:col` and saves nothing.
6. Add a slider → with `"lease":L`: `create ["parameters","glow"]` plus a `["code"]` entry using `hxParam_glow`.
7. Remove a parameter → with `"lease":L`: `delete ["parameters","<id>"]` plus `["code"]` without `hxParam_<id>`, in one call.
8. Rename a Shader → `shader_rename_asset` with `W`, `B` — My Library only.
9. Duplicate → `shader_duplicate_asset {"shader":S,"base":B,"destination_origin":"user","title":"Copy",..}`.
10. Delete → `shader_delete_asset` with `W`, `B` — My Library only.
11. Play, pause, jump to 3 s → `shader_control_clock {"action":"play"|"pause"|"seek","time":3,..}` — on screen.
12. Save or apply a Look → `shader_save_look {..,"title":"Warm"}`; `shader_apply_look {..,"name":"Warm"}` — no base, owner fields or hash needed.
13. Go back a version → `shader_restore_revision {..,"steps_back":1}` (or a history row's `document_ref` and `document_hash`).
14. Render a still → `shader_preflight_still_export` then `shader_export_still` — on screen (below).
15. Render a sequence → `preflight_shader_sequence` then `render_shader_sequence` (below).
16. Edit a Built-in → `shader_edit` by its id when `writable` is true (dev mode); a `read_only` reply means duplicate it and edit the copy.
17. New Shader from pasted GLSL → `shader_create_asset {"request_id":U,"project_context_witness":W,"action":"paste","title":"..","source":"<glsl>"}`; from the starter → `"action":"new"` (W also comes from `shader_list_assets`).
18. Clock or timeline → `["clock","bpm"|"speed"]`; first timeline edit sets `["timeline","start"]`, `["timeline","end"]` and `["timeline","loop"]` in one call.
19. Generate a 360 from a prompt → `validate_config` then `run_workflow` and `get_status` (hub skill).
20. Change a Fractal value or play its timeline → `fractal` skill; `get_fractal_context` fails until a Fractal scene is open.

Project Shaders are read-only to agents ("Project Shaders cannot be edited here yet."); make a My Library copy with `shader_save_as` or `shader_duplicate_asset`. Each `results[].outcome` must be checked: `skipped` changed nothing even when `save` says `saved`.

## Connect / what Shader is open?

If the registered `get_live_context` does not accept `view`, report that the host
tool registration needs a refresh/reconnect. This read needs no
`get_capabilities` handshake, catalog dump or DevTools.

The reply names `shader.origin`, `shader.shaderId` (the same value as
`shader.shader_id`), `title` (the saved package title), `writable`,
`project_context_witness`, `studio_surface_id`, `lease` (`holder`,
`generation`), `commit`, `revision`, `saved_base`, `connected`, `mcp_enabled`
and `agent_open`. `connected: false` or `shader: null` means the Workshop is
empty. APP down: “Launch 360 Hextile, then retry.” MCP disabled: enable MCP in
APP Settings. A connection is not a save and not permission to write.

`shader_open_asset` only asks the user to put another Shader on screen; poll its
request id and never retry a dismissed request. Use force only when the user
asked for an agent-driven session. Editing another Shader needs no open.

## Export 8K equirect PNG at 2×

Keep `studio_surface_id`, the witness and `saved_base` from the one live read. To edit a Shader other than the one on screen, take `base` from its `shader_list_assets` row, not `saved_base`. Every write reply returns the next `base`; chain with it instead of re-reading. Read GLSL and parameter help of any Shader with `shader_get_asset_state {..,"include":["source","parameters"]}`.
Every still needs that surface id, including App – High precision. Then
`shader_preflight_still_export`, then `shader_export_still` with that preflight
id. No preview is needed first.

Profile `shader-raster-still/1`. Output: `projection` `equirectangular`,
`encoding` `png`, `width` `8192`, `height` `4096`, `supersampling` `2`,
`output_path` the absolute PNG file. A still writes a file. A sequence writes
a folder: `preflight_shader_sequence` then `render_shader_sequence`, with
top-level `width`, `height`, `supersampling`, `seed` and
`folder_export.destination_folder`. `shader_capture_sequence_input` is optional
for a Shader with no sequence input.

Omit `render_route` for App – High precision. Otherwise send
`{profile: "shader-render-route/1", route}` using
`webgl-display-native-encode`, `webgl-browser-encode-desktop`,
`webgl-browser-encode-backend`, or `webgl-raw-float`. The two browser routes
also send `browser_codec`: `{format: "png"}`, `{format: "jpeg", jpeg_quality}`
from 0.50 to 1.00, or `{format: "exr"}`. Equirect EXR uses profile
`shader-linear-rgba-exr/1` and omits `projection`. Window supersampling presets
are 1, 1.5, and 2. Any finite scale of at least 1 is sent through. Viewer –
High precision sequences are EXR.

## Edit rules

[The authoring procedure](references/authoring.md) has the package layout,
merge outcomes, lease and credits rules. Send `seen` for a unit a human has
edited. Only the human moves the lease (Take control / Hand back); a
`stale_lease` result means the human holds the code or the generation you sent
is old. Read `compile` after a code edit. Personal Library tags for
`shader_set_tags` have no list tool; ask the user. A Shader technique question
is `get_guide(name="shader-cookbook")` and does not open a Shader.

Never auto-install, restart or change host permissions. After an update, observe
the installed package, the registered tools and the running APP. A source checkout
alone proves no activation.

Human guides: https://360hextile.com/docs/create/shader and
https://360hextile.com/docs/user-guide/agent-mode.
For Workshop UI questions, call `search_docs` then `read_doc` on `create/shader`.
