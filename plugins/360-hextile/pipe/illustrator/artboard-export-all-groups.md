Build a production-quality batch asset exporter for Adobe Illustrator.

Before writing files:

1. Research the current Adobe Illustrator JavaScript/ExtendScript scripting
   interface using Adobe documentation.
2. Produce a concise implementation plan.
3. List any Illustrator API assumptions that need to be tested inside
   Illustrator.
4. Wait for my approval before implementing.

Do not invent Illustrator methods or properties. Verify every Illustrator DOM
API used against available documentation or established examples.

# PROJECT GOAL

Create one self-contained Adobe Illustrator ExtendScript file:

    ExportGroupedAssets.jsx

Adobe Illustrator, not Node.js, will execute this file.

The user will manually group every intended asset beforehand. Each selected
Illustrator GroupItem represents exactly one exportable asset. No computer
vision, semantic grouping, or MCP interpretation is needed.

The script must batch-export every selected group as:

1. Native editable Adobe Illustrator .ai
2. SVG
3. Transparent PNG

The original document must remain unchanged.

# TECHNOLOGY CONSTRAINTS

Use Adobe Illustrator ExtendScript.

The final executable file must:

- Have a .jsx extension.
- Begin with #target illustrator.
- Use ExtendScript-compatible legacy JavaScript.
- Use var rather than let or const.
- Use traditional function declarations.
- Avoid arrow functions.
- Avoid classes.
- Avoid template literals.
- Avoid promises and async/await.
- Avoid ES modules and imports.
- Avoid Node.js APIs.
- Avoid browser APIs.
- Avoid external packages.
- Avoid requiring UXP, CEP, MCP, or an Illustrator plug-in.
- Be a single runnable file with no runtime dependencies.
- Use an IIFE or equivalent structure to avoid leaking global variables.

Do not build a panel or extension. Use a standard ScriptUI dialog.

# SOURCE SELECTION BEHAVIOR

Use the currently selected Illustrator objects.

Rules:

1. Process only selected objects whose typename is GroupItem.
2. Each selected GroupItem is one asset.
3. If both a parent group and one of its descendants are selected, process
   only the highest selected ancestor to avoid duplicate exports.
4. Ignore non-group selections and include them in the final skipped count.
5. Do not automatically process every group in the document.
6. Do not rearrange, rename, resize, move, expand, outline, flatten, or delete
   anything in the original document.
7. Preserve the original selection and active document as closely as the
   Illustrator scripting API permits.

# USER INTERFACE

Display a ScriptUI dialog titled:

    Export Grouped Assets

Include:

OUTPUT FOLDER
- Read-only path display.
- Browse button using Folder.selectDialog().
- Remember the selected folder during the current script execution.

FORMATS
- Export AI checkbox, default enabled.
- Export SVG checkbox, default enabled.
- Export PNG checkbox, default enabled.
- Require at least one format.

PNG SETTINGS
- Target pixel size field, default 2048.
- Canvas mode dropdown:
  1. Tight bounds
  2. Square canvas
- Default canvas mode: Square canvas.
- Transparent background, always enabled.
- Padding percentage field, default 5.
- Anti-aliasing enabled.

FILE SETTINGS
- Overwrite existing files checkbox, default disabled.
- Create format subfolders checkbox, default enabled.
- Open output folder when finished checkbox, default disabled.

A short explanatory label should say:

    Each selected Illustrator group will be exported as one asset.

Buttons:

- Export
- Cancel

Validate all fields before starting.

# OUTPUT STRUCTURE

When format subfolders are enabled:

    chosen-output-folder/
        AI/
            asset-name.ai
        SVG/
            asset-name.svg
        PNG/
            asset-name.png
        export-report.txt

When subfolders are disabled, place all files directly in the selected folder.

# FILE NAMING

Use the Illustrator group name as the filename.

If a group has no useful name, generate:

    asset-001
    asset-002
    asset-003

Filename handling must:

- Trim leading and trailing whitespace.
- Replace Windows-invalid filename characters:
  < > : " / \ | ? *
- Remove trailing periods and spaces.
- Protect against Windows reserved filenames such as:
  CON, PRN, AUX, NUL, COM1 through COM9, and LPT1 through LPT9.
- Preserve Unicode where Illustrator and the filesystem permit it.
- Prevent collisions.
- When duplicate names occur, append:
  _002, _003, and so on.
- Apply collision detection across all enabled output formats.
- Do not silently overwrite files unless overwrite is enabled.

Create a dedicated sanitizeFilename() helper that can be reviewed separately.

# EXPORT PROCESS

For each valid selected group:

