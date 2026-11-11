# Export Selected Layers (Photoshop) — Design / Brainstorm

**Status:** brainstorm → design draft (not implemented)  
**Target script:** `export-selected-layers.jsx` (ExtendScript, Adobe Photoshop)  
**Sibling:** `illustrator/export-grouped-assets.jsx` (parity where it makes sense)  
**Version target:** 0.1.0  
**Updated:** 2026-08-08  

---

## 1. Purpose

Batch-export **selected Photoshop layers** (or layer groups treated as one asset) to **transparent PNGs**, at **native document pixel resolution**, with optional **padding**, without permanently changing the source PSD.

**Primary flow**

1. Open a PSD; select the layers / groups you want (one asset each).  
2. Run the script → ScriptUI dialog.  
3. Choose output folder, padding, naming, options.  
4. Each unit is copied into a **temporary document**, trimmed/padded, exported as PNG, temp closed.  
5. Source document remains open and unmodified (no save forced).

---

## 2. Goals and non-goals

### Goals (v0.1)

- Export **only the current selection** (not whole document by default).  
- One file per **export unit** (see §5).  
- **Transparent** PNG background.  
- **Native resolution** — export at the PSD’s pixel grid (1:1). No upscale/downscale by default.  
- Optional **padding in pixels** around content (transparent).  
- Optional **hard max** longest side later (like Illustrator) — not required for v0.1 if native-only.  
- Source document safety: never save over PSD; restore selection/active layer as best-effort.  
- Prefs: remember last folder + key options (same idea as Illustrator).  
- Report: `export-report.txt` with success/fail per layer.

### Non-goals (v0.1)

- Multi-format (PSD/TIFF/WebP) — PNG only first.  
- UXP panel / CEP extension.  
- Exporting every layer in the file without selection.  
- Auto-renaming layers in the PSD.  
- Animations / video layers / 3D.  
- Matching Illustrator’s depth A-01 hierarchy unless we explicitly add a mode later.

---

## 3. What “native resolution + padding” means

| Term | Meaning |
|------|---------|
| **Native** | Output pixel size comes from the layer’s **visible pixel bounds** in the document (or document size if full-canvas), at the PSD’s existing PPI/metadata. No “target 2048” scale by default. |
| **Padding** | Extra transparent pixels around that content, e.g. `padPx = 16` → grow canvas by 16 px on each side (or max-side % — pick one; recommend **pixels** for PS). |
| **Trim** | After isolating the layer, **trim transparent** so the canvas hugs content, **then** add padding. |

**Recommended v0.1 pipeline per unit**

```
duplicate layer → new temp RGB 8-bit (or match source) transparent doc
  → paste/duplicate layer into temp (single layer stack)
  → reveal all / trim transparent (if content doesn’t fill canvas)
  → resize canvas + padPx transparent border
  → export PNG (transparency on)
  → close temp without saving
```

**VRAM / size:** Native can mean huge (8K boards). Optional later: “max longest side” hard cap (Illustrator-style no overshoot). v0.1: warn in dialog if any unit bounds exceed e.g. 8192 on a side.

---

## 4. Brainstorm — groups, linked layers, smart objects

### 4.1 Layer groups (folders)

| Approach | Behavior | When to use |
|----------|----------|-------------|
| **A. Group = one asset (Recommended default)** | If a **layer set** is selected, export the **entire group flattened** as one PNG (name = group name). | Icon sets where each folder is one asset. Closest to Illustrator “group of art”. |
| **B. Group = vessel, export children** | If a group is selected, export each **direct child** layer/group as its own file (like Illustrator depth 2). | “Folder of variants” you don’t want to multi-select. |
| **C. Ignore groups, only leaf layers** | Selection of a group expands to all nested art layers. | Rare; noisy. |

**v0.1 recommendation:** **Mode A default** + optional dialog:  
`When a group is selected: (•) Export group as one  ( ) Export each top-level child`

Do **not** auto-recurse infinitely without a mode — same lesson as Illustrator depth.

### 4.2 Linked layers (layer links)

