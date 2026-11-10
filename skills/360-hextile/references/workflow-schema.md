# Workflow schema (agent)

Enabling MCP fully trusts the connected agent; `get_local_access_status` reports the connection state. APP binds its actual current document writer without Follow, session selection or separate source/formula/capture grants. Include options select bounded content, and task paths select destinations. Native witnesses, validation, ownership, revision conflicts and original-request reconciliation still apply. Read the live `shader_contract` and its blockers before authoring; APP automatically Applies and saves singular ready Shader candidates through the native writer. Compilation alone is not a Save receipt. The MCP host retains its own filesystem, execution and desktop permissions.

App preferences, storage, cache, and license are not Workflow fields. Read `get_guide` `best-practices` before `get_app_preferences`, `update_app_preferences`, `get_storage_summary`, `get_cache_buckets`, `clear_disposable_cache`, or `get_license_status`.

A **Workflow** is a full `.hextile.json` document. There is no second format.

Validated by APP `HextileConfig`. The MCP never merges or validates as authority.

## Required / important fields

| Field | Role |
|-------|------|
| `schema_version` | Usually `prompt-data-model-v2` |
| `pipeline` | Model family id, e.g. `sd21`, `sdxl`, `flux_schnell`, `realesrgan` |
| `hextile` | Template + tile sizes (`template` like `Dodecahedron`) |
| `input` | `source` is **`file` or `render` only**. `path` must be non-empty for a **live** run |
| `diffusion` | `model`, `seed` (`-1` random), `strength`, `guidance_scale`, `num_inference_steps` |
| `prompt` | At least `prompt.global`. Tile / directional prompts optional |
| `output` | Width/height, `file_format`, optional `path` |
| `passes` | Optional multipass list (max 10). Arrays **replace wholesale** on merge |
| `upscale` | Optional. `scale_factor` is `2` or `4` |
| `tiles`, `sequence`, `coverage`, `post_process` | Optional |

Retired render-time `input.source` values (`pattern`, `360_lora`, `solid_color`, `marble`, `blockade`) coerce to `file`. Do not write them.

## Live run vs dry_run

- `validate_config` / `dry_run: true` — empty `input.path` is OK.
- `run_workflow` live — after merge, `input.path` must be a real file (or a render id when `source=render`).

## Persist

`POST /api/workflows/{user|project}` create-only. Builtin is immutable. Existing id → 409.

## Builtin starting points

`quick-scout` (fast 2K / `sd21`), `progressive-build`, `structure-first`, `bloom-from-noise`, `grand-remaster`, `painters-pass`.

## Native render requests

Native Shader/Fractal rendering uses the named native tools, separate from a
Workflow document. Require `get_capabilities.native_render.contract` equal to
`native-render/1`; missing support requires upgrade rather than dropped fields.
The capability projection gives actual native bounds and supported combinations.
`native_render.render_routes` lists `native`, `webgl-raw-float`,
`webgl-display-native-encode`, `webgl-browser-encode-desktop`, and
`webgl-browser-encode-backend`. The API default is native. The Render Shader
dialog can prefer Viewer - App codec for fresh PNG/JPG settings when advertised
as available. An omitted `render_route`
on `shader_preflight_still_export`, `shader_export_still`,
`preflight_shader_sequence`, `render_shader_sequence`, and
`shader_request_preview` stays native. A route is available only while that
discovery row says `available:true`. A qualification fixture does not make it
available. No mounted capable Workshop refuses with `no_capable_client`; a
desktop writer without the desktop app refuses with `desktop_only`. The agent
does not produce frames. APP delivers `shader_render_produce` on the existing
mounted channel, and the Workshop claims that grant. Status keeps `route`,
`producer_state`, and `published_cursor` inside the existing projection.
Cancel and recovery stay on the original request, sequence, run, and attempt IDs.
`available` reports the mounted runtime/writer; it does not activate a pipeline.
For explicitly enabled local testing, discovery reports `available:true` and
`qualification:"testing"`, with no qualified envelopes. This permits testing
through the same UI/MCP native operations; it is not a quality or production
approval. The source-owned `WEBGL_TESTING_ENABLED` switch in
`plugins/shader/backend/webgl_admission.py` controls this access; requests cannot
enable it. It also requires existing source developer mode (`HEXTILE_DEV_MODE=1`);
packaged processes cannot use it. Setting it false restores the existing reviewed production envelopes.
Device, format, memory, history, currentness and ownership checks still apply,
and the requested route is never silently changed.
Viewer - High precision (`webgl-raw-float`) still output can be tested. Its Sequence
raw-spool consumer is not implemented: testing preflight refuses with
`raw_float_sequence_unsupported` before job creation; use the other Viewer
routes for Sequence tests. Do not claim that testing access completes that handoff.
`qualification:"closed"` / `admission:"route_unqualified"` means production
requests are refused unchanged. Keep the selected route and request bytes; never
retry as native or lower quality. Check each format's `geometry_limits` and
`history_limits`: direct Dome history is unsupported; WebGL history requires
1× SS, at most 2048×1024 equirectangular or 1024² Preserve 360°.
Custom dimensions and finite SS ≥1 remain subject to actual format/device and
working-set admission, not the preset list. EXR retains its own float limits.
Sequence status preserves the closed `render_route` including browser codec
quality when supplied, alongside the bounded producer/publication cursor.
Publication-only Continue reuses verified saved frames; rendering Continue starts
at the first unpublished frame using the original frozen recipe. Inspect/Continue,
status and observed-run Stop remain the same native operations. Recover unknown
outcomes with the original UUID/key/sequence/run/attempt and original request;
missing status is unknown, never permission to mint a new request.


