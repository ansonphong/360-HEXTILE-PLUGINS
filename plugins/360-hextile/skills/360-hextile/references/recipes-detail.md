# Recipes: detail

Index with placeholders (`W`, `B`, `S`, `U`, `L`) and the common one-liners: `get_guide(name="recipes")`.

## More Shader one-liners

- Attach an image input → `shader_stage_resource` (Shader on screen, else 403 `authority`), then `shader_set_resource` `action:"attach"`, `slot_id:"input1"` with `W` and `B`. The slot needs no creation step; `shader_edit` create on `["inputs","input1"]` fails.
- Modulator, driver, controls channel or binding → `create` on `["modulators","mod_<24 hex>"]` (`["modulators","wave1"]` is 400 `invalid_address`), `["drivers","<param>"]`, `["controls","channels","<id>"]` (Recipes I and J). On a Shader with no `controls`, a channel alone is 400 `invalid_value`; send one batch in this order: `set ["controls","camera"]` null; `set ["controls","profile"]` `{"id":"x/1","revision":1,"label":"X"}`; `set ["controls","instructions"]` text; `create` the channel; `create` the modulator.
- Suggest credits → `shader_get_credits {"shader":S,"project_context_witness":W}` (on screen; 403 off screen) for `provenance_hash`, then `shader_propose_credits` — a person applies it.
- Put another Shader on screen → `shader_open_asset {"project_context_witness":W,"request_id":U,"target":{"origin":"user","shaderId":"<id>"},"shader":S_current,"studio_surface_id":"<sid>"}`, then `shader_get_operation {"request_id":U,"project_context_witness":W,"scope":"asset","shader":S_current}` — the user is asked; never retry a dismissed request. Not needed to edit (off-screen Shaders need no `get_live_context` before `shader_edit`; only on-screen work does).
- Check the MCP build and render contract → `get_capabilities {}`.
- Read a Shader's parameter help, labels or GLSL when it is not on screen → `shader_get_asset_state {..,"include":["parameters","source"]}` (see the index).

## Shader library

- To change the ID and folder name → `shader_change_id {"shader":S,"project_context_witness":W,"request_id":U,"base":B,"new_shader_id":"new_id"}` for My Library. Check the returned `shader_id` and use it for later edits. Saved sequences can still refer to the former ID. A lost reply can be checked with `shader_get_operation` using `scope:"asset"`, the original Shader ref and the original request ID. An identical retry in the same Project recovers the original result.

