---
name: shader
description: "Connect to the open Shader and inspect its state, or edit a Project or My Library Shader through acknowledged native files and APP-owned checks and Save."
---

# 360 Hextile — Shader

## Connect / what Shader is open?

For a read-only connection or current-Shader question, call the installed
`get_live_context(view="shader")` once. This compact read needs no
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
access, candidate Apply nor Save. Missing compact support requires an APP/plugin
update; report it instead of silently dumping the full app snapshot. APP down:
“Launch 360 Hextile, then retry.” MCP disabled: enable MCP in APP Settings.

Only use DevTools when the request needs visual/DOM inspection. Discovery does
not navigate, duplicate, attach, Apply, Save, render or take screenshots.

## Edit, controls, diagnostics or output

Before any Shader change or specialized operation, read
[the authoring procedure](references/authoring.md). It retains the native file,
capability, provenance, control, diagnostics, output and original-ID recovery
contracts. Load only the task-relevant guides it names. Shared reasoning runs in
the coding host; APP owns attachment, checks, accepted state, compilation and
Save. Read fresh `current_surface` and `shader_contract` before authoring;
discovery metadata grants no authority.

Keep native ownership, witness and base checks. Only acknowledged workspace open
releases editable paths; register exact complete raw bytes and reconcile an
uncertain outcome with its original request ID. Never auto-install/restart or
change host permissions. Installed package and running APP support must both be
observed after an update; repository changes do not activate installed caches.

Human guides: https://360hextile.com/docs/create/shader and
https://360hextile.com/docs/user-guide/agent-mode.