Full-quality Shader inspection advertises `native_render.shader_preview.profile`
`shader-export-preview/2`. `shader_request_preview` adds required `mode:"still"|
"sequence"`, `width`, `height` to its saved mounted-owner request; `output` retains
projection/framing and optional finite `supersampling` ≥1, subject to format/device/working-set admission. Sequence requires
`sequence_sample:{start_time,end_time,frame_rate,frame_count,index}` with reduced
rational string endpoints, exact integer FPS, zero-based index and exclusive End.
Geometry/quality/history use native export limits. This is a transient inspector,
not an export job or Workflow. Native status/cancellation and uncertainty use the
original request UUID. Default `shader_get_preview` returns actual full-size
metadata and progress; `image:true` is a labeled reduced display attachment capped
at 512 px per side/1 MiB. It never replaces the native full-resolution raster.
`shader_release_preview` also cancels the original queued capture or native
freeze. `released:false,status:"cancel_pending",cleanup:"pending"` keeps the
original owner until cleanup is confirmed; it is not permission to start anew.

When advertised under `native_render.shader_preview.timing` and `.estimate`,
completed preview metadata also carries optional `timing` (`shader-render-timing/1`)
and `estimate` (`shader-render-estimate/1`). Timing separates native `startup_ms`,
selected `frame_work_ms`, prior `history_replay_ms` and `history_frame_count`.
The processing duration is the sum of these three times; animation `time` remains
the sampled timeline position. Sequence estimates use setup once plus exact frame
count times selected-frame work. History replay is not multiplied. They are
approximate, based on one preview, and exclude process launch, preview transfer,
file encoding and destination writing. Frame complexity can change over time.
Still previews have timing but no sequence estimate. Missing/null evidence means
unavailable; never assume zero or launch a benchmark to obtain it.

The local inspector can rescale this native linear model for End-only count
changes while source, inputs, output/SS, Start and FPS still match and the measured
sample remains inside the interval. Other changes require a matching new preview;
Auto off still requires Refresh. The estimate never changes image currentness.
Direct Shader sequence status may expose `render_estimate` with
`basis:"saved_frames"`, `includes_output:true`, bounded sample count and approximate
`remaining_ms`. It uses current-run saved-frame throughput including encoding and
writing; `total_ms` describes the current run, not cumulative resumed attempts.
Startup, replay, pause, interruption and insufficient evidence yield unavailable.
New runs reset measurement history; cancellation and original-request recovery
continue through existing native controls. No new mutation or GPU job is added.

Shader sequence input includes the saved identity/hashes/Project witness, exact
rational interval/FPS/count, dimensions, seed, output and optional hundredth
`supersampling` ≥1 with no preset-derived ceiling. Direct output carries
`folder_export:{destination_folder,format:"PNG"|"JPG"|"EXR",quality_if_jpg}`; JPG requires
quality1–100 and PNG and EXR use null. Explicit `publication_mode:"deferred"`
omits that folder and retains separate native-master publication tools. Fractal
remains deferred, with saved scene/revision, native quality preset and optional
`destination_intent`; it has no sequence supersampling field.

