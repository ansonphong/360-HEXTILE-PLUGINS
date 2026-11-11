---
name: shader
description: "Connect to the open Shader and inspect its state, or edit a Project or My Library Shader through acknowledged native files and APP-owned checks and Save."
---

# 360 Hextile — Shader

## Connect / what Shader is open?

For a read-only connection or current-Shader question, first check that the
registered tool accepts `view`. If missing, report that the host tool registration
needs refresh/reconnect; do not send an unsupported field or call the full view.
Otherwise call `get_live_context(view="shader")` once. This compact read needs no
`get_capabilities` handshake. Use the tools already exposed by the host; do not
print the whole catalog or inspect DevTools just to discover the Shader.

Report the returned Shader name (or “name unavailable”), origin, `save_state`,
`draft_state`, `editable` and actionable `blockers` in one short reply. A Builtin
is readable; `shader_not_editable` means duplicate into My Library or a writable
Project before source editing. `draft_dirty` means the human must resolve their
edits; `save_unknown` means reconcile the existing Save. `owner_missing` or
`surface_missing` means open the Shader in Workshop and retry. Do not change
anything to answer this question.

`metadata_status=unavailable` / `save_state=unknown` stay unknown; do not guess a
name from an ID or claim Saved. A successful connection proves neither file
access, candidate Apply nor Save. Invalid/missing compact replies require an
APP/plugin update; report this instead of dumping the full app snapshot. APP down:
“Launch 360 Hextile, then retry.” MCP disabled: enable MCP in APP Settings.

Only use DevTools when the request needs visual/DOM inspection. Discovery does
not navigate, duplicate, attach, Apply, Save, render or take screenshots.

## Edit, controls, diagnostics or output

Before any Shader change or specialized operation, read
[the authoring procedure](references/authoring.md). It retains the native file,
capability, provenance, control, diagnostics, output and original-ID recovery
contracts. Load only the task-relevant guides it names. When the user asks for a
Shader technique, scene type, or cookbook recipe, read
`get_guide(name="shader-cookbook")` once, then `detail=true` only if the index
names the cards. Shared reasoning runs in the coding host; APP owns attachment,
checks, accepted state, compilation and Save. Read fresh `current_surface` and
`shader_contract` before authoring; discovery metadata grants no authority.

Current authoring uses document schema 4 and workspace schema 2. Require the
acknowledged complete file set; older content needs offline migration, never a
workspace downgrade. Extension and transport versions are independent. Follow
live `apply_policy`: `mounted` applies and saves one singular ready candidate;
`unavailable` leaves Apply to the human. A source read for another Shader does
not use this Shader's lease: open that reference first, then return.

Keep native ownership, witness and base checks. Only acknowledged workspace open
releases editable paths; register exact complete raw bytes and reconcile an
uncertain outcome with its original request ID. Never auto-install/restart or
change host permissions. Package, registered tools and running APP support must
all be observed after an update; source/cache versions alone prove no activation.

Human guides: https://360hextile.com/docs/create/shader and
https://360hextile.com/docs/user-guide/agent-mode.