1. Keep a reference to the original source document.
2. Create a temporary Illustrator document using the source document’s color
   space where supported.
3. Duplicate the source group into the temporary document.
4. Never use clipboard copy and paste unless cross-document duplicate is
   demonstrably impossible.
5. Determine the duplicated group’s visible bounds.
6. Use visibleBounds rather than geometricBounds so strokes are included.
7. Apply the requested padding.
8. Set the temporary document’s artboard around the duplicated artwork.
9. Center the duplicated group within the artboard.
10. Export all enabled formats.
11. Close the temporary document without saving additional changes.
12. Return focus to the original document.
13. Continue with the next group.

All temporary documents must be closed even when an individual asset fails.

Use try/catch/finally or an ExtendScript-compatible equivalent to guarantee
cleanup.

# ARTBOARD AND PNG RULES

AI AND SVG:

- Keep the artwork at its original vector dimensions.
- Fit the artboard to the visible bounds plus padding.
- Do not rescale the source artwork merely to normalize AI or SVG dimensions.
- Crop export output to the artboard.
- Preserve editability wherever the export format permits.
- Do not expand appearance.
- Do not outline text without an explicit option.
- Do not rasterize vector artwork for AI or SVG output.

PNG TIGHT BOUNDS MODE:

- Use the padded visible bounds as the artboard.
- Preserve the asset’s aspect ratio.
- Scale the PNG export so its longest dimension equals the requested target
  pixel size.
- Do not stretch the artwork.

PNG SQUARE CANVAS MODE:

- Construct a square artboard centered around the duplicated asset.
- The square must contain the complete padded asset.
- Export an image exactly target-size by target-size pixels.
- Center the asset on the transparent canvas.
- Preserve aspect ratio.
- Do not stretch the artwork.

Use Illustrator’s PNG24 export functionality and artboard clipping.

Calculate export scale from artboard dimensions instead of resizing the
original source group.

# AI EXPORT

Save a native editable .ai document using IllustratorSaveOptions or the
appropriate documented Illustrator API.

Requirements:

- Preserve vectors.
- Preserve clipping groups.
- Preserve compound paths.
- Preserve gradients and patterns where Illustrator supports them.
- Preserve editable text in the AI file.
- Do not flatten transparency unless forced by the selected Illustrator
  compatibility level.
- Choose a sensible compatibility setting for the installed Illustrator
  version, but isolate it in one configuration function so it can be changed.
- Document the compatibility choice in README.md.

# SVG EXPORT

Use Illustrator’s documented SVG export options.

Requirements:

- Crop to the temporary artboard.
- Preserve vector geometry.
- Preserve appearance as faithfully as Illustrator’s SVG exporter permits.
- Do not modify the source artwork.
- Do not depend on an SVG post-processing package.
- Keep SVG option construction in a dedicated createSvgOptions() function.

If Illustrator requires text handling choices, preserve editable text by
default and document the portability implications.

# PNG EXPORT

Use Illustrator’s documented PNG24 export options.

Requirements:

- Transparent background.
- Anti-aliasing enabled.
- Artboard clipping enabled.
- Correct scale calculation for the requested output pixel size.
- Keep PNG option construction in a dedicated createPngOptions() function.

# BOUNDS HANDLING

Create a dedicated getEffectiveBounds() function.

Initial behavior may use GroupItem.visibleBounds.

However:

- Clearly document known Illustrator limitations involving clipping masks,
  live effects, brushes, raster effects, and placed artwork.
- Do not add undocumented geometric hacks without explaining them.
- Keep bounds logic isolated so it can be improved after real Illustrator
  testing.
- Detect invalid or zero-sized bounds and skip the asset with an error rather
  than crashing the entire batch.

Remember that Illustrator bounds use the array order:

    [left, top, right, bottom]

Handle Illustrator’s coordinate direction correctly.

# ERROR HANDLING

The script must not abort the entire batch because one asset fails.

For each asset, record:

- Original group name.
- Final filename.
- Exported formats.
- Output paths.
- Success or failure.
- Illustrator error message.
- Error line number when available.
- Any skipped reason.

At completion, show a summary dialog containing:

- Total selected objects.
- Valid groups.
- Successfully exported groups.
- Failed groups.
- Skipped non-group objects.
- Output folder.
- Path to the export report.

Write a plain-text UTF-8-compatible report when possible:

    export-report.txt

Include:

- Script version.
- Date and time.
- Illustrator version.
- Source document name.
- Chosen settings.
- Per-asset results.
- Final totals.

If writing UTF-8 has ExtendScript-specific limitations, document and implement
the safest compatible approach.

# CANCELLATION AND CLEANUP