Inspection takes `{request}` for Shader and `{request,destination}` for Fractal.
The existing control tool's `continue` action adds `inspection_fingerprint` and
the same immutable request. The fingerprint is an optimistic check, never source
or write authority. Keep original request/job/run/attempt IDs on uncertain replies.

Shader RGB policy requires `native_render.shader_raster_policy.profile` equal to
`shader-raster-policy/1`. New supported PNG requests should explicitly send
`raster_policy:{"profile":"shader-raster-policy/1","processing":"auto","png_compress_level":0}`;
compression On selects 6. Both levels decode identically within a processing path.
Use `processing:"cpu"` for the maintained compatibility path. JPG and native RGB
Preview accept only profile/processing (no PNG level). Put policy at the top
level of a direct Sequence request, or inside `output` for Preview and raster
Still/Dome preflight. Policy is excluded from deferred Sequence, PNG master,
linear EXR and Fractal. Omission retains legacy CPU/PNG6 identities and recovery;
never add policy when replaying an original request that omitted it.

WebGL display jobs may separately report bounded `display_processing` work: `cpu`, `gpu`, or `gpu_cpu_repair`, with the issued kernel hash, readback bytes and calculated owned memory. This evidence does not qualify a route or prove file publication; retain the native `raster_execution` and publication receipts independently. Legacy peers may omit it.

Bounded status retains admitted `raster_policy`, arithmetic `raster_profiles`
and effective `raster_execution` where applicable. Preview/Still execution is
pending (`null`) until available; completed new-policy output needs a checked
receipt. Sequence accepted settings carry policy/profiles and storage encoding
carries the selected PNG level. Static support does not mean every job used the GPU.
Discovery advertises `gpu_qualified` and `production_activated` from the live
gates. Use `qualified_subpaths` as the activation authority: a staged still
candidate does not enable GPU stills while `still` is absent. Existing
`preview` and `direct_sequence` support remains equirectangular PNG/RGB only.
When `still` is advertised, native PNG still processing supports 2:1
equirectangular output, square `fulldome` and `fulldome_angular`, and both
Dome laws with `preserve_360:true`. Explicit still subpaths distinguish those
five domains. Native still resolve requires the continuous effective ratio
`ceil(height * supersampling) / height <= 2`; higher valid SS preserves the
requested quality through the CPU stream. Dimensions and SS are not reduced.
Preserve-360 retains the canonical 2:1 physical panorama on GPU only when its
texture, mapped band, postpass, resources and helper memory fit the observed
device limits and available memory. Unknown capacity, an oversized source or
nonresident request chooses the CPU mapper before source evaluation. Native
mapping uses the same pose, longitude wrap, latitude clamp and sanitized
associated-alpha bilinear rule as the CPU mapper; source pixels are evaluated
once. Dome/Preserve Preview and Sequence, JPG, history and EXR remain CPU paths.
Runtime identity and the completed execution receipt still decide what actually
ran; eligible geometry and static policy support alone cannot prove GPU work.
While native selection is pending, Preview, direct Sequence and still output
publish no execution (`raster_execution` null). The immediate 5-key CPU receipt
is `forced_cpu` for an explicit CPU request and `gpu_unqualified` for an excluded
automatic job, including a late still resident-capacity refusal. That refusal
emits its receipt before CPU source rendering and does not submit another job.
The closed 8-key receipt appears after the resident stream runs or falls
back. Its `actual_processing` is `retained_native`,
`retained_native_with_cpu_repair`, or `cpu` with reason `dense_cpu_fallback`
or `cpu_fallback`. A native pair may set both flags true only for an admitted
qualified job. A CPU outcome keeps both flags false. An `actual_processing`
of `gpu` or any extra key is not evidence. The retained-source postpass maximum is 1/255 RGB; it does not measure
projection agreement or establish successful saved-image publication.
Compression does not change RGB Preview identity; processing does. Progress,
Stop, Continue and unknown-outcome recovery keep the same original native IDs.

