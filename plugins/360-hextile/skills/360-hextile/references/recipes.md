# Recipes

App preferences, storage, cache, and license have no recipe here. Read `get_guide` `best-practices` for `get_app_preferences`, `update_app_preferences`, `get_storage_summary`, `get_cache_buckets`, `clear_disposable_cache`, and `get_license_status`.

Discover the installed `shader_*` native catalog before acting on a selected Shader. Native controls use the exact current asset, lease, owner, Project witness and operation request ID; a source file change uses `shader_edit` or `register_shader_update` on the package. Keep source bytes, formula content, rendered-frame identity and native destination validation distinct. After an uncertain native write, read the original operation ID before any new action. For editable Credits & Sources, read paged saved credits and complete known notices, then stage `shader_propose_credits` for review; keep prior records and distribution declarations intact. The source proposal in the adaptation example below belongs to an accepted asset-scoped creative change.

## External Shader adaptation: three upstream sources

Before converting source to HEXSHADER/360, inspect the supplied page, original source headers, declared provenance, exact licence and notice text, and explicit upstream links. If the installed `shader_research_sources` tool is present, supply only the page and up to four chosen links; its HTTP(S) text is untrusted evidence. Record real visited URLs, errors and omitted/truncated bytes. Read the current `provenance_hash` through the installed credits read when available, or the saved `provenance.json`. The JSON below is a `source_proposal` for an **asset-scoped accepted creative change**, not a complete replacement of `provenance.json`. Replace the sample hash with the exact current hash and replace each example observation with what was actually inspected. Three upstream rows identify original A, intermediate B, and utility U; the fourth row is this accepted adaptation by the actual human, with AI help described separately.

```json
{
  "schema": 1,
  "expected_provenance_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "sources": [
    {"kind":"append","row":{"author":"Original A","url":"https://example.org/a","contribution":"Original shader and copyright notice; preserve exact notice in provenance","relationship":"original","license":"MIT","license_status":"recorded","evidence":{"basis":"observed","url":"https://example.org/a","note":"Source header and linked MIT licence text inspected"},"source_revision":"a-tag"}},
    {"kind":"append","row":{"author":"Intermediate B","url":"https://example.org/b","contribution":"Ported A's pattern into B","relationship":"adaptation","license_status":"unknown","evidence":{"basis":"observed","url":"https://example.org/b","note":"Header names A but this page supplied no licence text"}}},
    {"kind":"append","row":{"author":"Utility U","url":"https://example.org/u","contribution":"Reused noise utility","relationship":"original","license":"MIT","license_status":"recorded","evidence":{"basis":"observed","url":"https://example.org/u","note":"Utility header and licence text inspected"},"source_digest":{"kind":"sha256","digest":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}}},
    {"kind":"append","row":{"author":"Current human creator","contribution":"Accepted HEXSHADER/360 adaptation of A via B using U","relationship":"adaptation","license_status":"unknown","ai_assistance":"AI helped convert GLSL; human reviewed and accepted","evidence":{"basis":"user_declared","note":"Human identified the accepted creative change"}}}
  ]
}
```

If B is inaccessible, keep its row `license_status:"unknown"`, with `evidence:{"basis":"user_declared","note":"User supplied B link; fetch failed"}` and the fetch error in the report. If B's header and page disagree, use `license_status:"conflicting"` and `basis:"observed"` with both observations in `note`; preserve both exact notices in the acknowledged provenance. If ancestry is only recognizable by a code pattern, use `basis:"inferred"` and `license_status:"unknown"`; never turn that inference into `recorded`. Keep any existing source rows and opaque fields, `retained_credits`, and `distribution` unchanged. A source proposal can append or change a lineage row only. Remove, reorder and current-credit correction use the native Credits & Sources path, which archives the old canonical row. Reuse the same adaptation row on later saves of the same adaptation, then read the saved credits and notices. A private export is not permission to distribute.

Enabling MCP fully trusts the connected agent. APP automatically binds its actual current document writer; source, Apply, capture and task paths need no separate consent or session selection. Include-source/formula/image options select bounded content. Native validation, ownership, CAS, resource limits and exact receipts remain authoritative. Disconnect blocks fresh or unadmitted work; an admitted export finishes to its frozen destination and remains recoverable by its original request/job ID. Stop separately requests cancellation. The MCP host’s own filesystem and execution rules still apply.

