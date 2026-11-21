# Recipes

One line per task. Long examples (Recipes A–J, sequence JSON, library, Fractal): `get_guide(name="recipes-detail")`.

## How to work fast

- Shader on screen (or "this Shader"): orient with one read, `get_live_context {"view":"shader"}`. A Shader named by title: skip it and start with `shader_list_assets`. On screen: (`shaderId`, `writable`, witness, `studio_surface_id`, `lease`, `revision`, `saved_base`).
- Act by id: `shader_edit {"shader_id":..}` edits a Shader with no window and no open step, and saves itself; no `get_live_context` first for an off-screen Shader. One call per edit; put related entries (min with max, create with code) in one `edits` list.
- 403 `No document is open` or `connected:false`: do not poll. Ask the user to open a document or the Workshop, then try once.
- Lost reply: send the same request with the same `request_id`; it returns the recorded result; `request_expired` (409) means the record is gone, so check state, then use a new id. Use a new id for a new or repaired edit.

## Placeholders

- `W` = `project_context_witness`. `B` = `base` (`{"kind":"saved","working_revision":N,"document_hash":..,"source_hash":..}`). Every write reply returns the next `base`: chain with it, no re-reads. Looks, checkpoint and restore may omit `base`. `S` = `{"origin":"user","shaderId":"<id>"}`. `U` = a fresh UUIDv4.
- `L` = the lease `{"holder":"agent","generation":0}`. On screen, copy `lease` from `get_live_context {"view":"shader"}`. A Shader not on screen takes `L` as written: do not call `open_shader_workspace` for it; read the lease there only after a 409 `stale_lease`. It goes at the top level of `shader_edit`, never inside an edit:
  `{"shader_id":"S","request_id":"U","lease":{"holder":"agent","generation":0},"edits":[{"op":"set","address":["code"],"value":{"source.glsl":"<full file>"}}]}`
- `shader_edit` and `shader_get_asset_state` work on any My Library Shader by id without opening it; `get_live_context` only describes the Shader on screen. `W` is project-wide: one witness works for every Shader.
- On-screen Shader: `W` and `B` (= `saved_base`) come from `get_live_context {"view":"shader"}`. Any other Shader (or `get_live_context` shows a different one): `shader_list_assets {"search":"<name>"}` gives `W`, `S`, `base`; send the row's `base` as-is (not `saved_base`).
- Every `shader_*` write except `shader_edit` takes a UUIDv4 `request_id`. `shader_edit` takes any unique string.
- Library `library_intent` and `confirmation_scope` are filled for you on Looks, history tools and rename; send them only for delete (`"library_intent":"saved","confirmation_scope":{"operation":"delete","shader":S}`).
- "On screen" = mounted in the Workshop, else 403 `authority`.

## Who can be edited

- My Library (`origin:"user"`): everything below. Built-in: editable only when `writable:true` (APP dev mode). Project: read-only. Otherwise `read_only` → `shader_duplicate_asset` (or `shader_save_as` on screen), then edit the copy.

## Saving

- Change a My Library Shader's ID and folder name → `shader_change_id {"shader":S,"base":B,"project_context_witness":W,"request_id":U,"new_shader_id":"new_id"}`. If the reply is lost, use `shader_get_operation` with `scope:"asset"`, the original Shader ref and the original request ID.

`shader_edit` autosaves each accepted batch to the working copy and returns `commit` and `revision`. Read `edit_counts` and each `results[].outcome`. For a skipped operation or one that lost to a newer human edit, read `results[].reason` before making any correction. A lost reply uses the original request ID. A corrected edit uses a new request ID.

## Find what's open

