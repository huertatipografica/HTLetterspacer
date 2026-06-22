# MenuTitle: Apply HTLS Values
# -*- coding: utf-8 -*-
"""Floating window to apply specific manual values (Area / Depth / Overshoot /
LSB / RSB / fixed width) to the current selection, independent of the stored rules.

UI equivalent of the old `HT_Letterspacer_UI.py` (ui=True). Mirrors the
two-script pattern of the standalone (this = values-UI; `Apply HTLS Config` =
headless config-runner). Unlike the config runner it ignores the font's rules:
every selected glyph is spaced against itself using the values typed here.
"""
from __future__ import division, print_function, unicode_literals
import os
import sys

# Find the shared `htls` package inside the plugin bundle. Prefer discovering it
# relative to this script (which lives at <repo>/HT Letterspacer Scripts/),
# resolving symlinks so it still works when the script is symlinked into Glyphs'
# Scripts folder; fall back to the installed Plugins bundle.
_BUNDLE = "HTLetterspacer.glyphsPlugin/Contents/Resources"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_CANDIDATES = [
	os.path.join(_REPO_ROOT, _BUNDLE),
	os.path.expanduser("~/Library/Application Support/Glyphs 3/Plugins/" + _BUNDLE),
]
for _PLUGIN_RESOURCES in _CANDIDATES:
	if os.path.isdir(_PLUGIN_RESOURCES):
		if _PLUGIN_RESOURCES not in sys.path:
			sys.path.insert(0, _PLUGIN_RESOURCES)
		break

import vanilla
from GlyphsApp import Glyphs, Message
from htls import engine as engine_mod

# Where the window remembers its last-used values.
DEFAULTS = "com.htfonts.letterspacer.values"

# Engine fallbacks when a master has no paramArea/paramDepth/paramOver.
_FALLBACK = {
	"paramArea": engine_mod.HTLSEngine.DEFAULT_AREA,
	"paramDepth": engine_mod.HTLSEngine.DEFAULT_DEPTH,
	"paramOver": engine_mod.HTLSEngine.DEFAULT_OVER,
}

# Pasteable Glyphs 3 master custom-parameter snippet (Copy parameters button).
_COPY_TEMPLATE = """{
    customParameters = (
        {
            name = paramArea;
            value = %g;
        },
        {
            name = paramDepth;
            value = %g;
        },
        {
            name = paramOver;
            value = %g;
        }
    );
}"""


def _master_param(master, name):
	"""master.customParameters[name] as a float, or the engine fallback."""
	try:
		value = master.customParameters[name]
		if value is not None:
			return float(value)
	except Exception:
		pass
	return float(_FALLBACK[name])


def _width_avg(layers):
	"""Average advance width of the selection, rounded — the fixed-width target."""
	if not layers:
		return 0
	return int(round(sum(layer.width for layer in layers) / len(layers)))