## Shader scalar expression and mounted timeline

For a simple exposed control such as Cell Count, read `get_shader_parameters` first and find its exact ID, type, current value and current bounds. `writable:true` means the current Shader can be authored; preserve its exact witness. Change that value with `shader_edit`. A value change needs a connected actual writer, not source disclosure. Structural edits use the same native ownership, Prepare and saved-receipt checks.

Discover `get_shader_context` and `propose_shader` in MCP `tools/list`. Read the fresh `get_live_context.current_surface` for the exact `shader`, `project_context_witness`, saved `base`, `studio_surface_id`, `owner_id`, `owner_generation`, `viewer_generation`, and `source_epoch`; these owner values are opaque, not frame/time counters. Inspect `get_shader_context` for stable typed parameter addresses and aliases. Check APP `available` and `executable_capabilities` for `parameter-expressions/1`, `shader-timeline/1`, and any existing `modulation/3`. By default metadata omits both hx-math and parameter-expression formula source. `include_formula=true` requests both formula families as bounded optional content; `include_source=true` separately requests GLSL/authoring bytes. Formula and GLSL inclusion are separate content choices.

For a saved Shader, assemble `propose_shader.base` from one fresh `get_shader_context` response: copy `shader`, `project_context_witness`, `working_revision`, `document_hash`, `source_hash`, and `manifest_hash` into a flat object. Confirm those fields match the mounted Shader and saved revision. Do not copy `current_surface.base` into the proposal: it can have `kind:"saved"` and lacks the Shader identity/witness. The complete JSON below illustrates the wire shape; replace its sample witness and hashes with fields from the same fresh context before calling.

```json
{"kind":"shader_document_candidate","base":{"shader":{"origin":"user","shaderId":"aurora"},"project_context_witness":"wit","working_revision":1,"document_hash":"sha256:abababababababababababababababababababababababababababababababab","source_hash":"sha256:cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd","manifest_hash":null},"explanation":"Animate gain over the saved interval","modulation_edits":{"schema":2,"edits":[{"op":"set_parameter_expression","target":"shader.params.gain","source_text":"T*2","refs":{}},{"op":"set_timeline","start":{"num":"0","den":"1"},"end":{"num":"4","den":"1"},"loop":true}]}}
```

`T` and `D` are seconds; `hx-scalar/1` values use each target's typed lane and angles use radians. For `MOD_X` or `P_gain` dependencies, `refs` must map every used token to the exact discovered stable modulator or parameter address; do not guess aliases. Cycles, unknown aliases and nonfinite results refuse with diagnostics. `remove_parameter_expression` returns the target to its base value. `set_parameter_mode` selects `fixed`, `expression` or `modulator` with the observed binding when needed; a new binding uses an existing stable `mod_*` string source ID and the target's exact typed signature, including enum choices or vector/channel kind. The proposal is a ticket, not a saved package. On unknown proposal or save, reconcile the exact ticket/current saved revision; never blindly repost or assume success. Reread the accepted saved hash before later work. Preserve all existing required capabilities, including unknown ones.

For **session playback only**, use `shader_control_clock` and `shader_step_frame`. `shader_step_frame` does not take `seen` and does not save. Do not call the mounted UI poll/ack routes. Session playback does not save. Changing `start`, `end` or `loop` is an edit of the timeline settings and is saved by register.

## Saved Shader native sequence

### Selected-folder Shader PNG/JPG/EXR

After confirmed native Apply and Save, read the fresh source hashes/revision and
Project witness. Require `get_capabilities.native_render.contract:"native-render/1"`
and a native-replayable source. Replace every sample identity below with that
same acknowledged saved source and choose an existing folder on the APP machine.
This example is24FPS over[0,2),48frames, final2048×1024, JPG90 and1.25spatial
supersampling. Use the byte-identical intent for preflight and submit.

For playable camera controls, first use `shader_capture_sequence_input` with the
discovered saved base, mounted surface and edit sequence. Wait for its original
`shader_get_operation(scope="asset")` ticket to apply, then include that request
ID as `input_capture_id` in both requests below. Captures expire after five
minutes before admission. The native recipe retains camera pose and persistent
toggles, neutralizes movement and preserves time animation. Unsupported event
history still refuses. Continue uses its stored snapshot without recapturing;
an uncertain submission must be recovered by its original sequence ID/key.

