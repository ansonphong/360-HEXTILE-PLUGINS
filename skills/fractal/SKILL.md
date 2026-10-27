---
name: fractal
description: "Edit the mounted 360 Hextile Fractal Workshop, control its timeline, Open or Save scenes, and render or export saved Fractal sequences through the existing MCP tools."
---

# 360 Hextile — Fractal Workshop

Use the running APP's discovered Fractal tools. APP owns the mounted authoring session, saved scenes, GPU jobs and folder publication. The general `360-hextile` skill routes workflow automation; the separate `shader` skill describes native Shader authoring. Connected MCP edits the actual mounted renderer and uses native scene writers.

## Fresh context and ownership

Call `get_fractal_context` before composing work. Use current registry target IDs, retained orphan IDs, scene revision, owner and draft/source/viewer/renderer generations; never guess a numeric JSON leaf is eligible. Copy its complete `witness` unchanged, including the public header and Project witnesses. Source-free observation still needs the exact current owner and generations for a write. Missing witness, capability or input-conflict information is unavailable evidence: rediscover or report unsupported, rather than inventing it or assuming input is safe. `capabilities` contains exactly one input-acquisition token, `none` or `host_canvas_v1`, from the admitted ready renderer; it reports capability, never arming. `base` and `effective` are bounded finite target maps; `effective` is only the current acknowledged displayed sample and may be empty. Source-free `suspensions` and `diagnostics` may include advisory saved-binding conflicts as `{target: bindingID, code: binding_conflict|binding_unknown}` and expose no physical-key or event data.

Mounted mutations require MCP connected and the actual current renderer owner/generations. APP binds its private writer locally; do not send lease IDs, actor overrides or Copilot tokens. Only the exact matching native acknowledgement establishes an effect.

The four native action kinds — `fractal_edit`, `fractal_transport`, `fractal_open` and `fractal_save` — use the existing native witness/revision doors without user grants, session picks or Resume consent. Disconnect immediately closes fresh admission while preserving admitted original results.

Allocate a caller-known `client_request_id` (1–64 ASCII letters, digits, `_` or `-`) per intent and keep its exact arguments. Submit edits through `apply_fractal_edits` with `expected_draft_generation` equal to the witness. One atomic batch contains 1–32 closed ops; an invalid or stale batch changes nothing. After a refusal, refresh context and explain the actual reason. Use a new intent for changed work, never mutate the body under the same request ID.

## Authoring, clock and camera

Discover closed shapes in `tools/list`. The admitted ops are `set_base`, `set_driver_mode`, `set_expression`, `set_mapping`, `remove_mapping`, `remove_driver`, `upsert_modulator`, `remove_modulator`, the five input declarations below, `clock_action`, `set_timeline`, `set_fps`, `use_current_view_as_start` and `resume_driver`.

Fixed uses the authored base; Modulator and Expression drive an effective sample without overwriting it. Use returned target signatures for mappings and stable alias-to-ID `refs` for expressions (`hx-scalar/1`); do not substitute labels for IDs. Typed compound edits validate together. An incompatible retained driver stays authored and suspended until repaired or explicitly removed. Unsupported camera/presentation targets cannot be assumed to affect panorama output.

`control_fractal_timeline` supports play, pause, rewind, seek with exact `{num:string,den:string}`, and step with `frames=-1|1`. These are transient mounted transport actions. `set_timeline` writes authored start/end/loop; `set_fps` writes reduced rational FPS. Frame n samples exactly `start+n/fps`, with end exclusive. `clock_action` reset/align/rate explicitly reanchors the master clock at the selected sample; changing BPM/speed preserves phase according to APP's clock owner. Sample/effective values and playback do not dirty the authored base or save a scene.

Camera navigation changes the live pose. `use_current_view_as_start` explicitly authors that pose as the camera start; seek/playback alone does not. Human takeover can suspend a driver; `resume_driver` resumes only the named admitted driver under fresh authority.

## Input declarations and retained orphans

The five input ops are `set_mouse_input`, `upsert_input_gate`, `remove_input_gate`, `upsert_input_binding`, `remove_input_binding`. MouseInput is exactly `{schema:1,enabled:boolean,abi:"hx-mouse/1"}`. GateChannel is exactly `{id,alias,label,mode:"gate",unit:"gate",min:0,max:1,default:0}`. GateBinding is exactly `{id,channel_id,source:{kind:"key",code,modifiers},scale:1,activation:"interact"}`. IDs and aliases follow the discovered schema; modifiers are unique and sorted from Alt, Control, Meta, Shift. Bindings must reference an existing gate and pass current host key/navigation conflicts.

Declarations cannot arm Interact, inject physical events or captured input, or acquire a plugin host input lease. Reopening an interactive document remains unarmed and preserves its declarations. Only the human's Interact gesture acquires input. An `input_acquisition:none` consumer can inspect, disable or repair a document but refuses enabled live Click/Envelope sampling as `interactive_input_unsupported`; neutral input is not a substitute.

Even a dormant Click definition requires admitted enabled mouse input (`mouse_required`). A dormant Envelope retains its gate reference; removing that gate while any Envelope references it fails `input_gate_in_use`. An enabled Envelope needs a valid binding for its gate (`envelope_binding_required`). Repair the whole proposed document in one batch: remove/repoint dependent definitions and bindings before removing their gate, or remove every Click before disabling mouse. Merely disabling a definition does not erase its reference. Gate and binding validity is checked on the final atomic proposal, with the exact refusal codes above; a rejected proposal leaves everything intact.

