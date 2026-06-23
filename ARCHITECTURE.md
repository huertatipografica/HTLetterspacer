# HT Letterspacer — Architecture

A map of how the plugin is put together, so you can find the right file fast.

The project ships **two Glyphs bundles** that share **one Python package** (`htls/`):

| Bundle | Type | Bundle id | Role |
|---|---|---|---|
| `HTLetterspacer.glyphsPlugin` | `GeneralPlugin` | `com.htfonts.letterspacer` | The management window (rules, master overrides, parameters, inspector) + the spacing actions. |
| `HTLetterspacerPreview.glyphsReporter` | `ReporterPlugin` | `com.htfonts.letterspacerPreview` | The live, non-destructive **areas overlay** + per-glyph **rule report** drawn in the edit view. |

The reporter does **not** duplicate any logic — it adds the main plugin's `Resources/` to `sys.path` and imports the same `htls` package, so both run identical engine/config/rule code.

---

## Repository layout

```
HTLetterspacer/
├─ HTLetterspacer.glyphsPlugin/
│  └─ Contents/
│     ├─ Info.plist
│     ├─ MacOS/plugin                     # Glyphs convention (symlink)
│     └─ Resources/
│        ├─ plugin.py                     # GeneralPlugin: window, tabs, spacing actions
│        └─ htls/                         # SHARED package (engine + config + UI)
│           ├─ __init__.py
│           ├─ engine.py                  # spacing math + polygon calc (the core)
│           ├─ config.py                  # font storage, import/export, migration
│           ├─ rules.py                   # rule matching + effective area/depth
│           ├─ drawing.py                 # Cocoa overlay drawing (areas, text)
│           └─ ui/
│              ├─ rules.py                # Font-rules & Master-rules tabs
│              ├─ parameters.py           # Parameters tab (+ live preview strip)
│              └─ inspector.py            # Inspector tab (read-only)
├─ HTLetterspacerPreview.glyphsReporter/
│  └─ Contents/Resources/plugin.py        # ReporterPlugin; imports htls/ via sys.path
├─ HT Letterspacer Scripts/
│  ├─ Apply HTLS Config.py                # headless: space selection from font rules
│  └─ Apply HTLS Values.py               # floating UI: space selection from manual values
├─ Examples/                              # sample fonts + an exported setup (.json)
└─ ARCHITECTURE.md
```

Both bundles are typically **symlinked** into `…/Glyphs 3/Plugins/`. Plugin code loads at launch, so **restart Glyphs to pick up code changes**.

---

## The shared `htls/` package

### `engine.py` — the spacing core
A faithful port of the standalone HT Letterspacer script's math; spacing matches it exactly (stroke expansion via `applyPrepareLayerCallbacks`, `paramOver`, `paramFreq = 5`).

- **`HTLSEngine(layer, …)`** — per-layer engine. On construction it resolves the master parameters and the matching rule (`_resolve_rule`), then computes on demand. Useful attributes after construction: `effectiveArea`, `effectiveDepth`, `paramArea/Depth/Over`, `factor`, `reference_layer`, and **`matched_rule` / `matched_rule_id`** (what the reporter/inspector label with).
  - **`calculate_polygons()`** → the L/R area polygons, *without writing anything*. This is what the reporter and the Parameters preview draw.
  - **`current_layer_sidebearings()`** → computed LSB/RSB.
- **`space_layers(layers, …)`** — the batch entry point used by every "apply" path. Dedupes by (glyph, master), reads font rules once, wraps writes so the view redraws once, and handles component shifting + metric-key sync. **`space_layer(layer)`** is the single-layer convenience.
- The inputs layer is the only departure from the script: instead of a global `paramArea * factor`, each glyph gets an **effective area/depth** resolved from its matched rule (see `rules.py`).

### `rules.py` — matching & effective values
- **`find_rule(glyph, font_rules, master)`** → the best-matching `(rule_id, rule)` or `None`. **`rank_rules(...)`** returns all matches ranked (the Inspector uses this).
- Scoring (`_match_score`) is specificity-based: glyphlist (hard filter) > category > script/subcategory/case > filter. `"Any"` on a field = no constraint.
- **`resolve_area` / `resolve_depth`** turn a rule's `{mode, value}` spec (+ any per-master override) into absolute units against the master base parameters.

### `config.py` — storage, import/export, migration
The **font is the single source of truth at runtime**; files are import/export only.