```json
{"shader_ref":{"origin":"project","id":"aurora"},"project_context_witness":"project-witness","working_revision":2,"document_hash":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","source_hash":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","resource_manifest_hash":null,"selected_resource_frames":[],"idempotency_key":"aurora-direct-001","name":"Aurora direct","frame_rate":{"num":24,"den":1},"frame_count":48,"start_time":{"num":"0","den":"1"},"end_time":{"num":"2","den":"1"},"width":2048,"height":1024,"seed":7,"supersampling":1.25,"output":{"projection":"equirectangular","pan":0,"tilt":0,"roll":0},"folder_export":{"destination_folder":"D:\\Renders\\Aurora","format":"JPG","quality_if_jpg":90}}
```

`preflight_shader_sequence` returns the known ID/request hash before admission;
`render_shader_sequence` uses that exact body/key. Poll `get_shader_sequence` for
actual owner/run/revision/checking/replay/rendering/writing and saved completion.
No intermediate PNG image sequence or automatic final copy is requested by this
direct flow. For PNG or EXR use that format and null JPG quality. Temporal/input/
resource or supersampling refusals remain native; never silently downgrade.

For existing output, `inspect_shader_sequence_output({request:<same intent>})`
reports new/unfinished/completed/unavailable/conflict without checking pixels.
Only a matching unfinished result can Continue with the exact request plus its
inspection fingerprint. Keep the accepted continuation receipt after a lost
reply and reconcile that original run; previous terminal status alone cannot
prove the new Continue was rejected. Stop uses the current observed run ID.

### Explicit deferred Shader masters and publication

After the expression or timeline edit, read merge and compile, then read the saved revision. A proposal ticket or uncertain Save is insufficient: reconcile the exact ticket and confirmed saved revision, or refuse. Reread `get_shader_context` for the **new saved** `shader`, `project_context_witness`, `working_revision`, `document_hash` and `source_hash`. Use those actual returned values in place of the sample identities below. The same exact JSON request goes to `preflight_shader_sequence` and `render_shader_sequence`; keep the caller-chosen `idempotency_key` unchanged. The example is 24 FPS over [0,2) seconds, so `frame_count` is 48. Do not add `folder_export` or infer a destination or live Dome pose.

```json
{"shader_ref":{"origin":"project","id":"aurora"},"project_context_witness":"project-witness","working_revision":2,"document_hash":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","source_hash":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","idempotency_key":"aurora-native-001","name":"Aurora native","frame_rate":{"num":24,"den":1},"frame_count":48,"start_time":{"num":"0","den":"1"},"end_time":{"num":"2","den":"1"},"width":2048,"height":1024,"seed":7,"output":{"projection":"equirectangular","pan":0,"tilt":0,"roll":0},"publication_mode":"deferred"}
```

Preflight returns `sequence_id`, `status` (`ready` or `existing`), `request_hash` and, for an existing record, `recipe_hash`. Only after that receipt, send the same request to `render_shader_sequence`; it returns the same ID/hash with queued or existing status. Poll `get_shader_sequence({"sequence_id":"<preflight ID>"})` for native progress and its reported terminal outcome. Restart counts remain last reported until explicit verification. If the render reply is lost, GET that **known** ID and compare `request_hash`; a 404 is outcome unknown, not permission to mint a key or blindly repost. The GET projection omits source, formula and private paths, including on older automatic records. An explicitly chosen native square Dome instead uses `width=height=diameter` and `output={"projection":"fulldome","diameter":2048,"fov_deg":180,"pan":0,"tilt":0,"roll":0}`; `fulldome_angular` is the other native projection, and FOV is 10–360 degrees. APP checks operational Standard or Pro access to queue; Lite/unlicensed work refuses. Generic `create_sequence`/`start_sequence` remain folder upres.