- Which Shader is open → `get_live_context {"view":"shader"}`.
- Did this saved source reach the Workshop → `get_live_context {"view":"shader"}`. Match `preview.studio_surface_id`, `working_revision`, `document_hash` and `source_hash` to the mounted saved base. `presented` confirms a visible frame. For `failed`, read the source-mapped diagnostics. `showing_previous:true` marks an earlier frame.
- Create a named blank Shader → `shader_create_asset {"request_id":U,"project_context_witness":W,"action":"new","template_id":"hx_starter","title":"My Shader"}`. The title is optional. Recover a lost reply with `shader_get_operation {"request_id":U,"project_context_witness":W,"scope":"creation"}`.
- Find by name → `shader_list_assets {"search":"beam"}` (searches titles, not ids); returns `W`, `S`, `base`.
- Another Shader's title, tags, saved values → `shader_get_asset_state {"shader":S,"project_context_witness":W}`.
- On-screen parameters → `get_shader_parameters {"limit":32}`. Follow `next_cursor` with `{"cursor":"<next_cursor>"}` until null. The reply gives `count` and `max_parameters` (1,024). A wide enum continues with the same parameter id and the next slice of its options.
- Read GLSL and parameter help/labels/options, any Shader (off-screen Built-ins too) → `shader_get_asset_state {"shader":S,"project_context_witness":W,"include":["source","parameters"]}` — one call.
- Package files on disk (`shader.json`, `source.glsl`, `modules/*.glsl`) → `open_shader_workspace` (file flow only; the sibling `revisions/<NNNNNN>/` of `workspace_path` is the saved copy).

## Shader parameters

All: `shader_edit {"shader_id":"<id>","request_id":"<unique>","edits":[<entry>]}`. Ids from `get_shader_parameters`.

- Label / help / group / widget / clamp / default → `{"op":"set","address":["parameters","<id>","label"|"help"|"group"|"control"|"clamp"|"default"],"value":..}`.
- Min / max / step → `["parameters","<id>","min"|"max"|"step"]` — send min and max together.
- Rename dropdown options → `["parameters","<id>","option_labels"]` value `{"0":"A","1":"B"}` (all labels).
- Star / unstar a parameter (shown with an accent outline and the Workshop "starred only" filter) → `{"op":"set","address":["parameters","<id>","starred"],"value":true}`; unstar with `{"op":"delete","address":["parameters","<id>","starred"]}` (never `false`); `get_shader_parameters` reports `starred:true`.
- Current value → `{"op":"set","address":["values","<id>"],"value":0.7}`; reorder → `["order","parameters"]` with all ids.
- Add a slider → with `lease`: `{"op":"create","address":["parameters","glow"],"value":{"type":"float","default":0.4,"min":0,"max":1,"step":0.01,"label":"Glow"}}` plus a `["code"]` entry using `hxParam_glow`. A new float with valid `min < max` defaults to `control: "slider"`. Set `"control":"number"` to keep a numeric field.
- Remove a parameter → with `lease`: `delete` `["parameters","<id>"]` plus a `["code"]` entry without `hxParam_<id>`, in one call.
- Change type or options → with `lease`: `reshape` `["parameters","<id>"]` value `{"type":"enum","options":[0,1,2],"default":0}`.
- Tags / title → `["meta","tags"|"title"]`; clock → `["clock","bpm"|"speed"]`; size → `["output","width"|"height"]`; `["view","fov"]`; `["capture","seed"]`.
- Loop or timeline on a Shader with no timeline yet: send all three in one call (a lone `loop` is `skipped`): `["timeline","start"]` `[0,1]`, `["timeline","end"]` `[4,1]`, `["timeline","loop"]` `true`. Times are `[numerator, denominator]` seconds: `[4,1]` = 4 s, `[1,2]` = 0.5 s. After that one field works.
- Modulators (`mod_<24 hex>`), drivers, channels, image inputs, credits: recipes-detail. No `controls` yet: one ordered batch, recipes-detail.

## Shader code

- Edit the GLSL → read every file with `shader_get_asset_state {"shader":S,"project_context_witness":W,"include":["source"]}` (one call), then `shader_edit` with top-level `lease` and `{"op":"set","address":["code"],"value":{"source.glsl":"<full>","modules/x.glsl":"<full>"}}` — the value holds every file; an incomplete map is `skipped`.
- Helper module → add `"modules/lib/noise.glsl"` to the map; `#include "modules/lib/noise.glsl"` in `source.glsl` (full declared path).
- Compile error → `prepare_failed` with `file:line:col`, nothing saved; fix, new request id.

## Looks and history