In Photoshop, **Link** means “transform/move together,” **not** “same pixels.”

| Policy | Behavior |
|--------|----------|
| **Recommended: ignore links for export set** | Export only what is **selected**. Linked-but-not-selected siblings are **not** auto-included. Predictable. |
| Alternative: expand links | Selecting one linked layer exports all linked layers **as separate files** or **as one merged file**. Surprising; avoid for v0.1. |

**If user wants several layers as one PNG:** they should **group** them or **select multiple and use a “merge selection to one file” mode** (optional advanced).

**v0.1:** Ignore link relationships for unit discovery. Document that clearly in the dialog.

### 4.3 Clipping masks

| Policy | Behavior |
|--------|----------|
| **Recommended:** When exporting a base layer, include **clipping-mask children** that clip to it (standard “what you see”). |
| When exporting only a clipped child alone | Export that layer with transparency as painted; may look incomplete without base — user responsibility. |

Implementation note: duplicating a layer tree into a temp doc should preserve clipping structure, then **merge visible** once for a flat PNG.

### 4.4 Smart objects

| Policy | Behavior |
|--------|----------|
| **Recommended:** Export **as rendered** (rasterize smart object appearance at document resolution). Do not open/edit contents. |
| Linked smart objects | Same — use current placed appearance. Missing link → fail that unit with clear error. |

### 4.5 Adjustment layers / fill / shapes / text

- **Included** if selected (or inside a selected group).  
- Flatten with merge so PNG is pixels.  
- Hidden layers inside a selected group: **skip hidden** by default (export “what’s visible in the group”).

### 4.6 Background layer

- Locked Background: if selected, export as opaque RGB unless user converts — or export with white/transparent option.  
- **Default:** if Background has no transparency, PNG is still fine (opaque pixels).

### 4.7 Layer masks

- **Recommended:** Apply mask when rasterizing (respect mask). Don’t export mask channel as separate file in v0.1.

### 4.8 Artboards (multi-artboard PSD)

- **v0.1:** Work in active document; bounds in document coordinates.  
- Optional later: export only layers intersecting active artboard.

---

## 5. Selection → export units (LOCKED proposal for v0.1)

1. Require an open document.  
2. Read selection: top-level selected `ArtLayer` / `LayerSet` items (Photoshop’s selection model via `activeLayer` + multi-select is awkward — use documented approach: **selected layers via ScriptListener / `getSelectedLayers` pattern** or AM descriptors).  
3. Build unit list in **selection order** (same lesson as Illustrator: don’t reverse by layer stack).  
4. De-dupe: if both a parent `LayerSet` and a child are selected, **keep parent only** when mode is “group as one”; when mode is “export children,” drop parent and keep children.  
5. Skip: empty groups, fully empty masks (optional), locked sets that can’t duplicate (report error).

**Export unit types**

| Unit | Source | Filename default |
|------|--------|------------------|
| Single `ArtLayer` | That layer (+ its clipping kids if we include them) | Layer name |
| `LayerSet` (group as one) | Flatten group visibility | Group name |
| Child of set (children mode) | Each child | Child name |

---

## 6. Naming

### v0.1 default (Photoshop-native)

- Use **layer / group name** as filename.  
- Sanitize like Illustrator: Windows-invalid chars, reserved names, trim, collisions → `_002`.  
- Empty name → `layer-001`, …

### Optional (parity with Illustrator)

- **Prefix + sequence** override: ignore layer names; `ICON-01`, `ICON-02` in selection order.  
- Good for dumps of unnamed “Layer 1” stacks.

**Dialog:**  
`Naming: (•) Layer names  ( ) Prefix + sequence`

---

## 7. Output

- Default: **flat folder** of PNGs + `export-report.txt`.  
- Optional: no multi-format split needed for v0.1 (PNG only).  
- Prefs under `Folder.userData/ExportSelectedLayers/prefs.txt` (mirror Illustrator pattern).

---

## 8. UI (ScriptUI sketch)

