# 🌐 360 Hextile — agent marketplace

Agent tools for **360 artists**. Add the marketplace once. Install one plugin. Start working.

| | |
|:--|:--|
| **Marketplace** | `360-hextile` |
| **Plugin** | `360-hextile` (Claude / Codex id `360-hextile@360-hextile`) |
| **GitHub** | [ansonphong/360-HEXTILE-PLUGINS](https://github.com/ansonphong/360-HEXTILE-PLUGINS) |
| **On disk** | `D:\Projects\360-HEXTILE\360-HEXTILE-PLUGINS` |

This repository is both the marketplace and the plugin source. The one plugin lives in [`plugins/360-hextile/`](plugins/360-hextile/). It ships everything:

- the `hextile` MCP proxy for the running 360 Hextile app;
- the Workflow, Shader, Fractal and upres skills;
- the Hextile Pipe studio matte CLIs (knockout, cutout, recolor PNG/SVG, despeckle, trim);
- the Illustrator export script and the Photoshop design notes.

All three host catalogs point at that same directory in this repository. There are no submodules, cross-repository SHA pins or sync scripts.

The former repositories `ansonphong/360-hextile-agent` and `ansonphong/hextile-pipe` are retired, along with their `hextile-agent` marketplace and the separate `hextile-pipe` plugin. Their complete histories are preserved here as annotated tags:

- `provenance/360-hextile-agent/master`
- `provenance/hextile-pipe/master`
- `provenance/hextile-pipe/catalog-trim`

---

## Install

Add **one** marketplace source, then install the plugin. Adding the marketplace does not install it.

Use the **GitHub** source. Do not also add the local disk path: two sources with the same name make `360-hextile` ambiguous.

<details open>
<summary><strong>Claude Code</strong></summary>

```text
/plugin marketplace add ansonphong/360-HEXTILE-PLUGINS
/plugin install 360-hextile@360-hextile
```

Then:

```text
/360-hextile:hextile-pipe doctor
```

Claude install id is **`360-hextile@360-hextile`**. Never `hextile@360-hextile`.

</details>

<details open>
<summary><strong>Grok</strong></summary>

```text
grok plugin marketplace add ansonphong/360-HEXTILE-PLUGINS
grok plugin install 360-hextile --trust
grok plugin enable 360-hextile
```

Reload (`r` in `/plugins`) or start a new session.

The Grok install name is **`360-hextile`**. Not `hextile`, `hextile-agent` or `hextile-pipe`. Not `360-hextile@ansonphong/360-HEXTILE-PLUGINS`: `@` on `grok plugin install` is a git ref, not a marketplace pin. Trusted MCP needs `--trust`.

Studio disk clone (only if you did **not** add the GitHub source):

```text
grok plugin marketplace add D:\Projects\360-HEXTILE\360-HEXTILE-PLUGINS
```

</details>

<details open>
<summary><strong>Codex</strong></summary>

```text
codex plugin marketplace add ansonphong/360-HEXTILE-PLUGINS
codex plugin add 360-hextile@360-hextile
```

Use a current Codex CLI with `codex plugin` support. The plugin includes all skills and the bundled `hextile` stdio MCP proxy; no separate clone or installer is required. Git and Python 3.9 or newer are prerequisites, and `python3` must be available to the agent. Start a new Codex session after installation and check `/mcp` for `hextile`. Keep 360 Hextile open on the same computer at `127.0.0.1:8000`.

Local checkout: `codex plugin marketplace add D:\Projects\360-HEXTILE\360-HEXTILE-PLUGINS`.

</details>

### Upgrading from the old split installs

Earlier installs used a separate `hextile-pipe` plugin and/or the standalone `hextile-agent` marketplace (`360-hextile@hextile-agent`). Remove those, keep or re-add the `360-hextile` marketplace from this repository, and install `360-hextile`.

| Host | Steps |
|:-----|:------|
| Claude | `/plugin uninstall hextile-pipe@360-hextile`; `/plugin uninstall 360-hextile@hextile-agent`; `/plugin marketplace remove hextile-agent`; `/plugin marketplace update 360-hextile`; `/plugin install 360-hextile@360-hextile` (or `/plugin update`) |
| Grok | `grok plugin uninstall hextile-pipe`; remove any `hextile-agent` source; `grok plugin marketplace update`; `grok plugin update 360-hextile` (or install it) |
| Codex | `codex plugin remove hextile-pipe@360-hextile`; `codex plugin remove 360-hextile@hextile-agent`; `codex plugin marketplace remove hextile-agent`; `codex plugin marketplace upgrade 360-hextile`; `codex plugin add 360-hextile@360-hextile` |

Skip any step for something you never installed. Start a new host session afterwards.

---

## What's in the plugin

| Area | Skills (Claude: `/360-hextile:<skill>`) | Where |
|:-----|:----------------------------------------|:------|
| Workflow automation hub | `360-hextile` | `skills/360-hextile/`, MCP `mcp/` |
| Shader authoring | `shader` | `skills/shader/` |
| Fractal Workshop | `fractal` | `skills/fractal/` |
| GPU upres | `upres` | `skills/upres/` |
| Studio matte (Pipe) | `hextile-pipe` (hub + doctor), `hextile-knockout`, `hextile-cutout`, `hextile-recolor-png`, `hextile-recolor-svg`, `hextile-despeckle`, `hextile-trim` | `pipe/`, `skills/hextile-*/` |
| Adobe helpers | — (manual run) | `pipe/illustrator/`, `pipe/photoshop/` |

`360-hextile` talks to a local 360 Hextile instance through `local-endpoint.json` (default `127.0.0.1:8000`). Open the app first. If the app is down, tools return a clean error; the MCP process stays up. `get_guide` works without the app. Details: [plugin README](plugins/360-hextile/README.md), [Pipe README](plugins/360-hextile/pipe/README.md).

---

## All tools

### `hextile` MCP server — 179 tools

Every tool the bundled `hextile` MCP proxy lists, grouped by area. Each one forwards to the running 360 Hextile app on `127.0.0.1:8000`, except `get_guide`, which reads the bundled guides. Full argument schemas come from the host's `tools/list`.

<details>
<summary><strong>Workflows and renders</strong> (17)</summary>

| Tool | What it does |
|:--|:--|
| `list_workflows` | List workflow templates on all shelves (builtin / user / project). |
| `get_workflow` | Read one workflow template before overriding fields. |
| `get_capabilities` | Handshake: GET /api/workflows/capabilities (workflow_api_version + features). |
| `describe_image` | Describe one exact local image or equirectangular crop using APP's local vision. |
| `get_live_context` | Read-only studio snapshot (K1). |
| `apply_config_delta` | Apply a live delta to the exact current studio document while MCP is enabled. |
| `save_workflow` | Create-only persist of a .hextile.json document on the user or project shelf. |
| `delete_workflow` | Delete a user or project workflow. |
| `run_workflow` | Merge overrides into a workflow, validate, and queue a render. |
| `validate_config` | Terraform-plan: merge + validate without queueing (dry_run: true). |
| `get_status` | Poll render/job status by run_id from run_workflow. |
| `get_render_config` | Read the producing .hextile.json for a render (GET /api/renders/{id}/config). |
| `get_logs` | Fetch failed-run logs (GET /api/renders/{id}/logs). |
| `list_runs` | List library renders (monitor without a stored run_id). |
| `search_library_prompts` | Search saved global and tile prompts in render and sequence library rows. |
| `cancel_run` | Stop a running render (status → cancelled). |
| `retry_run` | Retry a crashed/failed render (POST /api/renders/{id}/retry). |

</details>

<details>
<summary><strong>360-LoRA seeds</strong> (6)</summary>

| Tool | What it does |
|:--|:--|
| `generate_seed` | Submit one 360-LoRA seed job with a caller-supplied UUID. |
| `get_seed_job` | Read one exact 360-LoRA job (GET /api/360-lora/jobs/{job_id}). |
| `list_seed_history` | List stored 360-LoRA seed batches (GET /api/360-lora/history). |
| `get_seed_batch` | Read one stored 360-LoRA seed batch (GET /api/360-lora/history/{batch_id}). |
| `cancel_seed` | Cancel only the named 360-LoRA job (POST /api/360-lora/jobs/{job_id}/cancel). |
| `list_360_loras` | List installed/known 360-LoRAs. |

</details>

<details>
<summary><strong>Models</strong> (6)</summary>

| Tool | What it does |
|:--|:--|
| `list_installed_models` | List installed weights for a pipeline (GET /api/models/{pipeline_id}?installed_only=true). pipeline_id is required. |
| `get_model_readiness` | Read current model fit, availability, and install bundle from the app. |
| `get_model_download_queue` | Read the app's active and queued model downloads, including queue_entry_id for exact cancellation. |
| `install_model` | Queue one registry model, or its current default-catalog selected bundle. |
| `repair_model` | Ask the app to diagnose and queue repair for one registry model. |
| `cancel_model_download` | Request cancellation of only the observed queue admission. |

</details>

<details>
<summary><strong>Shader</strong> (66)</summary>

| Tool | What it does |
|:--|:--|
| `get_shader_context` | Read the open Shader, including bounded source-free conventions/1, modulation/2 or /3, parameter-expressions/1, shader-timeline/1, stable typed parameter addresses … |
| `get_shader_parameters` | Read exposed controls on the mounted Shader without including source. |
| `set_shader_parameter` | Change one exposed control on the exact witnessed mounted Shader. |
| `propose_shader` | POST one closed Shader proposal, including schema-2 parameter expression, mode and saved timeline edits, and return ticket identity. |
| `control_shader_timeline` | Control only the currently mounted Shader Workshop session after fresh get_live_context discovery. |
| `preflight_shader_sequence` | Check a confirmed saved Shader revision and exact rational native interval without queuing. |
| `inspect_shader_sequence_output` | Inspect one selected Shader destination with metadata only. |
| `render_shader_sequence` | Queue only the exact saved Shader request already preflighted, with its caller-known idempotency_key and confirmed revision. |
| `get_shader_sequence` | Read a source-free and path-free Shader sequence status by the caller-known ID. |
| `control_shader_sequence` | Stop the observed run_id, resume an admitted native job, or Continue the exact inspected request and fingerprint. |
| `preflight_shader_sequence_export` | Check verified native masters and an explicitly chosen existing local destination folder. |
| `export_shader_sequence` | Publish only the exact preflighted folder intent using its transaction_fingerprint. |
| `open_shader_workspace` | Reuse the original request id. |
| `register_shader_update` | Register native file bytes once for automatic APP prepare/compile/preview. |
| `get_shader_update` | Read one exact authorized workspace receipt, including attachment_state, check_attempt, prepare/compile/preview/presentation/save and bounded diagnostics/raw_log/reason. |
| `request_shader_doctor` | Request one GPU Doctor pass for the clean, currently previewed Shader in the mounted Workshop. |
| `get_shader_doctor` | Poll one exact Shader Doctor request receipt. |
| `shader_list_assets` | List bounded saved, draft and incomplete Shader metadata in the current library. |
| `shader_get_asset_state` | Read a bounded current Shader identity and saved base under the active lease. |
| `shader_request_preview` | Request shader-export-preview/2 at the selected full dimensions and supersampling. |
| `shader_capture_sequence_input` | Freeze camera pose and persistent toggles from the current completed Shader frame for offline sequences; no GPU work or private input bytes. |
| `shader_get_preview` | Read actual full-resolution dimensions, selected supersampling, exact sample and native progress by original request ID. |
| `shader_release_preview` | Cancel/release this original inspector, including a queued capture or resource freeze, without starting new work. |
| `shader_preflight_still_export` | Preflight one native PNG/JPG raster, PNG master, linear EXR, or Dome profile using the mounted completed frame; no GPU start. |
| `shader_export_still` | Start the exact preflighted native still job once. |
| `shader_get_output_job` | Read a native still job by original UUID and Project witness without starting GPU work. |
| `shader_stop_output_job` | Signal Stop for an existing exact native still job only. |
| `shader_export_bundle` | Publish an accepted saved .hexshader Bundle with exact Looks and provenance at an optional absolute output_path or the host output default. |
| `shader_export_to_project` | Copy the exact accepted saved Shader, Looks, resources, credits and originals to the separately selected existing Project. |
| `shader_get_history` | Read bounded retained Shader revision or checkpoint metadata; a stale cursor requires restart. |
| `shader_get_looks` | Read bounded saved Look identities without source or pixel data. |
| `shader_save_look` | Save the exact durable Shader values and authored state as a named Look; optional replacement binds the old Look envelope. |
| `shader_apply_look` | Apply one exact compatible saved Look through the native writer; source formula changes require their separate policy. |
| `shader_rename_look` | Rename one saved Look with its exact envelope hash. |
| `shader_delete_look` | Remove one exact saved Look while retaining historical revision pins. |
| `shader_checkpoint` | Save, rename or remove one exact checkpoint name through the bound native history action. |
| `shader_restore_revision` | Restore one exact retained revision or checkpoint as the next revision; an uncertain result requires original request ID recovery. |
| `shader_copy_revision` | Save an independent copy of one exact retained revision or checkpoint, preserving credits, Looks and resources. |
| `shader_history_retention` | Preview, compact or uncompact recoverable history. |
| `shader_get_project_conventions` | Read bounded Project Shader convention profiles and digest. |
| `shader_stage_resource` | Stage an exact Render node, complete Sequence range, or absolute local file/folder/ordered frame paths. |
| `shader_set_resource` | Attach, replace, locate, remove, or change typed settings of one exact Shader input through the native CAS writer. |
| `shader_get_library_organization` | Read the active Project or My Library folder revision and bounded folder membership for exact moves and remove confirmation. |
| `shader_organize_library` | Create, rename, remove or move Shader folders/items, including one atomic move-many and native Undo. |
| `shader_set_tags` | Assign or remove one existing personal Tag for one exact Shader through the native tag registry. |
| `shader_set_project_conventions` | Replace Project convention profiles through the fixed native document writer with exact expected digest and Project witness. |
| `shader_get_proposal` | Read one existing Shader proposal ticket, including acceptance or expiry and saved identity when confirmed. |
| `shader_get_workspace` | Recover an existing workspace attachment and current source-free candidate receipt, including before first registration. |
| `shader_recheck_update` | Start a new check attempt for the same current candidate after a failed or unavailable check. |
| `shader_stop_workspace` | Stop only this current workspace attachment and preserve files. |
| `shader_rename_asset` | Rename one saved Shader with an exact base, owner and request ID. |
| `shader_delete_asset` | Delete one exact saved Shader. |
| `shader_get_operation` | Read one original Shader operation outcome by exact request ID and asset, creation, library, Project, or output scope without starting work. |
| `shader_get_credits` | Read paged saved Credits and Sources for the current Shader identity without including source. |
| `shader_propose_credits` | Freeze a credits-only pending review intent; recover uncertain outcomes by request ID. |
| `shader_research_sources` | Fetch only one supplied public HTTP(S) source URL and up to four supplied links locally with bounded text. |
| `shader_open_asset` | Open one saved Shader only while the current mounted draft is clean and settled. |
| `shader_save_asset` | Save the exact dirty MCP-held RAM draft through the native Prepare and writer ticket. |
| `shader_save_as` | Save a copy of the current mounted RAM Shader through its native library writer, preserving Looks, credits and resources. |
| `shader_create_asset` | Create a saved Shader from hx_starter or paste exact supplied UTF-8 source as an inert original while MCP is connected. |
| `shader_fork_asset` | Fork the exact saved source Shader and retain its credits, Looks, resources and history pins. |
| `shader_duplicate_asset` | Duplicate one exact saved Shader into My Library or the active Project. |
| `shader_import_bundle` | Import an absolute .hexshader file through the native importer. |
| `shader_set_capture` | Set a live uint32 seed or the complete authored capture defaults on the exact mounted Shader. |
| `shader_control_clock` | Reanchor the authored Master Clock at the native preview action time, collect Tap tempo, Align beat, or reset Master. |
| `shader_step_frame` | Step one exact frame on the current mounted published Shader. |

</details>

<details>
<summary><strong>Fractal</strong> (14)</summary>

| Tool | What it does |
|:--|:--|
| `get_fractal_context` | Read the mounted Fractal workshop. |
| `apply_fractal_edits` | Submit one closed Fractal authoring batch through the actual current native writer. |
| `control_fractal_timeline` | Play, pause, seek, step, or rewind the mounted Fractal session clock. |
| `open_fractal_scene` | Open one saved Fractal scene id on the mounted workshop. |
| `save_fractal_scene` | Save the acknowledged scene or Save As a caller-known create-only scene id. mode save requires the adopted scene_revision. mode save_as omits scene_revision. |
| `get_fractal_request` | Read one Fractal action by its caller-known client_request_id. |
| `capture_fractal_still` | Mint exactly the last acknowledged finished 360 Fractal preview through the mounted private writer. |
| `preflight_fractal_sequence` | Check one saved Fractal scene revision, rational frame rate, exact range, and native output without queueing. |
| `inspect_fractal_sequence_output` | Inspect one selected Fractal destination with metadata only. |
| `render_fractal_sequence` | Queue the exact saved Fractal sequence request already checked, using the same idempotency_key. |
| `get_fractal_sequence` | Read one known Fractal sequence id. |
| `control_fractal_sequence` | Stop the observed run_id, resume an admitted native job, or Continue the exact inspected request. cancel_export, retry_export, and open_folder require the observed … |
| `preflight_fractal_sequence_export` | Check verified native Fractal masters and an existing local folder for a separate publication. |
| `export_fractal_sequence` | Publish only the preflighted folder intent with its transaction_fingerprint. |

</details>

<details>
<summary><strong>Sequences and upres</strong> (16)</summary>

| Tool | What it does |
|:--|:--|
| `extract_sequence_video` | Extract video frames to a folder (POST /api/sequences/extract-video). |
| `create_sequence` | Create a seq_* from a folder of stills (POST /api/sequences/create). config is a full HextileConfig (clone get_workflow upres-still; never a partial). run_workflow … |
| `start_sequence` | Start GPU processing of an existing sequence (POST /api/sequences/{sequence_id}/start). |
| `get_sequence` | Poll bounded sequence status by sequence_id (GET /api/sequences/{id}?include_frames=false). |
| `list_sequences` | List sequences (monitor without a stored sequence_id). |
| `list_sequence_frames` | Read one bounded page of sequence frame states and output handles. |
| `inspect_sequence_upscale` | Inspect a saved sequence for native upscale eligibility. |
| `upscale_sequence` | Upscale a saved sequence with a caller-owned UUID. |
| `get_sequence_upscale_request` | Recover the original sequence upscale request by its UUID. |
| `resume_sequence` | Resume the exact accepted sequence run. |
| `retry_sequence_failed_frames` | Retry failed frames for the exact accepted sequence run. |
| `stop_sequence` | Stop a running sequence (POST /api/sequences/{id}/stop). |
| `rename_sequence` | Rename only a sequence's display metadata; preserve frozen recipes, paths and render ownership. |
| `set_sequence_lifecycle` | Archive, move to Trash or restore the named sequence via the native library operation. |
| `set_sequence_tags` | Replace the named sequence's tag selection with existing tag IDs. |
| `get_sequence_tags` | Read the named sequence's selected tags and recover an uncertain set_sequence_tags reply. |

</details>

<details>
<summary><strong>Batches</strong> (11)</summary>

| Tool | What it does |
|:--|:--|
| `preflight_batch` | Create a Batch preflight (POST /api/batch-workflows/preflight). |
| `get_batch_preflight` | Poll GET /api/batch-workflows/preflights/{id} until scanning ends (ready\|failed\|expired). |
| `start_batch` | Queue a Batch job from a ready preflight (POST /api/batch-workflows). |
| `list_batches` | List Batch jobs (GET /api/batch-workflows). |
| `get_batch` | Read one Batch job (GET /api/batch-workflows/{job_id}). |
| `get_batch_items` | Page Batch item attempts (GET /api/batch-workflows/{job_id}/items). |
| `pause_batch` | Durably request pause (POST /api/batch-workflows/{job_id}/pause). |
| `resume_batch` | Resume a paused Batch job (POST /api/batch-workflows/{job_id}/resume). |
| `cancel_batch` | Cancel a Batch job (POST /api/batch-workflows/{job_id}/cancel). |
| `retry_batch` | Retry failed/interrupted items (POST /api/batch-workflows/{job_id}/retry-failed). |
| `import_batch_outputs` | Import published Batch outputs into the Library (POST /api/batch-workflows/{job_id}/import). |

</details>

<details>
<summary><strong>Layers and spot clone</strong> (10)</summary>

| Tool | What it does |
|:--|:--|
| `get_layer_draft` | Inspect the exact saved render HEAD and v6 Layers draft before any generation or land. |
| `generate_layer` | Start one Generate Layer job. |
| `get_layer_generation` | Read one exact Generate Layer job by id until terminal. |
| `cancel_layer_generation` | Request cancellation of one exact Generate Layer job. |
| `rematte_layer` | Re-matte an exact retained RGB draft, or Keep rectangle with alpha.mode=opaque. |
| `land_generated_layer` | Land one ready job pair into an exact v6 draft; no commit. |
| `commit_layer_draft` | Explicitly bake the exact saved v6 draft onto current HEAD as a final op:layers node. |
| `preflight_spot_clone` | Read-only Spot Clone readiness for an exact saved render parent. |
| `clone_spot` | After explicit approval, clone one saved render from a witnessed parent and mask, or commit only an already prepared live Spot Clone through the private Copilot ticket. |
| `get_spot_clone` | Read the stored receipt for one exact Spot Clone node after an unknown reply. |

</details>

<details>
<summary><strong>Export</strong> (5)</summary>

| Tool | What it does |
|:--|:--|
| `get_unreal_export_catalog` | Read the Unreal export catalog (GET /api/renders/unreal-export/catalog). |
| `preflight_unreal_export` | Advisory Unreal-project preflight. |
| `export_to_unreal_project` | Export one render into a paired Unreal project via POST /api/renders/{id}/export. |
| `preflight_file_export` | Read-only check of an exact graph-node export into a selected folder. |
| `export_render_file` | Create-only ordinary render export. |

</details>

<details>
<summary><strong>Local files</strong> (8)</summary>

| Tool | What it does |
|:--|:--|
| `get_local_access_status` | Read the MCP connection switch from GET /api/agent/mcp-status. |
| `local_file_stat` | Stat one absolute regular file through APP. |
| `local_file_read` | Read a bounded chunk of one absolute regular file. |
| `local_file_write_begin` | Start a staged create or replace. |
| `local_file_write_append` | Append one ordered chunk to a pending write. data_base64 is at most 64 KiB decoded. |
| `local_file_write_abort` | Abort staging for write_id. |
| `local_file_write_commit` | Publish staged bytes. create is create-only. |
| `local_file_write_status` | Read the caller-bound write receipt by original request_id. |

</details>

<details>
<summary><strong>Hotkeys</strong> (6)</summary>

| Tool | What it does |
|:--|:--|
| `list_hotkeys` | Read this app's device-local Hotkeys profile, revision, effective bindings and availability in pages of 20 actions. |
| `inspect_hotkey` | Inspect one Hotkey and optional candidate bindings for edit errors, conflicts and explained overlaps at the current revision. |
| `set_hotkey_bindings` | Replace one complete Hotkey alias list; an empty list unbinds it. |
| `remove_hotkey_binding` | Remove exactly one assigned Hotkey chord using the revision from a fresh read. |
| `restore_hotkey` | Restore one customized Hotkey to its factory bindings using the revision from a fresh read. |
| `reset_hotkeys` | Clear all Hotkey binding overrides, including inert unknown IDs. |

</details>

<details>
<summary><strong>App, settings and diagnostics</strong> (14)</summary>

| Tool | What it does |
|:--|:--|
| `call_hextile_api` | Call the configured local Hextile native API with relative /api/... paths, or GET /openapi.json. |
| `get_config_schema` | Read owned workflow config model names, or one model's JSON schema. |
| `list_processors` | Read processor identity, display, type, channel, surface, and admission metadata. |
| `get_processor_schema` | Read one processor UI schema by pipeline_id. |
| `get_plugin_catalog` | Read plugin metadata, availability, dependencies, and operations. |
| `get_app_preferences` | Read safe app preferences plus effective_default_pipeline. |
| `update_app_preferences` | Patch one nonempty closed set of safe preferences through the native settings update. |
| `get_storage_summary` | Read disk free and total, default and fallback flags, and storage class identity. refresh defaults to false and keeps the native memoized scan. |
| `get_cache_buckets` | Read cache bucket identity, display name, size, file count, protection, and total size. |
| `clear_disposable_cache` | Clear disposable cache through the native clear routes. |
| `get_license_status` | Read the current license activation, tier, access state and source, features, and non-secret access flags. |
| `get_gpu_diagnostics` | Read the app's current GPU/VRAM status without changing GPU state. |
| `get_seed_memory_advice` | Read separate GPU status and APP memory-pressure advice for one listed 360-LoRA resolution. |
| `get_guide` | Read bundled agent documentation (schema, best practices, website index, recipes, shader cookbook). |

</details>

### Hextile Pipe studio matte tools

Run any matte tool with `bash "$PLUGIN_ROOT/pipe/scripts/fp-run.sh" <tool> …`, or through its skill (Claude: `/360-hextile:<skill>`). Flags and examples: [Pipe README](plugins/360-hextile/pipe/README.md).

| Tool | Skill | What it does |
|:--|:--|:--|
| `knockout` | `hextile-knockout` | Knock out a black (or light) background: greyscale → alpha plus a solid fill, for art-on-black PNGs that need a transparent matte. |
| `cutout` | `hextile-cutout` | White-on-black cutout: solid fill (default white) with transparent, anti-aliased black. For glyphs and logos on black. |
| `recolor_png` | `hextile-recolor-png` | Force a PNG's opaque pixels to one solid color (default white) and keep alpha; `--min-alpha` skips the AA fringe. |
| `recolor_svg` | `hextile-recolor-svg` | Force SVG shape fills and strokes to one solid color (default white), for flat icon silhouettes. |
| `despeckle` | `hextile-despeckle` | Remove dust and freckles from black-background or transparent art with min-area components plus levels; scale-aware, multi-pass. |
| `trim` | `hextile-trim` | Crop a transparent PNG to its content box and/or add a margin (px or %). |
| `fp-doctor.sh` | `hextile-pipe` | Check the Pipe install (Python, Pillow, optional numpy, scripts). The `hextile-pipe` skill is also the hub that routes to the tools above. |

### Adobe helpers (run by hand)

| Tool | What it does |
|:--|:--|
| `pipe/illustrator/export-grouped-assets.jsx` | Illustrator ExtendScript: select page items (groups or ungrouped), then export them as AI / SVG / PNG from a dialog. Run with **File → Scripts → Other Script…**; see [Pipe README](plugins/360-hextile/pipe/README.md#illustrator). |
| `pipe/photoshop/export-selected-layers-design.md` | Design notes for exporting selected Photoshop layers (no script yet). |

### Agent skills

| Skill (Claude: `/360-hextile:<skill>`) | What it does |
|:--|:--|
| `360-hextile` | Workflow automation hub: compose, validate and run 360 Hextile workflows, seeds, sequences, batches and exports. |
| `shader` | Inspect the open Shader, or edit a Project or My Library Shader through its native files with APP-owned checks; the human Applies. |
| `fractal` | Edit the mounted Fractal Workshop, control its timeline, Open or Save scenes, and render or export saved Fractal sequences. |
| `upres` | GPU upres a still, a folder of stills or a video through 360 Hextile Real-ESRGAN. |
| `hextile-pipe` and `hextile-*` | The Pipe matte skills listed above. |

---

## Layout

```text
360-HEXTILE-PLUGINS/
  .claude-plugin/marketplace.json    name: 360-hextile → ./plugins/360-hextile
  .agents/plugins/marketplace.json   name: 360-hextile → local ./plugins/360-hextile (Codex)
  .grok-plugin/marketplace.json      name: 360-hextile → local ./plugins/360-hextile
  plugins/360-hextile/               the one plugin (manifests, mcp/, skills/, pipe/, tests/)
```

All three marketplace JSON `"name"` fields stay **`360-hextile`**; Codex freezes upgrades if that name drifts.

---

## Release

Commit plugin changes here, bump `version` in `plugins/360-hextile/.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` together (plus `SERVER_VERSION` in `mcp/hextile_mcp.py` and `PACKAGE_VERSION` in `codex/install.py`), and push `master`. Hosts do **not** auto-update:

| Host | Then |
|:-----|:-----|
| Claude | `/plugin marketplace update 360-hextile`, then `/plugin update 360-hextile@360-hextile` |
| Grok | `grok plugin marketplace update` then `grok plugin update 360-hextile` |
| Codex | `codex plugin marketplace upgrade 360-hextile` |

---

## License

The plugin's licensing is described in [plugins/360-hextile/README.md](plugins/360-hextile/README.md#license): MIT, except the Pipe material (`pipe/`, `skills/hextile-*`), which remains private studio tooling.