For a retained orphan, read fresh context → choose the exact `retained_orphans[].target` → call `apply_fractal_edits` with `{op:"remove_driver",target:"<exact retained ID>"}` under the same current writer and witness. The target may be absent from the active registry but must retain a driver. Extra fields, an absent driver, stale authority or more than 32 ops refuse. This removes only that target's expression, bindings and exact suspension, preserving shared sources/gates, other signatures and drivers.

## Open, Save and uncertain outcomes

`open_fractal_scene` opens an exact saved `scn_` ID. `save_fractal_scene(mode="save")` requires the adopted `scene_revision` (`sha256:` plus 64 lowercase hex) and target scene ID. Save As uses `mode="save_as"` and a caller-proposed create-only `scn_[0-9a-f]{8}` ID, without an overwrite revision. Only a definitive collision permits another ID. A revision conflict requires fresh inspection; never force an overwrite.

Open or Save As that adopts B replaces A’s current writer identity. Fresh edits use B’s actual writer and witness. The first admitted receipt remains truthful after Disconnect or owner replacement; recover that original result without treating it as a new action on B.

For pending work, poll `get_fractal_request` with the original request ID. Exact replay means exactly the same request ID and immutable arguments, not a new ID or a re-composed witness. Prefer status GET after transport loss. A 410 or absent historical receipt is `unknown`, not proof of refusal or cancellation. Save reconciliation also checks `GET /api/fractal/scenes/{target}/write-status/{client_request_id}`; accepted publication proves the saved SHA even if a later mounted acknowledgement reports `ok:false` or `status:unknown`. Keep known scene/base revisions and do not resend that Save. Unknown durable status remains unknown; it never authorizes another mint or write.

## Saved native sequences and folder publication

Require `get_capabilities.native_render.contract:"native-render/1"`. Preflight
and submit the same saved scene/revision and original idempotency key through
`preflight_fractal_sequence` → `render_fractal_sequence`. Native requests use
reduced rational FPS1–120, exact `[start,end)` within0–86400seconds, matching
ceil(duration×FPS) count1–10000, seed, quality, dimensions and output. Keep
`publication_mode:"deferred"`; Fractal has no sequence supersampling option.
Equirectangular output is even-height2:1,128×64 through16384×8192. Dome supports
square1024/2048/4096/8192, both native projections, FOV10–360 and bounded pose.
Use actual advertised quality presets and captured native `project_path` when
supplied; never normalize the APP's locator on the MCP host.

Optional `destination_intent` records the chosen PNG/JPG folder before native
work. It is retained later-publication intent, not direct JPG rendering or an
early successful export. Native PNG completion alone does not prove that the
requested destination is saved. Separate existing publication remains available:
`preflight_fractal_sequence_export` → `export_fractal_sequence`, preserving exact
folder/format/quality and transaction fingerprint/attempt ID/revision.

Use `inspect_fractal_sequence_output` with `{request,destination}` for existing
output. This reads native identity metadata, not frame bytes. For matching
unfinished work, `control_fractal_sequence(action="continue")` carries the same
request/destination and returned inspection fingerprint. Accepted native work
owns cancellable verification/replay/rendering/publication. Native-complete work
retries only publication; both-complete output starts no GPU job. Unsafe or
unsupported output returns its actual refusal and preserves existing files.

Poll `get_fractal_sequence` about every1–2seconds, backing off on unchanged state.
Saved count may exceed the contiguous cursor. Checking totals, animation replay,
timing and last-reported restart counts are separate facts. Stop supplies the
observed run ID and is pending until ownership drains; stale409 needs a fresh
read, never an unscoped Stop fallback. Export controls also target the observed
attempt. Lost replies and known-ID404 remain unknown until the original request/
run/attempt is reconciled; do not silently mint another key or replay mutations.

## Current-preview still capture

`capture_fractal_still` uses the current finished360preview and its complete
native witness, with one caller-owned `client_request_id`. It does not switch
Fly mode, wait for a replacement sample, upscale the preview or start a one-frame
sequence. Stale source/Project/owner/context, unready required images and active
conflicting work refuse before mint. Keep the actual native frame provenance:
animated timing/sample evidence is distinct from a static completion stamp.

A known capture returns the real Render/node IDs and actual dimensions, at most
2048×1024. Export that exact source through `preflight_file_export` →
`export_render_file`, with the UI's supported generic Dome sizes, PNG/JPG/HDR/EXR,
pose/FOV, JPG quality and metadata options. HDR/EXR conversion of preview pixels
is not native scene-linear Fractal rendering. Render minting and destination
publication are separate outcomes.

Recover a lost capture reply with `get_fractal_request` for its original ID.
Unknown promotion retains its original frozen frame evidence through the existing
receipt lifetime; missing/expired410 remains unknown and never authorizes an
automatic recapture, replacement ID or latest-Render guess. A known mint remains
known after owner changes; failed export does not erase that source identity.

## Discovery evidence

The installer copies this sibling skill into a temporary home in focused tests. That proves source/temp discovery and does not prove an installed host, its MCP inventory, native GPU output or folder publication. Confirm the actual installed picker and `tools/list` before promising those operations. Do not install, publish or modify caches merely to use this procedure.