- **Rule shape** — a flat dict `{rule_id: rule}`. Each rule: `name, category, script, subcategory, case, filter, reference, area{mode,value}, depth{mode,value}, tabular, sides{LSB,RSB}, glyphlist`. `make_rule(**fields)` / `_normalize_rule` fill defaults; `default_rules()` is the "Reset to defaults" set.
- **Read/write** — `read_font_rules(font)` / `write_font_rules(font, rules)`. The loader (`_load_rules`) is dual-shape: it reads the current flat shape *and* older bucketed/legacy shapes, normalising them.
- **Migration** — `migrate_font` / `migrate_master_rules` rename legacy keys to the current namespace on first write (see *Storage keys* below). Legacy eweracs rules (single factor) map to `area {percent, factor*100}`.
- **Legacy import** — `import_config_file` + `parse_config_text` hand-parse the old comma-separated `.yml`/`.py` configs (both dialects). No external YAML dependency.
- **Setup import/export** — `serialize_setup` / `parse_setup_text` / `import_setup` handle the full **versioned JSON** setup (rules + per-master parameters + per-master overrides), with master-name remapping.

### `drawing.py` — Cocoa overlay rendering
Pure drawing, never writes to the font. Used by the reporter and the Parameters preview.
- **`build_area_path(polygons)` + `fill_path(path, color)`** — split so the reporter can **cache the `NSBezierPath`** and just re-fill each frame. `draw_areas` is a build+fill convenience for the preview.
- **`area_color(index)`** — per-rule fill colour from a 20-entry golden-ratio palette (`index is None` → grey).
- **`draw_lines(...)` / `draw_label(...)`** — constant-on-screen-size text (scaled by the edit-view zoom).

### `ui/` — the window tabs
Each tab is a manager class given the `plugin` and its `vanilla` group:
- **`ui/rules.py`** — `FontRulesManager` and `MasterRulesManager` (a two-column list + `RuleEditor`), sharing `_RuleListMixin` for sort-safe, identity-based selection. Also holds the toolbar (`+`, `+=`, `−`, Duplicate, `⋯` menu) and the import/export/reset handlers + the v2 setup import sheet (`_ImportSetupSheet`).
- **`ui/parameters.py`** — `ParametersManager`: edit the master's `paramArea/paramDepth/paramOver`, a **live non-destructive preview strip** (`_StripView`, drawing predicted areas via `drawing`), copy-from-master and **interpolate** (`_InterpolateSheet`).
- **`ui/inspector.py`** — `InspectorManager`: read-only view of the selected glyph's categorization and which rules match it (via `rules.rank_rules`).

---

## The main plugin (`plugin.py`)

`class HTLetterspacer(GeneralPlugin)` owns the window and is the hub the UI talks back to.

- **Window & tabs** — built in `showWindow_`: a `Tabs` of *Font rules / Master rules / Parameters / Inspector*, plus a shared footer (Apply to selection / Apply to current tab / Live tab apply / All masters / Keep components).
- **Working state** — `font_rules` (in-memory copy), reloaded with `reload_rules`, persisted with `write_rules`.
- **Spacing actions** — `_apply_selection`, `_apply_tab`, `space_current_tab`, `live_apply_tab` — all funnel into `engine.space_layers`. `_scope_layers` applies the All-masters / Keep-components toggles.
- **Reporter coupling** — `_bump_rules_gen()` increments `RULES_GEN_KEY`; `respace()` calls `Glyphs.redraw()`. **Every change that affects spacing must do both** (this is how the overlay refreshes — see *Data flow*).
- **Font switching** — `updateInterface_` reacts to master/selection changes and the frontmost font; `_rebind_font` rebinds to a new font, `_close_window` cleans up. Refreshes are gated so only the visible tab rebuilds.

---

## The reporter (`HTLetterspacerPreview/…/plugin.py`)

`class HTLetterspacerPreview(ReporterPlugin)` draws the overlay.

- **`foreground(layer)`** (active glyph) → coloured areas **+** the rule report.
- **`inactiveLayerForeground(layer)`** (other glyphs) → coloured areas only.
- **`_compute(layer, active)`** runs the engine once, builds the area path, the report lines and the colour, and caches them per `(glyph, layerId)` keyed by a **signature**.
- **Report** (`_rule_report` / `_headline`) = `Name / Script / Cat / SubCat / Case / filter` (omitting "Any"/empty), then `Area %`, `Depth %`, `Ref`. No match → `No matching rule`. Drawn below the descender; grey text. Toggle via the context menu (`SHOW_LABEL_KEY`).
- **Per-rule colours** — `_build_order` ranks rules by script/category/subcategory/case → palette index, so each rule's areas get a distinct colour.

### Performance model (why it stays fast with many glyphs)
- The **active** glyph's signature includes a full outline checksum (so live edits refresh immediately); **inactive** glyphs use a cheap signature (params + counts + rules-generation, no per-frame node walk).
- The `NSBezierPath` and fill colour are **cached** and re-filled each frame instead of rebuilt.
- When you edit a glyph, `_note_active` detects the outline change and **evicts only the cached areas of glyphs that use it as a component** (transitive closure via `_dependents_for`), so composites refresh without scanning everything.

---

## Storage & defaults keys

Namespace: **`com.htfonts.letterspacer`**. The plugin writes the current keys and reads legacy keys for backwards compatibility (one-way migrate on first write).