Once GET reports `status:"completed"` and `published_cursor==frame_count`, use the exact existing destination_folder task path. The caller supplies the folder path to the local MCP tool; no UI picker or retained private path is exposed by GET. Send the following intent to `preflight_shader_sequence_export` (replace the sample sequence ID and folder with the chosen values). For JPG, use `"format":"JPG","quality_if_jpg":90`; PNG keeps quality null. Deferred PNG masters cannot export EXR; use direct `render_shader_sequence` with `folder_export.format:"EXR"` to render EXR frames.

```json
{"sequence_id":"seq_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","destination_folder":"C:\\Chosen\\Frames","format":"PNG"}
```

Keep the returned `attempt_id` and `transaction_fingerprint`. Submit `export_shader_sequence` with the **same** `sequence_id`, `destination_folder`, and `format`, plus `"transaction_fingerprint":"<preflight fingerprint>"`. Poll `get_shader_sequence({"sequence_id":"<preflight ID>"})`, matching `attempt_id` and fingerprint in `folder_export` or `publication_attempts`. If export acknowledgement is lost, GET that known ID/attempt before another action; absence is unknown, never a reason to blindly repost. To stop native work use `control_shader_sequence({"sequence_id":"<preflight ID>","action":"stop"})`; resume uses `action:"resume"` and current Standard/Pro access. To cancel or retry folder publication use `action:"cancel_export"` or `action:"retry_export"` with the exact current `attempt_id`. GET after uncertain control replies. Native equirectangular and square Dome masters keep their frozen timing/projection; deferred folder PNG/JPG encoding does not change them.

## Shader file session — the package

Invoke the installed `shader` skill through the host's observed picker. Verify actual `tools/list`, the MCP connection and the shader id, then call `open_shader_workspace` with `shader_id` and `request_id` only. The result is the lease, commit and revision.

The package folder holds `shader.json`, `source.glsl`, `modules/**/*.glsl`, `provenance.json`, `resources/`, `originals/` and an optional cover. `shader.json` is the authored data. GLSL stays in `source.glsl` and the modules. A helper such as `modules/lib/noise.glsl` is included from `source.glsl` with `#include "lib/noise.glsl"`. Include paths are relative to the including file. Keep unused helpers in the package. `shader_edit` cannot write `provenance.json`.

`shader_edit` sends set, create, reshape or delete on one address. `register_shader_update` sends the package digest and saves. Read merge. Watch compile. A repair after prepare failed uses a new request id. The same request_id returns the recorded result. The agent never uses a Git commit, checkout or export as a substitute for registration. Human detail: https://360hextile.com/docs/create/shader.

## A — Prompt-only scout from a builtin

```
get_workflow(origin=builtin, id=quick-scout)
validate_config(workflow_id=quick-scout, origin=builtin, overrides={
  "prompt": {"global": "<user look>"},
  "input": {"path": "<existing equirect file>", "source": "file"}
})
run_workflow(same)
get_status(run_id)
```

`quick-scout` ships with empty `input.path` — a live run needs a file (or a seed from B).

## B — 360-LoRA seed then run

```
list_360_loras          # pick path + base_model (and trigger_word if listed)
generate_seed(request_id=<fresh UUID>, prompt, lora_path, base_model, n=4)
get_seed_job(job_id)    # poll until terminal; retain this exact ID
# choose completed_variations entry with original index=0, if present
run_workflow(workflow_id=quick-scout, overrides={
  "input": {"path": "<variation path>", "source": "file"},
  "prompt": {"global": "<look>"}
})
```

If the submit acknowledgement is uncertain, GET the same UUID. A provisional 404 permits replay of the identical body and UUID, never a new ID. `partial`, `cancelled`, `failed`, and `interrupted` may retain completed entries; report the status and any missing requested index honestly. `cancel_seed(job_id)` affects only that seed job. `list_seed_history` and `get_seed_batch` remain for stored batches.

## C — Save a user variant

```
get_workflow(builtin, quick-scout) → document
# apply overrides locally
validate_config(document=modified)
save_workflow(origin=user, id=my-scout, document=modified)
run_workflow(workflow_id=my-scout, origin=user)
```

If `save_workflow` returns 409, pick a new id or `delete_workflow` first (only if the user asked).

## D — Monitor without run_id

```
list_runs(lifecycle_status=active)
# each row: render_id, status, progress, output_path
get_status(run_id=render_id)
```