- To duplicate → `shader_duplicate_asset {"request_id":U,"project_context_witness":W,"shader":S,"base":B,"destination_origin":"user","title":"Copy"}` — returns the new `shaderId`; the copy is not opened.
- To rename (Library title) → `shader_rename_asset {"shader":S,"project_context_witness":W,"request_id":U,"base":B,"title":"New"}` (`base` required here; owner fields filled) — `origin:"user"` only; the id does not change. Look rename needs only `name` (or `look_id`) plus `title`; Look delete only `name` (or `look_id`); no base or confirmation scope.
- To delete → `shader_delete_asset {"shader":S,"project_context_witness":W,"request_id":U,"base":B,<saved-shelf fields, operation "delete">}` — `origin:"user"` only.
- To export a .hexshader → `shader_export_bundle {"shader":S,"project_context_witness":W,"studio_surface_id":"<sid>","request_id":U,"base":B,"expected_looks":[..from shader_get_looks..],"expected_provenance_hash":"<from shader_get_credits>","output_path":"<abs>"}` — on screen only, My Library only (`shader_get_credits` is 403 off screen, so there is no hash); `expected_looks` is `[]` with no Looks.
- Create, paste and fork replies return a saved receipt with the new `base`; if the reply is lost, `shader_get_operation` with `scope:"creation"` and the request id finds it. Writes whose reply is lost recover via `scope:"asset"` (a restore replay with the same id is a 409 `request_conflict`).
- To make a new Shader → `shader_create_asset {"request_id":U,"project_context_witness":W,"action":"new","template_id":"hx_starter","space":"direction_360","title":"T"}`. Omit `title` for `Untitled Shader`. To create from GLSL, use `"action":"paste","source":"<GLSL>","title":"T"`.
- To Save As → `shader_save_as {"shader":S,"project_context_witness":W,"studio_surface_id":"<sid>","request_id":U,"title":"Copy"}` — on screen. It replies `pending` and the Workshop switches to the copy. `shader_get_operation` may say unknown or 404 even though the copy exists: confirm with `shader_list_assets`. To go back use `shader_open_asset` (asks the user).
- To fork a revision → `shader_fork_asset {"shader":S,"project_context_witness":W,"request_id":U,"action":"fork","expected_document_hash":".."}` (schema only).
- To copy a revision as a new Shader (random id) → `shader_copy_revision {"shader":S,"project_context_witness":W,"request_id":U,"base":B,"destination_origin":"user","target":{"document_ref":"rev:34","document_hash":".."},"library_intent":"saved","confirmation_scope":{"operation":"shader_copy_revision"}}`; `target` comes from `shader_get_history`.
- To preview history compaction → `shader_history_retention {..,"action":"preview","mode":"current"|"checkpoints"}`.
- To import a bundle → `shader_import_bundle {"request_id":U,"project_context_witness":W,"input_path":"<abs>.hexshader","collision_intent":"fork"}` — the new shaderId comes from the file name, not the title.
- To copy into a Project → `shader_export_to_project {..,"destination_project":"<name>"}` (schema only).
- To move into a folder → `shader_get_library_organization {"project_context_witness":W,"origin":"user"}` for `revision`, then `shader_organize_library {"request_id":U,"project_context_witness":W,"origin":"user","library_session_id":"<UUID>","expected_revision":"<revision>","command":{"kind":"moveShader","shaderId":"<id>","folderId":"<folder>"}}`; `folderId:null` moves it back to the root.

## Playback (on screen, not saved)

- To play, pause or seek → `shader_control_clock {"shader":S,"project_context_witness":W,"request_id":U,"action":"play"|"pause"|"seek","time":2.5}`.
- To step one frame → `shader_step_frame {"shader":S,"project_context_witness":W,"request_id":U,"direction":1}` — `owner` is optional; omit it to step the Shader on screen.
- To read the frame preview → `shader_request_preview {..,"studio_surface_id":"<sid>","request_id":U,"base":B,"mode":"still","width":512,"height":256,"output":{..}}`, then poll `shader_get_preview` with the same `request_id` (a 512x256 frame took ~12 s), then `shader_release_preview`.
- To stop an export → `shader_stop_output_job` with the export `request_id` (U2), not the preflight id. It can return 404 `output_job_unknown` in the first seconds, and small stills finish before a stop lands; a stopped export reports 409 `dome_stopped` on the export call.

## Studio and render extras

- To change the open document's prompt → `apply_config_delta {"config_partial":{"prompt":{"global":".."}},"doc_generation":"<from get_live_context>"}`.
- To make a seed image → `list_360_loras`, `get_seed_memory_advice` (needs `lora_path`, `width`, `height`), `generate_seed`, `get_seed_job` (Recipe B).
- To upscale a still or folder → `run_workflow` builtin `upres-still` (Recipe E); folder or video: Recipe F; saved sequence: `inspect_sequence_upscale` then `upscale_sequence`.
- To describe an image → `describe_image {"source":"render_node","render_id":..,"node_id":..}`.
- To export a render file → `preflight_file_export {"render_id":..,"source_node_id":..,"folder_path":"<abs>","output_name":"x.png","projection":"equirectangular","encoding":"png"}`, then `export_render_file`. `output_name` includes the extension; `source_node_id` is the render row's `head`.
- To list Batch jobs → `list_batches {}` — 409 `batch_unavailable` until Batch is enabled in the APP.


- Read the frame preview → `shader_request_preview`, `shader_get_preview`, `shader_release_preview` (schema only). GPU Doctor → `request_shader_doctor {"request_id":U,"origin":"user","shader_id":"<id>","project_context_witness":W,"studio_surface_id":"<sid>"}` (flat, no `shader` object) then `get_shader_doctor`.

