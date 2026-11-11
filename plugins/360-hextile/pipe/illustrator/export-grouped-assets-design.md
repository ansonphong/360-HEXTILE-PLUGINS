# Export Grouped Assets — Design

**Status:** design locked — depth hierarchy + naming  
**Target script:** `ExportGroupedAssets.jsx` (ExtendScript, Adobe Illustrator)  
**Related brief:** `artboard-export-all-groups.md` (original production brief; this design **overrides** naming and clarifies selection)  
**Version target:** 0.2.8  
**Design revision:** 2026-08-13 — selected **page items** export (groups or ungrouped); mixed siblings stay in the sequence; names still prefix + depth tokens only.

---

## 1. Purpose

Batch-export **selected Illustrator page items** (groups or ungrouped art) as multi-format assets without renaming layers or modifying the source document.

**Primary user flow**

1. Select the objects to export (grouped or not — e.g. 5 beachball variants).
2. Run the script → a dialog appears.
3. Enter a **series prefix** once (e.g. `beachball-`), choose folder/formats/PNG options.
4. Export produces numbered files: `beachball-01`, `beachball-02`, …

Next batch can use a different prefix (`soccerball-`) with no document renames.

---

## 2. Goals and non-goals

### Goals

- Export **selected page items** discovered from the selection at the chosen **depth** (1–3). Groups and ungrouped art both count.
- Formats: native **AI**, **SVG**, transparent **PNG** (user can enable any non-empty subset).
- **Prefix + hierarchical sequence** filenames defined **per export run** in the dialog (flat folder).
- Leave the original document **unchanged** (no save, no rename, no move, no expand/outline/rasterize).
- Isolate failures per asset; continue the batch; write a report.

### Non-goals

- Artboard-targeted export (“everything on artboard X”).
- Using Illustrator **group / layer names** as file names (names ignored; nesting structure used at depth > 1).
- Hierarchy mirrored as nested folders on disk (filenames carry structure).
- Computer vision, auto-grouping, or semantic detection.
- CEP/UXP panels, plugins, Node, or external packages.
- Print-oriented **DPI/PPI** control in v0.1 (pixel size only; see §7).
- Renaming groups inside the document to match export names.

---

## 3. Product decisions (brainstorm outcomes)

| Topic | Decision |
|--------|----------|
| What is exported | **Currently selected** drawable page items (groups **and** ungrouped art). Guides / non-art skipped. |
| Artboard as source | **No** — artboards are only temporary export frames |
| File naming | **Prefix + depth hierarchy tokens + zero-padded numbers** (see §6 / §6.6) |
| Group / object name | **Ignored** for filenames (structure only — child page items) |
| Depth | **1–3** — how far to expand selected objects into export units |
| When naming is entered | Script launch → **ScriptUI dialog** → prefix + depth → Export |
| Number series | Leaf sequence uses Start # + pad; intermediate numeric segments start at 1 |
| Root order (A/B/C…) | **Selection order** after de-dupe — not re-sorted by layer stack (avoids inverted A/B/C) |
| Child order inside a vessel | Stacking order **within that parent** (siblings only) |
| Output layout | **One flat folder by default** (hierarchy lives in the filename) |
| Output layout | **Per format:** top-level dump **or** `AI/` `SVG/` `PNG/` subfolder (independent) |
| Hierarchy folders | **Not used** — no A/01/ series dirs; names only |
| Source safety | Hard rule: never modify/save/close the source document |

---

## 4. End-to-end workflow

```
Select objects in Illustrator
        ↓
File > Scripts > Other Script… (or installed Scripts menu entry)
        ↓
Dialog: Export Grouped Assets
  • Output folder
  • Naming: prefix, depth (1–3), start #, pad digits
  • Formats + PNG / file options
        ↓
[Export]  →  expand selection by depth → for each export unit:
              temp doc → duplicate leaf item → artboard → export formats
              close temp doc (no save)
        ↓
Summary dialog + export-report.txt
```

**Cancel** on the dialog: no export, no document changes.  
**Mid-batch cancel: NONE in v0.1** (locked — see §11). The batch runs to completion; per-asset failures are isolated and logged.

---

## 5. Selection rules

1. Process selected **drawable page items** as **roots** (after highest-ancestor de-dupe). Groups and ungrouped art both qualify.
2. **Depth** expands each root into one or more **export units** (the item duplicated and exported). Depth 1: root itself. Depth 2–3: walk child page items (see §6.6).
3. If a parent item and a nested descendant are both selected as roots, process **only the highest selected ancestor** (no duplicate roots).
4. Skip only non-art (guides, layers, text ranges). Count those as skipped in the summary. Do **not** skip ungrouped paths, compounds, symbols, or text frames.
5. Do **not** auto-process all objects in the document outside the selection+depth walk.
6. Do not rearrange, rename, resize, move, expand, outline, flatten, or delete anything in the source.
7. A `GroupItem` is still a nestable vessel. Ungrouped siblings of a group are their own export units at that depth — they are not dropped. A group that contains only non-groups is still one leaf unless depth harvest splits an all-path vessel (existing MOON-A case).