Terminal statuses: `completed`, `failed`, `cancelled`, `crashed`. Stop uses `cancelled`, not `stopped`.

## Recipe E — Upres still

```
get_capabilities
validate_config(workflow_id=upres-still, origin=builtin, overrides={
  "input": {"path": "<absolute image path>", "source": "file"},
  "upscale": {"scale_factor": 2 or 4}
})
run_workflow(same)
get_status(run_id)
```

Builtin default is 4×. Omit `upscale` unless the user asked for 2×. Request `cancel_run` only when replacement is authorized, then observe the original job and GPU-holder drain before a second heavy job; a cancellation acknowledgement is not settlement.

## Recipe F — Upres folder or video

`run_workflow` cannot create a `seq_*`. Do not loop `run_workflow` over frames.

Tools: `extract_sequence_video`, `create_sequence`, `start_sequence`, `get_sequence`, `list_sequences`, `stop_sequence`.

```
extract_sequence_video({video_path})   # video only; use returned folder_path
get_workflow(origin=builtin, id=upres-still)
# If pipeline is top-level, that object is the document.
# If nested document.pipeline exists, use that nested object.
# Patch input.mode=sequence, input.path=<folder>, input.source=file,
# optional upscale.scale_factor 2 or 4.
# Never POST a partial {pipeline, input, upscale} stub — 422.
create_sequence({folder_path, config: patched document})
start_sequence
get_sequence   # poll while queued or processing
```

`create_sequence.config` is a full `HextileConfig` cloned from `upres-still`. Stop and report `paused` and `incomplete` (`incomplete` is resumable in the app; v1 has no resume MCP tool). Terminal: `completed`, `completed_with_errors`, `failed`, `cancelled`. Request cancellation with `stop_sequence`; the top-level sequence can report `cancelled` before the active frame drains. Observe frame/holder settlement before starting replacement GPU work. Use `list_sequences` if the id is lost.

## Recipe G — Generate Layer into an exact saved render

No viewer is required. Ask for approval for each mutating call. Find the exact saved render in `list_runs`; its `head` is the parent for `get_layer_draft`. Here `r-123` and the 12-hex HEAD are samples. Use the actual IDs returned by each call.

```text
list_runs                         # choose exact render_id and its head
get_layer_draft(render_id="r-123", parent_id="aaaaaaaaaaaa")
# Require head == parent_id, studio_owned == false. If a draft exists, carry its
# exact draft_id and mutation_rev; otherwise omit both for pointer-first creation.
generate_layer(target="saved", render_id="r-123",
  request_id="11111111111111111111111111111111",
  expected_head="aaaaaaaaaaaa", parent_id="aaaaaaaaaaaa", mode="generate",
  controls={"pipeline":"sdxl","prompt":{"global":"a red enamel pin","negative":""},
    "diffusion":{"model":"sdxl-base","quantization":"none","seed":1,
      "scheduler":"euler","guidance_scale":7.5,"num_inference_steps":20},
    "output":{"width":1024,"height":1024},"alpha":{"mode":"opaque"},
    "layer_gen":{"scene":{"enabled":false}}})
get_layer_generation(render_id="r-123", job_id="11111111111111111111111111111111")
# Poll until ready. Keep the returned draft_id and composition_id.
land_generated_layer(target="saved", render_id="r-123", layer_id="pl_enamel1",
  job_id="11111111111111111111111111111111", expected_head="aaaaaaaaaaaa",
  draft_id=<returned draft_id>, composition_id=<returned composition_id>,
  expected_mutation_rev=1,
  pose={"yaw":20,"pitch":-10,"roll":0,"fov":40,"projection":"auto"})
commit_layer_draft(target="saved", render_id="r-123", parent_id="aaaaaaaaaaaa",
  draft_id=<same draft_id>, composition_id=<same composition_id>,
  expected_mutation_rev=<land receipt mutation_rev>)
```