## Fractal (open Fractal first)

All writes copy the `witness` block from `get_fractal_context` unchanged and add a `client_request_id`. `get_fractal_context` replies `Fractal workshop is not mounted.` (503) until a Fractal scene is open; ask the user to open one.

- To see what is open → `get_fractal_context {}`.
- To change a value → `apply_fractal_edits {"client_request_id":"c1","witness":{..},"expected_draft_generation":N,"ops":[{"op":"set_base","target":"<id>","value":0.5}]}`.
- To play, pause or seek → `control_fractal_timeline {"client_request_id":"c2","witness":{..},"action":"seek","time":{"num":"3","den":"1"}}`.
- To save → `save_fractal_scene {"client_request_id":"c3","witness":{..},"mode":"save_as","target_scene_id":"scn_<8hex>"}`.
- To capture a still → `capture_fractal_still`, then `preflight_file_export` and `export_render_file`.
- To render a sequence → `preflight_fractal_sequence` then `render_fractal_sequence`.

## Library, settings, docs

- To list renders → `list_runs {}` returns 20 rows; pass `data.next_cursor` as `cursor` (and `limit` up to 100) for more; prompts → `search_library_prompts {"query":"neon"}`; sequences → `list_sequences {}`.
- To rename, favorite, duplicate or trash a render → `call_hextile_api {"method":"PATCH","path":"/api/renders/<id>/name","body":{"name":".."}}`, `POST /api/renders/<id>/favorite`, `POST /api/renders/<id>/duplicate`, `DELETE /api/renders/<id>` (schema only).
- To export to Unreal → `get_unreal_export_catalog`, `preflight_unreal_export`, `export_to_unreal_project`.
- To read app preferences → `get_app_preferences {}`; change → `update_app_preferences {"changes":{..}}`; MCP status → `get_local_access_status {}`.
- To list hotkeys → `list_hotkeys {}`; write → `set_hotkey_bindings {"id":..,"bindings":[..],"revision":N}` after a fresh read.
- To see storage, cache, GPU, models, license → `get_storage_summary`, `get_cache_buckets`, `get_gpu_diagnostics` (slow, ~30 s), `get_model_readiness`, `list_installed_models {"pipeline_id":"flux"}`, `get_license_status`.
- To read a guide or the docs → `get_guide {"name":"recipes"}` (names: `workflow-schema`, `best-practices`, `website-index`, `recipes`, `recipes-detail`, `shader-cookbook`, `index`); `search_docs {"query":".."}` then `read_doc`.

## No tool yet

Set or clear a Shader cover; New Shader "From an image"; save the human's unsaved Workshop draft; list personal Library tag ids (ask the user for `shader_set_tags`); rename or delete a Built-in or Project Shader; list saved Fractal scenes; switch or create Projects (`call_hextile_api` only).

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

## Shader scalar expression and timeline

Edit values, clock and timeline with the `shader_edit` addresses in the index above; each accepted batch autosaves. Read each outcome before rendering. Playback (`shader_control_clock`, `shader_step_frame`) does not save; changing `bpm`, `speed`, `start`, `end` or `loop` is a saved edit.

## Shader Audio

Audio turns a sound, MIDI, CSV or label file into signals that drive a saved Shader. Use the tools only when the running APP's `get_capabilities` has `audio_signals` with `contract` `audio-signals/1` and `available:true` and the host's `tools/list` shows them; a source checkout does not activate an installed host. `audio_signals` also lists `operations.tools`, `edit_commands`, `bounds`, `read_budgets`, `resources` and `supported_track_limit`.