def _space_selection(layers, area, depth, over, lsb, rsb, tabular, width,
                     preserve_components=True):
	"""Space `layers` with manual values, no rules. Returns (report, spaced).

	Mirrors `engine.space_layers`: dedupe by layerId (so a special layer and its
	master layer stay distinct), wrap the writes in disableUpdateInterface, and
	sync metric keys only after the whole batch so a glyph keyed to another in the
	selection resolves against final metrics.
	With `preserve_components`, glyphs used as components are spaced first and
	their referencing components shifted back so composites stay in place (it
	reuses the same helpers as `engine.space_layers`).
	"""
	seen = set()
	unique = []
	for layer in layers:
		glyph = layer.parent
		key = (glyph.name if glyph else id(layer), layer.layerId)
		if key in seen:
			continue
		seen.add(key)
		unique.append(layer)
	if not unique:
		return [], 0

	font = unique[0].parent.parent if unique[0].parent else None
	overrides = {"paramArea": area, "paramDepth": depth, "paramOver": over}

	reverse_manual = None
	ordered = unique
	if preserve_components and font is not None:
		master_ids = {l.associatedMasterId for l in unique}
		forward, reverse_manual = engine_mod._build_component_graph(font, master_ids)
		ordered = engine_mod._topo_order(unique, forward)

	def _space_one(layer):
		"""Build a manual-values engine, apply it, return (name, sb)."""
		engine = engine_mod.HTLSEngine(layer, font_rules={}, param_overrides=overrides)
		engine.LSB = lsb
		engine.RSB = rsb
		engine.tabVersion = tabular
		engine.width = int(width) if tabular and width else None
		name = layer.parent.name if layer.parent else "?"
		sb = engine.current_layer_sidebearings()
		if sb is not None:
			layer.LSB, layer.RSB = sb[0], sb[1]
			if engine.newWidth:
				layer.width = engine.newWidth
		return name, sb

	report = []
	spaced = 0
	if font is not None:
		font.disableUpdateInterface()
	try:
		if preserve_components and reverse_manual is not None:
			# Bases first, interleaved: space a glyph, then shift the components
			# that reference it before the composites using it are reached.
			for layer in ordered:
				glyph = layer.parent
				master_id = layer.associatedMasterId
				try:
					layer.syncMetrics()
				except Exception:
					pass
				lsb_before = layer.LSB
				name, sb = _space_one(layer)
				if sb is None:
					report.append("%-16s skipped (no spacing)" % name)
					continue
				spaced += 1
				report.append("%-16s LSB=%-5g RSB=%-5g" % (name, sb[0], sb[1]))
				if glyph is None:
					continue
				try:
					layer.syncMetrics()
				except Exception:
					pass
				left_diff = lsb_before - layer.LSB
				if left_diff:
					engine_mod._shift_components(reverse_manual, glyph.name, master_id, left_diff)
			for layer in ordered:
				try:
					layer.syncMetrics()
				except Exception:
					pass
		else:
			for layer in ordered:
				name, sb = _space_one(layer)
				if sb is None:
					report.append("%-16s skipped (no spacing)" % name)
					continue
				spaced += 1
				report.append("%-16s LSB=%-5g RSB=%-5g" % (name, sb[0], sb[1]))
			for layer in ordered:
				layer.syncMetrics()
	finally:
		if font is not None:
			font.enableUpdateInterface()

	try:
		if font is not None and font.currentTab:
			font.currentTab.forceRedraw()
	except Exception:
		pass

	return report, spaced