Include a progress window if it can be implemented reliably with ScriptUI.

It should display:

- Current asset number.
- Total assets.
- Current filename.
- Current export operation.
- Cancel button.

Cancellation must:

- Finish or safely abort the current operation.
- Close any temporary document.
- Leave the original document intact.
- Write a partial report.
- State that the batch was cancelled.

Do not sacrifice export reliability merely to provide progress UI. If a
reliable responsive Cancel button is not practical in Illustrator
ExtendScript, explain the limitation and implement the safest simpler
behavior.

# SOURCE DOCUMENT SAFETY

This is a hard requirement.

The script must never save over the original document.

It must not:

- Save the source document.
- Close the source document.
- Change source artboard sizes.
- Move source artwork.
- Rename source groups.
- Expand appearances.
- Outline text.
- Rasterize source artwork.
- Embed or relink placed artwork in the source.
- Delete source content.

Store the source document reference and explicitly restore it after every
temporary export.

# PROJECT FILES

Create:

1. ExportGroupedAssets.jsx
   The complete self-contained runnable script.

2. CLAUDE.md
   Persistent project rules, including:
   - ExtendScript legacy JavaScript only.
   - No invented Illustrator APIs.
   - Source document must never be modified.
   - Final distribution remains one self-contained JSX file.
   - Make minimal patches after Illustrator test failures.
   - Preserve exact error messages and line numbers during debugging.

3. README.md
   Include:
   - Purpose.
   - Supported workflow.
   - How to group and name assets.
   - How to select assets.
   - How to run using File > Scripts > Other Script.
   - How to install permanently in Illustrator’s Scripting folder.
   - Explanation of each option.
   - Output folder example.
   - Known limitations.
   - Debugging procedure.
   - Uninstallation instructions.

4. TEST_PLAN.md
   Include a manual Illustrator test matrix.

5. CHANGELOG.md
   Begin at version 0.1.0.

Do not introduce a package.json, dependency manager, transpiler, or build
system unless it becomes genuinely necessary.

# TEST MATRIX

Document manual tests for:

1. One simple vector group.
2. Several selected groups.
3. Nested groups.
4. Parent and child simultaneously selected.
5. Clipping mask group.
6. Compound paths.
7. Thick strokes extending beyond paths.
8. Gradient fills.
9. Pattern fills.
10. Opacity and blend modes.
11. Live text.
12. Duplicate group names.
13. Blank group names.
14. Unicode group names.
15. Windows-invalid filename characters.
16. Existing destination files.
17. Missing output folder.
18. One deliberately invalid or zero-sized asset.
19. PNG tight bounds mode.
20. PNG square canvas mode.
21. Cancellation during a batch.
22. Failure during one format while other assets continue.
23. Source document saved state before and after export.
24. Source selection before and after export.
25. A batch of at least 100 groups.

# IMPLEMENTATION STYLE

Keep the script readable and conservative.

Use small functions such as:

- main()
- showExportDialog()
- collectSelectedGroups()
- removeNestedDuplicates()
- sanitizeFilename()
- createUniqueFilename()
- createOutputFolders()
- createTemporaryDocument()
- duplicateGroupToDocument()
- getEffectiveBounds()
- applyPaddedArtboard()
- centerItemOnArtboard()
- calculatePngScale()
- createIllustratorSaveOptions()
- createSvgOptions()
- createPngOptions()
- exportAi()
- exportSvg()
- exportPng()
- writeReport()
- showSummary()
- cleanupTemporaryDocument()

Use comments to explain Illustrator-specific behavior and coordinate math,
not obvious JavaScript syntax.

Avoid giant functions.

# VERSIONING

Set:

    SCRIPT_NAME = "Export Grouped Assets"
    SCRIPT_VERSION = "0.1.0"

Show the version in the UI and report.

# DEVELOPMENT PROCESS

Milestone 1:

- Create the project documentation.
- Implement selected-group collection.
- Implement filename sanitization.
- Implement temporary-document duplication.
- Implement tight-bounds AI export only.
- Make this structurally clean and testable.

Milestone 2:

- Add SVG export.
- Add transparent PNG tight-bounds export.
- Add logging and per-asset error isolation.

Milestone 3:

- Add square PNG mode.
- Add ScriptUI options.
- Add progress reporting and cancellation if reliable.

Do not implement all milestones as one unreviewed monolithic edit.

After each milestone:

1. Re-read the complete JSX file.
2. Check for accidental modern JavaScript syntax.
3. Check every Illustrator API name.
4. Check source-document safety.
5. Update CHANGELOG.md.
6. Tell me exactly what must be tested manually in Illustrator.

Begin by presenting the implementation plan only.