### Selection API pitfalls (locked handling)

- `doc.selection` is **`null`** when nothing is selected (not an empty array) — guard before iterating.
- With a text insertion point / text-edit mode active, `doc.selection` can return a **TextRange**, not an array — check `instanceof Array` (or `typename`) before treating it as items.
- Copy `doc.selection` into a plain array **once** at start; repeated `.selection` access is slow and can re-evaluate.
- When a whole group is selected normally, its children do NOT appear separately in `selection`; parent+child both present happens via Layers-panel targeting or direct-select — which is why rule 3 exists.
- **Highest-ancestor filter (locked algorithm):** for each selected page item, walk `item.parent` upward until `typename === "Layer"` or the document; if any ancestor along the way is itself in the selected-items set, drop the descendant. Membership test uses `===` reference equality — **VERIFY** in Illustrator that two references to the same item compare `===` true; if flaky, fall back to `PageItem.uuid` (present in recent CC — VERIFY availability).

### Number / series order — LOCKED algorithm

#### Roots (letter A, B, C… at depth 2–3, or depth-1 leaf index)

**Use selection order**, not layer-stack re-sort.

1. Copy `doc.selection` once into an array (left → right as returned).
2. Filter to exportable page items (drop guides / non-art); apply highest-ancestor de-dupe **without reordering** the remaining roots.
3. Root index `0` → letter `A` / first series; `1` → `B`; etc.

**Why:** Sorting roots by layer stacking (top → bottom) **inverted** user-selected series (select A then B then C exported as C, B, A). Selection order matches “the order I picked them.”

**Do NOT** re-sort roots with `sortGroupsByStacking` or `zOrderPosition`.

**Note:** Illustrator’s selection array order is usually click / multi-select order, but can vary by version. If a host ever returns roots reversed, reverse once after de-dupe — default is forward selection order.

#### Children inside one vessel (B-01, B-02… / nested leaves)

Still use **stacking order within that parent only** (index path among siblings) so moons inside a set stay visually stable regardless of click order:

1. Sibling index in `container.pageItems` / `groupItems` (frontmost / panel order as implemented).
2. `zOrderPosition` still **banned**.

Multi-artboard: ignored for sequencing.

Dialog note:

> Root series A, B, C… = selection order · Children inside a set = stack order

---

## 6. Naming design

### 6.1 Dialog fields

| Field | Type | Default | Notes |
|--------|------|---------|--------|
| Prefix | text | empty | Required stem; trailing `-` optional (script normalizes) e.g. `ICOSA-SOLID` or `ICOSA-SOLID-` |
| Depth | integer 1–3 | `1` | How deep to expand objects inside the selection (see §6.6) |
| Start number | integer ≥ 0 | `1` | Applied to the **leaf** numeric segment only |
| Pad digits | integer 1–6 | `2` | All numeric segments use this pad; never truncates |

### 6.2 Filename construction — LOCKED patterns

Join segments with a single hyphen. Normalize prefix: trim; strip trailing hyphens; then join.

| Depth | Pattern | Example |
|-------|---------|---------|
| **1** | `PREFIX-##` | `ICOSA-SOLID-01` |
| **2** | `PREFIX-A-##` | `ICOSA-SOLID-A-01` |
| **3** | `PREFIX-A-##-##` | `ICOSA-SOLID-A-01-01` |

**Segment rules:**

| Segment | Rule |
|---------|------|
| `PREFIX` | Dialog stem after normalize (group names never used) |
| Letter `A` | Depth 2–3: index among **selected roots in selection order** → `A`…`Z`; if more than 26 roots, zero-padded numbers (`27`, …) |
| Intermediate `##` (depth 3 only) | Child-group index **within its parent**, start at **1**, stacking among siblings |
| Leaf `##` | Depth 1 = root index in selection order; depth 2–3 = sibling leaf index under parent (stacking). Uses **Start #** + pad |

```
baseName = sanitize( joinHyphen( prefixStem, depthTokens... ) )
```

Depth 1 examples (prefix `ICOSA-SOLID`, start `1`, pad `2`):

| Index | Base name |
|-------|-----------|
| 0 | `ICOSA-SOLID-01` |
| 1 | `ICOSA-SOLID-02` |

Depth 2 examples (two outer groups A/B, each with two child groups):