class HTLSValuesWindow(object):
	def __init__(self):
		font = Glyphs.font
		if font is None:
			Message("No font", "Open a font first.")
			return
		layers = font.selectedLayers
		if not layers:
			Message("Nothing selected", "Select some glyphs to space.")
			return

		self.master = layers[0].master

		# Defaults: last-used values, else the current master's parameters.
		area = Glyphs.defaults["%s.area" % DEFAULTS] or _master_param(self.master, "paramArea")
		depth = Glyphs.defaults["%s.depth" % DEFAULTS] or _master_param(self.master, "paramDepth")
		over = Glyphs.defaults["%s.over" % DEFAULTS]
		if over is None:
			over = _master_param(self.master, "paramOver")
		lsb = Glyphs.defaults["%s.lsb" % DEFAULTS]
		rsb = Glyphs.defaults["%s.rsb" % DEFAULTS]
		tabular = Glyphs.defaults["%s.tabular" % DEFAULTS]
		keep = Glyphs.defaults["%s.keepComponents" % DEFAULTS]

		col = 95   # label column width
		x2 = 115   # field x
		w = vanilla.FloatingWindow((250, 248), "HT Letterspacer Values",
		                           autosaveName="%s.window" % DEFAULTS)
		self.w = w

		w.lsb = vanilla.CheckBox((15, 12, 46, 20), "LSB",
		                         value=True if lsb is None else bool(lsb), sizeStyle="small")
		w.rsb = vanilla.CheckBox((63, 12, 46, 20), "RSB",
		                         value=True if rsb is None else bool(rsb), sizeStyle="small")
		w.tabular = vanilla.CheckBox((111, 12, 120, 20), "Fixed width",
		                             value=bool(tabular), sizeStyle="small",
		                             callback=self._toggleTabular)

		w.widthLabel = vanilla.TextBox((15, 45, col, 17), "Width", sizeStyle="small")
		w.width = vanilla.EditText((x2, 42, -15, 21), str(_width_avg(layers)), sizeStyle="small")

		w.areaLabel = vanilla.TextBox((15, 75, col, 17), "Area", sizeStyle="small")
		w.area = vanilla.EditText((x2, 72, -15, 21), "%g" % float(area), sizeStyle="small")

		w.depthLabel = vanilla.TextBox((15, 103, col, 17), "Depth", sizeStyle="small")
		w.depth = vanilla.EditText((x2, 100, -15, 21), "%g" % float(depth), sizeStyle="small")

		w.overLabel = vanilla.TextBox((15, 131, col, 17), "Overshoot", sizeStyle="small")
		w.over = vanilla.EditText((x2, 128, -15, 21), "%g" % float(over), sizeStyle="small")

		w.keepComponents = vanilla.CheckBox((15, 158, -15, 20), "Keep components in place",
		                                    value=(True if keep is None else bool(keep)),
		                                    sizeStyle="small")

		w.copyButton = vanilla.Button((15, 200, 120, 22), "Copy parameters",
		                              sizeStyle="small", callback=self._copy)
		w.applyButton = vanilla.Button((-95, 200, -15, 22), "Apply",
		                               sizeStyle="small", callback=self._apply)
		w.setDefaultButton(w.applyButton)

		self._toggleTabular(w.tabular)
		w.open()
		w.makeKey()

	# --- helpers -----------------------------------------------------------

	def _toggleTabular(self, sender):
		"""The width field only matters in fixed-width mode."""
		on = bool(sender.get())
		self.w.width.enable(on)
		self.w.widthLabel.enable(on)

	def _values(self):
		"""Read and validate the fields. Returns a dict or None (after a
		Message) when a number can't be parsed."""
		try:
			return {
				"area": float(self.w.area.get()),
				"depth": float(self.w.depth.get()),
				"over": float(self.w.over.get()),
				"width": int(round(float(self.w.width.get() or 0))),
				"lsb": bool(self.w.lsb.get()),
				"rsb": bool(self.w.rsb.get()),
				"tabular": bool(self.w.tabular.get()),
				"keep": bool(self.w.keepComponents.get()),
			}
		except (ValueError, TypeError):
			Message("Invalid value", "Area, Depth, Overshoot and Width must be numbers.")
			return None

	def _save(self, v):
		Glyphs.defaults["%s.area" % DEFAULTS] = v["area"]
		Glyphs.defaults["%s.depth" % DEFAULTS] = v["depth"]
		Glyphs.defaults["%s.over" % DEFAULTS] = v["over"]
		Glyphs.defaults["%s.lsb" % DEFAULTS] = v["lsb"]
		Glyphs.defaults["%s.rsb" % DEFAULTS] = v["rsb"]
		Glyphs.defaults["%s.tabular" % DEFAULTS] = v["tabular"]
		Glyphs.defaults["%s.keepComponents" % DEFAULTS] = v["keep"]

	# --- callbacks ---------------------------------------------------------

	def _apply(self, sender):
		v = self._values()
		if v is None:
			return
		if not (v["lsb"] or v["rsb"]):
			Message("Nothing to space", "Enable LSB and/or RSB.")
			return
		self._save(v)

		font = Glyphs.font
		layers = list(font.selectedLayers) if font is not None else []
		if not layers:
			Message("Nothing selected", "Select some glyphs to space.")
			return

		report, spaced = _space_selection(
			layers, v["area"], v["depth"], v["over"],
			v["lsb"], v["rsb"], v["tabular"], v["width"],
			preserve_components=v["keep"],
		)
		Glyphs.clearLog()
		print("Applying HTLS values "
		      "(area=%g, depth=%g, overshoot=%g, LSB=%s, RSB=%s, fixed width=%s)\n"
		      % (v["area"], v["depth"], v["over"], v["lsb"], v["rsb"], v["tabular"]))
		print("\n".join(report))
		print("\nDone. Spaced %d glyph(s)." % spaced)

	def _copy(self, sender):
		"""Copy a master custom-parameter snippet for the typed Area/Depth/
		Overshoot, to paste into a master."""
		v = self._values()
		if v is None:
			return
		text = _COPY_TEMPLATE % (v["area"], v["depth"], v["over"])
		try:
			from AppKit import NSPasteboard, NSStringPboardType
			pasteboard = NSPasteboard.generalPasteboard()
			pasteboard.declareTypes_owner_([NSStringPboardType], None)
			pasteboard.setString_forType_(text, NSStringPboardType)
		except Exception:
			import traceback
			print(traceback.format_exc())
			Message("Clipboard error", "Could not copy — see the Macro panel.")


HTLSValuesWindow()
