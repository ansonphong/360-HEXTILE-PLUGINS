#!/usr/bin/env node
/**
 * Exercises DOM-free helpers from the shipped export-grouped-assets.jsx.
 * Does not re-implement logic — extracts PURE_HELPERS_BEGIN..END and evals them.
 */
"use strict";

var fs = require("fs");
var path = require("path");

var jsxPath = path.join(__dirname, "export-grouped-assets.jsx");
var src = fs.readFileSync(jsxPath, "utf8");

var begin = src.indexOf("// --- PURE_HELPERS_BEGIN ---");
var end = src.indexOf("// --- PURE_HELPERS_END ---");
if (begin < 0 || end < 0 || end <= begin) {
    console.error("FAIL: pure helper markers missing in " + jsxPath);
    process.exit(1);
}

var chunk = src.slice(begin, end);
// Eval into a sandbox object
var sandbox = {};
var fn = new Function(
    "exports",
    chunk +
        "\nexports.sanitizeFilename = sanitizeFilename;" +
        "\nexports.zeroPad = zeroPad;" +
        "\nexports.buildSequenceBaseName = buildSequenceBaseName;" +
        "\nexports.normalizePrefixStem = normalizePrefixStem;" +
        "\nexports.letterFromIndex = letterFromIndex;" +
        "\nexports.buildDepthBaseName = buildDepthBaseName;" +
        "\nexports.previewDepthNames = previewDepthNames;" +
        "\nexports.defaultPrefs = defaultPrefs;" +
        "\nexports.parsePrefsText = parsePrefsText;" +
        "\nexports.serializePrefs = serializePrefs;" +
        "\nexports.applyStaleFolderRule = applyStaleFolderRule;" +
        "\nexports.prefsToDialogDefaults = prefsToDialogDefaults;" +
        "\nexports.settingsToPrefs = settingsToPrefs;" +
        "\nexports.normalizePrefs = normalizePrefs;" +
        "\nexports.isFormatTopLevel = isFormatTopLevel;" +
        "\nexports.relativePathForFormat = relativePathForFormat;" +
        "\nexports.compareIndexPaths = compareIndexPaths;" +
        "\nexports.computePaddedBounds = computePaddedBounds;" +
        "\nexports.computeArtboardRect = computeArtboardRect;" +
        "\nexports.calculatePngScalePct = calculatePngScalePct;" +
        "\nexports.predictedPngPixels = predictedPngPixels;" +
        "\nexports.pngScaleRespectsMax = pngScaleRespectsMax;" +
        "\nexports.artboardLongestSide = artboardLongestSide;" +
        "\nexports.resolveCollisionBaseName = resolveCollisionBaseName;" +
        "\nexports.nextFreeBaseName = nextFreeBaseName;" +
        "\nexports.enabledFormatKeys = enabledFormatKeys;" +
        "\nexports.previewSequenceNames = previewSequenceNames;"
);
fn(sandbox);

var failed = 0;
function assert(cond, msg) {
    if (!cond) {
        console.error("FAIL: " + msg);
        failed++;
    } else {
        console.log("PASS: " + msg);
    }
}

// sanitize
assert(sandbox.sanitizeFilename('a<b>c:d"e/f\\g|h?i*j') === "a_b_c_d_e_f_g_h_i_j", "sanitize strips Windows-invalid chars");
assert(sandbox.sanitizeFilename("  hello  ") === "hello", "sanitize trims");
assert(sandbox.sanitizeFilename("CON") === "_CON", "sanitize reserves CON");
assert(sandbox.sanitizeFilename("file.") === "file", "sanitize strips trailing period");

// zero-pad + sequence
assert(sandbox.zeroPad(1, 2) === "01", "zeroPad 1 pad 2 → 01");
assert(sandbox.zeroPad(104, 2) === "104", "zeroPad never truncates");
assert(
    sandbox.buildSequenceBaseName("beachball-", 1, 2, 0) === "beachball-01",
    "beachball- + start1 + pad2 + idx0 → beachball-01"
);
assert(
    sandbox.buildSequenceBaseName("beachball-", 1, 2, 4) === "beachball-05",
    "beachball-05 for index 4"
);
assert(
    sandbox.buildSequenceBaseName("beachball-", 95, 2, 0) === "beachball-95",
    "start 95 pad 2 not truncated"
);
assert(
    sandbox.buildSequenceBaseName("beachball-", 95, 2, 9) === "beachball-104",
    "95+9=104 expands past pad"
);