For Shader still preflight, `shader-raster-still/1` output chooses projection,
`encoding:"png"|"jpg"`, exact `output_path` and native geometry. Equirectangular
widths1024/2048/4096 have half-height; Dome uses native diameter/FOV/pose. Raster
JPEG quality is fixed95. Raster stills accept checked custom 2:1 sizes or square Dome diameters and optional finite supersampling ≥1. Read model-derived dimensions and admission constraints from discovery; presets are conveniences. EXR uses its separately advertised float-processing limits.
`shader-linear-rgba-exr/1` uses width/height and optional native Dome projection/
pose; it remains scene-linear float/alpha. `png-master/1` keeps its existing
supported sizes/supersampling/import behavior. Still preflight's optional boolean
`allow_unpreviewed_revision` is an explicit native confirmation, never a fabricated
preview or a bypass of the mounted capture producer's readiness/currentness.

Native status is a bounded snapshot: committed saved count may exceed contiguous
cursor; checking/replay is separate work; timing is observed, not a proxy ETA.
Last-reported restart counts are unverified until accepted Continue checks them.
Stop carries the observed run ID and settles only after its owner drains.

### Preserve the 360° appearance in Shader dome output

Discover `native_render.shader_dome_preservation` before sending this option.
For either Shader dome projection, set `preserve_360:true` and
`preserve_360_profile:"shader-dome-from-360/1"` on the output object. The same
setting applies to native preview, raster/linear EXR stills, and sequences.
Equirectangular output has no preservation field. Missing means the historical
direct dome path; explicit false selects that path. Continue and recovery use
their original frozen mode/profile, never a new default or request ID.

Preservation first renders a complete canonical 2:1 panorama (logical 2D×D for
dome diameter D), then maps its completed scene-linear pixels to the dome.
Bilinear filtering wraps longitude, clamps latitude and interpolates associated
alpha. PNG/JPG keep opaque display output; EXR keeps associated scene-linear
HDR and transparent black outside the disk. Computation and render time
increase. Stateless preview/sequences use their selected supersampling; native
stills keep 1×. Stateful rendering keeps existing source-size/replay limits
and 1× supersampling (accumulation/separate feedback: D=1024, ≤240 frames).
Unsupported capacity is refused; no silent downscale or direct fallback occurs.
Use the existing status, cancellation and original-request recovery tools.

## Library Duplicate

`shader_duplicate_asset` copies one exact saved Shader into My Library or the writable active Project. Built-ins are not a destination. A saved receipt reports `placement` as `placed` or `unavailable` and the copy as `shader` with `origin` and `shaderId`, plus the revision and hashes. `shader.origin` is the acknowledged shelf, and the receipt has no title field. Workshop keeps the copy title in its own confirmation; a missing or unavailable placement confirms that title and shelf without opening or selecting the copy. Replay and status use the original request ID and return the same created identity, including a known refusal; they do not create a second copy.

## Separate Shader workspace format

Mounted Shader parameter controls are live session values, not Workflow fields, workspace source edits, or proof of a Saved document. `get_shader_parameters` returns the current source-free descriptor, exact witness and native `writable` state. With MCP enabled, `set_shader_parameter` submits one exact-witness value using `operation:"submit"` and a caller-known `client_request_id`; APP validates the current bounds, writable state and writer before one undoable edit. `applied` acknowledges that edit only. Verify Save separately through the exact clean saved revision/hash. If the result is uncertain, use `operation:"status"` with the original request ID, including after selection changes. An absent or expired receipt remains unknown; read fresh metadata and obtain human direction before any new ID. Never retry automatically. Source/formula include options select content independently; structural edits use the acknowledged workspace and native Apply/Save receipts.

`authoring.json` is **not** a `.hextile.json` Workflow. The current document schema 4 / `workspace_schema:2` Project Shader stores metadata/config and complete path inventories in `workspace/authoring.json`; root `workspace/source.glsl` and arbitrary declared relative `.glsl` helpers hold the actual code. No GLSL bodies belong in durable JSON. The ordered full source set, including unused helpers, and declared Looks/provenance are raw-byte registered using the v2 digest returned in APP open instructions; resources/originals are verified separately. Use only the acknowledged complete-set v2 digest or serialize transient `source_modules` API text into the portable manifest. `source-modules/1` must be executable on the running APP before promising compilation, independently of format negotiation. See the installed `360-hextile` skill and https://360hextile.com/docs/create/shader.

