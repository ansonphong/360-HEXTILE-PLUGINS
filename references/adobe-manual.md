# Adobe helpers (manual)

Illustrator and Photoshop scripts in this package are **reference / manual-run only**. Agents do not automate Adobe UIs.

## Illustrator

| File | Role |
|------|------|
| `illustrator/export-grouped-assets.jsx` | Select objects (grouped or not) → dialog → export AI / SVG / PNG |
| `illustrator/export-grouped-assets-design.md` | Design notes |
| `illustrator/artboard-export-all-groups.md` | Earlier brief |
| `illustrator/test-pure-helpers.js` | Pure-helper unit tests (no Illustrator) |

**Run:** File → Scripts → Other Script… → pick the `.jsx`.

## Photoshop

| File | Role |
|------|------|
| `photoshop/export-selected-layers-design.md` | Selected-layer PNG export design |

**Not implemented yet** — no `.jsx`. Do not claim a working Photoshop export script.

## Agent policy

- Point users at these paths under the plugin root.
- Do not invent CLI wrappers for JSX.
- Matte work uses Python via `scripts/fp-run.sh`, not Adobe.