- Set a value and save it as a Look, in one call → `shader_edit {"shader_id":"<id>","request_id":"<unique>","edits":[{"op":"set","address":["values","travel_speed"],"value":0.4},{"op":"create","address":["looks","warm"],"value":{"name":"Warm","values":{"travel_speed":0.4}}}]}` (Look id: lowercase, no spaces). Parameter ids are usually the label in snake_case ("Travel speed" → `travel_speed`); a wrong id returns 400 `unknown_id` and saves nothing. Set → Look → set → apply is 4 calls: `shader_list_assets` (for `S`, `W`), this edit, the next value edit, `shader_apply_look {"shader":S,"name":"Warm"}`.
- Save a Look → `shader_save_look {"shader":S,"project_context_witness":W,"request_id":U,"title":"Warm"}` (on screen add `studio_surface_id`). It creates a revision.
- Apply a Look → `shader_apply_look {"shader":S,"name":"Warm"}`; the reply includes a minted `request_id` and the `project_context_witness` used. Recover with `shader_get_operation {shader, scope:"asset", request_id, project_context_witness}` using the reply's values; never resend the short form. `shader_get_looks` rows (`id`, `envelope_hash`) also work as `look_id`/`id`, hash optional. Rename / delete still require `project_context_witness` and `request_id`; rename needs `name` (or `look_id`) plus `title`.
- History → `shader_get_history {"shader":S,"project_context_witness":W,"kind":"revisions","newest":true,"limit":5}`.
- Previous version → `shader_restore_revision {"shader":S,"project_context_witness":W,"request_id":U,"steps_back":1}` steps back one restore point (one agent session, or one sealed point). Undoing a single edit means sending the inverse shader_edit. `shader_copy_revision` makes a new Shader; or a `target` `{"document_ref":"rev:34","document_hash":".."}` from history. Writes a new revision.

## Audio (Shader)

Steps, data tracks and recovery: recipes-detail "Shader Audio". `O` = the `owner` object a `shader_get_audio` reply returns; pass it unchanged. Timeline times are `{"num":"<int>","den":"<int>"}` seconds.

- Check Audio → `get_capabilities {}`: `audio_signals.contract` is `audio-signals/1` with `available:true` (else read `reason`); it lists the Audio tools, `edit_commands`, bounds and `supported_track_limit` (4 audio tracks; MIDI, CSV and label tracks are not counted).
- Read tracks or signals → `shader_get_audio {"shader":S,"project_context_witness":W,"selector":"tracks"|"signals","limit":20}`; follow `next_cursor`. 409 `page_changed` or 422 `invalid_cursor` → read again without `cursor`.
- Import a file → `audio_prepare_resource {"request_id":U,"owner":O,"source":{"kind":"local_file","path":"<abs .wav/.flac/.mp3/.mid/.csv/.txt>"}}`, then `audio_get_preparation {"receipt":"<receipt_id>","wait_s":25}` until `state` is `ready`. The path resolves in the APP.
- Attach it → `shader_edit_audio {"request_id":U,"owner":O,"command":{"command":"attach_track","receipt_id":"<ready resource receipt_id>","timeline_start":{"num":"0","den":"1"}}}`; the reply's `receipt.track_id` is the new track. It saves itself.
- One signal → `audio_prepare_signal {"request_id":U,"owner":O,"demand_id":U2,"signal_spec":{"id":"signal_<24 hex>","track_id":"<track_id>","measurement":{"kind":"rms","profile_id":"hann2048-hop512/1"},"gain":1,"attack":0.01,"release":0.2,"normalization":"fixed_full_scale"}}`; it starts the analysis itself, so wait on `audio_get_preparation` with `wait_s:25` and read `progress`. Then `shader_edit_audio` command `{"command":"create_signal","receipt_id":"<ready signal receipt_id>","alias":"kick","label":"Kick","output_min":0,"output_max":1}`.
- Four-signal set (audio tracks only; a data track takes one `create_signal`) → `shader_get_audio {..,"selector":"set_suggestion","track_id":"<track_id>"}`, prepare each of the four `proposals[].signal_spec`, then `shader_edit_audio` command `{"command":"create_set","specs":[{"receipt_id":..,"alias":..,"label":..,"output_min":..,"output_max":..}, ×4]}` in proposal order. `alias_collision` → read its `details`, then send again with a new `request_id`.
- Audio visualizer: prepare a Spectrum signal, create_signal, read `<alias>Count`/`<alias>(i)` in GLSL; call `<alias>History(x, age)` for waterfalls (History turns on when the shader uses it). Names, bands and History come from `shader_get_audio` `interface`; History length is `spectrum_history` on `create_signal` or a receipt-less `edit_signal` with `modulator_id`, `label`, `output_min`, `output_max`; GLSL: `get_guide(name="shader-cookbook", detail:true)`, "Using the spectrum in a shader".
- Drive a parameter → `shader_edit` `create ["drivers","<param>"]` with a `{"kind":"modulator","source":"<modulator_id>",..}` row (Recipe J shape), or name the alias in GLSL as `uniform float <alias>`.
- Nudge timing → `edit_signal {"signal_id":..,"offset_ms":-40}` (−1000..1000; negative leads the sound; visual only, no re-analysis). Swap the curve and its shaping in one atomic `edit_signal` with `receipt_id`, `modulator_id`, `label`, `output_min`, `output_max`.
- Monitor delay → `update_app_preferences {"changes":{"audio_monitor_latency_ms":40}}` (0..500; preview only, never renders).
- Render with Audio → the usual `preflight_shader_sequence` then `render_shader_sequence`; `get_shader_sequence {"sequence_id":..,"wait_s":25}` reports `companions` (soundtrack WAV and `timing.json`). Not `ready` with `retry_allowed:true` → `control_shader_sequence {"sequence_id":..,"action":"retry_companions","closure_sha256":..,"receipt_revision":<companions.revision>,"attempt_id":..,"destination":..}`.
- Refused → read `code` and `next_step`. Lost reply (`audio_outcome_unknown`) → read the outcome with the original `request_id` (`audio_get_preparation`, or `shader_get_operation` `scope:"asset"` for an edit), or resend the same payload with the same `request_id`; never a new id.

