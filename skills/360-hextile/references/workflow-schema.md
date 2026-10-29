# Workflow schema (agent)

Enabling MCP fully trusts the connected agent; `get_local_access_status` reports the connection state. APP binds its actual current document writer without Follow, session selection or separate source/formula/capture grants. Include options select bounded content, and task paths select destinations. Native witnesses, validation, ownership, revision conflicts and original-request reconciliation still apply. Read the live `shader_contract` and its blockers before authoring; APP automatically Applies and saves singular ready Shader candidates through the native writer. Compilation alone is not a Save receipt. The MCP host retains its own filesystem, execution and desktop permissions.

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

Full-quality Shader inspection advertises `native_render.shader_preview.profile`
`shader-export-preview/2`. `shader_request_preview` adds required `mode:"still"|
"sequence"`, `width`, `height` to its saved mounted-owner request; `output` retains
projection/framing and optional hundredth `supersampling`. Sequence requires
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
`supersampling`1.00–2.00. Direct output carries
`folder_export:{destination_folder,format:"PNG"|"JPG",quality_if_jpg}`; JPG requires
quality1–100 and PNG uses null/omission. Explicit `publication_mode:"deferred"`
omits that folder and retains separate native-master publication tools. Fractal
remains deferred, with saved scene/revision, native quality preset and optional
`destination_intent`; it has no sequence supersampling field.

Inspection takes `{request}` for Shader and `{request,destination}` for Fractal.
The existing control tool's `continue` action adds `inspection_fingerprint` and
the same immutable request. The fingerprint is an optimistic check, never source
or write authority. Keep original request/job/run/attempt IDs on uncertain replies.

For Shader still preflight, `shader-raster-still/1` output chooses projection,
`encoding:"png"|"jpg"`, exact `output_path` and native geometry. Equirectangular
widths1024/2048/4096 have half-height; Dome uses native diameter/FOV/pose. Raster
JPEG quality is fixed95, with no still supersampling or arbitrary raster sizes.
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

`authoring.json` is **not** a `.hextile.json` Workflow. A negotiated `workspace_schema:2` Project Shader stores metadata/config and complete path inventories in `workspace/authoring.json`; root `workspace/source.glsl` and arbitrary declared relative `.glsl` helpers hold the actual code. No GLSL bodies belong in durable JSON. The ordered full source set, including unused helpers, and declared Looks/provenance are raw-byte registered using the v2 digest returned in APP open instructions; resources/originals are verified separately. Do not use the v1 source/authoring pair digest for v2 or serialize transient `source_modules` API text into the portable manifest. `source-modules/1` must be executable on the running APP before promising compilation, independently of format negotiation. See the installed `360-hextile` skill and https://360hextile.com/docs/create/shader.