| What | Current key | Legacy (read-only) |
|---|---|---|
| Font rules (`font.userData`) | `…letterspacer.rules` | `com.eweracs.HTLSManager.fontRules` |
| Master overrides (`master.userData`) | `…letterspacer.masterRules` | `HTLSManagerMasterRules` |
| Linked master (`master.userData`) | `…letterspacer.linkedMaster` | `HTLSManagerLinkedMaster` |

Per-master base parameters (`paramArea`, `paramDepth`, `paramOver`) stay as **master custom parameters**.

App-level `Glyphs.defaults` keys:
- `…letterspacer.rulesGen` — bumped on every rule/override change; part of the reporter's cache signature.
- `…letterspacer.showRuleLabel` — reporter report on/off (context-menu toggle).
- `…letterspacer.keepComponents` — footer "Keep components in place" toggle.

---

## Data flow

**Spacing (apply):** UI action → `plugin.space_*` → `engine.space_layers(layers, font_rules)` → per layer `HTLSEngine` resolves rule (`rules.find_rule`) → effective area/depth → computes sidebearings → writes LSB/RSB (+ component shift + metric-key sync), redrawing the view once.

**Editing a rule / importing a file:** UI writes to `plugin.font_rules` → `plugin.write_rules()` (persists + `_bump_rules_gen`) → `plugin.respace()` (`Glyphs.redraw`). The reporter's signatures now differ → its cache misses → it recomputes and redraws. (Import and Reset paths call the same bump+respace so the overlay updates exactly like a value edit.)

**Reporter draw (per frame):** Glyphs calls `foreground`/`inactiveLayerForeground` per visible glyph → `_compute` returns cached `(path, report, color)` unless the signature changed → `drawing.fill_path` + (active only) the report.

---

## Aux scripts (`HT Letterspacer Scripts/`)
Both discover the bundle's `Resources/` relative to the script (symlink-resolved) and import `htls`.
- **Apply HTLS Config** — headless; spaces the selection using the **font's stored rules** (`engine.space_layers`).
- **Apply HTLS Values** — floating window; spaces the selection against **manual** Area/Depth/Overshoot/LSB/RSB/tabular values, ignoring stored rules.

---

## Import / export formats
- **Import** reads legacy `.yml`/`.py` configs (comma-separated, hand-parsed) **and** the project's own JSON setup.
- **Export** writes the **versioned JSON setup** (`{"format": "HTLetterspacer", "version": 2, …}` — rules + per-master parameters + overrides) and a legacy-compatible `.yml` config. No `.py` export.

---

## Naming conventions
Classes use `CapWords` (`HTLSEngine`, the UI managers, the custom views). New, pure-Python functions and methods use `snake_case` (`space_layers`, `calculate_polygons`, `is_brace_layer`, `build_rule_order`, the `_update_*` UI helpers). Two sets of names are **intentionally** camelCase and must stay that way — a PEP8 linter should skip them, not "fix" them:

- **Objective-C selector methods** — `drawRect_`, `tabChanged_`, `updateInterface_`, `windowClosed_`, `initWithManager_`, `tableView_willDisplayCell_forTableColumn_row_`, etc. The underscores stand in for the selector colons (`drawRect:`, `tableView:willDisplayCell:…`); PyObjC dispatches by the exact selector name, so renaming them breaks the binding.
- **Geometry/measuring functions ported verbatim from the original script** — `area`, `triangle`, `getMargins`, `totalMarginList`, `zoneMargins`, `setSpace`, `setDepth`, `diagonize`, `closeOpenCounters`, `calculateSBValue`, `maxPoints`, `processMargins`, plus mirrored fields like `self.newL` / `self.minYref`. These are kept name-for-name so the math can be diffed against `HT_Letterspacer_script.py` and stays parity-tested; renaming buys cosmetics at the cost of traceability and regression risk.

The plugin also sits on a camelCase Glyphs/Cocoa API (`layer.completeBezierPath`, `customParameters`, `associatedMasterId`, …), so uniform `snake_case` isn't attainable regardless — follow the prevailing convention of whatever you're calling (per PEP8's own "know when to be inconsistent").

## Where to add things (quick index)
- **Change spacing math** → `htls/engine.py` (keep it matching the standalone script).
- **Add a rule field** → `htls/config.py` (`_normalize_rule`, serialization), `htls/rules.py` (matching/effective), `htls/ui/rules.py` (`RuleEditor` + columns), and consume it in `engine.py`.
- **Change how rules match** → `htls/rules.py` (`_match_score`).
- **Change the overlay look** → `htls/drawing.py`; report content/placement/colours → reporter `plugin.py`.
- **Add a window tab** → new manager in `htls/ui/`, wire it in `plugin.py` `showWindow_`.
- **Add an import/export format** → `htls/config.py`, expose it from the `⋯` menu in `htls/ui/rules.py`.