`ready` does not insert a layer. Land does not commit. To stop the exact job, call `cancel_layer_generation(render_id="r-123", job_id=<job id>)` and poll until released; omitted `execution_target` means saved. `rematte_layer` also defaults to saved, and its separate `target` identifies the witnessed recovery take. If any acknowledgement is lost, reconcile the exact request/job/layer/draft IDs with `get_layer_generation` and `get_layer_draft`; inspect graph HEAD for an uncertain commit. Never send a fresh request or layer ID as an automatic retry. A missing RAM job after restart remains unknown. A rematte reply loss is non-replayable because APP chooses its new job ID; inspect local job activity before asking for another approved action. Max 64 layers per draft and eight takes per Re-gen layer. External `target=live` or `execution_target=live` is forbidden; an approved internal Copilot child may control only its matching armed live job.

## Recipe H — Spot Clone on an exact saved render

No viewer is required. Choose a final parent and explicit source/destination poses for the native clone write. The IDs below are examples, not defaults.

```text
preflight_spot_clone(render_id="r-123", parent_id="aaaaaaaaaaaa")
# Require head == parent_id and parent_final. Choose a listed template/raster
# fingerprint, or use a deterministic shape with no fingerprint.
clone_spot(target="saved", render_id="r-123", node_id="bbbbbbbbbbbb",
  expected_head="aaaaaaaaaaaa", parent_id="aaaaaaaaaaaa",
  destination_id="spot-copy-1",
  source_pose={"yaw":10,"pitch":0},
  destination_pose={"yaw":30,"pitch":10,"roll":0,"fov":45},
  mask={"source":"shape","shape":"hexagon"})
get_spot_clone(render_id="r-123", node_id="bbbbbbbbbbbb")
```

For `from_template`, use the listed `template_id` and `face_index`; for `from_raster`, use a listed render-local `raster_id`. Both require `expected_mask_fingerprint` equal to that preflight entry's fingerprint. A changed mask or HEAD refuses the write. On a lost POST reply, read the exact node receipt and recipe digest; 404 remains unknown, not permission for a new id. Stop cannot undo a graph node that already committed. External MCP cannot use `target=live`; Copilot may commit only an already prepared, matching Spot Clone operation after its own approval.

## Recipe I — Playable Shaders: fly source

Use the installed `shader` skill. The package is `shader.json` plus `source.glsl`. Observe the running APP, then put the fly controls in `shader.json`: parameters `fold` and `hue`, `space` `direction_360`, and `controls.camera` set to the resolved fly camera. A preset id is not a definition. Use the resolved bytes already in the document or supplied by the user.

This source matches the shipped fly-fractal example. Keep `space` `direction_360` and values `{ "fold": 1, "hue": 0 }`.

```glsl
float sceneDist(vec3 point) {
    vec3 q = mod(point + 2.0, 4.0) - 2.0;
    float scale = 1.0;
    for (int i = 0; i < 4; i++) {
        q = abs(q) - vec3(0.35 * hxParam_fold);
        q = q * 1.6;
        scale = scale * 1.6;
    }
    return (length(q) - 0.6) / scale;
}

vec4 hxMain(in HxFrag hx) {
    // The scene ray comes from the generated camera helpers, not from hx.rayOrigin.
    vec3 ro = hxCameraPosition;
    vec3 rd = hxCameraDirection(hx.direction);
    float t = 0.0;
    float steps = 0.0;
    for (int i = 0; i < 64; i++) {
        float d = sceneDist(ro + rd * t);
        if (d < 0.002 || t > 30.0) { break; }
        t = t + d;
        steps = steps + 1.0;
    }
    float hit = 1.0 - step(30.0, t);
    vec3 tint = 0.5 + 0.5 * cos(6.2831853 * (vec3(0.0, 0.33, 0.67) + hxParam_hue + t * 0.05));
    vec3 color = mix(vec3(0.02, 0.03, 0.06), tint * (1.0 - steps / 64.0), hit);
    return vec4(color, 1.0);
}
```

The fly camera's channels, bindings and camera fields stay together on `controls`. Unreal fly (`hextile.unreal-fly/1`) uses RMB look, W/S travel, A/D strafe, Q/E rise/fall and Shift boost. Arrow fly (`hextile.arrow-fly/1`) keeps the same channels but uses Arrows and PageUp/PageDown with `activation` `interact`. The GLSL stays unchanged.