1. **Owner.** `shader_get_audio {"shader":S,"project_context_witness":W,"selector":"tracks"}` returns `owner` (`O`), `provenance` (`saved` or `mounted`) and `base`. Pass `O` unchanged to every preparation and edit. After each edit read `shader_get_audio` again for the next `O`; `stale_owner` means it moved. Pages hold 1 to 50 rows: follow `next_cursor` until null; 409 `page_changed` or 422 `invalid_cursor` means read again without `cursor`. Rows are source-free: no paths, media, curves or leases.
2. **Import.** `audio_prepare_resource {"request_id":U,"owner":O,"source":{"kind":"local_file","path":"<abs>"}}`, or `{"kind":"retained","resource_id":"audio_<24 hex>"}` to reuse a resource the Shader already holds. Audio is `.wav`, `.flac` or `.mp3`. Data files are MIDI `.mid` (notes only), CSV time/value curves `.csv` and Audacity labels `.txt`. Data times are seconds only (MIDI tempo becomes exact seconds; the Shader BPM never applies). Exact size and duration bounds are in `audio_signals.resources`. Read the receipt with `audio_get_preparation {"receipt":"<receipt_id or original request_id>","wait_s":25}`; states are `pending`, `ready`, `error` and `cancelled`, and `pending` is never a ready zero.
3. **Attach.** `shader_edit_audio` `{"command":"attach_track","receipt_id":"<ready resource receipt_id>","timeline_start":{"num":"0","den":"1"}}`. An audio track may add `in_sample` and `out_sample` together; a data track takes placement only. The reply `receipt` names `track_id`. At most `supported_track_limit` (4) audio tracks: one more refuses `supported_track_limit`; data tracks are not counted. `set_track` moves a track (`timeline_start`; audio tracks may also send `in_sample`, `out_sample`, `monitor_gain` 0..1 and `monitor_mute` together). Monitor gain and mute change listening only, never analysis or visuals. `replace_track` swaps in a ready resource of the same kind with reviewed timing; a kind change refuses. `remove_track` needs the exact `dependent_ids` from `shader_get_audio`.
4. **Prepare a signal.** `audio_prepare_signal {"request_id":U,"owner":O,"demand_id":U2,"signal_spec":{..}}`. The spec is `id` (a new `signal_<24 hex>`), `track_id`, `measurement`, `gain` 0..100, `attack` and `release` 0..60 s, `normalization` `fixed_full_scale` and optional `offset_ms`. Measurements: audio `{"kind":"rms","profile_id":"hann2048-hop512/1"}` or `{"kind":"band","profile_id":"hann2048-hop512/1","low_hz":40,"high_hz":120}`; MIDI `{"kind":"midi_notes","filter":"all"|"note"|"range",..,"value":"trigger"|"gate"|"velocity"}` (`pitch`, or `pitch_low`/`pitch_high`); CSV `{"kind":"curve","column":1,"interpolation":"linear"|"step","input_min":0,"input_max":1}`; labels `{"kind":"labels","mode":"trigger"|"hold","text":null}`. Preparation starts the file analysis itself: wait on `audio_get_preparation` with `wait_s:25` and read `progress`; there is no separate analyze step. A MIDI trigger fires on note events; it is not beat detection. The ready receipt's `result.curve_handle` reads values: `audio_read_signal {"owner":O,"curve_handle":"..","selector":{"kind":"window","start":{"num":"0","den":"1"},"end":{"num":"4","den":"1"},"max_samples":128}}` (or `{"kind":"time","time":..}`).
5. **Create.** `create_signal` `{"receipt_id":"<ready signal receipt_id>","alias":"kick","label":"Kick","output_min":0,"output_max":1}` adds the signal and its sampled modulator; the reply `receipt` lists `signal_ids`, `modulator_ids` and `aliases`. For a set, `shader_get_audio {..,"selector":"set_suggestion","track_id":".."}` proposes four signals with aliases `<L>`, `<L>1`, `<L>2`, `<L>3` (L is the track's lane letter, A for the first) checked against every alias in the Shader. Prepare each `proposals[].signal_spec` under its own `request_id` and `demand_id`, then send one `create_set` with four `{receipt_id, alias, label, output_min, output_max}` in proposal order. The set is created whole or not at all: `alias_collision` returns refreshed names in `details`; review them and send again with a new `request_id`.
6. **Map.** Use the existing Shader tools: `shader_edit` `create ["drivers","<param>"]` with `{"kind":"modulator","source":"<modulator_id>","enabled":true,"signature":{..},"mode":"range","min":..,"max":..}` (Recipe J), an `hx-scalar/1` expression bound through the modulator's stable ID, or `uniform float <alias>` in the GLSL. An alias the code still names cannot be removed (`alias_in_code`); drop it from the code first.
7. **Adjust.** `edit_signal {"signal_id":..,"offset_ms":-40}` commits at once: −1000..1000 ms, negative makes the visual lead the sound, visual only, no re-analysis. To change the measurement, prepare the new spec and swap it with its shaping in one atomic `edit_signal` `{"signal_id":..,"receipt_id":..,"modulator_id":..,"label":..,"output_min":..,"output_max":..}`. `remove_signal` needs the exact `dependent_ids`. The preview-only delay between sound and picture is `update_app_preferences {"changes":{"audio_monitor_latency_ms":40}}` (0..500); it never changes a render.
8. **Look.** `audio_read_preview` reads a ready receipt without decoding again: `waveform` (`start_sample`, `end_sample`, `max_points` ≤128), `data` (`start`, `end`, `max_points` ≤128) or `spectrum` (`center_sample`, one 1025-bin row). Spectrum needs `audio_prepare_analysis {"request_id":U,"owner":O,"resource_id":..,"profile_id":"hann2048-hop512/1","demand_id":U2}` ready first. `audio_release_preparation {"receipt":..}` drops your demand; shared work continues for other demands.
9. **Saving.** A saved or off-screen Shader autosaves each accepted edit: `state:"saved"`, `save` and the next `base`. A mounted unsaved draft answers `state:"applied"` with no `save` or `base`; it stays unsaved. While a person works the Audio panel, the Workshop borrows the code lease and hands it back after about 8 s idle; an agent edit meanwhile refuses `stale_lease` with a `next_step`: wait, then retry with the same `request_id`.
10. **Render.** Use the usual `preflight_shader_sequence` and `render_shader_sequence`. Preflight refuses until every enabled signal is ready (`audio_curve_not_ready`: wait on `audio_get_preparation`, then preflight again). Admission freezes the Audio, so later edits do not change that render. `get_shader_sequence {"sequence_id":..,"wait_s":25}` keeps frames and soundtrack apart: `companions` has `state` (`pending`, `partial`, `ready`, `error`), `error`, `revision`, `closure_sha256`, `destination`, `files` (`soundtrack-<track_id>.wav` and `timing.json`, with `published`, `sha256`, `size`), `attempt_id`, `frames_complete`, `retry_allowed` and `publishing`. Complete frames are not full delivery until `companions.state` is `ready`. The wait ends once companions stop publishing. With `retry_allowed:true`, `control_shader_sequence {"sequence_id":..,"action":"retry_companions","closure_sha256":..,"receipt_revision":<companions.revision>,"attempt_id":..,"destination":..}` rewrites only the soundtrack files from the frozen Audio; it never renders or rewrites frames. `shader_get_output_job` reports `companions` the same way.

Recovery: every refusal carries `code`, `message` and `next_step`; `invalid_arguments` names the missing and unknown keys. A lost write reply is `audio_outcome_unknown`: read `audio_get_preparation` with the original `request_id`, or `shader_get_operation {"shader":S,"project_context_witness":W,"scope":"asset","request_id":U}` for an edit, or resend the identical payload with the same `request_id`. Never resend under a new id. `request_expired` means check the current state, then use a new id.

Not available: live or device capture, a mixer, beat detection, MIDI CC or pitch bend, and movie (video plus sound) output, which is planned separately as Shader video output. In-app Automation reads and edits Audio with `shader_get_audio` and `shader_edit_audio` only; importing and preparing files needs an external MCP host.

## Saved Shader native sequence

### Selected-folder Shader PNG/JPG/EXR

After confirmed native Apply and Save, read the fresh source hashes/revision and
Project witness. Require `get_capabilities.native_render.contract:"native-render/1"`
and a native-replayable source. Replace every sample identity below with that
same acknowledged saved source and choose a folder on the APP machine that already exists (a missing folder is named in the refusal).
This example is24FPS over[0,2),48frames, final2048×1024, JPG90 and1.25spatial
supersampling. Use the byte-identical intent for preflight and submit.

For playable camera controls, first use `shader_capture_sequence_input` with the
discovered saved base and mounted surface. Wait for its original
`shader_get_operation(scope="asset")` ticket to apply, then include that request
ID as `input_capture_id` in both requests below. Captures expire after five
minutes before admission. The native recipe retains camera pose and persistent
toggles, neutralizes movement and preserves time animation. Unsupported event
history still refuses. Continue uses its stored snapshot without recapturing;
an uncertain submission must be recovered by its original sequence ID/key.

```json
{"shader_ref":{"origin":"project","id":"aurora"},"project_context_witness":"project-witness","working_revision":2,"document_hash":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","source_hash":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","resource_manifest_hash":null,"selected_resource_frames":[],"idempotency_key":"aurora-direct-001","name":"Aurora direct","frame_rate":{"num":24,"den":1},"frame_count":48,"start_time":{"num":"0","den":"1"},"end_time":{"num":"2","den":"1"},"width":2048,"height":1024,"seed":7,"supersampling":1.25,"output":{"projection":"equirectangular","pan":0,"tilt":0,"roll":0},"folder_export":{"destination_folder":"D:\\Renders\\Aurora","format":"JPG","quality_if_jpg":90}}
```

Fields: `shader_ref` is `{"origin":"user","id":"<shaderId>"}` (the same `origin` and id as `S`); `working_revision`, `document_hash` and `source_hash` are the Shader's `base` fields: send them flat or as one nested `base` object (from `shader_get_asset_state` or the last write reply); `resource_manifest_hash` is null unless the Shader has staged resources. `frame_count` = fps × seconds (24 fps for 1 s = 24, with `end_time` `{"num":"1","den":"1"}`); `idempotency_key` is any new unique string. PNG frames: `"folder_export":{"destination_folder":"<existing abs folder>","format":"PNG","quality_if_jpg":null}`.

`preflight_shader_sequence` returns the known ID/request hash before admission;
`render_shader_sequence` uses that exact body/key. Poll `get_shader_sequence` for
actual owner/run/revision/checking/replay/rendering/writing and saved completion.
No intermediate PNG image sequence or automatic final copy is requested by this
direct flow. For PNG or EXR use that format and null JPG quality. Temporal/input/
resource or supersampling refusals remain native; never silently downgrade.

Still and sequence preflight report the native CPU source policy result and
the available route and codec choices for the requested output on the current
host. Driver compilation happens during rendering. A source-policy refusal
can name the logical Shader file and line. Correct the source and preflight
the new saved revision. If a route is unqualified, read the reason before
deciding whether to select another route and preflight again.

Read `shader_get_output_job` with the original still export request ID and
profile, or use `get_shader_sequence` with the preflight sequence ID and match
the request hash. Report the current state, last confirmed phase, verified
output count or its unknown state, and the next action. A managed sequence
can finish rendering while its folder export fails. A diagnostic ID points
to the local backend log. Use the original handle after a lost reply, poll
the same handle while active, and stop polling a stopped attempt.

For existing output, `inspect_shader_sequence_output({request:<same intent>})`
reports new/unfinished/completed/unavailable/conflict without checking pixels.
Only a matching unfinished result can Continue with the exact request plus its
inspection fingerprint. Keep the accepted continuation receipt after a lost
reply and reconcile that original run; previous terminal status alone cannot
prove the new Continue was rejected. Stop uses the current observed run ID.

### Explicit deferred Shader masters and publication

After the expression or timeline edit, read merge and compile, then read the saved revision. An uncertain edit must be reconciled by its original request ID and confirmed saved revision. Read `shader_get_asset_state` for the **new saved** `shader`, `project_context_witness`, and `base` (`working_revision`, `document_hash`, `source_hash`). Use those actual returned values in place of the sample identities below. The same exact JSON request goes to `preflight_shader_sequence` and `render_shader_sequence`; keep the caller-chosen `idempotency_key` unchanged. The example is 24 FPS over [0,2) seconds, so `frame_count` is 48. This deferred example has no `folder_export` (publication is a separate step below); do not infer a destination or live Dome pose.

```json
{"shader_ref":{"origin":"project","id":"aurora"},"project_context_witness":"project-witness","working_revision":2,"document_hash":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","source_hash":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","idempotency_key":"aurora-native-001","name":"Aurora native","frame_rate":{"num":24,"den":1},"frame_count":48,"start_time":{"num":"0","den":"1"},"end_time":{"num":"2","den":"1"},"width":2048,"height":1024,"seed":7,"output":{"projection":"equirectangular","pan":0,"tilt":0,"roll":0},"publication_mode":"deferred"}
```

Preflight returns `sequence_id`, `status` (`ready` or `existing`), `request_hash` and, for an existing record, `recipe_hash`. Only after that receipt, send the same request to `render_shader_sequence`; it returns the same ID/hash with queued or existing status. Poll `get_shader_sequence({"sequence_id":"<preflight ID>"})` for native progress and its reported terminal outcome. Restart counts remain last reported until explicit verification. If the render reply is lost, GET that **known** ID and compare `request_hash`; a 404 is outcome unknown, not permission to mint a key or blindly repost. The GET projection omits source, formula and private paths, including on older automatic records. An explicitly chosen native square Dome instead uses `width=height=diameter` and `output={"projection":"fulldome","diameter":2048,"fov_deg":180,"pan":0,"tilt":0,"roll":0}`; `fulldome_angular` is the other native projection, and FOV is 10–360 degrees. APP checks operational Standard or Pro access to queue; Lite/unlicensed work refuses. Generic `create_sequence`/`start_sequence` remain folder upres.

Once GET reports `status:"completed"` and `published_cursor==frame_count`, use the exact existing destination_folder task path. The caller supplies the folder path to the local MCP tool; no UI picker or retained private path is exposed by GET. Send the following intent to `preflight_shader_sequence_export` (replace the sample sequence ID and folder with the chosen values). For JPG, use `"format":"JPG","quality_if_jpg":90`; PNG keeps quality null. Deferred PNG masters cannot export EXR; use direct `render_shader_sequence` with `folder_export.format:"EXR"` to render EXR frames.

```json
{"sequence_id":"seq_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","destination_folder":"C:\\Chosen\\Frames","format":"PNG"}
```

Keep the returned `attempt_id` and `transaction_fingerprint`. Submit `export_shader_sequence` with the **same** `sequence_id`, `destination_folder`, and `format`, plus `"transaction_fingerprint":"<preflight fingerprint>"`. Poll `get_shader_sequence({"sequence_id":"<preflight ID>"})`, matching `attempt_id` and fingerprint in `folder_export` or `publication_attempts`. If export acknowledgement is lost, GET that known ID/attempt before another action; absence is unknown, never a reason to blindly repost. To stop native work use `control_shader_sequence({"sequence_id":"<preflight ID>","action":"stop","run_id":"<get_shader_sequence render_observation.run_id>"})`; resume uses `action:"resume"` and current Standard/Pro access. To cancel or retry folder publication use `action:"cancel_export"` or `action:"retry_export"` with the exact current `attempt_id`. GET after uncertain control replies. Native equirectangular and square Dome masters keep their frozen timing/projection; deferred folder PNG/JPG encoding does not change them.

## Shader package layout

The package folder holds `shader.json` (authored data), `source.glsl`, `modules/**/*.glsl`, `provenance.json`, `resources/`, `originals/` and an optional cover. A helper such as `modules/lib/noise.glsl` is included from `source.glsl` with `#include "modules/lib/noise.glsl"`; use the full declared path (`"lib/noise.glsl"` fails: "Include target is not an exact declared module"). Keep unused helpers. `shader_edit` cannot write `provenance.json`. Git commit, checkout or export never replaces a save. Human detail: https://360hextile.com/docs/create/shader.

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
