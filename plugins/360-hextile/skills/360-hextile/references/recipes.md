# Recipes

One line per task. Long examples (Recipes A–J, sequence JSON, library, Fractal): `get_guide(name="recipes-detail")`.

## How to work fast

- Orient with one read: `get_live_context {"view":"shader"}` (`shaderId`, `writable`, witness, `studio_surface_id`, `lease`, `revision`, `saved_base`).
- Act by id: `shader_edit {"shader_id":..}` edits a Shader with no window and no open step, and saves itself. One call per edit; put related entries (min with max, create with code) in one `edits` list.
- 403 `No document is open` or `connected:false`: do not poll. Ask the user to open a document or the Workshop, then try once.
- Lost reply: send the same request with the same `request_id`; it returns the recorded result. Use a new id only for a new or repaired edit.

## Placeholders

- `W` = `project_context_witness`. `B` = `base` (`{"kind":"saved","working_revision":N,"document_hash":..,"source_hash":..}`). `S` = `{"origin":"user","shaderId":"<id>"}`. `U` = a fresh UUIDv4.
- `L` = the lease `{"holder":"agent","generation":0}`. Copy `lease` from `get_live_context {"view":"shader"}` (on screen) or from the `open_shader_workspace` reply (any Shader); a new Shader starts at agent generation 0. It goes at the top level of `shader_edit`, never inside an edit:
  `{"shader_id":"S","request_id":"U","lease":{"holder":"agent","generation":0},"edits":[{"op":"set","address":["code"],"value":{"source.glsl":"<full file>"}}]}`
- On-screen Shader: `W` and `B` (= `saved_base`) come from `get_live_context {"view":"shader"}`. Any other Shader (or when `get_live_context` shows a different Shader than the one you edit): `shader_list_assets {"search":"<name>"}` gives `W`, `S` and `base`; send that row's `base` as-is as `B` (not `saved_base`).
- Every `shader_*` write except `shader_edit` takes a UUIDv4 `request_id`. `shader_edit` takes any unique string.
- Saved-shelf writes (rename, delete, Look, restore) add `"library_intent":"saved","confirmation_scope":{"operation":"<op>","shader":S}` and no `studio_surface_id`.
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
- Read the GLSL and `shader.json` → `open_shader_workspace {"shader_id":"<id>","request_id":"w1"}` returns `workspace_path` (`<dir>/workspace`). `workspace/` can be stale; read the sibling `<dir>/revisions/<revision as 6 digits>/` (`shader.json`, `source.glsl`, `modules/*.glsl`) — that is the current saved copy.
- A Shader's parameter help or labels when it is not on screen → `shader_get_asset_state` (saved values only for now; an `include` flag for parameter definitions and source is coming — until then use the workspace read above).

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

- Save a Look → `shader_save_look {"shader":S,"project_context_witness":W,"base":B,"request_id":U,"title":"Warm",<saved-shelf fields, operation "shader_save_look">}` (on screen: `studio_surface_id` instead). It creates a new revision.
- List Looks → `shader_get_looks {"shader":S,"project_context_witness":W}`; rows have `id` and `envelope_hash`.
- Apply a Look → `shader_apply_look {..,"look_id":<row id>,"expected_look_envelope_hash":<row envelope_hash>}`.
- History → `shader_get_history {"shader":S,"project_context_witness":W,"kind":"revisions","newest":true,"limit":5}`.
- Go back to the previous version → in that list take the entry right after the current head (the head is `working_revision` of `B`; "previous" is the next-older revision) → `shader_restore_revision {..,"base":B,"request_id":U,<saved-shelf fields>,"target":{"document_ref":"rev:34","document_hash":".."}}` using that entry's ref and hash; it writes a new revision.

## Render and export

- Still → `shader_preflight_still_export {"shader":S,"project_context_witness":W,"studio_surface_id":"<sid>","request_id":U1,"base":B,"profile":"shader-raster-still/1","output":{"projection":"equirectangular","encoding":"png","width":8192,"height":4096,"supersampling":2,"output_path":"<abs>.png"}}`, then `shader_export_still {..same ids..,"request_id":U2,"preflight_request_id":U1,"profile":"shader-raster-still/1"}`. On screen. The output folder must already exist. Poll `shader_get_output_job` with `U2`.
- Frame sequence → `preflight_shader_sequence` then `render_shader_sequence` with one identical body (example in recipes-detail), poll `get_shader_sequence`. Needs `native-render/1` and `seed`; the destination folder must already exist.
- Stop → `control_shader_sequence {"sequence_id":"seq_..","action":"stop","run_id":"<render_observation.run_id>"}`.

## Studio workflows

- List / read → `list_workflows {}`; `get_workflow {"origin":"builtin","id":"quick-scout"}`.
- Validate → `validate_config {"workflow_id":"quick-scout","origin":"builtin","overrides":{"prompt":{"global":"a neon city"},"input":{"path":"<abs seed image>","source":"file"}}}`. quick-scout needs an input image or a seed (`generate_seed`), else validation fails.
- Run → `run_workflow {..same..}`, then `get_status {"run_id":..}`.
- Seed image → `list_360_loras`, `generate_seed`, `get_seed_job`.
- Upscale, layers, Fractal, library, settings, docs: recipes-detail.
