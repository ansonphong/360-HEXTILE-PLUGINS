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

The reply is the live Shader: `shader.origin`, `shader.shader_id`, `lease`
(`holder` and `generation`), `commit`, `revision`, `connected` and
`mcp_enabled`. Report those. Do not guess a title from an id. A missing Shader
means none is open. APP down: “Launch 360 Hextile, then retry.” MCP disabled:
enable MCP in APP Settings.

A successful connection is not a save and not permission to write. Only use
DevTools when the request needs visual or DOM inspection. Discovery does not
navigate, duplicate, edit, register, render or take screenshots.

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

Playback (`control_shader_timeline` play, pause, seek and reset, and
`shader_step_frame`) is not an edit. Changing bpm, speed, start, end or loop is
an edit.

Never auto-install, restart or change host permissions. After an update, observe
the installed package, the registered tools and the running APP. A source checkout
alone proves no activation.

Human guides: https://360hextile.com/docs/create/shader and
https://360hextile.com/docs/user-guide/agent-mode.
For Workshop UI questions, call `search_docs` then `read_doc` on `create/shader`.