Generated signatures: `vec3 hxCameraPosition`, `mat3 hxCameraRotation`, `vec3 hxCameraDirection(vec3 canonicalDirection)`. A null camera supplies `const vec3(0.0)` and `const mat3(1.0)`. The helper returns `normalize(hxCameraRotation * canonicalDirection)`. Wire `ro=hxCameraPosition` and `rd=hxCameraDirection(hx.direction)` into your own ray marcher once. `hx.direction`, `hx.rayOrigin` and `hx.rayDirection` remain canonical. Camera angles and sensitivity are radians, +Y is up and +Z is forward.

## Recipe J — Playable Shaders: one-prompt Enter BLAST, camera null

“Make it when I press ENTER then we get a blast event” means one `shader.json` together with the GLSL. Parameters are destinations, channels are inputs, and an envelope supplies the shaping. Edit with `shader_edit`. No event callback or new MCP tool is needed.

Write this source (the shipped camera-null example):

```glsl
vec4 hxMain(in HxFrag hx) {
    vec3 d = hx.direction;
    // Slice is driven by the X accumulator; Glow is driven by the BLAST envelope.
    float bands = 0.5 + 0.5 * sin(8.0 * (d.x + 0.5 * d.y + 0.25 * d.z) + 6.2831853 * hxParam_slice);
    // BLAST is read raw here too, so the ring also widens during the blast.
    float ring = exp(-(6.0 - 3.0 * BLAST) * abs(d.y));
    vec3 base = mix(vec3(0.05, 0.08, 0.20), vec3(0.20, 0.50, 0.90), bands);
    vec3 color = base + vec3(1.0, 0.55, 0.2) * hxParam_glow * ring;
    return vec4(color, 1.0);
}
```

Put this `shader.json` on the package. An address is a list of strings, one unit: `["parameters", "glow"]`, `["controls", "channels", "blast_press"]`, `["modulators", "mod_0123456789abcdef01234567"]`, `["drivers", "glow"]`. Do not replace a parent object. `controls.camera` is null. The ids below are the sample ids; preserve existing ids on a revision.

```json
{
  "hexshader": 1,
  "meta": {
    "title": "Enter blast",
    "tags": []
  },
  "space": "direction_360",
  "parameters": {
    "slice": {
      "type": "float",
      "label": "Slice",
      "default": 0,
      "min": 0,
      "max": 1,
      "step": 0.01,
      "control": "slider"
    },
    "glow": {
      "type": "float",
      "label": "Glow",
      "default": 0,
      "min": 0,
      "max": 2,
      "step": 0.01,
      "control": "slider"
    }
  },
  "values": {
    "slice": 0,
    "glow": 0
  },
  "controls": {
    "mouse": true,
    "profile": {
      "id": "hextile.example-enter-blast/1",
      "revision": 1,
      "label": "Enter blast example"
    },
    "instructions": "No camera moves here. Press Enter: Blast rises in 20 ms and fades over 400 ms, driving Glow from 0 to 2. Each right mouse click adds 0.1 to X, and X drives Slice. If Enter belongs to a built-in shortcut, use Bind key to pick another key.",
    "channels": {
      "x": {
        "alias": "X",
        "label": "X",
        "mode": "accumulator",
        "unit": "unitless",
        "min": 0,
        "max": 1,
        "default": 0
      },
      "blast_press": {
        "alias": "BLAST_PRESS",
        "label": "Blast press",
        "mode": "gate",
        "unit": "unitless",
        "min": 0,
        "max": 1,
        "default": 0
      }
    },
    "bindings": {
      "x_right_button": {
        "channel": "x",
        "source": {
          "kind": "button",
          "button": 2
        },
        "scale": 0.1,
        "activation": "interact"
      },
      "blast_enter": {
        "channel": "blast_press",
        "source": {
          "kind": "key",
          "code": "Enter",
          "modifiers": []
        },
        "scale": 1,
        "activation": "interact"
      }
    },
    "camera": null
  },
  "modulators": {
    "mod_0123456789abcdef01234567": {
      "kind": "envelope",
      "alias": "BLAST",
      "label": "Blast",
      "enabled": true,
      "input": "blast_press",
      "mode": "oneshot",
      "attack": 0.02,
      "release": 0.4,
      "attack_curve": {
        "shape": "linear",
        "exponent": 1
      },
      "release_curve": {
        "shape": "ease_out",
        "exponent": 2
      },
      "output_min": 0,
      "output_max": 1
    }
  },
  "drivers": {
    "slice": [
      {
        "kind": "control",
        "source": "x",
        "enabled": true,
        "signature": {
          "kind": "float",
          "unit": "unitless",
          "min": 0,
          "max": 1
        },
        "mode": "range",
        "min": 0,
        "max": 1
      }
    ],
    "glow": [
      {
        "kind": "modulator",
        "source": "mod_0123456789abcdef01234567",
        "enabled": true,
        "signature": {
          "kind": "float",
          "unit": "unitless",
          "min": 0,
          "max": 2
        },
        "mode": "range",
        "min": 0,
        "max": 2
      }
    ]
  }
}
```