// depth hierarchical naming (design §6.2)
assert(sandbox.normalizePrefixStem("ICOSA-SOLID-") === "ICOSA-SOLID", "strip trailing hyphen on prefix");
assert(sandbox.letterFromIndex(0, 2) === "A", "letter A");
assert(sandbox.letterFromIndex(25, 2) === "Z", "letter Z");
assert(sandbox.letterFromIndex(26, 2) === "27", "letter overflow → 27");
assert(
    sandbox.buildDepthBaseName("ICOSA-SOLID", 1, [0], 2, 1) === "ICOSA-SOLID-01",
    "depth1 ICOSA-SOLID-01"
);
assert(
    sandbox.buildDepthBaseName("ICOSA-SOLID-", 2, [0, 0], 2, 1) === "ICOSA-SOLID-A-01",
    "depth2 ICOSA-SOLID-A-01"
);
assert(
    sandbox.buildDepthBaseName("ICOSA-SOLID", 2, [1, 0], 2, 1) === "ICOSA-SOLID-B-01",
    "depth2 B-01"
);
assert(
    sandbox.buildDepthBaseName("ICOSA-SOLID", 3, [0, 0, 0], 2, 1) === "ICOSA-SOLID-A-01-01",
    "depth3 ICOSA-SOLID-A-01-01"
);
assert(
    sandbox.buildDepthBaseName("ICOSA-SOLID", 3, [0, 1, 0], 2, 1) === "ICOSA-SOLID-A-02-01",
    "depth3 mid index 1 → A-02-01"
);
assert(
    sandbox.buildDepthBaseName("ICOSA-SOLID", 3, [0, 0, 1], 2, 1) === "ICOSA-SOLID-A-01-02",
    "depth3 leaf index 1 → A-01-02"
);
var prev3 = sandbox.previewDepthNames("ICOSA-SOLID", 3, 1, 2, 3);
assert(prev3[0] === "ICOSA-SOLID-A-01-01", "preview depth3 first");

// prefs parse/serialize — full dialog (shipped helpers)
var emptyP = sandbox.parsePrefsText("");
assert(emptyP.lastOutputFolder === "" && emptyP.lastPrefix === "" && emptyP.lastDepth === 1, "empty prefs → defaults");
assert(emptyP.targetPx === 2048 && emptyP.pngTopLevel === true && emptyP.exportAi === true, "empty prefs → format/png defaults");
var corruptP = sandbox.parsePrefsText("not=valid\n###\nlastDepth=99\nlastPrefix=ICOSA\ntargetPx=-5");
assert(corruptP.lastDepth === 1, "invalid depth ignored → default 1");
assert(corruptP.lastPrefix === "ICOSA", "prefix still parsed from partial file");
assert(corruptP.targetPx === 2048, "invalid targetPx → default");
var fullPrefs = {
    lastOutputFolder: "D:\\Exports\\icosa",
    lastPrefix: "ICOSA-SOLID",
    lastDepth: 2,
    startNumber: 3,
    padDigits: 3,
    exportAi: false,
    exportSvg: true,
    exportPng: false,
    targetPx: 1024,
    canvasMode: "tight",
    paddingPct: 10,
    overwrite: true,
    aiTopLevel: false,
    svgTopLevel: false,
    pngTopLevel: true,
    openFolder: true
};
var body = sandbox.serializePrefs(fullPrefs);
var round = sandbox.parsePrefsText(body);
assert(round.lastOutputFolder === "D:\\Exports\\icosa", "prefs round-trip folder");
assert(round.lastPrefix === "ICOSA-SOLID", "prefs round-trip prefix");
assert(round.lastDepth === 2, "prefs round-trip depth");
assert(round.startNumber === 3 && round.padDigits === 3, "prefs round-trip start/pad");
assert(round.exportAi === false && round.exportSvg === true && round.exportPng === false, "prefs round-trip formats");
assert(round.targetPx === 1024 && round.canvasMode === "tight" && round.paddingPct === 10, "prefs round-trip PNG");
assert(round.overwrite === true && round.pngTopLevel === true && round.aiTopLevel === false, "prefs round-trip top-level flags");
assert(round.openFolder === true, "prefs round-trip openFolder");
var dlg = sandbox.prefsToDialogDefaults(round);
assert(dlg.folderPath === "D:\\Exports\\icosa" && dlg.prefix === "ICOSA-SOLID" && dlg.depth === 2, "prefsToDialogDefaults names");
assert(dlg.targetPx === 1024 && dlg.canvasMode === "tight" && dlg.overwrite === true, "prefsToDialogDefaults options");
assert(dlg.pngTopLevel === true && dlg.svgTopLevel === false, "prefsToDialogDefaults top-level");
var back = sandbox.settingsToPrefs(dlg);
assert(back.lastDepth === 2 && back.exportPng === false && back.pngTopLevel === true, "settingsToPrefs maps dialog");

// mixed layout paths (PNG root, SVG/AI subfolders)
var layout = { aiTopLevel: false, svgTopLevel: false, pngTopLevel: true };
assert(sandbox.relativePathForFormat(layout, "MOON-A-01", "png") === "MOON-A-01.png", "PNG top-level path");
assert(sandbox.relativePathForFormat(layout, "MOON-A-01", "svg") === "SVG/MOON-A-01.svg", "SVG subfolder path");
assert(sandbox.relativePathForFormat(layout, "MOON-A-01", "ai") === "AI/MOON-A-01.ai", "AI subfolder path");
var legacy = sandbox.parsePrefsText("subfolders=true\nlastPrefix=X\n");
assert(legacy.aiTopLevel === false && legacy.pngTopLevel === false, "legacy subfolders=true → all not top-level");
var legacyFlat = sandbox.parsePrefsText("subfolders=false\nlastPrefix=Y\n");
assert(legacyFlat.pngTopLevel === true, "legacy subfolders=false → top-level");
var stale = sandbox.applyStaleFolderRule(
    { lastOutputFolder: "D:\\gone", lastPrefix: "X", lastDepth: 3, targetPx: 512 },
    function () {
        return false;
    }
);
assert(stale.lastOutputFolder === "", "stale folder cleared");
assert(stale.lastPrefix === "X" && stale.lastDepth === 3 && stale.targetPx === 512, "stale keeps other settings");
var fresh = sandbox.applyStaleFolderRule(
    { lastOutputFolder: "D:\\ok", lastPrefix: "Y", lastDepth: 2 },
    function (p) {
        return p === "D:\\ok";
    }
);
assert(fresh.lastOutputFolder === "D:\\ok", "existing folder kept");

