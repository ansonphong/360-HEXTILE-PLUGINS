# Recipes

One line per task. Long examples (Recipes A–J, sequence JSON, library, Fractal): `get_guide(name="recipes-detail")`.

## How to work fast

- Orient with one read: `get_live_context {"view":"shader"}` (`shaderId`, `writable`, witness, `studio_surface_id`, `lease`, `revision`, `saved_base`).
- Act by id: `shader_edit {"shader_id":..}` edits a Shader with no window and no open step, and saves itself. One call per edit; put related entries (min with max, create with code) in one `edits` list.
- 403 `No document is open` or `connected:false`: do not poll. Ask the user to open a document or the Workshop, then try once.
- Lost reply: send the same request with the same `request_id`; it returns the recorded result; `request_expired` (409) means the record is gone, so check state, then use a new id. Use a new id for a new or repaired edit.

## Placeholders

- `W` = `project_context_witness`. `B` = `base` (`{"kind":"saved","working_revision":N,"document_hash":..,"source_hash":..}`). Every write reply returns the next `base`: chain with it, no re-reads. Looks, checkpoint and restore may omit `base`. `S` = `{"origin":"user","shaderId":"<id>"}`. `U` = a fresh UUIDv4.
- `L` = the lease `{"holder":"agent","generation":0}`. Copy `lease` from `get_live_context {"view":"shader"}` (on screen) or from the `open_shader_workspace` reply (any Shader); a new Shader starts at agent generation 0. It goes at the top level of `shader_edit`, never inside an edit:
  `{"shader_id":"S","request_id":"U","lease":{"holder":"agent","generation":0},"edits":[{"op":"set","address":["code"],"value":{"source.glsl":"<full file>"}}]}`
- On-screen Shader: `W` and `B` (= `saved_base`) come from `get_live_context {"view":"shader"}`. Any other Shader (or `get_live_context` shows a different one): `shader_list_assets {"search":"<name>"}` gives `W`, `S`, `base`; send the row's `base` as-is (not `saved_base`).
- Every `shader_*` write except `shader_edit` takes a UUIDv4 `request_id`. `shader_edit` takes any unique string.
- Library `library_intent` and `confirmation_scope` are filled for you on Looks, history tools and rename; send them only for delete (`"library_intent":"saved","confirmation_scope":{"operation":"delete","shader":S}`).
- "On screen" = mounted in the Workshop, else 403 `authority`.

## Who can be edited

- My Library (`origin:"user"`): everything below. Built-in: editable only when `writable:true` (APP dev mode). Project: read-only. Otherwise `read_only` → `shader_duplicate_asset` (or `shader_save_as` on screen), then edit the copy.

## Saving

`shader_edit` saves each accepted batch as one revision and returns `commit` and `revision`. Do not call `register_shader_update` or a Save after it. Read each `results[].outcome`: `skipped` changed nothing even when `save` says `saved`. A repaired edit uses a new request id. Read merge rows for what was kept.

## Find what's open

- Which Shader is open → `get_live_context {"view":"shader"}`.
- Find by name → `shader_list_assets {"search":"beam"}`; returns `W`, `S`, `base`.
- Another Shader's title, tags, saved values → `shader_get_asset_state {"shader":S,"project_context_witness":W}`.
- On-screen parameters → `get_shader_parameters {}` (ids, values, label, type, help, min, max, step, options).
- Read GLSL and parameter help/labels/options, any Shader (off-screen Built-ins too) → `shader_get_asset_state {"shader":S,"project_context_witness":W,"include":["source","parameters"]}` — one call.
- Package files on disk (`shader.json`, `source.glsl`, `modules/*.glsl`) → `open_shader_workspace` (file flow only; the sibling `revisions/<NNNNNN>/` of `workspace_path` is the saved copy).

## Shader parameters

All: `shader_edit {"shader_id":"<id>","request_id":"<unique>","edits":[<entry>]}`. Ids from `get_shader_parameters`.

