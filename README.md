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