## Saved Sequence upscale

When `get_capabilities` advertises `sequence_upscale.scope_witness_version: 1`, `inspect_sequence_upscale` checks a saved source and returns an opaque scope witness. `upscale_sequence` submits that witness, a caller-owned UUID, scale 2 or 4 and optional name to the native operation. The source stays intact. A lost submission reply is resolved with `get_sequence_upscale_request` and the same UUID; do not generate another request. Use bounded `get_sequence` and `list_sequence_frames` reads and the accepted run ID for Stop, Resume and retry. No per-frame workflow loop or private source manifest is needed.

The original-request receipt retains the opaque scope witness, source ID, requested name and scale for scope-based requests, so the same body can be recovered after a restart. A `reserved` or `interrupted` receipt without a run ID is a reservation awaiting repair. Replay `upscale_sequence` with the same UUID and the same source, scope witness, scale and name; do not navigate to the child until that replay returns its recovered run. This repairs ownership without automatically starting GPU work.


Scene-linear EXR supersampling uses the same strict CPU float resolve for native and WebGL raw-float source data. It clips alpha and associates RGB once in float32, accumulates area weights in float64, and writes FLOAT/ZIP without sRGB, background, unpremultiplication or 8-bit conversion. Both Dome laws retain transparent physical/logical rims and Preserve 360 reprojection. Omitted/1× keeps the existing path. Read the advertised format, resource and working-set constraints; history retains its 1× rule. GPU float resolve is not enabled by this contract.


## Shader workspace authoring protocol

Before attaching or editing source, use the installed Shader skill and its
`references/authoring.md`, then follow the acknowledged APP instructions.