| Path | Base name |
|------|-----------|
| root0 / child0 | `ICOSA-SOLID-A-01` |
| root0 / child1 | `ICOSA-SOLID-A-02` |
| root1 / child0 | `ICOSA-SOLID-B-01` |

Depth 3 example:

| Path | Base name |
|------|-----------|
| root0 / mid0 / leaf0 | `ICOSA-SOLID-A-01-01` |
| root0 / mid0 / leaf1 | `ICOSA-SOLID-A-01-02` |
| root0 / mid1 / leaf0 | `ICOSA-SOLID-A-02-01` |

Extensions per format: `.ai`, `.svg`, `.png`.

### 6.6 Depth expand — LOCKED (objects inside the selection)

**Depth** is not “how nested the art looks”; it is **how many levels to walk from each selected root** to find export units (the page item that is duplicated and exported).

| Depth | User selects | Export unit (duplicated) | Name shape |
|-------|----------------|---------------------------|------------|
| **1** | Any drawable objects | Each selected item itself | `PREFIX-##` |
| **2** | Outer “series” vessels | **All siblings** inside each root (groups **and** ungrouped art); unwrap a single wrapper group; if none, nested leaf groups; if still none, split all-path contents or export the root | `PREFIX-A-##` |
| **3** | Top “family” vessels | Each grandchild page item (child of child). An ungrouped mid is one leaf (`A-##-01`) | `PREFIX-A-##-##` |

**Child discovery:** all exportable `pageItems` of the parent (groups via the dual `groupItems`/`pageItems` walk, plus ungrouped siblings). Mixed children stay in one sequence — do **not** drop loose paths because a sibling group exists.

**Empty / shallow trees:**

- Depth 2 root with **zero** child groups → skip that root; record failure reason `no child groups at depth 2`.
- Depth 3 root/mid with missing intermediate groups → skip that branch; record reason.
- Do **not** silently fall back to exporting the outer composite unless depth is 1.

**Order:**

1. Selected roots stay in **selection order** (§5) — letter `A` = first selected root, not topmost layer.
2. Within each parent, sort child / harvested items by stacking order **within that container**.
3. Letter `A` tracks root selection order; numeric mids/leaves track sibling order under their parent.

**Still ignored for names:** Illustrator group/layer display names. Nesting structure + dialog prefix only.

### 6.3 Sanitization (`sanitizeFilename`)

- Trim leading/trailing whitespace on the full base name.
- Replace Windows-invalid characters: `< > : " / \ | ? *`
- Remove trailing periods and spaces.
- Protect Windows reserved names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) by suffixing or prefixing safely (e.g. `_CON`).
- Preserve Unicode where OS + Illustrator allow.
- **Do not** use group names as input.

### 6.4 Collisions — LOCKED