```
┌─ Export Selected Layers  v0.1.0 ─────────────────────┐
│  Output folder  [ .................... ] [ Browse ]  │
│                                                      │
│  Units                                               │
│  (•) Selection only                                  │
│  Groups: (•) Each selected group = one file          │
│          ( ) Export top-level children of group      │
│  [x] Include clipping-mask layers with base          │
│  [ ] Expand linked layers (off — not v0.1 default)   │
│                                                      │
│  Canvas                                              │
│  [x] Trim transparent to content                     │
│  Padding (px)  [ 16 ]                                │
│  (no scale — native document pixels)                 │
│                                                      │
│  Naming                                              │
│  (•) Layer / group names                             │
│  ( ) Prefix + sequence  Prefix [ asset- ]  Pad [ 2 ] │
│                                                      │
│  [x] Overwrite existing                              │
│  [ ] Open folder when finished                       │
│                                                      │
│  Linked layers: not auto-included (select or group). │
│                                                      │
│                    [ Cancel ]  [ Export ]            │
└──────────────────────────────────────────────────────┘
```

---

## 9. Source safety

Must **not**:

- Save the source PSD as part of export.  
- Delete or permanently rasterize source layers.  
- Flatten the source document.

Temp docs only; `close(SaveOptions.DONOTSAVECHANGES)`.

Best-effort: restore `activeLayer` and selection after batch (Photoshop selection restore is imperfect — document limitation).

---

## 10. Best-practice cheat sheet (what you should do in the PSD)

| Goal | Do this in Photoshop |
|------|----------------------|
| One icon = one file | One **layer** or one **group** per icon; select them; export. |
| Many pieces that move together | **Group** them (not only Link). |
| Linked layers for transform | Fine for authoring; for export, **select all** you want or put in a group. |
| Clean bounds | Keep content tight; use masks; script trims + pad. |
| Consistent library | Name layers well **or** use prefix+sequence. |
| Smart objects | Leave as SO; script exports appearance. |

---

## 11. Technical notes (implementation later)

- `#target photoshop`, ExtendScript, `var` only, ScriptUI, single IIFE file.  
- Selected layers: use a known multi-select getter (Action Manager `targetLayers` / community `getSelectedLayers()` pattern) — verify on PS 2024/2025.  
- Duplicate: `layer.duplicate(newDoc, ElementPlacement.PLACEATBEGINNING)` or merge-visible recipe.  
- Trim: `newDoc.trim(TrimType.TRANSPARENT, true, true, true, true)`.  
- Canvas pad: `resizeCanvas(w+2p, h+2p, AnchorPosition.MIDDLECENTER)`.  
- PNG: `PNGSaveOptions` with transparency / or `ExportOptionsSaveForWeb`. Prefer modern save path that keeps alpha.  
- Pure helpers: sanitizeFilename, collision, prefs parse — extractable for Node tests like Illustrator.

---

## 12. Open decisions (for you)

| # | Question | Recommendation |
|---|----------|----------------|
| 1 | Group selected → one file or children? | **One file** default; children optional. |
| 2 | Linked layers auto-expand? | **No** for v0.1. |
| 3 | Naming | **Layer names** default; prefix+seq optional. |
| 4 | Max pixel cap? | **Not in v0.1** (native only); add later like Illustrator. |
| 5 | Formats | **PNG only** first. |

---

## 13. Summary

- Yes: a Photoshop sibling script that exports **each selected layer/group** to transparent PNG at **native pixels + pad**.  
- **Groups:** treat selected group as **one asset** by default (flatten); optional child mode.  
- **Linked layers:** **don’t** auto-include links — select or group intentionally.  
- **Smart objects / masks / clipping:** export **rendered appearance**.  
- Source PSD stays clean via temp docs.

---

## 14. Implementation milestones (when you say go)

1. Design sign-off (this file).  
2. M1: dialog + selected layers → temp doc → trim → pad → PNG + report.  
3. M2: group-as-one + children mode; clipping include; prefs.  
4. M3: prefix naming; collision; polish; pure-helper tests.

▶ **NEXT:** Confirm the five open decisions (or accept recommendations), then say **go** to implement `export-selected-layers.jsx`.
