# Workflow schema (agent)

Enabling MCP fully trusts the connected agent; `get_local_access_status` reports the connection state. APP binds its actual current document writer without Follow, session selection or separate source/formula/capture grants. Include options select bounded content, and task paths select destinations. Native witnesses, validation, ownership, revision conflicts and original-request reconciliation still apply. Shader package edits use shader_edit or register_shader_update. Read merge. Watch compile. Only the human moves the lease. Compilation alone is not a saved package. The MCP host retains its own filesystem, execution and desktop permissions.

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
An old sequence may refuse Continue with `shader_source_format_retired` when its
frozen source uses the retired format, or `shader_source_unavailable` when the
frozen source cannot be read. Read, list and delete still work; start a new
render instead of retrying Continue with altered source.


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

## Shader package

Mounted Shader parameter controls are live session values, not Workflow fields and not proof of a saved package. `get_shader_parameters` returns the current source-free descriptor, exact witness and native `writable` state. Structural edits use `shader_edit`.

`shader.json` is not a `.hextile.json` Workflow. It holds the authored data. `source.glsl` and `modules/**/*.glsl` hold the code. No GLSL bodies belong in durable JSON. Include unused helpers. `shader.json` is at most 2 MiB. GLSL is at most 64 KiB in total, with at most 31 modules plus the entry, include depth at most 16, and a path of at most 256 bytes. Register saves. Read merge. Watch compile. See the installed `shader` skill and https://360hextile.com/docs/create/shader.

## Saved Sequence upscale

When `get_capabilities` advertises `sequence_upscale.scope_witness_version: 1`, `inspect_sequence_upscale` checks a saved source and returns an opaque scope witness. `upscale_sequence` submits that witness, a caller-owned UUID, scale 2 or 4 and optional name to the native operation. The source stays intact. A lost submission reply is resolved with `get_sequence_upscale_request` and the same UUID; do not generate another request. Use bounded `get_sequence` and `list_sequence_frames` reads and the accepted run ID for Stop, Resume and retry. No per-frame workflow loop or private source manifest is needed.

The original-request receipt retains the opaque scope witness, source ID, requested name and scale for scope-based requests, so the same body can be recovered after a restart. A `reserved` or `interrupted` receipt without a run ID is a reservation awaiting repair. Replay `upscale_sequence` with the same UUID and the same source, scope witness, scale and name; do not navigate to the child until that replay returns its recovered run. This repairs ownership without automatically starting GPU work.


Scene-linear EXR supersampling uses the same strict CPU float resolve for native and WebGL raw-float source data. It clips alpha and associates RGB once in float32, accumulates area weights in float64, and writes FLOAT/ZIP without sRGB, background, unpremultiplication or 8-bit conversion. Both Dome laws retain transparent physical/logical rims and Preserve 360 reprojection. Omitted/1× keeps the existing path. Read the advertised format, resource and working-set constraints; history retains its 1× rule. GPU float resolve is not enabled by this contract.


## Shader package edits

Before editing, use the installed Shader skill and its `references/authoring.md`.

`open_shader_workspace` takes `shader_id` and `request_id` only and returns the lease, commit and revision. `shader_edit` sends set, create, reshape or delete on one address, plus `seen` and `lease` when the edit needs them. `register_shader_update` sends the package digest and saves. Read merge. Watch compile. Prepare failure is `prepare: failed` plus diagnostics. A repair uses a new request id. The same request id returns the recorded result.

For Playable Shaders, read recipes and best-practices. `conventions/1` and `modulation/2` name the fly camera and the envelope recipe. Read `available` and `executable_capabilities`, and observe `execution_ready` independently of the saved package. Camera helpers are `vec3 hxCameraPosition`, `mat3 hxCameraRotation`, `vec3 hxCameraDirection(vec3 canonicalDirection)`. A null camera is identity. Fly GLSL uses `ro=hxCameraPosition` and `rd=hxCameraDirection(hx.direction)`. Portable conventions/1 sources remain keyboard/mouse. MIDI/OSC/gamepad adapters stay unsupported unless APP reports them. Control authoring never arms Interact, presses keys, changes live pose or writes Project presets. `frame-accumulation/1` is executable only when listed in `executable_capabilities`. Do not add a pass graph, a history file, or a new tool.

Saved Shader sequences still use `preflight_shader_sequence`, `render_shader_sequence` and `get_shader_sequence` on the saved revision. A lost render reply is recovered by that same id.

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

### Shader code lease

The lease is `{holder, generation}`. `holder` is `human` or `agent`. Only the human moves the lease, with Take control or Hand back. No MCP tool moves the lease. A `stale_lease` result means the lease moved. While the human holds the code, register is refused: the human holds the code and can hand it back. Hand the code back, then register again.

Send `seen` as `{address, human}` for every unit a human has edited. A `lost_to_human` row kept their value and returns the new number. Resend a lost register unit with `shader_edit` and that pair only if you still mean it. Stop cancels work. It does not move the lease.