Discover the three workspace tools via MCP tools/list; get_capabilities remains the APP workflow handshake. Read get_live_context.current_surface and bind its actual document and writer identity. Current authoring requires workspace_schema:2 for the complete portable manifest; the client sends 2 when omitted, with no older-format fallback. V2 returns server-owned saved/unaccepted base, root and ordered source paths; preserve these exact identities. Use strict UTF-8 confined relative GLSL paths (<=256 UTF-8 bytes), no .git, native/absolute paths or escapes. Declare every source in authoring.json: <=32 GLSL files, <=64 KiB aggregate raw and expanded source, include depth <=16. V2 registers the full declared set, including unused modules, Looks and provenance: follow APP's raw-byte v2 digest instructions. Use only the complete-set v2 digest. Originals/resources are verified separately; unlisted files confer nothing. get_shader_update include_source_diagnostics:true requests bounded logical locations for the current writer, witness and candidate. Omitted/false keeps the source-free legacy receipt. Missing support requires upgrade/reconnect, never downgrade. Workspace schema 2 is format support; source-modules/1 execution requires APP available and executable_capabilities. frame-accumulation/1 is executable only when listed in executable_capabilities. Author extensions.frame_accumulation as {schema:1, prior_frame_binding:"hxPriorColor", decay_parameter:"trail_decay"} plus sorted required capability frame-accumulation/1, and sample hxPriorColor at hx.mapUv. Do not author it when the id is absent. Do not add a get_capabilities flag, a pass graph, a history file, or a new tool. Replay from the start, at most 240 frames, full frame at most 2048×1024. Recognized capabilities, guide text and version numbers do not prove execution or installed host filesystem access. Open requires a clean Project or My Library Shader and its actual current private writer. Only acknowledged open returns files after APP acquires the mounted readonly/autosave hold. Edit only declared current members: root/helpers stay within the 64 KiB raw/expanded source bounds; metadata remains bounded to 2 MiB. Preserve the closed metadata inventory and raw member bytes. Register automatically checks the frozen candidate; it never wakes idle intelligence and never synthesizes Apply. Poll prepare/compile/preview/presentation/save, attachment_state, check_attempt and candidate-bound diagnostics; prepare success is not compile proof or a save. Native Apply in Workshop advances the accepted base after its exact acknowledgement. APP Retry rechecks the same candidate; a native-file repair uses a fresh canonical change_id. After a lost open reply, make at most one identical open request with the same surface, witness, Shader, saved hashes/revision and optional adoption digest; changed authority requires rediscovery. Never infer attachment from a notice or timeout. 410 means workspace/receipt expired: preserve files, rediscover and reopen; never recreate successful receipts. Existing divergent files require explicit existing_workspace adoption of the reported exact digest. APP owns eight handles, one attachment, eight receipts per handle, one current complete candidate, a 300-second idle TTL and an aggregate 8 MiB workspace-copy budget; this proxy has no workspace cache or scheduler. For Playable Shaders, read recipes and best-practices plus acknowledged closed conventions/1 instructions. Pass through APP ABI/conventions instructions, available and executable_capabilities; observe execution_ready independently of the current document declaration. Check conventions/1 and modulation/2 separately. For schema-2 expression edits check parameter-expressions/1, shader-timeline/1 and admitted modulation/3 separately. Discover control_shader_timeline through tools/list; current_surface owner generations are opaque witness, and known client_request_id status recovers uncertain control replies without a new action. Session playback does not save: propose_shader set_timeline edits document start/end/loop through native Apply. Author Enter -> default-0 logical gate -> schema-2 oneshot BLAST (20 ms Linear Attack, 400 ms Ease Out Release, exponent 2) -> Range -> declared Glow parameter and GLSL effect as one complete candidate, with the default Master Clock and sorted sidecar declarations. Camera helpers are vec3 hxCameraPosition, mat3 hxCameraRotation, vec3 hxCameraDirection(vec3 canonicalDirection); camera:null is identity. Fly GLSL must use ro=hxCameraPosition and rd=hxCameraDirection(hx.direction). Schema-2 modulation envelopes target stable typed logical input IDs shared with future INPUT session bindings. Portable conventions/1 sources remain keyboard/mouse. MIDI/OSC/gamepad adapters are future/unsupported unless APP reports their availability; executable capabilities or keyboard bindings do not prove adapter availability. Do not author source IDs, packets or live events or invent workspace flags in get_capabilities. Source candidate authoring never arms Interact, presses keys, changes live pose, writes Project presets or self Applies. For an explicitly requested Project convention change, discover shader_get_project_conventions and shader_set_project_conventions; use the native writer with the current Project witness and exact digest. A shortcut conflict requires an explicit remap proposal, not a compiler-failure claim or Hotkeys override. Saved Shader native sequences use preflight_shader_sequence, render_shader_sequence, then get_shader_sequence with the preflight-known deterministic ID and matching request_hash. Require confirmed native Apply and its saved revision/hash, explicit deferred publication_mode, exact rational interval/frame count and explicit native output. A lost render reply is recovered by GET of that same ID; a missing ID leaves the outcome unknown. After verified native masters, preflight_shader_sequence_export and export_shader_sequence use an explicitly chosen existing local folder, PNG or JPG, and the preflight fingerprint. Deferred masters are PNG; EXR is available through direct render_shader_sequence folder_export only. Recover an uncertain export through get_shader_sequence and its known attempt_id; never blindly repost. control_shader_sequence stops/resumes native work or cancels/retries the exact current export attempt. Generic create_sequence/start_sequence remain folder upres.


Workspace refusals carry bounded `accepted`, `files_preserved`,
`retry_unchanged`, `fields`, `next_action` and `recovery` details. Do not retry unchanged bytes
when `retry_unchanged:false`. `original_binding_legacy` uses `copy_and_replay`:
preserve pending edits, create an authorized native copy, and replay edits into its
acknowledged workspace while keeping its new identity and corrected provenance.
Rehash the complete resulting workspace. `original_binding_invalid` uses
`restore_original`: restore verified original material or matching metadata;
do not delete protected bindings to bypass the check. Follow the installed Shader
skill's recovery procedure. These refusals precede candidate admission.

Shader sequence recovery requires
`native_render.sequences.shader.recovery.profile:"shader-sequence-recovery/1"`.
Inspect the destination first. `counts_verified:false` means saved counts are last
reported; native Resume verifies journal-backed files before reuse. Setting
`differences` are bounded public values. `saved_settings` contains a
`saved_sequence:{sequence_id,recipe_hash}` selector and reusable render controls;
it omits the private destination, witness, request key, live capture and name.
Retain the original chosen folder locally and supply the current Project witness,
a caller-owned name and request key when constructing the exact request. Reapply
the returned folder encoding to that same chosen destination.