- Collision detection across **all enabled formats** for that base name (one base name must be free — or overwritten — in every enabled format's target path).
- Overwrite **off** (default): append `_002`, `_003`, … to the base name until free in **all** enabled formats. Never skip, never abort.
- Overwrite **on**: replace existing files at the exact target paths. No suffixing.
- Flat-folder browsing: all basenames land in the same directory (unless format subfolders opt-in).

### 6.5 Explicitly not used

- Illustrator group / layer **names** as filename tokens
- Artboard name
- Nested hierarchy folders on disk (`A/01/…`)
- Document name (except in the report metadata)

---

## 7. PNG sizing (and DPI)

### Controls

| Control | Default | Behavior |
|---------|---------|----------|
| Target pixel size | `2048` | **Hard maximum** longest edge (and square edge) in pixels — **never overshoot** |
| Canvas mode | Square canvas | See below |
| Padding % | `5` | Inside the artboard before scale-to-max (does **not** add pixels beyond target) |
| Transparent background | always on | |
| Anti-aliasing | always on | |

### HARD RULE — no pixel overshoot (LOCKED)

- Dialog **Target size** = **MAX** dimension in pixels, not a soft estimate.
- After PNG export, longest side must be **≤ target** (e.g. target 2048 ⇒ never 2053).
- Prefer as close to target as possible without going over (may land at `target` or a few px under if AI rounding requires it).
- Padding % only grows the **vector artboard in points**, then scale is chosen so predicted pixels stay ≤ target.
- `horizontalScale === verticalScale` always (no stretch).

**Why old exports hit 2053:** naive `scalePct = target/side*100` + float artboards + Illustrator’s %→pixel rounding could **round up**. Implementation must use a **no-overshoot scale** (see `calculatePngScalePct`): predict pixels with conservative rounding and step scale down until `ceil`/`round` prediction ≤ target.

### Modes — LOCKED math

Work on the **duplicated** item in the temp doc. From `visibleBounds = [left, top, right, bottom]` (Y-up: `top > bottom`):

```
w   = right - left        h   = top - bottom
pad = (paddingPct / 100) * max(w, h)
padded = [left - pad, top + pad, right + pad, bottom - pad]
paddedW = w + 2*pad       paddedH = h + 2*pad
cx = (left + right) / 2   cy = (top + bottom) / 2
```

PNG24 with artboard clip: approximately  
`pixels ≈ artboardSidePoints × (scalePct / 100)` (1 pt ≈ 1 px at 100%).

**Tight bounds**

- `artboardRect = padded` (aspect preserved).
- `side = max(paddedW, paddedH)`.
- `scalePct = calculatePngScalePct(side, target)` → **longest PNG side ≤ target**; shorter side follows aspect (variable, always ≤ longest ≤ target).
- No stretch.

**Square canvas** (default)

- `side = max(paddedW, paddedH)`; square artboard centered on `(cx, cy)`.
- Same `scalePct = calculatePngScalePct(side, target)` → both edges **≤ target** (aim both equal and as close to target as possible without overshoot).
- Aspect of art preserved; transparent letterbox.

**`calculatePngScalePct(sidePts, targetPx)` contract (pure helper):**

1. `target = floor(targetPx)`.
2. Start from ideal `scale = target * 100 / sidePts`.
3. While predicted pixel length (using **ceil** and **round** of `sidePts * scale / 100`) **> target**, reduce scale until both predictions ≤ target.
4. Return that scale (or null if inputs invalid).
5. Property tests: for representative sides, `predicted ≤ target` always.

**Invalid bounds:** if `w` or `h` ≤ 0.001 pt, or non-finite, skip asset (batch continues).

### DPI / PPI

**v0.1: no DPI field.** Output is defined in **pixels** only.  
Illustrator’s PNG24 export may set an internal resolution; implementation should use documented PNG24 options and document the effective value in README after real testing. Print “inches @ 300 DPI” is out of scope until requested.

### Bounds

- Prefer `visibleBounds` over `geometricBounds` so strokes count.
- Bounds array order: `[left, top, right, bottom]`; `top > bottom` numerically (Y up). All height math is `top - bottom`.
- Isolate in `getEffectiveBounds()`; skip zero/invalid bounds with a per-asset error (see Modes above).
- **Known Illustrator footguns — these are §20 test items, not code assumptions:**
  - **Clipped groups:** `visibleBounds` of a clip group has historically returned the bounds of ALL content, ignoring the mask, in some versions. Test with a clip-mask group; if oversized, mitigation is: when `group.clipped === true`, use the bounds of the clipping path (`pathItem.clipping === true`) instead.
  - **Raster live effects** (drop shadow, blur, outer glow): may NOT be included in `visibleBounds`. Test; if clipped output matters, padding is the v0.1 mitigation, not bounds surgery.
  - **Point text:** bounds may reflect the em box/leading, not tight ink extents. Test; accept the slack in v0.1.
  - **Placed/linked art and brushes:** bounds may deviate from rendered extents. Test representative cases.

### AI / SVG sizing

- Keep vector scale as in the source group.
- Fit temp artboard to padded visible bounds (not forced to PNG target).
- Do not rescale vectors just to match PNG pixel size.
- Crop export to artboard; preserve editability where the format allows.

---

## 8. User interface

**Title:** `Export Grouped Assets`  
**Shown when:** script starts (before any export).

### Sections

**Output folder**

- Path field + Browse (`Folder.selectDialog()` — classic OS dialog; **not** a Windows 11 modern IFileDialog; ExtendScript cannot provide that without UXP/CEP).
- Prefills from **persistent prefs** when present (see §8.1).

**Naming**

- Prefix (required) — stem e.g. `ICOSA-SOLID` (prefills from last export when stored)
- Depth dropdown: **1 / 2 / 3** (default 1; prefills from last export when stored)
- Start number (leaf segment)
- Pad digits
- Live preview from depth pattern e.g. `ICOSA-SOLID-A-01`, …
- Note: order = layers top → bottom; group **names** ignored; structure used at depth > 1

**Formats** (each row = enable + where it lands)

| Enable | Format | Top-level checkbox | If top-level off |
|--------|--------|--------------------|------------------|
| ☑ | AI | ☑ Top-level (default on) | → `AI/` subfolder |
| ☑ | SVG | ☑ Top-level (default on) | → `SVG/` subfolder |
| ☑ | PNG | ☑ Top-level (default on) | → `PNG/` subfolder |

- At least one format enabled.
- **Grug rule:** “Top-level” means file goes in the **output folder root**. Unchecked means that format uses its named subfolder.
- Example (PNG top-level on; SVG/AI top-level off):

```
MOON/
  MOON-A-01.png
  SVG/MOON-A-01.svg
  AI/MOON-A-01.ai
```

- All three top-level on → fully flat (previous “subfolders off”).
- All three top-level off → classic AI/SVG/PNG split (previous “subfolders on”).
- Hierarchy-as-folders (A/01/) still **not** offered.

**PNG settings** (enabled when PNG checked)

- Target pixel size (default 2048)
- Canvas mode: Tight bounds | Square canvas (default Square)
- Padding % (default 5)

**File settings**

- Overwrite existing files (default off)
- Open output folder when finished (default off)
- ~~Single master “format subfolders” checkbox~~ — **replaced** by per-format Top-level (above)

**Label**

> Depth expands groups-within-groups. Files are named PREFIX-… in one folder — not from group names.

**Buttons:** Cancel · Export  

### 8.1 Persistent prefs — LOCKED

Remember **all Export dialog settings** from the last validated Export across script runs (not session-only).

| Key | Dialog control | Default if missing |
|-----|----------------|--------------------|
| `lastOutputFolder` | Output folder | empty |
| `lastPrefix` | Prefix | empty |
| `lastDepth` | Depth 1–3 | `1` |
| `startNumber` | Start # | `1` |
| `padDigits` | Pad digits | `2` |
| `exportAi` | Format AI | `true` |
| `exportSvg` | Format SVG | `true` |
| `exportPng` | Format PNG | `true` |
| `targetPx` | PNG target size | `2048` |
| `canvasMode` | `square` \| `tight` | `square` |
| `paddingPct` | Padding % | `5` |
| `overwrite` | Overwrite existing | `false` |
| `aiTopLevel` | AI files in output root (not `AI/`) | `true` |
| `svgTopLevel` | SVG in root | `true` |
| `pngTopLevel` | PNG in root | `true` |
| `openFolder` | Open folder when finished | `false` |
| ~~`subfolders`~~ | Legacy only — if present without top-level keys: `true` → all top-level false; `false` → all true | — |

**Store location (Windows-first, portable API):**

- Directory: `Folder.userData` + `/ExportGroupedAssets/`  
  (on Windows: under the Adobe/user Application Data userData root)
- File: `prefs.txt`
- Shape: `<userData>/ExportGroupedAssets/prefs.txt`

**Format:** plain text, one `key=value` per line (first `=` separates key from value). Booleans as `true`/`false`. Unknown keys ignored. Missing file → design defaults.

```
lastOutputFolder=D:\Exports\icosa
lastPrefix=ICOSA-SOLID
lastDepth=2
startNumber=1
padDigits=2
exportAi=true
exportSvg=true
exportPng=true
targetPx=2048
canvasMode=square
paddingPct=5
overwrite=false
aiTopLevel=true
svgTopLevel=true
pngTopLevel=true
openFolder=false
```

**Load (before dialog opens):**

1. Read prefs if present; corrupt/unreadable → defaults (never block dialog).
2. Prefill **every** dialog control from the table above.
3. **Stale folder rule:** if `lastOutputFolder` is set but the folder does **not** exist, **clear only the folder field**. All other settings still apply.
4. Invalid values for a single key fall back to that key’s default without discarding the rest.

**Save (when):**

- After **Export** validation succeeds, write **all** keys from the current dialog settings (before/after batch; must run even if some assets fail).
- Cancel → do not write.
- Browse alone → do not write.

**Browse:** `Folder.selectDialog()` — classic picker. No Win11-native picker.

### Validation — LOCKED behavior

**Before the dialog even opens (fail fast, alert + exit):**
- No document open (`app.documents.length === 0`) → alert "Open a document first."
- Selection empty/null, not an item array, or contains zero exportable page items after the highest-ancestor filter → alert "Select at least one object to export."

**On Export click (alert + stay in dialog, fix and retry):**
- Prefix empty after trim → "Prefix is required."
- Depth not in 1–3 → "Depth must be 1, 2, or 3."
- Start number not an integer ≥ 0, or pad digits not 1–6 → name the field and range.
- No format checked → "Enable at least one format."
- After expand, zero export units → "No objects to export at this depth." (alert; stay or exit cleanly)
- Output folder path missing on disk (stale/typed) → attempt `new Folder(path).create()`; if creation fails → "Can't create output folder."
- Writability probe: create the report file (or subfolders) before the first asset; failure → alert + stay in dialog. Never discover an unwritable folder on asset 1 of 40.

`zeroPad` pads but never truncates: start 95 + pad 2 over 10 files yields `…-95` … `…-104` — longer numbers are correct output, not an error.

---

## 9. Output structure

**Path rule (per format):**

```
if formatTopLevel:  outputFolder / basename.ext
else:               outputFolder / AI|SVG|PNG / basename.ext
```

`export-report.txt` always sits in **output folder root**.

**Default (all top-level on — fully flat):**

```
chosen-output-folder/
  MOON-A-01.png
  MOON-A-01.svg
  MOON-A-01.ai
  export-report.txt
```

**Mixed (PNG top-level; SVG + AI in subfolders):**

```
chosen-output-folder/
  MOON-A-01.png
  SVG/MOON-A-01.svg
  AI/MOON-A-01.ai
  export-report.txt
```

**All top-level off:**

```
chosen-output-folder/
  AI/…
  SVG/…
  PNG/…
  export-report.txt
```

No per-series or per-depth hierarchy folders.

---

## 10. Export process (per asset)

1. Keep a reference to the source document (`var sourceDoc = app.activeDocument`).
2. Create a temporary document matching the source color space: `app.documents.add(sourceDoc.documentColorSpace, w, h)`. Note `documents.add` makes the temp doc active — that's expected; restore with `sourceDoc.activate()` after.
3. **Duplicate strategy — LOCKED:** `srcGroup.duplicate(tempDoc.layers[0], ElementPlacement.PLACEATBEGINNING)` — the cross-document `PageItem.duplicate(relativeObject, placement)` form. This works in CC-era Illustrator and carries swatches/patterns/symbols into the temp doc automatically (fine — temp doc is discarded). **VERIFY once in Milestone 1** before building on it. Clipboard copy/paste is the fallback of last resort only if `duplicate()` is demonstrably broken — it destroys the user's clipboard and depends on app focus; do not reach for it first.
4. Measure effective bounds **on the duplicate**; apply padding; set `tempDoc.artboards[0].artboardRect` (§7 math — artboard centers on the art, so no move needed).
5. Export each enabled format.
6. Close temp doc **without** saving: `tempDoc.close(SaveOptions.DONOTSAVECHANGES)` — always, including on failure (try/finally).
7. Restore focus to the source document (`sourceDoc.activate()`).
8. Continue to next group.

**Batch-wide guards (locked):** wrap the whole batch in `app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS` (suppresses missing-font and similar modal dialogs during duplication) and restore the prior level in a finally. Color-space note: a CMYK source produces a CMYK temp doc; PNG/SVG export will color-convert — expected and acceptable in v0.1 (test in §20; don't add an RGB-convert option until asked).

### Source document safety (hard)

Must **never**:

- Save or close the source document
- Change source artboards or move/rename source art
- Expand appearance, outline text, rasterize, embed/relink in the source
- Delete source content

### AI export

- Editable `.ai` via documented save options
- Preserve vectors, clips, compounds, gradients/patterns, editable text where supported
- Compatibility setting isolated in one config function; document in README

### SVG export

- Crop to temp artboard; vector geometry; dedicated `createSvgOptions()`
- Prefer editable text by default; document portability tradeoffs
- ⚠ Artboard cropping is the known SVG trap — see §19 (`saveMultipleArtboards`) before writing this function

### PNG export

- PNG24, transparent, anti-aliased, artboard clip
- Scale from artboard dimensions for target pixel size (`createPngOptions()`)
- Do not permanently resize the source group

---

## 11. Errors, progress, report

- One asset failure does not abort the batch.
- **LOCKED (v0.1): no progress window, no mid-batch cancel.** A modally-launched ExtendScript blocks Illustrator's UI; ScriptUI palettes do not reliably repaint or receive clicks from a running script without fragile `app.redraw()`/`window.update()` pumping. v0.1 runs the batch synchronously — Illustrator appears frozen for the duration; the README sets that expectation and the summary dialog is the completion signal. Progress/cancel is a Milestone 3+ *option*, adopted only if a pumped palette proves reliable in real testing; cleanup correctness is never traded for it.
- End summary: totals selected / valid groups / success / failed / skipped / folder / report path.
- `export-report.txt`: script version, time, Illustrator version, source doc name, settings (including prefix/start/pad/order), per-asset results, totals.

---

## 12. Technology constraints

- Single file: `ExportGroupedAssets.jsx`
- `#target illustrator`
- ExtendScript-compatible JS only: `var`, function declarations, no `let`/`const`, no arrows, classes, template literals, promises, modules, Node, browser APIs
- IIFE (or equivalent) to avoid globals
- ScriptUI dialog only — no panel/extension
- Do not invent Illustrator DOM APIs; verify against Adobe docs / known examples

---

## 13. Project files (implementation phase)

| File | Role |
|------|------|
| `ExportGroupedAssets.jsx` | Runnable script |
| `README.md` | How to install/run, options, limits |
| `CLAUDE.md` | Agent rules for this mini-project |
| `TEST_PLAN.md` | Manual Illustrator matrix |
| `CHANGELOG.md` | Start at 0.1.0 |
| `export-grouped-assets-design.md` | This design (SSOT for product decisions) |

`artboard-export-all-groups.md` remains the long original brief; where it conflicts (especially **naming**), **this design wins**.

---

## 14. Implementation milestones (when building)

**Milestone 1**

- Dialog with folder + naming (prefix/start/pad) + AI-only export
- Selection collection + nested-duplicate removal
- Layer-order sequencing
- Temp doc duplicate + tight-bounds AI
- Source safety + basic report

**Milestone 2**

- SVG + PNG (tight bounds)
- Per-asset error isolation + full report fields

**Milestone 3**

- Square PNG mode
- Full options set
- Progress/cancel **only if** a pumped ScriptUI palette proves reliable in testing (v0.1 ships without — §11)

After each milestone: re-read JSX for modern JS leaks, verify API names, re-check source safety, update CHANGELOG, list manual Illustrator tests.

---

## 15. Acceptance criteria (v0.2)

- [ ] Depth 1: N selected objects (groups **or** ungrouped) + prefix `ICOSA-SOLID` → `ICOSA-SOLID-01` … `ICOSA-SOLID-N`
- [ ] Depth 2: selected outer vessels export **child** objects (groups and loose siblings) as `ICOSA-SOLID-A-01`, `ICOSA-SOLID-B-01`, …
- [ ] Depth 3: exports grandchildren as `ICOSA-SOLID-A-01-01`, …
- [ ] Object / group **names** do not appear in filenames; structure + prefix only
- [ ] Default output is a **flat** folder (format subfolders off by default)
- [ ] Source document is unmodified after a full or partial run
- [ ] Nested parent+child both selected as roots → highest ancestor only
- [ ] PNG square / tight behavior unchanged (§7)
- [ ] Failed asset / empty depth branch logged; batch continues
- [ ] Summary + `export-report.txt` include depth setting

---

## 16. Open items (optional later)

- Spatial sort (left→right) as alternate order
- Optional DPI field for print workflows
- Optional “use group name as hierarchy segment” (off by default; conflicts with rename-free workflow)
- Optional hierarchy-as-folders mode (explicitly non-default)
- “Also rename groups in document to match” (likely never)
- Artboard-scoped export mode

---

## 17. Dialog wireframe

```
┌─ Export Grouped Assets  v0.2.0 ──────────────────────┐
│                                                      │
│  Output folder                                       │
│  [ D:\Exports\icosa                   ] [ Browse ]  │
│                                                      │
│  Naming                                              │
│  Prefix       [ ICOSA-SOLID                        ] │
│  Depth        [ 1 ▼ ]  (1 / 2 / 3)                   │
│  Start #      [ 1 ]     Pad digits [ 2 ]             │
│  Preview: ICOSA-SOLID-01 · or -A-01 · or -A-01-01  │
│  Order: selection order (A,B,C…)  ·  Group names ignored │
│                                                      │
│  Formats          enable     top-level (root dump)   │
│  AI               [x]        [x]                     │
│  SVG              [x]        [x]                     │
│  PNG              [x]        [x]  ← uncheck → PNG/   │
│                                                      │
│  PNG                                                 │
│  Target size (px)  [ 2048 ]                          │
│  Canvas  [ Square canvas ▼ ]                         │
│  Padding %         [ 5 ]                             │
│                                                      │
│  Files                                               │
│  [ ] Overwrite existing                              │
│  [ ] Open folder when finished                       │
│                                                      │
│  Top-level = file in output root; else AI/SVG/PNG/.  │
│                                                      │
│                         [ Cancel ]    [ Export ]     │
└──────────────────────────────────────────────────────┘
```

---

## 18. Summary

**What:** One ExtendScript tool, selection-driven multi-format export with depth 1–3.  
**How you name files:** `PREFIX-##` / `PREFIX-A-##` / `PREFIX-A-##-##` in one flat folder.  
**How you run it:** Select objects → depth → dialog → Export.  
**What stays sacred:** Original Illustrator document untouched.

---

## 19. Hardened decisions — API surfaces (2026-08-07)

These are the real ExtendScript classes/properties to use. **Real** = well-established in CC-era Illustrator; **VERIFY** = confirm the flagged behavior in Illustrator before building on it (do the verify during Milestone 1, not after).

| Purpose | API | Status |
|---------|-----|--------|
| New temp doc | `app.documents.add(sourceDoc.documentColorSpace, w, h)` | Real |
| Cross-doc duplicate | `pageItem.duplicate(tempDoc.layers[0], ElementPlacement.PLACEATBEGINNING)` | **VERIFY** the cross-document form once, first thing |
| Artboard | `tempDoc.artboards[0].artboardRect = [L, T, R, B]` | Real |
| AI save | `tempDoc.saveAs(new File(path), IllustratorSaveOptions)` — `compatibility: Compatibility.ILLUSTRATOR17` (CC), `pdfCompatible: true`, `compressed: true`, `embedICCProfile: true` | Real; VERIFY the enum name for the installed version; keep isolated in `createIllustratorSaveOptions()` |
| SVG export | `tempDoc.exportFile(new File(path), ExportType.SVG, ExportOptionsSVG)` — `fontType`, `fontSubsetting`, `embedRasterImages: true`, `coordinatePrecision: 3`, `DTD: SVGDTDVersion.SVG1_1` | **VERIFY cropping**: plain `exportFile` SVG famously ignores the artboard. Set `saveMultipleArtboards: true` + `artboardRange: "1"` to crop — then VERIFY whether Illustrator appends an artboard suffix to the filename (if so, rename the file afterward with `File.rename`) |
| PNG export | `tempDoc.exportFile(new File(path), ExportType.PNG24, ExportOptionsPNG24)` — `antiAliasing: true`, `transparency: true`, `artBoardClipping: true` (note the capital **B**), `horizontalScale` / `verticalScale` (percent) | Real; scale limits are a VERIFY (§20 item 6) |
| Close temp | `tempDoc.close(SaveOptions.DONOTSAVECHANGES)` | Real |
| Refocus source | `sourceDoc.activate()` | Real |
| Suppress dialogs | `app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS`, restore prior value in finally | Real |
| Folder picker | `Folder.selectDialog()`; report via `File` with `file.encoding = "UTF-8"` before `open("w")` | Real |

Fallback noted, not chosen: `Document.exportForScreens()` (CC 2017+) crops correctly for PNG/SVG but auto-generates filenames (prefix + artboard name), which fights our prefix+sequence contract. Use it only if `exportFile` SVG cropping proves unfixable, and rename outputs after export.

**Do not invent APIs beyond this table.** Anything else you think you need → check Adobe's scripting reference first, and add it here.

---

## 20. Implementation risks — test-first checklist (run in Illustrator after Milestone 1)

1. `===` identity: an item from `doc.selection` compares `===` true against the same item reached by tree traversal (order + ancestor filter depend on it). If not → switch to `PageItem.uuid` (verify property exists in the installed version).
2. Cross-document `duplicate(target, placement)` works and lands the group in the temp doc unchanged (appearance, clips, text).
3. Clip-mask group: does `visibleBounds` honor the mask or return full hidden content? If oversized → use clipping-path bounds when `group.clipped`.
4. Raster live effects (drop shadow / blur): included in `visibleBounds` or clipped off in the PNG? Confirm padding covers the common case.
5. Point text: how loose are bounds vs ink? Acceptable slack or not.
6. Extreme PNG scale: tiny group (~10 pt) at target 2048 ⇒ scale ~20,000%. Does `ExportOptionsPNG24` honor it or silently cap? If capped → scale the *duplicate* up in the temp doc instead (never the source).
7. Square-mode pixel exactness: is output 2048×2048 or ±1 px from rounding? Document the observed behavior.
8. SVG artboard cropping via `saveMultipleArtboards: true` + `artboardRange: "1"` — and whether the output filename grows an artboard suffix that must be renamed away.
9. AI `saveAs` from the temp doc: reopen the .ai — artboard correct, art editable, nothing beyond the artboard lost.
10. Focus churn: `documents.add` → export → `close` → `sourceDoc.activate()` across 5+ groups; source document still active, **source selection state** after the run (acceptance says unmodified doc; selection loss is tolerable if unavoidable — record actual behavior).
11. CMYK source document end-to-end: temp doc CMYK, PNG/SVG color conversion looks acceptable.
12. `DONTDISPLAYALERTS` actually suppresses missing-font / profile dialogs during duplicate; interaction level restored after the run (check with a doc using a missing font).
13. Unicode prefix (e.g. Japanese) → dialog, filenames on disk, and UTF-8 report all round-trip.
14. Overwrite off + pre-existing `prefix-01.png` but free `.ai`/`.svg` → all formats shift together to `prefix-01_002`.
15. Batch of ~100 groups: no temp-doc leak (documents count returns to baseline), no runaway memory, source doc dirty-flag unchanged.

---

16. Depth 2: outer with child groups → names `PREFIX-A-01` and correct leaf art (not the outer composite).
17. Depth 3: three-level nest → `PREFIX-A-01-01` pattern; sibling mids and leaves ordered by stacking.
18. Depth 2 root with no child groups → skipped/failed entry; other roots continue.
19. Flat folder: all depth-3 names appear as siblings in one directory when format subfolders off.
