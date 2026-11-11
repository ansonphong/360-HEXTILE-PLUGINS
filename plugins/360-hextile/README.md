# 360-hextile plugin

**v0.6.2**

One Claude Code / Codex / Grok plugin that drives **360 Hextile** over localhost HTTP and carries the Hextile Pipe studio matte tools.

Source and the only marketplace: **[`ansonphong/360-HEXTILE-PLUGINS`](https://github.com/ansonphong/360-HEXTILE-PLUGINS)** (marketplace `360-hextile`). Install id **`360-hextile@360-hextile`**. Workflow, Shader, Fractal and upres skills, the `hextile` MCP proxy, and the Pipe matte CLIs (`pipe/`, skills `hextile-*`) all ship in this one plugin. The former standalone repositories `360-hextile-agent` and `hextile-pipe` and their marketplaces are retired; their histories are preserved as `provenance/*` tags in this repository.

The MCP process is a thin **stdio** JSON-RPC ↔ HTTP proxy (`python3`, stdlib only).  
All merge, validation, and render logic stay in the running app. The client reads `local-endpoint.json` and does not assume port 8000.

## Quick Shader connection

Ask “connect—what Shader is open?” The Shader skill uses one
`get_live_context(view="shader")` call for the current name, origin, Saved/draft
state, editability and blockers, without listing models or inventory. Detailed
source editing instructions load only when needed. Builtins are readable and
must be duplicated before source editing. Unknown metadata stays unknown;
connection is not evidence of Apply or Save. The default full tool response is
unchanged. Both the running APP and installed connector must support this view.
Updating this repository or its APP vendor snapshot does not update an installed
plugin cache; update through the host's existing plugin flow and reconnect/start
a new host session. No install or reconnect is performed by this change.

## Recorded live qualification (2026-10-24)

The connected MCP tool inventory still showed the original 16 Shader tools; new names including `shader_get_credits` and `shader_get_output_job` were absent. An actual `get_capabilities` call returned `isError` with “MCP availability could not be verified. Check 360 Hextile Settings → MCP and retry.” The loaded connector revision and installed APP behavior are therefore unverified. Native filesystem access, GPU output, and desktop behavior have not been qualified for this delivery. Source checkout and bundled-file checks do not establish installed-host behavior.

## Current Shader format

Version 0.5.5 source authoring requires document schema 4 and workspace schema 2. The
client requests workspace2 by default and refuses older acknowledgements without
releasing paths. Existing older content needs the separate checked offline
migration; opening a workspace never upgrades or overwrites it. Extension,
provenance and bundle versions remain independent.

Source/headless verification and isolated shelf conversions do not establish
installed-plugin or live visual acceptance. Update the installed host package and
reconnect only when the matching APP/content cutover is ready for your smoke test.

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| **360 Hextile running** | The client reads `local-endpoint.json` and does not assume port 8000. |
| **python3 ≥ 3.9** | On PATH — powers the MCP proxy (zero pip installs). On Windows, Claude `.mcp.json` `command` should be `python` or `py -3`, not `python3`. Optional launcher: `mcp/hextile-mcp.cmd` (picks `python` / `python3` / `py -3`). Committed `.mcp.json` stays `python3`. Codex installer already writes `sys.executable`. |
| App with `POST /api/workflows/run` | Workflow automation P0+ |
| Claude Code **or** Codex ≥ 0.34.0 | Install path below |

## Install — Claude Code

```bash
/plugin marketplace add ansonphong/360-HEXTILE-PLUGINS
/plugin install 360-hextile@360-hextile
```

A local checkout also works: `/plugin marketplace add /path/to/360-HEXTILE-PLUGINS`, then the same install id.

Upgrading from the retired routes: `/plugin uninstall hextile-pipe@360-hextile` and `/plugin uninstall 360-hextile@hextile-agent` (whichever exist), `/plugin marketplace remove hextile-agent` if present, then `/plugin marketplace update 360-hextile` and `/plugin update 360-hextile@360-hextile`. The Pipe skills are now part of this plugin.

```bash
# plugin root (plugins/360-hextile):
#   .claude-plugin/plugin.json
#   .mcp.json          → python3 ${CLAUDE_PLUGIN_ROOT}/mcp/hextile_mcp.py
#   skills/360-hextile/SKILL.md, skills/hextile-pipe/SKILL.md, …
#   pipe/scripts/fp-run.sh
```

On Windows, change Claude `.mcp.json` `command` to `python` or `py -3` (not `python3`). Do not rewrite the committed POSIX `.mcp.json`. Codex installer already writes `sys.executable`.

Update the canonical package in each host and start a new host session to load revised skills and MCP descriptors. Check the installed package revision and live `tools/list` separately from the source checkout; a repository version bump does not upgrade an installed cache. The running APP also reports its own live Shader contract revision and effective policy.

Confirm tools appear (`list_workflows`, `get_guide`, `get_local_access_status`, …). With the app down, tools return a clean error — the MCP process stays up.

Enabling MCP fully trusts the connected agent. APP automatically binds its actual current document writer; source, Apply, capture and task paths need no separate consent or session selection. Include-source/formula/image options select bounded content. Native validation, ownership, CAS, resource limits and exact receipts remain authoritative. Disconnect blocks fresh or unadmitted work; an admitted export finishes to its frozen destination and remains recoverable by its original request/job ID. Stop separately requests cancellation. The MCP host’s own filesystem and execution rules still apply. `get_local_access_status` reports `enabled` even with MCP OFF and no Studio. Canonical source is this plugin’s `mcp/hextile_mcp.py`; host configuration and the Codex installer point at it.

## Install — Grok

```bash
grok plugin marketplace add ansonphong/360-HEXTILE-PLUGINS
grok plugin install 360-hextile --trust
```

Enable `360-hextile` in `~/.grok/config.toml` `[plugins].enabled` (or Space in `/plugins`). Reload plugins (`r`) or start a new session. A local checkout also works: `grok plugin marketplace add /path/to/360-HEXTILE-PLUGINS`.

Upgrading: remove the old `hextile-pipe` and standalone `360-hextile` installs and any `hextile-agent` marketplace source, point the `360-hextile` source at `https://github.com/ansonphong/360-HEXTILE-PLUGINS.git`, then `grok plugin marketplace update` and install or update `360-hextile`.

## Install — Codex

Use a current Codex CLI with `codex plugin` support:

```bash
codex plugin marketplace add ansonphong/360-HEXTILE-PLUGINS
codex plugin add 360-hextile@360-hextile
```

This installs all bundled skills (including the Pipe `hextile-*` skills) and the `hextile` stdio MCP proxy. Git and Python 3.9 or newer are prerequisites, and `python3` must be available to the agent. Start a new Codex session and check `/mcp` for `hextile`, with 360 Hextile open on the same computer at `127.0.0.1:8000`. No separate clone or Python installer is needed for this route.

Upgrading: remove `hextile-pipe@360-hextile` and `360-hextile@hextile-agent` plus the `hextile-agent` marketplace if present, upgrade the `360-hextile` marketplace, then add `360-hextile@360-hextile`.

Alternative manual setup — clone this repo and run the installer from the plugin directory:

```bash
git clone https://github.com/ansonphong/360-HEXTILE-PLUGINS.git
cd 360-HEXTILE-PLUGINS/plugins/360-hextile
python3 codex/install.py
```

This writes:

- `~/.agents/skills/360-hextile/SKILL.md` + `references/`
- `~/.agents/skills/shader/SKILL.md`
- `~/.agents/skills/fractal/SKILL.md`
- `~/.agents/skills/upres/SKILL.md`
- `[mcp_servers.hextile]` **stdio** entry in `~/.codex/config.toml`  
  (`command` is the absolute `sys.executable`, `args = ["…/mcp/hextile_mcp.py"]`)

The manual installer does not install the Pipe skills; use the plugin route for those.

Uninstall:

```bash
python3 codex/install.py --uninstall
```

Restart Codex and run `/mcp` — you should see `hextile` and the same eight local-file tools as Claude.

The manual installer requires **Codex ≥ 0.34.0**. The MCP proxy uses **stdio** (no streamable HTTP dual-stack).

## Hextile Pipe (studio matte)

Python matte CLIs (knockout, cutout, recolor PNG/SVG, despeckle, trim), an Illustrator export script and Photoshop design notes live in `pipe/`. Skills: `hextile-pipe` (hub + doctor), `hextile-knockout`, `hextile-cutout`, `hextile-recolor-png`, `hextile-recolor-svg`, `hextile-despeckle`, `hextile-trim` (Claude: `/360-hextile:hextile-knockout`, …). Runner: `bash "$PLUGIN_ROOT/pipe/scripts/fp-run.sh" <tool> …`; doctor: `pipe/scripts/fp-doctor.sh`. Requires `pip install -r pipe/requirements.txt` (Pillow; numpy optional). Full reference: [`pipe/README.md`](pipe/README.md).

## /360-hextile:upres

GPU Real-ESRGAN upres through the running 360 Hextile app. Skill name is **`/360-hextile:upres`** (not bare `/upres`; the description also triggers on `/upres`). Not `hextile-pipe`. Do not invent `upscale_image`.

| Input | Door |
|-------|------|
| One still | `run_workflow` + builtin `upres-still` (`pipeline: realesrgan`) |
| Folder of stills, or video | sequence tools (`extract_sequence_video` if video, then `create_sequence` / `start_sequence` / `get_sequence`) |

`run_workflow` cannot create a `seq_*`. Folder and video must use the sequence tools.

### Hosts

Install id stays **`360-hextile@360-hextile`**. Hosts do **not** auto-update.

| Host | How `/360-hextile:upres` lands |
|------|---------------------------|
| **Claude Code** | Plugin skills auto-discover from `plugin.json` `"skills": "./skills/"` after `/plugin install 360-hextile@360-hextile` (or marketplace update + `/plugin update 360-hextile`). |
| **Grok** | Same-repository local source in `ansonphong/360-HEXTILE-PLUGINS`: `grok plugin marketplace update` then `grok plugin update 360-hextile`. |
| **Codex** | `codex plugin add 360-hextile@360-hextile` (or `python3 codex/install.py`, which writes `~/.agents/skills/upres/SKILL.md`). |

## Selected tools

| Tool | HTTP / source |
|------|----------------|
| `list_workflows` | `GET /api/workflows` |
| `get_workflow` | `GET /api/workflows/{origin}/{id}` |
| `get_capabilities` | `GET /api/workflows/capabilities` |
| `describe_image` | `POST /api/prompts/describe-source` (local vision, 300s) |
| `get_live_context` | `GET /api/agent/live-context` |
| `apply_config_delta` | `POST /api/agent/apply-live` |
| `save_workflow` | `POST /api/workflows/{user\|project}` |
| `delete_workflow` | `DELETE /api/workflows/{origin}/{id}` |
| `run_workflow` | `POST /api/workflows/run` |
| `validate_config` | same, `dry_run: true` |
| `get_status` | `GET /api/renders/{id}` |
| `get_render_config` | `GET /api/renders/{id}/config` |
| `get_logs` | `GET /api/renders/{id}/logs` |
| `list_runs` | `GET /api/renders/` |
| `cancel_run` | `POST /api/renders/{id}/stop` |
| `retry_run` | `POST /api/renders/{id}/retry` |
| `generate_seed` | `POST /api/360-lora/generate` |
| `list_seed_history` | `GET /api/360-lora/history` |
| `get_seed_batch` | `GET /api/360-lora/history/{batch_id}` |
| `cancel_seed` | `POST /api/360-lora/cancel` |
| `list_360_loras` | `GET /api/360-lora/loras` |
| `list_installed_models` | `GET /api/models/{pipeline_id}?installed_only=true` |
| `get_guide` | bundled `skills/360-hextile/references/*.md` |
| `extract_sequence_video` | `POST /api/sequences/extract-video` |
| `create_sequence` | `POST /api/sequences/create` |
| `start_sequence` | `POST /api/sequences/{id}/start` |
| `get_sequence` | `GET /api/sequences/{id}` |
| `list_sequences` | `GET /api/sequences/` |
| `stop_sequence` | `POST /api/sequences/{id}/stop` |
| `get_local_access_status` | `GET /api/agent/mcp-status` |
| `local_file_stat` | `GET /api/agent/local-files/stat` |
| `local_file_read` | `GET /api/agent/local-files/read` |
| `local_file_write_begin` | `POST /api/agent/local-files/writes` |
| `local_file_write_append` | `POST /api/agent/local-files/writes/{write_id}/chunks` |
| `local_file_write_abort` | `POST /api/agent/local-files/writes/{write_id}/abort` |
| `local_file_write_commit` | `POST /api/agent/local-files/writes/{write_id}/commit` |
| `local_file_write_status` | `GET /api/agent/local-files/writes/requests/{request_id}` |

Enable **MCP** in Settings; use **Disconnect** to block fresh work. File tools forward only to APP loopback; `local_file_write_status` can reconcile the original `request_id` after Disconnect.

Instruction surface: **`skills/360-hextile/SKILL.md`** (general automation hub), **`skills/shader/SKILL.md`** (authoritative Shader file procedure), **`skills/fractal/SKILL.md`** (Fractal Workshop), **`skills/upres/SKILL.md`** and the Pipe **`skills/hextile-*/SKILL.md`** matte skills.
Codex `AGENTS-fragment.md` is a frontmatter-stripped copy of the hub — edit SKILL only.
A temporary installer destination does not prove an installed host.

### Shader authoring in your coding host

The `shader` skill edits the open Project Shader through the complete acknowledged member set, registers a raw-byte framed digest and polls real APP Prepare/compiler receipts, with at most three repairs. APP automatically Applies and saves a singular ready `spt_` / `cpr_` candidate through the native writer. Registration alone does not prove Save; inspect the exact saved receipt, and keep unknown Save unknown. Installed MCP connectivity and native access to the same physical Project/worktree files are both required; a remote connector alone is insufficient. APP verifies current ownership, source and CAS; the host controls its own filesystem permissions. Reasoning belongs to your host account/provider and may incur charges or quota limits.

Claude prefixes plugin skills with the plugin name: `/360-hextile:360-hextile` (hub), `/360-hextile:shader`, `/360-hextile:fractal`, `/360-hextile:upres`. Codex uses separately installed sibling skill directories (`360-hextile`, `shader`, `fractal`, `upres`): confirm them in the installed picker. Check actual Codex/Grok invocation syntax on the installed client; source layout does not prove an installed host.

Open a clean Project or My Library Shader in Workshop, enable MCP, then invoke the installed skill with your requested change. If open acknowledgement is unknown, preserve files and reconnect; never edit presumed paths. Timeout or exhausted repairs includes the last exact receipt and instructions to re-enter this same host skill. APP Retry rechecks a candidate; it cannot wake an idle coding host. Playable and input-adapter guidance is conditional on observed executable support, not merely document declarations. Neither compiler pass nor a preview certifies physical input behavior or saving.

### Native Shader and Fractal output

Read `get_capabilities` and require `native_render.contract:"native-render/1"`
before new render semantics. Its bounded native limits describe supported sizes,
projections, quality and supersampling; native admission still checks the saved
source, Project, destination and owner. An older APP must report upgrade required,
never silently remove a setting or change direct output into a managed copy.

Shader sequences accept a chosen `folder_export` PNG/JPG destination and optional
hundredth supersampling1.00–2.00, including1.25. The native writer saves that format
in that folder. Explicit deferred masters and later export remain available.
Fractal sequences retain their native PNG masters and existing publication path;
optional `destination_intent` freezes the chosen later PNG/JPG publication.

Preflight and submit the same immutable request/key. Inspect existing output with
`inspect_shader_sequence_output` or `inspect_fractal_sequence_output`; matching
unfinished work can use the existing control tool's `continue` action with the
same request and inspection fingerprint. Poll native run/revision, ownership,
checking/replay/rendering/saving, committed count and contiguous cursor separately.
Stop targets the observed run; a stale409 needs a fresh read. Unknown replies keep
the original IDs and remain unknown until reconciled. No automatic new-key retry.

Still tools add `shader-raster-still/1` for direct PNG/JPG in equirectangular or
either Dome projection. Linear EXR also accepts native Dome geometry. Existing
`png-master/1` keeps its managed Render/import semantics. Still capture uses the
actual mounted Shader writer and completed frame; no caller-supplied capture or
preview packet. `capture_fractal_still` uses the current finished360preview, then
ordinary file export publishes that exact Render/node. A known capture is not a
successful destination export; an unknown mint is never automatically repeated.

These are canonical/source contracts. Installed catalogs and actual native output
need their own qualified activation; source or vendor synchronization alone does
not establish installed-host support. See the Shader/Fractal skills for controls.

### Ordinary render file export

Call `preflight_file_export` with an exact `render_id`, `source_node_id`, selected existing `folder_path`, Windows-safe basename `output_name`, `projection`, and `encoding`. It performs no writes and returns the source revision, exact output paths, blockers, and output fingerprint. Review those paths and obtain approval for the exact options before calling `export_render_file` with the same arguments plus the returned `source_revision` and `output_fingerprint`.

`export_render_file` calls the app's encoder once with `create_only: true`; an existing destination returns a collision instead of being replaced. If the source or derived output names changed, preflight again and obtain new approval. A timeout or lost connection leaves the outcome unknown: inspect the destination before considering a new attempt. These tools accept neither HDRI nor Unreal-project export arguments and never encode files in the plugin.

### Describe an exact local image

`describe_image` accepts `source: {"kind":"render_node","render_id":"...","node_id":"..."}` or `source: {"kind":"local_file","path":"/absolute/image.png"}`. Optionally add `crop: {"yaw":15,"pitch":-10,"fov":70}` for a 2:1 equirectangular panorama. The app resolves the exact source and runs local vision; the MCP proxy never opens the image. Approve the local compute/GPU call before invoking it. The result is text (`prompt`, source identity, mode, crop and image signature), never raster data. URLs, base64 and implicit current-selection sources are not accepted.

### Device-local Hotkeys

`list_hotkeys` reads the current profile, revision, effective bindings and availability;
`inspect_hotkey` explains one action and optional candidate bindings, conflicts and overlaps.
The app must be open; a mounted render document is not required.
Bindings use `meta_key` for the Meta modifier and `slash` for the slash key.

Start `list_hotkeys` with `{}`. Each page contains at most 20 actions plus `total`
and `next_cursor`; pass that cursor unchanged on the next call until it is null.
Pages share one profile revision. If continuation returns `stale_revision`,
discard the partial listing and restart without a cursor.

Read before every edit and approve the exact action, bindings and returned `revision`.
`set_hotkey_bindings` replaces the complete alias list (`[]` unbinds),
`remove_hotkey_binding` removes one assigned chord, `restore_hotkey` restores one
customized row, and `reset_hotkeys` clears all overrides including inert unknown IDs.
Reset leaves the separate single-key switch unchanged. Conflicts never silently
reassign another action. A stale revision requires a fresh read and new approval.
Only an explicit reset can replace a future-format profile.

If a write returns `hotkeys_outcome_unknown`, its effect is uncertain. Never replay
it automatically: re-read the profile, inspect the actual bindings, and obtain a
new approval only if another mutation is still needed.

## App not running

Every tool returns a structured error, roughly:

> 360 Hextile isn't running. Launch 360 Hextile, then retry.

The proxy never hangs waiting for the app at startup.

## curl fallback

If python3 / MCP is unavailable, agents can still drive the API — see the curl appendix in `skills/360-hextile/SKILL.md`.

```bash
curl -s http://127.0.0.1:8000/api/workflows
curl -s -X POST http://127.0.0.1:8000/api/workflows/run \
  -H 'Content-Type: application/json' \
  -d '{"workflow_id":"quick-scout","origin":"builtin","dry_run":true}'
```

## Layout

```
360-HEXTILE-PLUGINS/plugins/360-hextile/
  .claude-plugin/plugin.json
  .codex-plugin/plugin.json
  .mcp.json
  skills/360-hextile/SKILL.md
  skills/360-hextile/references/
  skills/shader/SKILL.md
  skills/fractal/SKILL.md
  skills/upres/SKILL.md
  skills/hextile-*/SKILL.md      Pipe matte skills
  mcp/hextile_mcp.py
  mcp/hextile_client.py
  codex/install.py
  codex/AGENTS-fragment.md
  pipe/                          matte/, scripts/, illustrator/, photoshop/, references/
  tests/
  README.md
```

The marketplace catalogs live at the repository root (`.claude-plugin/`, `.agents/plugins/`, `.grok-plugin/`).

## Develop / test

```bash
python3 -m py_compile mcp/hextile_client.py mcp/hextile_mcp.py codex/install.py
python3 -m pytest tests/test_tool_list_drift.py -q

# Codex installer smoke (temp HOME)
python3 -m pytest tests/test_codex_skill_discovery.py -q
python3 codex/install.py --home /tmp/hextile-codex-test
python3 codex/install.py --uninstall --home /tmp/hextile-codex-test

# Pipe
bash pipe/scripts/test-plugin.sh
bash pipe/scripts/smoke-matte-flags.sh
python3 -m pytest pipe/matte/test_trim.py -q
```

## Docs

Bundled agent guides: `get_guide` (`workflow-schema`, `best-practices`, `website-index`, `recipes`, `shader-cookbook`).
`website-index` points at **existing** https://360hextile.com/docs/ pages (templates, pipelines, input, prompts). A dedicated Automation docs section is still 06-docs.

## License

Everything outside `pipe/` and the `hextile-*` skills is MIT, as published in the former `360-hextile-agent` repository.

`pipe/` and the `skills/hextile-*` matte skills come from the former `hextile-pipe` repository, which was published without an open-source license (`UNLICENSED`, © Phong, all rights reserved). Consolidating them here does not change that licensing.