// sort path compare
assert(sandbox.compareIndexPaths([0, 1], [0, 2]) === -1, "index path compare");
assert(sandbox.compareIndexPaths([1], [0, 5]) === 1, "shorter higher first index loses");

// padded bounds — design §7
// visibleBounds [L,T,R,B] = [0, 100, 50, 0] → w=50 h=100
var pb = sandbox.computePaddedBounds([0, 100, 50, 0], 5);
assert(pb != null, "padded bounds valid");
assert(Math.abs(pb.w - 50) < 1e-9, "w=50");
assert(Math.abs(pb.h - 100) < 1e-9, "h=100");
// pad = 0.05 * max(50,100) = 5
assert(Math.abs(pb.pad - 5) < 1e-9, "pad=5");
assert(Math.abs(pb.paddedW - 60) < 1e-9, "paddedW=60");
assert(Math.abs(pb.paddedH - 110) < 1e-9, "paddedH=110");
assert(sandbox.computePaddedBounds([0, 0, 0, 0], 5) == null, "zero bounds null");

// square artboard
var sq = sandbox.computeArtboardRect(pb, "square");
var side = 110;
assert(sq != null, "square rect");
assert(Math.abs((sq[2] - sq[0]) - side) < 1e-6, "square width = max padded side");
assert(Math.abs((sq[1] - sq[3]) - side) < 1e-6, "square height = max padded side");

// tight
var tight = sandbox.computeArtboardRect(pb, "tight");
assert(Math.abs(tight[0] - pb.padded[0]) < 1e-9, "tight matches padded L");
assert(Math.abs(tight[2] - pb.padded[2]) < 1e-9, "tight matches padded R");

// PNG scale: hard max — never overshoot target
var scale = sandbox.calculatePngScalePct(110, 2048);
assert(scale != null, "PNG scalePct non-null");
assert(sandbox.predictedPngPixels(110, scale) <= 2048, "110pt → ≤2048px");
assert(sandbox.pngScaleRespectsMax(110, scale, 2048), "respects max 2048");

// Classic overshoot case: float side that used to yield ~2053
var sides = [100, 110, 312.47, 333.333, 512.1, 777.7, 1023.9, 2048, 0.5, 99.999];
var si;
var sc;
for (si = 0; si < sides.length; si++) {
    sc = sandbox.calculatePngScalePct(sides[si], 2048);
    assert(sc != null && sandbox.predictedPngPixels(sides[si], sc) <= 2048, "no overshoot side=" + sides[si]);
    sc = sandbox.calculatePngScalePct(sides[si], 4096);
    assert(sc != null && sandbox.predictedPngPixels(sides[si], sc) <= 4096, "no overshoot 4096 side=" + sides[si]);
}
// Exact when side divides cleanly at 100%
assert(sandbox.predictedPngPixels(2048, sandbox.calculatePngScalePct(2048, 2048)) <= 2048, "1:1 max");
assert(sandbox.predictedPngPixels(1024, sandbox.calculatePngScalePct(1024, 2048)) <= 2048, "2x scale max");

// collision
var taken = { "beachball-01": true };
var free = sandbox.nextFreeBaseName("beachball-01", function (b) {
    return !!taken[b];
});
assert(free === "beachball-01_002", "collision appends _002");

var formats = ["ai", "svg", "png"];
var existsMap = {
    "icon-01|png": true
};
var resolved = sandbox.resolveCollisionBaseName(
    "icon-01",
    formats,
    false,
    function (b, fk) {
        return !!existsMap[b + "|" + fk];
    }
);
assert(resolved === "icon-01_002", "collision across formats when only png exists");

var resolvedOw = sandbox.resolveCollisionBaseName(
    "icon-01",
    formats,
    true,
    function () {
        return true;
    }
);
assert(resolvedOw === "icon-01", "overwrite keeps base");

assert(sandbox.enabledFormatKeys(true, false, true).join(",") === "ai,png", "format keys");

var preview = sandbox.previewSequenceNames("x-", 1, 2, 3);
assert(preview[0] === "x-01" && preview[1] === "x-02" && preview[2] === "x-03", "preview sequence");

if (failed > 0) {
    console.error("\n" + failed + " assertion(s) failed");
    process.exit(1);
}
console.log("\nAll pure-helper assertions passed against shipped export-grouped-assets.jsx");
process.exit(0);
