# 🌐 360 Hextile — agent marketplace

Agent tools for **360 artists**. Add the catalog once. Install a plugin. Start working.

| | |
|:--|:--|
| **Marketplace** | `360-hextile` |
| **GitHub** | [ansonphong/360-hextile-plugins](https://github.com/ansonphong/360-hextile-plugins) |
| **On disk** | `D:\Projects\360-HEXTILE\360-hextile-plugins` |

This repo is the **catalog** (an index). Product code lives in each plugin’s own git repo. Codex and Grok install those repos by HTTPS URL + SHA. Claude uses the `plugins/` gitlinks in this clone.

Host pins follow the canonical `360-hextile` commit. Claude records that commit as the `plugins/360-hextile` gitlink. Codex records it as the SHA in `.agents/plugins/marketplace.json`. Grok records it as the SHA in `.grok-plugin/marketplace.json`.

---

## Install

Add **one** marketplace source. Then install the plugins. Marketplace add does not install them.

Use the **GitHub** catalog. Do not also add the local disk path — two sources with the same name make `360-hextile` ambiguous.

<details open>
<summary><strong>Claude Code</strong></summary>

```text
/plugin marketplace add ansonphong/360-hextile-plugins
/plugin install hextile-pipe@360-hextile
/plugin install 360-hextile@360-hextile
```

Then:

```text
/hextile-pipe doctor
```

Claude install id is **`360-hextile@360-hextile`**. Never `hextile@360-hextile`.

</details>

<details open>
<summary><strong>Grok</strong></summary>

```text
grok plugin marketplace add ansonphong/360-hextile-plugins
grok plugin install hextile-pipe --trust
grok plugin install 360-hextile --trust
grok plugin enable hextile-pipe
grok plugin enable 360-hextile
```

Reload (`r` in `/plugins`) or start a new session.

Grok install names are **`hextile-pipe`** and **`360-hextile`**. Not `hextile`. Not the old name `hextile-agent`. Not `360-hextile@ansonphong/360-hextile-plugins` (`@` on `grok plugin install` is a git ref, not a marketplace pin).

Enable in `/plugins` or `~/.grok/config.toml` `[plugins].enabled`. Trusted MCP needs `--trust`.

Studio disk clone (only if you did **not** add the GitHub source):

```text
grok plugin marketplace add D:\Projects\360-HEXTILE\360-hextile-plugins
```

A local-path marketplace does not move on `grok plugin marketplace update`. After a catalog pin, run `grok plugin update 360-hextile`. Prefer GitHub so `marketplace update` pulls origin.

</details>

<details open>
<summary><strong>Codex</strong></summary>

```text
codex plugin marketplace add ansonphong/360-hextile-plugins
codex plugin add hextile-pipe@360-hextile
codex plugin add 360-hextile@360-hextile
```

Use a current Codex CLI with `codex plugin` support. The `360-hextile` plugin includes its skills and the bundled `hextile` stdio MCP proxy; a separate agent clone or installer is not required. Git and Python 3.9 or newer are prerequisites, and `python3` must be available to the agent. Start a new Codex session after installation and check `/mcp` for `hextile`. Keep 360 Hextile open on the same computer at `127.0.0.1:8000`.

Local catalog checkout: `codex plugin marketplace add D:\Projects\360-HEXTILE\360-hextile-plugins`.

</details>

---

## Plugins

| Plugin | What it is | Claude / Codex | Grok |
|:-------|:-----------|:---------------|:-----|
| **hextile-pipe** | Studio matte and Adobe helpers. Whiten, cutout, knockout, despeckle, trim. | `hextile-pipe@360-hextile` | `hextile-pipe` |
| **360-hextile** | Drive the 360 Hextile app. Workflows, renders, 360-LoRA, GPU upres via `/360-hextile:upres`, over localhost HTTP. 28 MCP tools. | `360-hextile@360-hextile` | `360-hextile` |

| Plugin | Product repo |
|:-------|:-------------|
| hextile-pipe | [ansonphong/hextile-pipe](https://github.com/ansonphong/hextile-pipe) |
| 360-hextile | [ansonphong/360-hextile-agent](https://github.com/ansonphong/360-hextile-agent) |

---

## After install

```text
/hextile-pipe doctor
/hextile-knockout path/to/file.png
```

`360-hextile` talks to a local 360 Hextile instance on `127.0.0.1:8000`. Open the app first. If the app is down, tools return a clean error; the MCP process stays up. `get_guide` works without the app.

---

## Layout

```text
360-hextile-plugins/                 this catalog
  .claude-plugin/marketplace.json    name: 360-hextile  (local plugin paths)
  .agents/plugins/marketplace.json   name: 360-hextile  (git URL + SHA)
  .grok-plugin/marketplace.json      name: 360-hextile  (git URL + SHA)
  plugins/
    hextile-pipe/                    gitlink → ansonphong/hextile-pipe
    360-hextile/                   gitlink → ansonphong/360-hextile-agent
```

All three marketplace JSON `"name"` fields stay **`360-hextile`**. Codex freezes upgrades if that name drifts.

Codex and Grok do **not** init git submodules. Both indexes point at each product repo (`url` + `sha`), not at `./plugins/…`. Claude uses the gitlinks.

If a host rejects a leading-digit marketplace id, rename the tech id to **`hextile-360`** in all three indexes. Same tokens everywhere. Do not use a bare `hextile` marketplace name.

---

## Refresh a plugin

Ship in the product repo, then move this catalog’s pin.

```bash
./scripts/sync-hextile-pipe.sh      # gitlink + Codex/Grok SHA → hextile-pipe
./scripts/sync-360-hextile.sh       # gitlink + Codex/Grok SHA → 360-hextile
# append --push when origin should move too
```

Already current: exit 0, prints `already up to date` with short SHA + version.

Hosts do **not** auto-update. After the pin is on GitHub:

| Host | Then |
|:-----|:-----|
| Claude | marketplace update `360-hextile`, then `/plugin update 360-hextile` |
| Grok | `grok plugin marketplace update` then `grok plugin update 360-hextile` (and pipe) |
| Codex | `codex plugin marketplace upgrade 360-hextile` |

---

Private studio catalog unless you add a LICENSE.