Enter binds `blast_press` (a gate whose default is 0) to the `BLAST` envelope (`kind` `envelope`, `mode` `oneshot`). That modulator drives `glow` from 0 to 2, and the GLSL reads `hxParam_glow`. The right mouse button adds 0.1 to channel `x`, and that channel drives `slice`. The source also reads raw `BLAST`.

**Held alternative:** keep the same ids and set `mode` to `held`, `attack` to 0.2 and `release` to 0.6. **Burst:** `mode` `oneshot` completes attack then release even after key-up. Attack 0 is an instant burst.

Attack and release are seconds from 0 to 60. Curves are `linear`, `ease_in`, `ease_out` or `ease_in_out`. This example uses a 0.02 linear attack and a 0.4 ease-out release with exponent 2. Envelopes use interaction time. They do not follow scene pause or the clock BPM.

An envelope input must be an existing gate whose default is 0. A modulator or channel alias the code still names cannot be renamed or removed; such an edit comes back skipped. Change the code in the same batch to drop the name.

Report an Enter shortcut conflict and propose an explicit remap. Control authoring never arms Interact, presses keys, changes live pose or writes Project presets. Read merge. Watch compile. Compilation is not physical input or visual proof.
# Inspect an exact full-quality Shader Sequence frame

Discover `native_render.shader_preview` and require `shader-export-preview/2`.
Use the actual clean saved mounted Shader owner/base/witness and a fresh caller
UUID for this explicit request. For an Angular Dome frame near the end of a
10–11 second interval at 30000/1001 FPS, add these settings to that owner envelope:

```json
{
  "mode": "sequence",
  "width": 4096,
  "height": 4096,
  "output": {
    "projection": "fulldome_angular", "diameter": 4096,
    "fov_deg": 180, "pan": 0, "tilt": 0, "roll": 0,
    "supersampling": 1.5
  },
  "sequence_sample": {
    "start_time": {"num": "10", "den": "1"},
    "end_time": {"num": "11", "den": "1"},
    "frame_rate": {"num": 30000, "den": 1001},
    "frame_count": 30, "index": 29
  }
}
```

Call `shader_request_preview` once. Reconcile its original operation via
`shader_get_operation`; poll `shader_get_preview` under the same UUID. This is
frame 30 of 30 at exact time 329029/30000 s, strictly before End. Metadata must
confirm 4096² delivered pixels, 1.5× SS, Angular Dome and that exact sample;
queued settings or success alone do not prove those pixels. Supported stateful
Shaders replay the native frozen samples. A native refusal stays a refusal.

Opt into `image:true` only for a labeled reduced display attachment (512 px/side,
1 MiB maximum). Inspect source-pixel quality in the APP inspector at 100%; the
attachment does not prove it. Release/cancel with `shader_release_preview` using
the original UUID and original Shader/Project witness. Unknown replies retain the
original identity; never create a replacement ID automatically. Preview cleanup
does not cancel an accepted export job. Still uses `mode:"still"` and omits
`sequence_sample`, freezing the actual completed native frame.


Shader raster stills accept checked custom 2:1 dimensions or square Dome diameters; listed resolution presets are conveniences, not the allowed set. Read `native_render.stills["shader-raster-still/1"].dimensions` and the Shader Dome range. Supersampling accepts finite scales of at least 1, subject to format, device and working-set admission; never infer a 2× ceiling from presets. Omit the field to preserve a retained legacy request. Both Dome laws retain their explicit Preserve 360 choice. EXR supersampling remains gated by its separately advertised float-processing contract.
