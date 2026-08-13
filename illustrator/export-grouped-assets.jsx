#target illustrator

/**
 * Export Grouped Assets v0.2.8
 * Design: export-grouped-assets-design.md
 *
 * Select page items (groups or ungrouped) → dialog (prefix + depth 1–3 + sequence)
 * → export AI / SVG / PNG. Naming ignores object names (prefix + sequence only).
 * PNG target = hard max pixels (no overshoot); root selection order; per-format layout.
 * Source document is never saved, closed, or mutated.
 *
 * Pure helpers live between PURE_HELPERS_BEGIN / PURE_HELPERS_END so they can
 * be extracted and unit-tested without Adobe Illustrator.
 */

// --- PURE_HELPERS_BEGIN ---
// DOM-free pure functions. ExtendScript-safe: var, function, no let/const/arrows/templates.

var SCRIPT_NAME = "Export Grouped Assets";
var SCRIPT_VERSION = "0.2.8";
var PREFS_DIR_NAME = "ExportGroupedAssets";
var PREFS_FILE_NAME = "prefs.txt";

/**
 * Sanitize a filename base (no extension).
 */
function sanitizeFilename(name) {
    var s = String(name == null ? "" : name);
    // trim
    s = s.replace(/^\s+|\s+$/g, "");
    // Windows-invalid
    s = s.replace(/[<>:"\/\\|?*]/g, "_");
    // trailing periods/spaces
    s = s.replace(/[\s.]+$/g, "");
    if (s.length === 0) {
        s = "asset";
    }
    // reserved device names (whole base, case-insensitive)
    var upper = s.toUpperCase();
    var reserved = {
        CON: 1, PRN: 1, AUX: 1, NUL: 1,
        COM1: 1, COM2: 1, COM3: 1, COM4: 1, COM5: 1, COM6: 1, COM7: 1, COM8: 1, COM9: 1,
        LPT1: 1, LPT2: 1, LPT3: 1, LPT4: 1, LPT5: 1, LPT6: 1, LPT7: 1, LPT8: 1, LPT9: 1
    };
    if (reserved[upper]) {
        s = "_" + s;
    }
    return s;
}

/**
 * Zero-pad an integer; never truncates (start 95 + pad 2 → "95", 104 → "104").
 */
function zeroPad(n, padDigits) {
    var num = Math.floor(Number(n));
    if (isNaN(num)) {
        num = 0;
    }
    var s = String(num);
    var pad = Math.floor(Number(padDigits));
    if (isNaN(pad) || pad < 1) {
        pad = 1;
    }
    while (s.length < pad) {
        s = "0" + s;
    }
    return s;
}

/**
 * Sequence base name (depth 1 convenience): sanitize(prefixStem-##)
 */
function buildSequenceBaseName(prefix, startNumber, padDigits, index) {
    return buildDepthBaseName(prefix, 1, [index], padDigits, startNumber);
}

/**
 * Normalize prefix stem: trim, strip trailing hyphens (script joins with -).
 */
function normalizePrefixStem(prefix) {
    var s = String(prefix == null ? "" : prefix);
    s = s.replace(/^\s+|\s+$/g, "");
    s = s.replace(/-+$/g, "");
    return s;
}

/**
 * First hierarchy letter: 0→A … 25→Z; 26+ → zero-padded numbers 27, 28, …
 */
function letterFromIndex(index, padDigits) {
    var i = Math.floor(Number(index));
    if (isNaN(i) || i < 0) {
        i = 0;
    }
    if (i < 26) {
        return String.fromCharCode(65 + i);
    }
    return zeroPad(i + 1, padDigits);
}

/**
 * Hierarchical base name per design §6.2 / §6.6.
 * pathIndices:
 *   depth 1: [leafIdx]
 *   depth 2: [rootIdx, leafIdx]
 *   depth 3: [rootIdx, midIdx, leafIdx]
 * Start # applies to the leaf segment only; mid segments start at 1.
 */
function buildDepthBaseName(prefix, depth, pathIndices, padDigits, startNumber) {
    var d = Math.floor(Number(depth));
    if (d < 1) {
        d = 1;
    }
    if (d > 3) {
        d = 3;
    }
    var path = pathIndices || [];
    var stem = normalizePrefixStem(prefix);
    var parts = [];
    if (stem.length > 0) {
        parts.push(stem);
    }
    var leafStart = Math.floor(Number(startNumber));
    if (isNaN(leafStart)) {
        leafStart = 1;
    }
    var pad = padDigits;
    var leafIdx;
    var midIdx;
    var rootIdx;

    if (d === 1) {
        leafIdx = path.length > 0 ? path[0] : 0;
        parts.push(zeroPad(leafStart + Math.floor(Number(leafIdx)), pad));
    } else if (d === 2) {
        rootIdx = path.length > 0 ? path[0] : 0;
        leafIdx = path.length > 1 ? path[1] : 0;
        parts.push(letterFromIndex(rootIdx, pad));
        parts.push(zeroPad(leafStart + Math.floor(Number(leafIdx)), pad));
    } else {
        rootIdx = path.length > 0 ? path[0] : 0;
        midIdx = path.length > 1 ? path[1] : 0;
        leafIdx = path.length > 2 ? path[2] : 0;
        parts.push(letterFromIndex(rootIdx, pad));
        parts.push(zeroPad(1 + Math.floor(Number(midIdx)), pad));
        parts.push(zeroPad(leafStart + Math.floor(Number(leafIdx)), pad));
    }
    return sanitizeFilename(parts.join("-"));
}

/**
 * Compare two numeric index-path arrays lexicographically.
 * Returns -1, 0, or 1.
 */
function compareIndexPaths(a, b) {
    var i;
    var len = a.length < b.length ? a.length : b.length;
    for (i = 0; i < len; i++) {
        if (a[i] < b[i]) {
            return -1;
        }
        if (a[i] > b[i]) {
            return 1;
        }
    }
    if (a.length < b.length) {
        return -1;
    }
    if (a.length > b.length) {
        return 1;
    }
    return 0;
}

/**
 * Pad visibleBounds [L,T,R,B] (Illustrator Y-up: top > bottom).
 * paddingPct applied as pad = (pct/100)*max(w,h) on all four sides.
 * Returns { padded, paddedW, paddedH, cx, cy, w, h, pad } or null if invalid.
 */
function computePaddedBounds(visibleBounds, paddingPct) {
    if (!visibleBounds || visibleBounds.length < 4) {
        return null;
    }
    var left = Number(visibleBounds[0]);
    var top = Number(visibleBounds[1]);
    var right = Number(visibleBounds[2]);
    var bottom = Number(visibleBounds[3]);
    if (!isFinite(left) || !isFinite(top) || !isFinite(right) || !isFinite(bottom)) {
        return null;
    }
    var w = right - left;
    var h = top - bottom;
    if (w <= 0.001 || h <= 0.001) {
        return null;
    }
    var pct = Number(paddingPct);
    if (isNaN(pct) || pct < 0) {
        pct = 0;
    }
    var pad = (pct / 100) * (w > h ? w : h);
    var padded = [left - pad, top + pad, right + pad, bottom - pad];
    var paddedW = w + 2 * pad;
    var paddedH = h + 2 * pad;
    var cx = (left + right) / 2;
    var cy = (top + bottom) / 2;
    return {
        padded: padded,
        paddedW: paddedW,
        paddedH: paddedH,
        cx: cx,
        cy: cy,
        w: w,
        h: h,
        pad: pad
    };
}

/**
 * Artboard rect for canvas mode.
 * mode: "square" | "tight"
 * Returns [L, T, R, B] or null.
 */
function computeArtboardRect(paddedInfo, canvasMode) {
    if (!paddedInfo) {
        return null;
    }
    var mode = canvasMode === "tight" ? "tight" : "square";
    if (mode === "tight") {
        return [
            paddedInfo.padded[0],
            paddedInfo.padded[1],
            paddedInfo.padded[2],
            paddedInfo.padded[3]
        ];
    }
    var side = paddedInfo.paddedW > paddedInfo.paddedH ? paddedInfo.paddedW : paddedInfo.paddedH;
    var half = side / 2;
    var cx = paddedInfo.cx;
    var cy = paddedInfo.cy;
    return [cx - half, cy + half, cx + half, cy - half];
}

/**
 * Predicted PNG pixels along one artboard side for a given scale%.
 * Conservative: max(round, ceil) of raw points×scale/100 — must stay ≤ target.
 */
function predictedPngPixels(sidePts, scalePct) {
    var side = Number(sidePts);
    var scale = Number(scalePct);
    if (!isFinite(side) || side <= 0 || !isFinite(scale) || scale <= 0) {
        return 0;
    }
    var raw = side * scale / 100;
    var rounded = Math.round(raw);
    var ceiled = Math.ceil(raw - 1e-12);
    return rounded > ceiled ? rounded : ceiled;
}

/**
 * PNG export scale percent (horizontal === vertical).
 * targetPx is a HARD MAX longest-edge size — never overshoot (e.g. 2048 → never 2053).
 * Binary-search largest scale with predicted pixels ≤ target (may be slightly under).
 */
function calculatePngScalePct(artboardSidePts, targetPx) {
    var side = Number(artboardSidePts);
    var target = Math.floor(Number(targetPx));
    if (!isFinite(side) || side <= 0 || !isFinite(target) || target < 1) {
        return null;
    }
    var hi = (target * 100) / side;
    if (!isFinite(hi) || hi <= 0) {
        return null;
    }
    var lo = 0;
    var best = 0;
    var i;
    var mid;
    // 60 iterations → sub-ulp precision for practical sides
    for (i = 0; i < 60; i++) {
        mid = (lo + hi) / 2;
        if (predictedPngPixels(side, mid) <= target) {
            best = mid;
            lo = mid;
        } else {
            hi = mid;
        }
    }
    // Final safety shave if float edge-case still over
    i = 0;
    while (best > 0 && predictedPngPixels(side, best) > target && i < 1000) {
        best = best * 0.999;
        i++;
    }
    if (best <= 0 || predictedPngPixels(side, best) > target) {
        // Integer percent walk-down
        var intScale = Math.floor((target * 100) / side);
        while (intScale > 0 && predictedPngPixels(side, intScale) > target) {
            intScale--;
        }
        return intScale > 0 ? intScale : null;
    }
    return best;
}

/**
 * True if scale is valid under the no-overshoot contract.
 */
function pngScaleRespectsMax(sidePts, scalePct, targetPx) {
    var target = Math.floor(Number(targetPx));
    if (target < 1) {
        return false;
    }
    return predictedPngPixels(sidePts, scalePct) <= target;
}

/**
 * Longest side of artboard rect [L,T,R,B].
 */
function artboardLongestSide(artboardRect) {
    if (!artboardRect || artboardRect.length < 4) {
        return 0;
    }
    var w = artboardRect[2] - artboardRect[0];
    var h = artboardRect[1] - artboardRect[3];
    return w > h ? w : h;
}

/**
 * Resolve collision base name.
 * pathExistsFn(baseName, formatKey) → true if file exists for that format.
 * formatKeys: array of enabled format keys e.g. ["ai","svg","png"]
 * overwrite: boolean
 * Returns final base name string.
 */
function resolveCollisionBaseName(desiredBase, formatKeys, overwrite, pathExistsFn) {
    var base = desiredBase;
    if (overwrite) {
        return base;
    }
    function anyExists(b) {
        var i;
        for (i = 0; i < formatKeys.length; i++) {
            if (pathExistsFn(b, formatKeys[i])) {
                return true;
            }
        }
        return false;
    }
    if (!anyExists(base)) {
        return base;
    }
    var n = 2;
    var candidate;
    while (n < 10000) {
        candidate = base + "_" + zeroPad(n, 3);
        // design examples use _002 — zero-pad to 3 for suffix counter
        if (!anyExists(candidate)) {
            return candidate;
        }
        n++;
    }
    return base + "_" + String(new Date().getTime());
}

/**
 * Build collision suffix using _002 style (at least 3 digits for counter starting at 2).
 * Kept as separate pure path for tests: next free base when 01 taken.
 */
function nextFreeBaseName(desiredBase, isTakenFn) {
    if (!isTakenFn(desiredBase)) {
        return desiredBase;
    }
    var n = 2;
    var candidate;
    while (n < 10000) {
        candidate = desiredBase + "_" + zeroPad(n, 3);
        if (!isTakenFn(candidate)) {
            return candidate;
        }
        n++;
    }
    return desiredBase + "_x";
}

/**
 * Format keys from settings booleans.
 */
function enabledFormatKeys(exportAi, exportSvg, exportPng) {
    var keys = [];
    if (exportAi) {
        keys.push("ai");
    }
    if (exportSvg) {
        keys.push("svg");
    }
    if (exportPng) {
        keys.push("png");
    }
    return keys;
}

/**
 * Extension for format key.
 */
function extensionForFormat(formatKey) {
    if (formatKey === "ai") {
        return ".ai";
    }
    if (formatKey === "svg") {
        return ".svg";
    }
    if (formatKey === "png") {
        return ".png";
    }
    return "";
}

/**
 * Subfolder name for format key when that format is not top-level.
 */
function subfolderForFormat(formatKey) {
    if (formatKey === "ai") {
        return "AI";
    }
    if (formatKey === "svg") {
        return "SVG";
    }
    if (formatKey === "png") {
        return "PNG";
    }
    return "";
}

/**
 * True if this format dumps into the output folder root (not AI/SVG/PNG/).
 * settings: { aiTopLevel, svgTopLevel, pngTopLevel }
 */
function isFormatTopLevel(settings, formatKey) {
    var s = settings || {};
    if (formatKey === "ai") {
        return s.aiTopLevel !== false;
    }
    if (formatKey === "svg") {
        return s.svgTopLevel !== false;
    }
    if (formatKey === "png") {
        return s.pngTopLevel !== false;
    }
    return true;
}

/**
 * Relative path under output folder for one asset format (no leading slash).
 * Pure helper for tests: e.g. "MOON-A-01.png" or "SVG/MOON-A-01.svg"
 */
function relativePathForFormat(settings, baseName, formatKey) {
    var ext = extensionForFormat(formatKey);
    var name = String(baseName) + ext;
    if (isFormatTopLevel(settings, formatKey)) {
        return name;
    }
    var sub = subfolderForFormat(formatKey);
    if (sub) {
        return sub + "/" + name;
    }
    return name;
}

/**
 * Parse boolean prefs value. Invalid → fallback.
 */
function parsePrefsBool(val, fallback) {
    var s = String(val == null ? "" : val).replace(/^\s+|\s+$/g, "").toLowerCase();
    if (s === "true" || s === "1" || s === "yes") {
        return true;
    }
    if (s === "false" || s === "0" || s === "no") {
        return false;
    }
    return !!fallback;
}

/**
 * Default prefs = full dialog defaults (DOM-free).
 */
function defaultPrefs() {
    return {
        lastOutputFolder: "",
        lastPrefix: "",
        lastDepth: 1,
        startNumber: 1,
        padDigits: 2,
        exportAi: true,
        exportSvg: true,
        exportPng: true,
        targetPx: 2048,
        canvasMode: "square",
        paddingPct: 5,
        overwrite: false,
        // true = dump in output root; false = AI/ SVG/ PNG/ subfolder
        aiTopLevel: true,
        svgTopLevel: true,
        pngTopLevel: true,
        openFolder: false
    };
}

/**
 * Clamp/normalize a prefs object field-by-field (invalid key → that key's default).
 */
function normalizePrefs(prefs) {
    var d = defaultPrefs();
    var p = prefs || {};
    var out = defaultPrefs();
    out.lastOutputFolder = p.lastOutputFolder != null ? String(p.lastOutputFolder) : d.lastOutputFolder;
    out.lastPrefix = p.lastPrefix != null ? String(p.lastPrefix) : d.lastPrefix;

    var depth = Math.floor(Number(p.lastDepth));
    out.lastDepth = (!isNaN(depth) && depth >= 1 && depth <= 3) ? depth : d.lastDepth;

    var start = Math.floor(Number(p.startNumber));
    out.startNumber = (!isNaN(start) && start >= 0) ? start : d.startNumber;

    var pad = Math.floor(Number(p.padDigits));
    out.padDigits = (!isNaN(pad) && pad >= 1 && pad <= 6) ? pad : d.padDigits;

    out.exportAi = typeof p.exportAi === "boolean" ? p.exportAi : d.exportAi;
    out.exportSvg = typeof p.exportSvg === "boolean" ? p.exportSvg : d.exportSvg;
    out.exportPng = typeof p.exportPng === "boolean" ? p.exportPng : d.exportPng;

    var target = Math.floor(Number(p.targetPx));
    out.targetPx = (!isNaN(target) && target >= 1) ? target : d.targetPx;

    var mode = p.canvasMode === "tight" ? "tight" : "square";
    out.canvasMode = mode;

    var pct = Number(p.paddingPct);
    out.paddingPct = (!isNaN(pct) && pct >= 0) ? pct : d.paddingPct;

    out.overwrite = typeof p.overwrite === "boolean" ? p.overwrite : d.overwrite;
    out.aiTopLevel = typeof p.aiTopLevel === "boolean" ? p.aiTopLevel : d.aiTopLevel;
    out.svgTopLevel = typeof p.svgTopLevel === "boolean" ? p.svgTopLevel : d.svgTopLevel;
    out.pngTopLevel = typeof p.pngTopLevel === "boolean" ? p.pngTopLevel : d.pngTopLevel;
    out.openFolder = typeof p.openFolder === "boolean" ? p.openFolder : d.openFolder;
    return out;
}

/**
 * Parse prefs.txt body → prefs object. Corrupt/empty → defaults. Never throws.
 */
function parsePrefsText(text) {
    var out = defaultPrefs();
    if (text == null) {
        return out;
    }
    var raw = String(text);
    if (raw.length === 0) {
        return out;
    }
    var lines = raw.split(/\r\n|\n|\r/);
    var i;
    var line;
    var eq;
    var key;
    var val;
    var n;
    var sawTopLevelKey = false;
    var legacySubfolders = null;
    for (i = 0; i < lines.length; i++) {
        line = lines[i].replace(/^\s+|\s+$/g, "");
        if (line.length === 0 || line.charAt(0) === "#") {
            continue;
        }
        eq = line.indexOf("=");
        if (eq < 1) {
            continue;
        }
        key = line.substring(0, eq).replace(/^\s+|\s+$/g, "");
        val = line.substring(eq + 1);
        if (key === "lastOutputFolder") {
            out.lastOutputFolder = val;
        } else if (key === "lastPrefix") {
            out.lastPrefix = val;
        } else if (key === "lastDepth") {
            n = parseInt(val, 10);
            if (!isNaN(n) && n >= 1 && n <= 3) {
                out.lastDepth = n;
            }
        } else if (key === "startNumber") {
            n = parseInt(val, 10);
            if (!isNaN(n) && n >= 0) {
                out.startNumber = n;
            }
        } else if (key === "padDigits") {
            n = parseInt(val, 10);
            if (!isNaN(n) && n >= 1 && n <= 6) {
                out.padDigits = n;
            }
        } else if (key === "exportAi") {
            out.exportAi = parsePrefsBool(val, out.exportAi);
        } else if (key === "exportSvg") {
            out.exportSvg = parsePrefsBool(val, out.exportSvg);
        } else if (key === "exportPng") {
            out.exportPng = parsePrefsBool(val, out.exportPng);
        } else if (key === "targetPx") {
            n = parseInt(val, 10);
            if (!isNaN(n) && n >= 1) {
                out.targetPx = n;
            }
        } else if (key === "canvasMode") {
            if (val === "tight" || val === "square") {
                out.canvasMode = val;
            }
        } else if (key === "paddingPct") {
            n = parseFloat(val);
            if (!isNaN(n) && n >= 0) {
                out.paddingPct = n;
            }
        } else if (key === "overwrite") {
            out.overwrite = parsePrefsBool(val, out.overwrite);
        } else if (key === "aiTopLevel") {
            out.aiTopLevel = parsePrefsBool(val, out.aiTopLevel);
            sawTopLevelKey = true;
        } else if (key === "svgTopLevel") {
            out.svgTopLevel = parsePrefsBool(val, out.svgTopLevel);
            sawTopLevelKey = true;
        } else if (key === "pngTopLevel") {
            out.pngTopLevel = parsePrefsBool(val, out.pngTopLevel);
            sawTopLevelKey = true;
        } else if (key === "subfolders") {
            // Legacy master switch — only used if no per-format top-level keys
            legacySubfolders = parsePrefsBool(val, false);
        } else if (key === "openFolder") {
            out.openFolder = parsePrefsBool(val, out.openFolder);
        }
    }
    if (!sawTopLevelKey && legacySubfolders !== null) {
        // subfolders=true meant all in AI/SVG/PNG; false meant all flat
        out.aiTopLevel = !legacySubfolders;
        out.svgTopLevel = !legacySubfolders;
        out.pngTopLevel = !legacySubfolders;
    }
    return normalizePrefs(out);
}

/**
 * Serialize prefs object to prefs.txt body (all dialog keys).
 */
function serializePrefs(prefs) {
    var p = normalizePrefs(prefs);
    return (
        "lastOutputFolder=" + p.lastOutputFolder + "\n" +
        "lastPrefix=" + p.lastPrefix + "\n" +
        "lastDepth=" + String(p.lastDepth) + "\n" +
        "startNumber=" + String(p.startNumber) + "\n" +
        "padDigits=" + String(p.padDigits) + "\n" +
        "exportAi=" + (p.exportAi ? "true" : "false") + "\n" +
        "exportSvg=" + (p.exportSvg ? "true" : "false") + "\n" +
        "exportPng=" + (p.exportPng ? "true" : "false") + "\n" +
        "targetPx=" + String(p.targetPx) + "\n" +
        "canvasMode=" + p.canvasMode + "\n" +
        "paddingPct=" + String(p.paddingPct) + "\n" +
        "overwrite=" + (p.overwrite ? "true" : "false") + "\n" +
        "aiTopLevel=" + (p.aiTopLevel ? "true" : "false") + "\n" +
        "svgTopLevel=" + (p.svgTopLevel ? "true" : "false") + "\n" +
        "pngTopLevel=" + (p.pngTopLevel ? "true" : "false") + "\n" +
        "openFolder=" + (p.openFolder ? "true" : "false") + "\n"
    );
}

/**
 * Map prefs → showExportDialog defaults object.
 */
function prefsToDialogDefaults(prefs) {
    var p = normalizePrefs(prefs);
    return {
        folderPath: p.lastOutputFolder,
        prefix: p.lastPrefix,
        depth: p.lastDepth,
        startNumber: p.startNumber,
        padDigits: p.padDigits,
        exportAi: p.exportAi,
        exportSvg: p.exportSvg,
        exportPng: p.exportPng,
        targetPx: p.targetPx,
        canvasMode: p.canvasMode,
        paddingPct: p.paddingPct,
        overwrite: p.overwrite,
        aiTopLevel: p.aiTopLevel,
        svgTopLevel: p.svgTopLevel,
        pngTopLevel: p.pngTopLevel,
        openFolder: p.openFolder
    };
}

/**
 * Map dialog settings → prefs object for save.
 */
function settingsToPrefs(settings) {
    var s = settings || {};
    return normalizePrefs({
        lastOutputFolder: s.folderPath || "",
        lastPrefix: s.prefix || "",
        lastDepth: s.depth,
        startNumber: s.startNumber,
        padDigits: s.padDigits,
        exportAi: s.exportAi,
        exportSvg: s.exportSvg,
        exportPng: s.exportPng,
        targetPx: s.targetPx,
        canvasMode: s.canvasMode,
        paddingPct: s.paddingPct,
        overwrite: s.overwrite,
        aiTopLevel: s.aiTopLevel,
        svgTopLevel: s.svgTopLevel,
        pngTopLevel: s.pngTopLevel,
        openFolder: s.openFolder
    });
}

/**
 * Apply stale-folder rule: if folder non-empty and folderExistsFn false, clear folder only.
 */
function applyStaleFolderRule(prefs, folderExistsFn) {
    var p = normalizePrefs(prefs);
    if (p.lastOutputFolder.length > 0) {
        var exists = false;
        try {
            exists = !!(folderExistsFn && folderExistsFn(p.lastOutputFolder));
        } catch (eEx) {
            exists = false;
        }
        if (!exists) {
            p.lastOutputFolder = "";
        }
    }
    return p;
}

/**
 * Preview sequence strings for dialog (first few names) at a given depth.
 */
function previewSequenceNames(prefix, startNumber, padDigits, count) {
    return previewDepthNames(prefix, 1, startNumber, padDigits, count);
}

/**
 * Preview hierarchical names for depth 1–3 (synthetic paths for dialog).
 */
function previewDepthNames(prefix, depth, startNumber, padDigits, count) {
    var out = [];
    var d = Math.floor(Number(depth));
    if (d < 1) {
        d = 1;
    }
    if (d > 3) {
        d = 3;
    }
    var n = count > 0 ? count : 3;
    if (n > 5) {
        n = 5;
    }
    var i;
    if (d === 1) {
        for (i = 0; i < n; i++) {
            out.push(buildDepthBaseName(prefix, 1, [i], padDigits, startNumber));
        }
    } else if (d === 2) {
        // A-01, A-02, B-01 pattern sample
        var samples2 = [[0, 0], [0, 1], [1, 0]];
        for (i = 0; i < n && i < samples2.length; i++) {
            out.push(buildDepthBaseName(prefix, 2, samples2[i], padDigits, startNumber));
        }
    } else {
        var samples3 = [[0, 0, 0], [0, 0, 1], [0, 1, 0]];
        for (i = 0; i < n && i < samples3.length; i++) {
            out.push(buildDepthBaseName(prefix, 3, samples3[i], padDigits, startNumber));
        }
    }
    return out;
}

// --- PURE_HELPERS_END ---

(function () {
    "use strict";

    // -------------------------------------------------------------------------
    // Prefs I/O (File/Folder — Illustrator only)
    // -------------------------------------------------------------------------

    function getPrefsFile() {
        var dir = new Folder(Folder.userData.fsName + "/" + PREFS_DIR_NAME);
        if (!dir.exists) {
            dir.create();
        }
        return new File(dir.fsName + "/" + PREFS_FILE_NAME);
    }

    function loadPrefsFromDisk() {
        var prefs = defaultPrefs();
        try {
            var f = getPrefsFile();
            if (!f.exists) {
                return prefs;
            }
            f.encoding = "UTF-8";
            if (!f.open("r")) {
                return prefs;
            }
            var text = f.read();
            f.close();
            prefs = parsePrefsText(text);
        } catch (eLoad) {
            prefs = defaultPrefs();
        }
        return applyStaleFolderRule(prefs, function (path) {
            try {
                var folder = new Folder(path);
                return folder.exists;
            } catch (eEx) {
                return false;
            }
        });
    }

    function savePrefsToDisk(settings) {
        try {
            var prefs = settingsToPrefs(settings);
            var f = getPrefsFile();
            f.encoding = "UTF-8";
            if (!f.open("w")) {
                return false;
            }
            f.write(serializePrefs(prefs));
            f.close();
            return true;
        } catch (eSave) {
            return false;
        }
    }

    // -------------------------------------------------------------------------
    // Dialog
    // -------------------------------------------------------------------------

    function showExportDialog(defaults) {
        var dlg = new Window("dialog", SCRIPT_NAME + "  v" + SCRIPT_VERSION);
        dlg.orientation = "column";
        dlg.alignChildren = ["fill", "top"];
        dlg.spacing = 10;
        dlg.margins = 16;

        // Output folder
        var folderPanel = dlg.add("panel", undefined, "Output folder");
        folderPanel.orientation = "row";
        folderPanel.alignChildren = ["fill", "center"];
        folderPanel.margins = 12;
        var folderEdit = folderPanel.add("edittext", undefined, defaults.folderPath || "");
        folderEdit.preferredSize = [360, 24];
        folderEdit.enabled = true;
        var browseBtn = folderPanel.add("button", undefined, "Browse");
        browseBtn.onClick = function () {
            var f = Folder.selectDialog("Choose output folder");
            if (f) {
                folderEdit.text = f.fsName;
            }
        };

        // Naming
        var namePanel = dlg.add("panel", undefined, "Naming");
        namePanel.orientation = "column";
        namePanel.alignChildren = ["fill", "top"];
        namePanel.margins = 12;

        var prefixRow = namePanel.add("group");
        prefixRow.orientation = "row";
        prefixRow.add("statictext", undefined, "Prefix");
        var prefixEdit = prefixRow.add("edittext", undefined, defaults.prefix || "");
        prefixEdit.preferredSize = [280, 24];

        var depthRow = namePanel.add("group");
        depthRow.orientation = "row";
        depthRow.add("statictext", undefined, "Depth");
        var depthList = depthRow.add("dropdownlist", undefined, [
            "1 — selected objects (PREFIX-##)",
            "2 — child objects (PREFIX-A-##)",
            "3 — grandchildren (PREFIX-A-##-##)"
        ]);
        var defDepth = defaults.depth != null ? Math.floor(Number(defaults.depth)) : 1;
        if (defDepth < 1) {
            defDepth = 1;
        }
        if (defDepth > 3) {
            defDepth = 3;
        }
        depthList.selection = defDepth - 1;

        var numRow = namePanel.add("group");
        numRow.orientation = "row";
        numRow.add("statictext", undefined, "Start #");
        var startEdit = numRow.add("edittext", undefined, String(defaults.startNumber != null ? defaults.startNumber : 1));
        startEdit.preferredSize = [60, 24];
        numRow.add("statictext", undefined, "Pad digits");
        var padEdit = numRow.add("edittext", undefined, String(defaults.padDigits != null ? defaults.padDigits : 2));
        padEdit.preferredSize = [40, 24];

        var previewText = namePanel.add("statictext", undefined, "", { multiline: true });
        previewText.preferredSize = [420, 40];

        function currentDepth() {
            if (depthList.selection) {
                return depthList.selection.index + 1;
            }
            return 1;
        }

        function updatePreview() {
            var p = prefixEdit.text;
            var st = parseInt(startEdit.text, 10);
            var pd = parseInt(padEdit.text, 10);
            var dep = currentDepth();
            if (isNaN(st)) {
                st = 1;
            }
            if (isNaN(pd)) {
                pd = 2;
            }
            var names = previewDepthNames(p, dep, st, pd, 3);
            previewText.text = "Preview: " + names.join(", ") + "\nRoot A,B,C… = selection order · object names ignored";
        }
        prefixEdit.onChanging = updatePreview;
        startEdit.onChanging = updatePreview;
        padEdit.onChanging = updatePreview;
        depthList.onChange = updatePreview;
        updatePreview();

        // Formats: enable + top-level (root dump) per type
        var fmtPanel = dlg.add("panel", undefined, "Formats");
        fmtPanel.orientation = "column";
        fmtPanel.alignChildren = ["fill", "top"];
        fmtPanel.margins = 12;
        fmtPanel.add("statictext", undefined, "Top-level = dump in output folder; off = AI/ SVG/ PNG/ subfolder");

        var hdr = fmtPanel.add("group");
        hdr.orientation = "row";
        hdr.add("statictext", undefined, "     ");
        hdr.add("statictext", undefined, "Export");
        hdr.add("statictext", undefined, "  Top-level");

        function makeFormatRow(label, exportDefault, topDefault) {
            var row = fmtPanel.add("group");
            row.orientation = "row";
            row.alignChildren = ["left", "center"];
            var nameSt = row.add("statictext", undefined, label);
            nameSt.preferredSize = [36, 20];
            var expCb = row.add("checkbox", undefined, "");
            expCb.value = exportDefault !== false;
            var topCb = row.add("checkbox", undefined, "");
            topCb.value = topDefault !== false;
            return { exp: expCb, top: topCb };
        }

        var aiRow = makeFormatRow("AI", defaults.exportAi, defaults.aiTopLevel);
        var svgRow = makeFormatRow("SVG", defaults.exportSvg, defaults.svgTopLevel);
        var pngRow = makeFormatRow("PNG", defaults.exportPng, defaults.pngTopLevel);
        var aiCheck = aiRow.exp;
        var svgCheck = svgRow.exp;
        var pngCheck = pngRow.exp;
        var aiTopCheck = aiRow.top;
        var svgTopCheck = svgRow.top;
        var pngTopCheck = pngRow.top;

        // PNG
        var pngPanel = dlg.add("panel", undefined, "PNG");
        pngPanel.orientation = "column";
        pngPanel.alignChildren = ["left", "top"];
        pngPanel.margins = 12;

        var sizeRow = pngPanel.add("group");
        sizeRow.add("statictext", undefined, "Target size (px)");
        var targetEdit = sizeRow.add("edittext", undefined, String(defaults.targetPx != null ? defaults.targetPx : 2048));
        targetEdit.preferredSize = [80, 24];

        var modeRow = pngPanel.add("group");
        modeRow.add("statictext", undefined, "Canvas");
        var modeList = modeRow.add("dropdownlist", undefined, ["Square canvas", "Tight bounds"]);
        if (defaults.canvasMode === "tight") {
            modeList.selection = 1;
        } else {
            modeList.selection = 0;
        }

        var padPctRow = pngPanel.add("group");
        padPctRow.add("statictext", undefined, "Padding %");
        var padPctEdit = padPctRow.add("edittext", undefined, String(defaults.paddingPct != null ? defaults.paddingPct : 5));
        padPctEdit.preferredSize = [60, 24];

        function syncPngEnabled() {
            var on = pngCheck.value;
            targetEdit.enabled = on;
            modeList.enabled = on;
            padPctEdit.enabled = on;
            pngTopCheck.enabled = on;
        }
        function syncTopEnabled() {
            aiTopCheck.enabled = aiCheck.value;
            svgTopCheck.enabled = svgCheck.value;
            syncPngEnabled();
        }
        aiCheck.onClick = syncTopEnabled;
        svgCheck.onClick = syncTopEnabled;
        pngCheck.onClick = syncTopEnabled;
        syncTopEnabled();

        // Files
        var filePanel = dlg.add("panel", undefined, "Files");
        filePanel.orientation = "column";
        filePanel.alignChildren = ["left", "top"];
        filePanel.margins = 12;
        var overwriteCheck = filePanel.add("checkbox", undefined, "Overwrite existing");
        overwriteCheck.value = !!defaults.overwrite;
        var openFolderCheck = filePanel.add("checkbox", undefined, "Open folder when finished");
        openFolderCheck.value = !!defaults.openFolder;

        dlg.add("statictext", undefined, "Depth expands objects inside the selection. Hierarchy is in the filename.", { multiline: true });

        var btnRow = dlg.add("group");
        btnRow.alignment = "right";
        var cancelBtn = btnRow.add("button", undefined, "Cancel", { name: "cancel" });
        var exportBtn = btnRow.add("button", undefined, "Export", { name: "ok" });

        var result = null;

        function readSettings() {
            var canvasMode = "square";
            if (modeList.selection && modeList.selection.index === 1) {
                canvasMode = "tight";
            }
            return {
                folderPath: folderEdit.text.replace(/^\s+|\s+$/g, ""),
                prefix: prefixEdit.text,
                depth: currentDepth(),
                startNumber: parseInt(startEdit.text, 10),
                padDigits: parseInt(padEdit.text, 10),
                exportAi: aiCheck.value,
                exportSvg: svgCheck.value,
                exportPng: pngCheck.value,
                targetPx: parseInt(targetEdit.text, 10),
                canvasMode: canvasMode,
                paddingPct: parseFloat(padPctEdit.text),
                overwrite: overwriteCheck.value,
                aiTopLevel: aiTopCheck.value,
                svgTopLevel: svgTopCheck.value,
                pngTopLevel: pngTopCheck.value,
                openFolder: openFolderCheck.value
            };
        }

        function validateSettings(s) {
            if (!s.prefix || String(s.prefix).replace(/^\s+|\s+$/g, "").length === 0) {
                return "Prefix is required.";
            }
            if (isNaN(s.depth) || s.depth < 1 || s.depth > 3 || s.depth !== Math.floor(s.depth)) {
                return "Depth must be 1, 2, or 3.";
            }
            if (isNaN(s.startNumber) || s.startNumber < 0 || s.startNumber !== Math.floor(s.startNumber)) {
                return "Start # must be an integer ≥ 0.";
            }
            if (isNaN(s.padDigits) || s.padDigits < 1 || s.padDigits > 6 || s.padDigits !== Math.floor(s.padDigits)) {
                return "Pad digits must be an integer from 1 to 6.";
            }
            if (!s.exportAi && !s.exportSvg && !s.exportPng) {
                return "Enable at least one format.";
            }
            if (!s.folderPath) {
                return "Choose an output folder.";
            }
            if (s.exportPng) {
                if (isNaN(s.targetPx) || s.targetPx < 1) {
                    return "PNG target size must be a positive integer.";
                }
                if (isNaN(s.paddingPct) || s.paddingPct < 0) {
                    return "Padding % must be ≥ 0.";
                }
            }
            var folder = new Folder(s.folderPath);
            if (!folder.exists) {
                var created = folder.create();
                if (!created || !folder.exists) {
                    return "Can't create output folder.";
                }
            }
            return null;
        }

        exportBtn.onClick = function () {
            var s = readSettings();
            var err = validateSettings(s);
            if (err) {
                alert(err);
                return;
            }
            // writability probe
            try {
                ensureOutputLayout(s);
                var probe = new File(reportPathFor(s));
                probe.encoding = "UTF-8";
                probe.open("w");
                probe.write("");
                probe.close();
            } catch (eProbe) {
                alert("Can't write to output folder: " + eProbe.message);
                return;
            }
            result = s;
            dlg.close(1);
        };

        cancelBtn.onClick = function () {
            result = null;
            dlg.close(0);
        };

        if (dlg.show() !== 1) {
            return null;
        }
        return result;
    }

    function reportPathFor(settings) {
        return settings.folderPath + "/export-report.txt";
    }

    function ensureOutputLayout(settings) {
        var keys = enabledFormatKeys(settings.exportAi, settings.exportSvg, settings.exportPng);
        var i;
        var folder;
        var key;
        for (i = 0; i < keys.length; i++) {
            key = keys[i];
            if (!isFormatTopLevel(settings, key)) {
                folder = new Folder(settings.folderPath + "/" + subfolderForFormat(key));
                if (!folder.exists) {
                    folder.create();
                }
            }
        }
    }

    function filePathFor(settings, baseName, formatKey) {
        return settings.folderPath + "/" + relativePathForFormat(settings, baseName, formatKey);
    }

    // -------------------------------------------------------------------------
    // Selection + order
    // -------------------------------------------------------------------------

    function selectionToArray(doc) {
        var sel = doc.selection;
        if (sel == null) {
            return [];
        }
        // TextRange or non-array
        if (!(sel instanceof Array)) {
            // some hosts: selection is array-like Collection
            try {
                if (typeof sel.length === "number" && sel.typename !== "TextRange") {
                    var arr = [];
                    var i;
                    for (i = 0; i < sel.length; i++) {
                        arr.push(sel[i]);
                    }
                    return arr;
                }
            } catch (eCol) {
                // fall through
            }
            return [];
        }
        var out = [];
        var j;
        for (j = 0; j < sel.length; j++) {
            out.push(sel[j]);
        }
        return out;
    }

    function isGroupItem(it) {
        try {
            return !!(it && it.typename === "GroupItem");
        } catch (eG) {
            return false;
        }
    }

    /**
     * Drawable page item we can duplicate + export.
     * Drops guides, layers, documents, and text-edit ranges — not ungrouped art.
     */
    function isExportablePageItem(it) {
        if (!it) {
            return false;
        }
        try {
            if (it.guides) {
                return false;
            }
        } catch (eGuides) {
            // PathItem.guides missing → treat as art
        }
        var t;
        try {
            t = it.typename;
        } catch (eType) {
            return false;
        }
        if (!t || t === "Layer" || t === "Document" || t === "TextRange") {
            return false;
        }
        return true;
    }

    function collectSelectedItems(doc) {
        var items = selectionToArray(doc);
        var kept = [];
        var skipped = 0;
        var i;
        var it;
        for (i = 0; i < items.length; i++) {
            it = items[i];
            if (isExportablePageItem(it)) {
                kept.push(it);
            } else {
                skipped++;
            }
        }
        return { items: kept, skippedNonGroup: skipped, selectedCount: items.length };
    }

    function isInSet(item, setArr) {
        var i;
        for (i = 0; i < setArr.length; i++) {
            if (setArr[i] === item) {
                return true;
            }
            // VERIFY fallback: uuid if available
            try {
                if (item.uuid && setArr[i].uuid && item.uuid === setArr[i].uuid) {
                    return true;
                }
            } catch (eUuid) {
                // ignore
            }
        }
        return false;
    }

    function removeNestedDuplicates(groups) {
        var result = [];
        var i;
        var g;
        var p;
        var drop;
        for (i = 0; i < groups.length; i++) {
            g = groups[i];
            drop = false;
            p = g.parent;
            while (p) {
                try {
                    if (p.typename === "Document" || p.typename === "Layer") {
                        // Layer is not a selected group ancestor for this purpose;
                        // keep walking only through page items / groups
                        if (p.typename === "Document") {
                            break;
                        }
                        // parent Layer: stop ancestor group walk
                        break;
                    }
                } catch (eType) {
                    break;
                }
                if (isExportablePageItem(p) && isInSet(p, groups)) {
                    drop = true;
                    break;
                }
                try {
                    p = p.parent;
                } catch (ePar) {
                    break;
                }
            }
            if (!drop) {
                result.push(g);
            }
        }
        return result;
    }

    /**
     * Build index path: [topLayerIdx, ...sublayerIdxs, pageItemIdx]
     * Sublayer-nested groups sort before siblings that are direct pageItems
     * of the parent when paths diverge (design tie-break).
     *
     * Do NOT use selection-array order or zOrderPosition (banned — buggy on
     * sublayer items). Stacking uses index paths only.
     */
    function getIndexPath(item, doc) {
        var path = [];
        var chain = [];
        var cur = item;
        var safety = 0;
        while (cur && safety < 200) {
            safety++;
            try {
                if (cur.typename === "Document") {
                    break;
                }
            } catch (eDoc) {
                break;
            }
            chain.unshift(cur);
            try {
                cur = cur.parent;
            } catch (eP) {
                break;
            }
        }

        // chain[0] should be a Layer under the document
        var i;
        var node;
        var parentNode;
        var idx;
        var layers;
        var pageItems;
        var sublayers;

        for (i = 0; i < chain.length; i++) {
            node = chain[i];
            parentNode = i === 0 ? doc : chain[i - 1];

            if (node.typename === "Layer") {
                // find among parent.layers or doc.layers
                try {
                    layers = parentNode.layers;
                    idx = indexOfInCollection(layers, node);
                    if (idx < 0) {
                        idx = 9999;
                    }
                    path.push(idx);
                } catch (eL) {
                    path.push(9999);
                }
            } else {
                // page item: index within parent.pageItems
                try {
                    pageItems = parentNode.pageItems;
                    idx = indexOfInCollection(pageItems, node);
                    if (idx < 0) {
                        idx = 9999;
                    }
                    // design: sublayer-nested sorts before direct items of same
                    // container — encode by pushing a marker? Paths already differ
                    // because sublayer-nested has extra layer index segments.
                    path.push(idx);
                } catch (ePi) {
                    path.push(9999);
                }
            }
        }
        return path;
    }

    function indexOfInCollection(coll, item) {
        var i;
        try {
            for (i = 0; i < coll.length; i++) {
                if (coll[i] === item) {
                    return i;
                }
                try {
                    if (item.uuid && coll[i].uuid && item.uuid === coll[i].uuid) {
                        return i;
                    }
                } catch (eU) {
                    // ignore
                }
            }
        } catch (e) {
            return -1;
        }
        return -1;
    }

    function sortGroupsByStacking(groups, doc) {
        var decorated = [];
        var i;
        for (i = 0; i < groups.length; i++) {
            decorated.push({
                group: groups[i],
                path: getIndexPath(groups[i], doc)
            });
        }
        decorated.sort(function (a, b) {
            return compareIndexPaths(a.path, b.path);
        });
        var out = [];
        for (i = 0; i < decorated.length; i++) {
            out.push(decorated[i].group);
        }
        return out;
    }

    /**
     * Push group into list if not already present (=== / uuid).
     */
    function pushUniqueGroup(list, g) {
        if (!g || g.typename !== "GroupItem") {
            return;
        }
        if (!isInSet(g, list)) {
            list.push(g);
        }
    }

    /**
     * Immediate child GroupItems — use BOTH groupItems and pageItems.
     * Illustrator sometimes exposes nested groups on one collection but not the other
     * (clip groups, odd nesting). Sorted by stacking order.
     */
    function getDirectChildGroups(parentGroup, doc) {
        var kids = [];
        var i;
        var it;
        try {
            if (parentGroup.groupItems && parentGroup.groupItems.length) {
                for (i = 0; i < parentGroup.groupItems.length; i++) {
                    pushUniqueGroup(kids, parentGroup.groupItems[i]);
                }
            }
        } catch (eG) {
            // continue with pageItems
        }
        try {
            if (parentGroup.pageItems && parentGroup.pageItems.length) {
                for (i = 0; i < parentGroup.pageItems.length; i++) {
                    it = parentGroup.pageItems[i];
                    if (it && it.typename === "GroupItem") {
                        pushUniqueGroup(kids, it);
                    }
                }
            }
        } catch (eP) {
            // ignore
        }
        return sortGroupsByStacking(kids, doc);
    }

    /**
     * Immediate children to export as siblings: groups AND ungrouped art.
     * Groups still come from the dual groupItems/pageItems walk (Illustrator
     * sometimes hides nested groups on one collection). Loose paths/compounds/
     * symbols/text are appended from pageItems. Guides stay out.
     */
    function getDirectChildItems(parentItem, doc) {
        var kids = [];
        var i;
        var it;
        var groups = getDirectChildGroups(parentItem, doc);
        for (i = 0; i < groups.length; i++) {
            kids.push(groups[i]);
        }
        try {
            if (parentItem.pageItems && parentItem.pageItems.length) {
                for (i = 0; i < parentItem.pageItems.length; i++) {
                    it = parentItem.pageItems[i];
                    if (isExportablePageItem(it) && !isGroupItem(it) && !isInSet(it, kids)) {
                        kids.push(it);
                    }
                }
            }
        } catch (eItems) {
            // ignore
        }
        return sortPageItemsByStacking(kids, doc);
    }

    /**
     * Count immediate GroupItem children without sorting (safe without doc).
     */
    function countDirectChildGroups(parentGroup) {
        var n = 0;
        var i;
        var it;
        var seen = [];
        try {
            if (parentGroup.groupItems && parentGroup.groupItems.length) {
                for (i = 0; i < parentGroup.groupItems.length; i++) {
                    it = parentGroup.groupItems[i];
                    if (it && it.typename === "GroupItem" && !isInSet(it, seen)) {
                        seen.push(it);
                        n++;
                    }
                }
            }
        } catch (e1) { /* ignore */ }
        try {
            if (parentGroup.pageItems && parentGroup.pageItems.length) {
                for (i = 0; i < parentGroup.pageItems.length; i++) {
                    it = parentGroup.pageItems[i];
                    if (it && it.typename === "GroupItem" && !isInSet(it, seen)) {
                        seen.push(it);
                        n++;
                    }
                }
            }
        } catch (e2) { /* ignore */ }
        return n;
    }

    /**
     * True if this group has no GroupItem children (exportable leaf asset).
     */
    function isLeafGroup(groupItem) {
        return countDirectChildGroups(groupItem) === 0;
    }

    /**
     * All descendant GroupItems under parent (any depth), unique, not including parent.
     */
    function collectAllDescendantGroups(parentGroup, doc, acc, depthLeft) {
        if (depthLeft < 0) {
            return;
        }
        var kids = getDirectChildGroups(parentGroup, doc);
        var i;
        var k;
        for (i = 0; i < kids.length; i++) {
            k = kids[i];
            pushUniqueGroup(acc, k);
            collectAllDescendantGroups(k, doc, acc, depthLeft - 1);
        }
    }

    /**
     * All immediate page items under a container (any typename).
     */
    function getDirectPageItemsAll(parentItem) {
        var items = [];
        var i;
        var it;
        try {
            if (!parentItem.pageItems) {
                return items;
            }
            for (i = 0; i < parentItem.pageItems.length; i++) {
                it = parentItem.pageItems[i];
                if (it) {
                    items.push(it);
                }
            }
        } catch (eAll) {
            return [];
        }
        return items;
    }

    /**
     * Short diagnostic of what's inside a vessel (for the report).
     */
    function describeVesselContents(root) {
        var parts = [];
        var gi = -1;
        var pi = -1;
        var i;
        var t;
        var counts = {};
        var keys;
        var k;
        try {
            gi = root.groupItems ? root.groupItems.length : 0;
        } catch (e1) {
            gi = -1;
        }
        try {
            pi = root.pageItems ? root.pageItems.length : 0;
        } catch (e2) {
            pi = -1;
        }
        parts.push("groupItems=" + gi);
        parts.push("pageItems=" + pi);
        try {
            for (i = 0; i < pi && i < 24; i++) {
                t = root.pageItems[i].typename || "?";
                counts[t] = (counts[t] || 0) + 1;
            }
            keys = [];
            for (k in counts) {
                if (counts.hasOwnProperty(k)) {
                    keys.push(k + ":" + counts[k]);
                }
            }
            if (keys.length) {
                parts.push("types{" + keys.join(", ") + "}");
            }
        } catch (e3) {
            // ignore
        }
        return parts.join(" ");
    }

    /**
     * Sort any page items by document stacking (same as groups).
     */
    function sortPageItemsByStacking(items, doc) {
        return sortGroupsByStacking(items, doc);
    }

    /**
     * When there are no GroupItems, export every distinct drawable inside the
     * vessel: direct page items, or page items nested one wrapper deep.
     */
    function harvestNonGroupContents(root, doc) {
        var direct = getDirectPageItemsAll(root);
        var out = [];
        var i;
        var it;
        var nested;
        var j;
        if (direct.length === 0) {
            return out;
        }
        // Single wrapper group with only non-group guts was already handled by
        // group harvest. Here: raw paths/compounds/symbols/etc. as siblings.
        for (i = 0; i < direct.length; i++) {
            it = direct[i];
            if (!it) {
                continue;
            }
            if (it.typename === "GroupItem") {
                // Should have been caught earlier; still expand as safety
                nested = getDirectPageItemsAll(it);
                if (nested.length === 0) {
                    out.push(it);
                } else if (countDirectChildGroups(it) === 0) {
                    // Group of only paths — one asset (the group) if multi-path moon,
                    // OR each path if many siblings? Prefer group as one moon.
                    out.push(it);
                } else {
                    for (j = 0; j < nested.length; j++) {
                        out.push(nested[j]);
                    }
                }
            } else {
                out.push(it);
            }
        }
        // If everything collapsed to the root's single child group of paths, keep it
        if (out.length === 1 && out[0] === root) {
            return [];
        }
        return sortPageItemsByStacking(out, doc);
    }

    /**
     * Page items to export from inside one depth-2 root (vessel):
     * 1) all direct siblings (groups AND ungrouped art)
     * 2) unwrap a single wrapper group (same as before)
     * 3) nested leaf groups anywhere under root
     * 4) else every page item inside (paths, compounds, …)
     * 5) else empty (caller may export root)
     */
    function getExportChildrenDepth2(root, doc) {
        var siblings = getDirectChildItems(root, doc);
        var groups = [];
        var i;
        for (i = 0; i < siblings.length; i++) {
            if (isGroupItem(siblings[i])) {
                groups.push(siblings[i]);
            }
        }
        if (groups.length > 0) {
            // Only unwrap when the sole child is a wrapper group (no loose siblings)
            if (groups.length === 1 && siblings.length === 1) {
                var inner = getDirectChildGroups(groups[0], doc);
                if (inner.length > 1) {
                    return sortGroupsByStacking(inner, doc);
                }
                if (inner.length === 0) {
                    var wrapped = harvestNonGroupContents(groups[0], doc);
                    if (wrapped.length >= 1) {
                        return wrapped;
                    }
                    return groups;
                }
            }
            // Mixed or multiple children: keep ungrouped siblings in the sequence
            return siblings;
        }
        // No direct group children — harvest nested leaf groups anywhere under root
        var all = [];
        collectAllDescendantGroups(root, doc, all, 12);
        if (all.length > 0) {
            var leaves = [];
            for (i = 0; i < all.length; i++) {
                if (isLeafGroup(all[i])) {
                    leaves.push(all[i]);
                }
            }
            if (leaves.length > 0) {
                return sortGroupsByStacking(leaves, doc);
            }
            return sortGroupsByStacking(all, doc);
        }
        // Still no GroupItems at any depth (MOON-A case): export page items inside
        return harvestNonGroupContents(root, doc);
    }

    /**
     * Expand selected roots by depth into export units.
     * Each unit: { group, pathIndices }
     * skippedBranches: roots/mids that still produced nothing usable.
     */
    function expandExportUnits(roots, depth, doc) {
        var units = [];
        var skippedBranches = [];
        var d = Math.floor(Number(depth));
        if (d < 1) {
            d = 1;
        }
        if (d > 3) {
            d = 3;
        }
        var ri;
        var root;
        var children;
        var ci;
        var mids;
        var mi;
        var leaves;
        var li;
        var letter;

        if (d === 1) {
            for (ri = 0; ri < roots.length; ri++) {
                units.push({
                    group: roots[ri],
                    pathIndices: [ri]
                });
            }
            return { units: units, skippedBranches: skippedBranches };
        }

        if (d === 2) {
            for (ri = 0; ri < roots.length; ri++) {
                root = roots[ri];
                letter = letterFromIndex(ri, 2);
                children = getExportChildrenDepth2(root, doc);
                if (children.length === 0) {
                    // Last resort: export the outer group itself as one asset
                    units.push({
                        group: root,
                        pathIndices: [ri, 0]
                    });
                    skippedBranches.push({
                        rootIndex: ri,
                        reason: "root " + letter + ": empty vessel — exported outer as " + letter + "-01 [" + describeVesselContents(root) + "]"
                    });
                    continue;
                }
                // Note in report when we used non-group page items
                if (getDirectChildGroups(root, doc).length === 0) {
                    skippedBranches.push({
                        rootIndex: ri,
                        reason: "root " + letter + ": no child groups — split into " + children.length + " page item(s) [" + describeVesselContents(root) + "]"
                    });
                }
                for (ci = 0; ci < children.length; ci++) {
                    units.push({
                        group: children[ci],
                        pathIndices: [ri, ci]
                    });
                }
            }
            return { units: units, skippedBranches: skippedBranches };
        }

        // depth 3
        for (ri = 0; ri < roots.length; ri++) {
            root = roots[ri];
            letter = letterFromIndex(ri, 2);
            mids = getDirectChildItems(root, doc);
            if (mids.length === 0) {
                // Fall back: treat like depth 2 harvest under root, mid fixed 0
                children = getExportChildrenDepth2(root, doc);
                if (children.length === 0) {
                    units.push({
                        group: root,
                        pathIndices: [ri, 0, 0]
                    });
                    skippedBranches.push({
                        rootIndex: ri,
                        reason: "root " + letter + ": no mid objects at depth 3 — exported outer as single asset"
                    });
                    continue;
                }
                for (ci = 0; ci < children.length; ci++) {
                    units.push({
                        group: children[ci],
                        pathIndices: [ri, 0, ci]
                    });
                }
                continue;
            }
            for (mi = 0; mi < mids.length; mi++) {
                if (!isGroupItem(mids[mi])) {
                    units.push({
                        group: mids[mi],
                        pathIndices: [ri, mi, 0]
                    });
                    continue;
                }
                leaves = getDirectChildItems(mids[mi], doc);
                if (leaves.length === 0) {
                    // mid has no children — export mid itself; or nested harvest
                    children = getExportChildrenDepth2(mids[mi], doc);
                    if (children.length === 0) {
                        units.push({
                            group: mids[mi],
                            pathIndices: [ri, mi, 0]
                        });
                        skippedBranches.push({
                            rootIndex: ri,
                            midIndex: mi,
                            reason: "root " + letter + " mid " + (mi + 1) + ": no grandchildren — exported mid as single asset"
                        });
                        continue;
                    }
                    for (li = 0; li < children.length; li++) {
                        units.push({
                            group: children[li],
                            pathIndices: [ri, mi, li]
                        });
                    }
                    continue;
                }
                for (li = 0; li < leaves.length; li++) {
                    units.push({
                        group: leaves[li],
                        pathIndices: [ri, mi, li]
                    });
                }
            }
        }
        return { units: units, skippedBranches: skippedBranches };
    }

    // -------------------------------------------------------------------------
    // Bounds + artboard
    // -------------------------------------------------------------------------

    function getEffectiveBounds(pageItem) {
        try {
            // Clip mitigation: if clipped group, try clipping path bounds
            try {
                if (pageItem.typename === "GroupItem" && pageItem.clipped) {
                    var j;
                    var pi;
                    for (j = 0; j < pageItem.pageItems.length; j++) {
                        pi = pageItem.pageItems[j];
                        try {
                            if (pi.clipping) {
                                return pi.visibleBounds;
                            }
                        } catch (eClip) {
                            // continue
                        }
                    }
                }
            } catch (eClipped) {
                // not a group / no clipped flag
            }
            return pageItem.visibleBounds;
        } catch (e) {
            return null;
        }
    }

    function applyArtboardFromGroup(tempDoc, groupItem, settings) {
        var vb = getEffectiveBounds(groupItem);
        var padded = computePaddedBounds(vb, settings.paddingPct);
        if (!padded) {
            return { ok: false, error: "Invalid or zero-sized bounds" };
        }
        // AI/SVG: use tight padded artboard always for vector export geometry;
        // PNG square mode expands artboard to square (design §7).
        var mode = settings.canvasMode;
        // For AI/SVG we still use the artboard we set; PNG scale uses longest side.
        // Use square artboard when PNG square mode so all formats share one canvas.
        var rect = computeArtboardRect(padded, mode);
        if (!rect) {
            return { ok: false, error: "Could not compute artboard" };
        }
        tempDoc.artboards[0].artboardRect = rect;
        return {
            ok: true,
            artboardRect: rect,
            padded: padded,
            longestSide: artboardLongestSide(rect)
        };
    }

    // -------------------------------------------------------------------------
    // Export options (§19)
    // -------------------------------------------------------------------------

    function createIllustratorSaveOptions() {
        var opts = new IllustratorSaveOptions();
        try {
            // CC-era; VERIFY enum on installed version
            opts.compatibility = Compatibility.ILLUSTRATOR17;
        } catch (eCompat) {
            try {
                opts.compatibility = Compatibility.ILLUSTRATOR24;
            } catch (e2) {
                // leave default
            }
        }
        try {
            opts.pdfCompatible = true;
        } catch (ePdf) { /* ignore */ }
        try {
            opts.compressed = true;
        } catch (eC) { /* ignore */ }
        try {
            opts.embedICCProfile = true;
        } catch (eIcc) { /* ignore */ }
        return opts;
    }

    function createSvgOptions() {
        var opts = new ExportOptionsSVG();
        try {
            opts.embedRasterImages = true;
        } catch (e1) { /* ignore */ }
        try {
            opts.coordinatePrecision = 3;
        } catch (e2) { /* ignore */ }
        try {
            opts.DTD = SVGDTDVersion.SVG1_1;
        } catch (e3) { /* ignore */ }
        // Prefer editable SVG text (design); outline only as fallback
        try {
            opts.fontType = SVGFontType.SVGFONT;
        } catch (e4) {
            try {
                opts.fontType = SVGFontType.OUTLINEFONT;
            } catch (e5) { /* ignore */ }
        }
        // Artboard crop — known trap; VERIFY filename suffix
        try {
            opts.saveMultipleArtboards = true;
            opts.artboardRange = "1";
        } catch (e6) { /* ignore */ }
        return opts;
    }

    function createPngOptions(scalePct) {
        var opts = new ExportOptionsPNG24();
        opts.antiAliasing = true;
        opts.transparency = true;
        try {
            opts.artBoardClipping = true;
        } catch (eAbc) { /* ignore */ }
        opts.horizontalScale = scalePct;
        opts.verticalScale = scalePct;
        return opts;
    }

    function exportAi(tempDoc, filePath) {
        var f = new File(filePath);
        tempDoc.saveAs(f, createIllustratorSaveOptions());
    }

    function exportSvg(tempDoc, filePath) {
        var f = new File(filePath);
        tempDoc.exportFile(f, ExportType.SVG, createSvgOptions());
        // If Illustrator appended artboard suffix, rename back
        try {
            if (!f.exists) {
                var parent = f.parent;
                var base = f.name.replace(/\.svg$/i, "");
                var files = parent.getFiles("*.svg");
                var i;
                var cand;
                for (i = 0; i < files.length; i++) {
                    cand = files[i];
                    if (cand.name.indexOf(base) === 0 && cand.name !== f.name) {
                        cand.rename(f.name);
                        break;
                    }
                }
            }
        } catch (eRen) {
            // leave as exported
        }
    }

    function exportPng(tempDoc, filePath, scalePct) {
        var f = new File(filePath);
        tempDoc.exportFile(f, ExportType.PNG24, createPngOptions(scalePct));
    }

    // -------------------------------------------------------------------------
    // Per-asset export
    // -------------------------------------------------------------------------

    function exportOneAsset(sourceDoc, groupItem, settings, baseName, formatKeys) {
        var tempDoc = null;
        var paths = {};
        var formatsDone = [];
        var result = {
            ok: false,
            baseName: baseName,
            paths: paths,
            formats: formatsDone,
            error: null
        };

        try {
            var vb = getEffectiveBounds(groupItem);
            var paddedPre = computePaddedBounds(vb, settings.paddingPct);
            if (!paddedPre) {
                result.error = "Invalid or zero-sized bounds";
                return result;
            }

            // Temp doc large enough for content
            var w = Math.ceil(paddedPre.paddedW) + 100;
            var h = Math.ceil(paddedPre.paddedH) + 100;
            if (w < 100) {
                w = 100;
            }
            if (h < 100) {
                h = 100;
            }

            tempDoc = app.documents.add(sourceDoc.documentColorSpace, w, h);

            // Cross-doc duplicate — VERIFY in Illustrator (§19 / §20)
            var dup = groupItem.duplicate(tempDoc.layers[0], ElementPlacement.PLACEATBEGINNING);

            var ab = applyArtboardFromGroup(tempDoc, dup, settings);
            if (!ab.ok) {
                result.error = ab.error;
                return result;
            }

            var scalePct = null;
            var k;
            var key;
            var path;
            for (k = 0; k < formatKeys.length; k++) {
                key = formatKeys[k];
                path = filePathFor(settings, baseName, key);
                if (key === "ai") {
                    applyArtboardFromGroup(tempDoc, dup, settings);
                    exportAi(tempDoc, path);
                } else if (key === "svg") {
                    applyArtboardFromGroup(tempDoc, dup, settings);
                    exportSvg(tempDoc, path);
                } else if (key === "png") {
                    ab = applyArtboardFromGroup(tempDoc, dup, settings);
                    if (!ab.ok) {
                        result.error = ab.error || "PNG artboard failed";
                        return result;
                    }
                    scalePct = calculatePngScalePct(ab.longestSide, settings.targetPx);
                    if (scalePct == null || !pngScaleRespectsMax(ab.longestSide, scalePct, settings.targetPx)) {
                        scalePct = calculatePngScalePct(ab.longestSide, settings.targetPx);
                    }
                    if (scalePct == null) {
                        result.error = "Could not compute PNG scale under max " + settings.targetPx;
                        return result;
                    }
                    exportPng(tempDoc, path, scalePct);
                }
                paths[key] = path;
                formatsDone.push(key);
            }

            result.ok = true;
            return result;
        } catch (e) {
            result.error = String(e.message || e);
            try {
                if (e.line) {
                    result.error += " (line " + e.line + ")";
                }
            } catch (eLine) { /* ignore */ }
            return result;
        } finally {
            if (tempDoc) {
                try {
                    tempDoc.close(SaveOptions.DONOTSAVECHANGES);
                } catch (eClose) { /* ignore */ }
            }
            try {
                sourceDoc.activate();
            } catch (eAct) { /* ignore */ }
        }
    }

    function pathExistsOnDisk(settings, baseName, formatKey) {
        var p = filePathFor(settings, baseName, formatKey);
        var f = new File(p);
        return f.exists;
    }

    function resolveBaseForSettings(desiredBase, settings, formatKeys) {
        return resolveCollisionBaseName(
            desiredBase,
            formatKeys,
            settings.overwrite,
            function (b, fk) {
                return pathExistsOnDisk(settings, b, fk);
            }
        );
    }

    // -------------------------------------------------------------------------
    // Report + summary
    // -------------------------------------------------------------------------

    function writeReport(settings, meta, assetResults) {
        var lines = [];
        lines.push(SCRIPT_NAME + " v" + SCRIPT_VERSION);
        lines.push("Date: " + meta.dateStr);
        lines.push("Illustrator: " + meta.aiVersion);
        lines.push("Source: " + meta.sourceName);
        lines.push("Output: " + settings.folderPath);
        lines.push("Prefix: " + settings.prefix);
        lines.push("Depth: " + settings.depth);
        lines.push("Start: " + settings.startNumber + "  Pad: " + settings.padDigits);
        lines.push("Order: roots = selection order; children inside vessel = stacking within parent");
        lines.push("Naming: depth1 PREFIX-## · depth2 PREFIX-A-## · depth3 PREFIX-A-##-##");
        lines.push("Formats: AI=" + settings.exportAi + " SVG=" + settings.exportSvg + " PNG=" + settings.exportPng);
        lines.push("PNG targetPx=" + settings.targetPx + " canvas=" + settings.canvasMode + " padding%=" + settings.paddingPct);
        lines.push(
            "Overwrite=" + settings.overwrite +
            " topLevel AI=" + settings.aiTopLevel +
            " SVG=" + settings.svgTopLevel +
            " PNG=" + settings.pngTopLevel
        );
        lines.push("");
        lines.push("Per-asset results:");
        var i;
        var r;
        for (i = 0; i < assetResults.length; i++) {
            r = assetResults[i];
            if (r.ok) {
                lines.push("  OK  " + r.baseName + "  [" + r.formats.join(",") + "]");
            } else {
                lines.push("  FAIL " + (r.baseName || ("index-" + i)) + "  " + (r.error || "unknown"));
            }
        }
        lines.push("");
        lines.push("Totals: selected=" + meta.selectedCount +
            " units=" + meta.groupCount +
            " success=" + meta.successCount +
            " failed=" + meta.failedCount +
            " skippedNotExportable=" + meta.skippedNonGroup);

        var file = new File(reportPathFor(settings));
        file.encoding = "UTF-8";
        file.open("w");
        file.write(lines.join("\n"));
        file.close();
        return file.fsName;
    }

    function showSummary(meta, reportPath, folderPath) {
        var msg =
            SCRIPT_NAME + " complete.\n\n" +
            "Selected objects: " + meta.selectedCount + "\n" +
            "Export units: " + meta.groupCount + "\n" +
            "Exported OK: " + meta.successCount + "\n" +
            "Failed: " + meta.failedCount + "\n" +
            "Skipped (not exportable): " + meta.skippedNonGroup + "\n\n" +
            "Output: " + folderPath + "\n" +
            "Report: " + reportPath;
        alert(msg);
    }

    // -------------------------------------------------------------------------
    // Main
    // -------------------------------------------------------------------------

    function main() {
        if (app.documents.length === 0) {
            alert("Open a document first.");
            return;
        }

        var sourceDoc = app.activeDocument;
        var collected = collectSelectedItems(sourceDoc);
        var groups = removeNestedDuplicates(collected.items);

        if (groups.length === 0) {
            alert("Select at least one object to export.");
            return;
        }

        // Roots keep selection order (after de-dupe). Do NOT re-sort by layer
        // stacking — that inverted series (select A,B,C → exported C,B,A).
        // Children inside each vessel still use stacking order in expand helpers.

        var stored = loadPrefsFromDisk();
        var settings = showExportDialog(prefsToDialogDefaults(stored));

        if (!settings) {
            return;
        }

        // Persist all dialog settings on validated Export (batch may still fail per-asset)
        savePrefsToDisk(settings);

        var expanded = expandExportUnits(groups, settings.depth, sourceDoc);
        var units = expanded.units;
        if (units.length === 0) {
            alert("No objects to export at this depth.");
            return;
        }

        var formatKeys = enabledFormatKeys(settings.exportAi, settings.exportSvg, settings.exportPng);
        ensureOutputLayout(settings);

        var priorInteraction = app.userInteractionLevel;
        var assetResults = [];
        var successCount = 0;
        var failedCount = 0;
        var i;
        var baseDesired;
        var baseFinal;
        var one;
        var unit;

        // Record empty-branch skips as failed report rows
        for (i = 0; i < expanded.skippedBranches.length; i++) {
            assetResults.push({
                ok: false,
                baseName: "(branch)",
                formats: [],
                paths: {},
                error: expanded.skippedBranches[i].reason
            });
            failedCount++;
        }

        try {
            app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;

            for (i = 0; i < units.length; i++) {
                unit = units[i];
                baseDesired = buildDepthBaseName(
                    settings.prefix,
                    settings.depth,
                    unit.pathIndices,
                    settings.padDigits,
                    settings.startNumber
                );
                baseFinal = resolveBaseForSettings(baseDesired, settings, formatKeys);
                one = exportOneAsset(sourceDoc, unit.group, settings, baseFinal, formatKeys);
                assetResults.push(one);
                if (one.ok) {
                    successCount++;
                } else {
                    failedCount++;
                }
            }
        } finally {
            try {
                app.userInteractionLevel = priorInteraction;
            } catch (eUi) { /* ignore */ }
            try {
                sourceDoc.activate();
            } catch (eAct2) { /* ignore */ }
        }

        var meta = {
            dateStr: new Date().toString(),
            aiVersion: String(app.version),
            sourceName: sourceDoc.name,
            selectedCount: collected.selectedCount,
            groupCount: units.length,
            successCount: successCount,
            failedCount: failedCount,
            skippedNonGroup: collected.skippedNonGroup
        };

        var reportPath = writeReport(settings, meta, assetResults);
        showSummary(meta, reportPath, settings.folderPath);

        if (settings.openFolder) {
            try {
                var folder = new Folder(settings.folderPath);
                folder.execute();
            } catch (eOpen) { /* ignore */ }
        }
    }

    // Only auto-run inside Illustrator (not when pure helpers are extracted)
    try {
        if (typeof app !== "undefined" && app.name) {
            main();
        }
    } catch (eBoot) {
        // Outside Illustrator: silent — helpers remain loadable for tests
    }
})();