## Render and export

- Still → `shader_preflight_still_export {"shader":S,"project_context_witness":W,"studio_surface_id":"<sid>","request_id":U1,"base":B,"profile":"shader-raster-still/1","output":{"projection":"equirectangular","encoding":"png","width":8192,"height":4096,"supersampling":2,"output_path":"<abs>.png"}}`, then `shader_export_still {"shader":S,"project_context_witness":W,"studio_surface_id":"<sid>","base":B,"request_id":U2,"preflight_request_id":U1,"profile":"shader-raster-still/1"}` (no `output`; it comes from the preflight). On screen. Sizes are 2:1: 2K = 2048x1024, 4K = 4096x2048, 8K = 8192x4096. The folder must exist (it is not created for you; a missing one is named in the refusal). The reply usually says `completed`; only if it says running, read `shader_get_output_job {"shader":S,"project_context_witness":W,"profile":"shader-raster-still/1","request_id":U2,"wait_s":25}`.
- Frame sequence → `preflight_shader_sequence` then `render_shader_sequence` with one identical body (example in recipes-detail), read `get_shader_sequence` with `wait_s:25` while active. Needs `native-render/1` and `seed`; the folder must exist.
- Shader export status → read `shader_get_output_job` with the original export request ID and profile, or `get_shader_sequence` with the preflight sequence ID and compare the request hash. Pass `wait_s:25` while active instead of calling again. Use the reported phase, verified output and next action. Preflight reports qualified routes and codec options for the chosen output. A missing reply or record leaves the outcome unknown.
- Stop → `control_shader_sequence {"sequence_id":"seq_..","action":"stop","run_id":"<render_observation.run_id from get_shader_sequence>"}`; resume needs no `run_id`. More: recipes-detail.

## Studio workflows

- List / read → `list_workflows {}`; `get_workflow {"origin":"builtin","id":"quick-scout"}`.
- Validate → `validate_config {"workflow_id":"quick-scout","origin":"builtin","overrides":{"prompt":{"global":"a neon city"},"input":{"path":"<abs seed image>","source":"file"}}}`. quick-scout without an input image validates `ok:true` but warns `run_workflow` would refuse; give it an input image or a seed (`generate_seed`).
- Run → `run_workflow {..same..}`, then `get_status {"run_id":..,"wait_s":25}`.
- Seed image → `list_360_loras`, `generate_seed`, `get_seed_job`.
- Upscale, layers, Fractal, library, settings, docs: recipes-detail.