Use saved render settings selects the checked frozen source/resources and opaque
inputs without replacing or saving authoring. For a preview, keep the current
mounted owner/base/edit identity and send the `saved_sequence` selector with
`mode:"sequence"`, explicit output geometry, supersampling and exact
`sequence_sample`. The APP obtains the original seed/capture from the owned
recipe. Dirty authoring remains untouched and needs no new live-frame capture.
Observe/release that native inspector by its original request ID. Continue uses
the same frozen selector, exact render controls and fresh inspection fingerprint.
A changed selector, recipe or output refuses; IDs alone never grant authority.

Start over means rendering from frame zero with the displayed request. Confirm
the chosen destination and affected owned output with the user before sending
`control_shader_sequence(action="start_over",sequence_id=<old>,request=...,
inspection_fingerprint=...,confirmed=true)`. Only owned direct generated output
supports replacement; legacy output advertises
`sequence_replacement_legacy_unsupported`. Native replacement archives the old
owned generation recoverably and preserves unrelated files; the response contains
a new `sequence_id` and `replaced_sequence_id`. Do not use a folder-deletion tool.
On a lost reply, recover by replaying the identical original Start-over
POST/body/key/fingerprint against the original ID, then observe the returned new
ID. After restart, `sequence_replacement_pending` exposes a bounded `replacement`
reference (old/new IDs, request hash and phase) and `recover_start_over:true`. Use
`control_shader_sequence(action="recover_start_over",sequence_id=<old>,
new_sequence_id=<observed new>,destination_folder=<same chosen folder>,
project_context_witness=<current>,confirmed=true)` to resume that exact retained
transaction. The native owner loads the original request locally; its private
request body never enters MCP results. Never mint a new key or inspect a new body to
restart an unfinished replacement. The short archive transaction settles
atomically or remains recoverable, so it has no mid-move cancellation; after new
render admission, use normal native status and Stop with its observed `run_id`.

### Shader code lease and the human document

MCP holds code only when discovery includes `shader_contract.code_lease` for `shader-code-lease/1`: `code_body`, modules and file inventory, with composition authority `registered-candidate/1`. The human may edit and Save valid parameter definitions (minimum, maximum, default and type), values, modulators, mappings, expressions, BPM and ordinary document fields without Take control. A missing `code_lease` or `human_document` means coauthoring support is unknown. It does not permit concurrent document replacement, and legacy source-only workspace behavior remains only where that older peer still supports it.

Workspace bytes can lag the accepted human header and document. Do not rewrite them from a summary. Read the current accepted base, `human_document.version` and the summary first. That version is the same native `value_version`, not a second clock. The summary's eight `changed` arrays hold at most 16 IDs total. `omitted` counts IDs not shown. The summary carries no source, formulas, resource paths or private authority, and it is not a permanent history or a rollback. B is the acknowledged authoring baseline before divergence. H is the latest accepted CAS base. Frozen candidate C stays immutable. Final composition F is checked against the latest H. Human ABA intent wins a stale proposal. Compatible agent additions survive. A named conflict preserves the work; there is no retry loop and no blanket takeover.

Attachment status and `get_shader_update` may include optional `human_document`. Preserve it through clients. `get_shader_update` can also contain `publication` alongside the immutable original candidate and check. Its `composition_id`, `value_version`, `prepare_identity`, compile, preview, presentation, save and saved revision/hashes describe final F. Original Prepare stays `failed` or `not_requested` when it did not succeed. A `registered:` plus candidate id marker is not an external tool ticket and is not proof of original Prepare success. F still requires a returned `spt_` ticket and its own Prepare, compile, preview and consume. Original and final publication identities stay distinct. Preview published does not mean presentation shown. Source, check, preview, shown and Save stay distinct. This summary is not implementation acceptance and not a commercial-ownership claim. Resolve listed incompatible IDs without discarding the human edit. Recover unknown writes by the original update and request IDs; do not blindly retry or re-register. An adopted workspace after lost attachment history can require recovery when its stale document cannot be distinguished from intentional edits. Stop cancels the attachment. It does not take code possession. Take control stays explicit.