- Label / help / group / widget / clamp / default → `{"op":"set","address":["parameters","<id>","label"|"help"|"group"|"control"|"clamp"|"default"],"value":..}`.
- Min / max / step → `["parameters","<id>","min"|"max"|"step"]` — send min and max together.
- Rename dropdown options → `["parameters","<id>","option_labels"]` value `{"0":"A","1":"B"}` (all labels).
- Current value → `{"op":"set","address":["values","<id>"],"value":0.7}`; reorder → `["order","parameters"]` with all ids.
- Add a slider → with `lease`: `{"op":"create","address":["parameters","glow"],"value":{"type":"float","default":1,"min":0,"max":2,"step":0.01,"label":"Glow"}}` plus a `["code"]` entry using `hxParam_glow`.
- Remove a parameter → with `lease`: `delete` `["parameters","<id>"]` plus a `["code"]` entry without `hxParam_<id>`, in one call.
- Change type or options → with `lease`: `reshape` `["parameters","<id>"]` value `{"type":"enum","options":[0,1,2],"default":0}`.
- Tags / title → `["meta","tags"|"title"]`; clock → `["clock","bpm"|"speed"]`; size → `["output","width"|"height"]`; `["view","fov"]`; `["capture","seed"]`.
- Timeline, first time, all three in one call: `["timeline","start"]` `[0,1]`, `["timeline","end"]` `[4,1]`, `["timeline","loop"]` `true`. Times are `[numerator, denominator]` seconds: `[4,1]` = 4 s, `[1,2]` = 0.5 s. After that one field works.
- Modulators, drivers, channels, image inputs, credits: recipes-detail.

## Shader code

- Edit the GLSL → read the saved `revisions/<NNNNNN>/` files (above), then `shader_edit` with top-level `lease` and `{"op":"set","address":["code"],"value":{"source.glsl":"<full>","modules/x.glsl":"<full>"}}` — the value holds every file; an incomplete map is `skipped`.
- Helper module → add `"modules/lib/noise.glsl"` to the map; `#include "lib/noise.glsl"` in `source.glsl`.
- Compile error → `prepare_failed` with `file:line:col`, nothing saved; fix, new request id.

## Looks and history

- Save a Look → `shader_save_look {"shader":S,"project_context_witness":W,"request_id":U,"title":"Warm"}` (on screen add `studio_surface_id`). It creates a revision.
- Apply a Look → `shader_apply_look {"shader":S,"project_context_witness":W,"request_id":U,"name":"Warm"}`; `shader_get_looks` rows (`id`, `envelope_hash`) also work as `look_id`/`id`, hash optional. Rename / delete: same shape.
- History → `shader_get_history {"shader":S,"project_context_witness":W,"kind":"revisions","newest":true,"limit":5}`.
- Previous version → `shader_restore_revision {"shader":S,"project_context_witness":W,"request_id":U,"steps_back":1}` (2 calls with the edit); or a `target` `{"document_ref":"rev:34","document_hash":".."}` from history. Writes a new revision.

## Render and export

- Still → `shader_preflight_still_export {"shader":S,"project_context_witness":W,"studio_surface_id":"<sid>","request_id":U1,"base":B,"profile":"shader-raster-still/1","output":{"projection":"equirectangular","encoding":"png","width":8192,"height":4096,"supersampling":2,"output_path":"<abs>.png"}}`, then `shader_export_still {..same ids..,"request_id":U2,"preflight_request_id":U1,"profile":"shader-raster-still/1"}`. On screen. A missing folder is named in the refusal; create it. Poll `shader_get_output_job` with `U2`.
- Frame sequence → `preflight_shader_sequence` then `render_shader_sequence` with one identical body (example in recipes-detail), poll `get_shader_sequence`. Needs `native-render/1` and `seed`; the folder must exist.
- Stop → `control_shader_sequence {"sequence_id":"seq_..","action":"stop","run_id":"<render_observation.run_id>"}`.

## Studio workflows

- List / read → `list_workflows {}`; `get_workflow {"origin":"builtin","id":"quick-scout"}`.
- Validate → `validate_config {"workflow_id":"quick-scout","origin":"builtin","overrides":{"prompt":{"global":"a neon city"},"input":{"path":"<abs seed image>","source":"file"}}}`. quick-scout needs an input image or a seed (`generate_seed`), else validation fails.
- Run → `run_workflow {..same..}`, then `get_status {"run_id":..}`.
- Seed image → `list_360_loras`, `generate_seed`, `get_seed_job`.
- Upscale, layers, Fractal, library, settings, docs: recipes-detail.
