# encoding: utf-8

# HT Letterspacer Areas — reporter
# Live, non-destructive preview of the areas HT Letterspacer calculates.
# Reference: eweracs' ShowHTLetterspacerAreas.

from __future__ import division, print_function, unicode_literals
import objc
import os
import sys

from GlyphsApp import Glyphs
from GlyphsApp.plugins import ReporterPlugin

# Import the SHARED `htls` package from the MAIN plugin's Resources, so the
# reporter draws exactly what the engine would compute. This file is
#   <repo>/HTLetterspacerPreview.glyphsReporter/Contents/Resources/plugin.py
# so four dirnames up is <repo>.
_THIS = os.path.realpath(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_THIS))))
_MAIN_RESOURCES = os.path.join(
	_REPO_ROOT, "HTLetterspacer.glyphsPlugin", "Contents", "Resources"
)
if _MAIN_RESOURCES not in sys.path:
	sys.path.insert(0, _MAIN_RESOURCES)

from htls import drawing, config
from htls.engine import HTLSEngine

# Bumped by the plugin whenever rules/overrides change, so the cache below
# invalidates when the matched rule's factor could differ.
RULES_GEN_KEY = "com.htfonts.letterspacer.rulesGen"
# Whether to draw the matched-rule label (name · factor) top-right of the glyph.
# Defaults on; toggled from the reporter's context menu.
SHOW_LABEL_KEY = "com.htfonts.letterspacer.showRuleLabel"

CASE_SHORT = ["", "UC", "lc", "SC", "minor", "other"]


class HTLetterspacerPreview(ReporterPlugin):

	@objc.python_method
	def settings(self):
		self.menuName = Glyphs.localize({
			"en": "HT Letterspacer Areas",
			"es": "Áreas de HT Letterspacer",
		})
		# Per-layer cache: {(glyph, layerId): (signature, path, report, color)}.
		# Kept python-side (not tempData) so the NSPoint lists aren't bridged.
		self._cache = {}
		# Font-rules cache: read once per rules-generation, not per glyph (the
		# big "slow when there are rules" cost — every cache miss otherwise
		# re-reads + re-normalizes all rules from userData).
		self._rules = None
		self._rules_gen = None
		self._rules_font = None
		# {rule_id: colour index} — rules ordered by script/category/subcategory/
		# case, so each rule gets a stable, distinct area colour.
		self._order = {}
		# Active-glyph edit tracking: when the edited glyph's outline changes we
		# invalidate the cached areas of glyphs that use it as a component, so
		# composites refresh live without every inactive glyph walking its nodes.
		self._active_name = None
		self._active_sig = None
		# {base_glyph_name: set(glyph names that use it, transitively)} — built
		# once per font (component structure rarely changes).
		self._dependents = None
		self._dep_font = None

	@objc.python_method
	def _font_rules(self, font):
		gen = Glyphs.defaults[RULES_GEN_KEY] or 0
		if self._rules is None or self._rules_gen != gen or self._rules_font is not font:
			self._rules = config.read_font_rules(font) if font is not None else {}
			self._order = self._build_order(self._rules)
			self._rules_gen = gen
			self._rules_font = font
		return self._rules

	@objc.python_method
	def _build_order(self, rules):
		"""Map rule_id -> colour index by ordering rules on script, category,
		subcategory, case (rule_id breaks ties for determinism)."""
		def sort_key(item):
			rid, r = item
			return (
				str(r.get("script") or ""), str(r.get("category") or ""),
				str(r.get("subcategory") or ""), int(r.get("case") or 0), rid,
			)
		return {rid: i for i, (rid, _r) in enumerate(sorted(rules.items(), key=sort_key))}

	@objc.python_method
	def foreground(self, layer):
		# Active glyph: draw areas AND the rule report. Only this layer is being
		# edited, so it's the only one that needs the (costly) outline checksum.
		self._note_active(layer)
		self._draw(layer, with_report=True, active=True)

	@objc.python_method
	def _note_active(self, layer):
		"""Track the active glyph's outline checksum. When it changes (the glyph
		is being edited), drop the cached areas of every glyph that uses it as a
		component, so those composites recompute on their next draw."""
		if layer is None or layer.parent is None:
			return
		name = layer.parent.name
		try:
			sig = self._outline_sig(layer)
		except Exception:
			sig = 0.0
		if name == self._active_name and sig != self._active_sig:
			self._invalidate_dependents(layer.parent.parent, name)
		self._active_name = name
		self._active_sig = sig

	@objc.python_method
	def _invalidate_dependents(self, font, name):
		"""Evict cache entries for glyphs that (transitively) use `name` as a
		component. Runs only when the active glyph was actually edited, and
		touches only real dependents — not the whole cache."""
		if font is None:
			return
		deps = self._dependents_for(font).get(name)
		if not deps:
			return
		for key in [k for k in self._cache if k[0] in deps]:
			self._cache.pop(key, None)

	@objc.python_method
	def _dependents_for(self, font):
		"""{base_name: set(glyphs using it, transitively)}, cached per font."""
		if self._dep_font is font and self._dependents is not None:
			return self._dependents
		direct = {}  # base name -> set of glyphs directly using it
		try:
			for glyph in font.glyphs:
				for base in self._component_names(glyph):
					direct.setdefault(base, set()).add(glyph.name)
		except Exception:
			pass
		# transitive closure: a base's dependents include the dependents of its
		# dependents (composite-of-composite).
		dependents = {}
		for base in direct:
			seen = set()
			stack = list(direct.get(base, ()))
			while stack:
				user = stack.pop()
				if user in seen:
					continue
				seen.add(user)
				stack.extend(direct.get(user, ()))
			dependents[base] = seen
		self._dependents = dependents
		self._dep_font = font
		return dependents

	@objc.python_method
	def _component_names(self, glyph):
		"""Direct component base names used by `glyph` across its layers."""
		names = set()
		try:
			for layer in glyph.layers:
				for component in layer.components:
					n = component.componentName
					if n:
						names.add(n)
		except Exception:
			pass
		return names

	@objc.python_method
	def inactiveLayerForeground(self, layer):
		# Inactive glyphs: areas only, no report, and a cheap signature (no
		# per-frame node walk) — this is the big win when many glyphs are shown.
		self._draw(layer, with_report=False, active=False)

	@objc.python_method
	def _draw(self, layer, with_report=False, active=False):
		try:
			path, report, color = self._compute(layer, active)
			if path is not None:
				drawing.fill_path(path, color)
			if with_report and report and self._labels_on():
				self._draw_report(layer, report)
		except Exception:
			import traceback
			print(traceback.format_exc())

	@objc.python_method
	def _compute(self, layer, active):
		"""Return (path, report, color) for `layer`, cached by signature. `path`
		is a prebuilt NSBezierPath of the area polygons; `report` the matched
		rule's label lines (or None); `color` the per-rule fill (grey on no
		match). Inactive layers use a cheap signature so the cached path is
		reused without recomputing anything per frame."""
		if layer is None or layer.parent is None:
			return None, None, None
		key = (layer.parent.name, layer.layerId)
		signature = self._signature(layer, active)
		entry = self._cache.get(key)
		if entry is not None and entry[0] == signature:
			return entry[1], entry[2], entry[3]
		font = layer.parent.parent
		font_rules = self._font_rules(font)
		engine = HTLSEngine(layer, font_rules=font_rules)
		path = drawing.build_area_path(engine.calculate_polygons())
		report = self._rule_report(engine)
		color_index = self._order.get(engine.matched_rule_id) if engine.matched_rule_id else None
		color = drawing.area_color(color_index)
		self._cache[key] = (signature, path, report, color)
		return path, report, color

	@objc.python_method
	def _labels_on(self):
		value = Glyphs.defaults[SHOW_LABEL_KEY]
		return True if value is None else bool(value)

	@objc.python_method
	def _rule_report(self, engine):
		"""Lines for the matched rule: a headline (name / cat / subcat / case /
		filter, omitting "Any"/empty fields) then area %, depth %, reference
		glyph. "No matching rule" when none matches."""
		rule = engine.matched_rule
		if not rule:
			return ["No matching rule"]
		area_pct = int(round((engine.effectiveArea / engine.paramArea * 100)
		                     if engine.paramArea else 100))
		depth_pct = int(round((engine.effectiveDepth / engine.paramDepth * 100)
		                      if engine.paramDepth else 100))
		ref = "self"
		try:
			rl = engine.reference_layer
			if rl is not None and rl is not engine.layer and rl.parent is not None:
				ref = rl.parent.name
		except Exception:
			pass
		return [
			self._headline(rule),
			"Area %d%%" % area_pct,
			"Depth %d%%" % depth_pct,
			"Ref %s" % ref,
		]

	@objc.python_method
	def _headline(self, rule):
		"""Name / Script / Category / Subcategory / Case / filter — each field
		included only when it's an actual constraint (not "Any"/empty)."""
		bits = []
		name = (rule.get("name") or "").strip()
		if name:
			bits.append(name)
		script = rule.get("script")
		if script and script != "Any":
			bits.append(script)
		cat = rule.get("category")
		if cat and cat != "Any":
			bits.append(cat)
		sub = rule.get("subcategory")
		if sub and sub != "Any":
			bits.append(sub)
		case = int(rule.get("case") or 0)
		if 0 < case < len(CASE_SHORT):
			bits.append(CASE_SHORT[case])
		filt = (rule.get("filter") or "").strip()
		if filt:
			bits.append(filt)
		return " / ".join(bits) or "(rule)"

	@objc.python_method
	def _draw_report(self, layer, report):
		"""Stack the report lines below the descender, left-aligned at the glyph
		origin, at a constant on-screen size (scaled by the edit-view zoom)."""
		try:
			scale = self.getScale()
		except Exception:
			scale = 1.0
		try:
			descender = layer.master.descender
		except Exception:
			descender = -200
		y_top = descender - (12.0 / (scale or 1.0))
		drawing.draw_lines(report, 0, y_top, scale=scale, align_right=False)

	@objc.python_method
	def _outline_sig(self, layer, depth=3):
		"""Coordinate checksum of the layer's *rendered* outline: its own path
		nodes, plus each component's transform + name, plus (recursively, to
		`depth`) the nodes of the glyph it references. Folding components in is
		what makes the cache notice a component being moved, or its base glyph
		being edited / re-spaced — otherwise a pure composite's fingerprint
		never changes and its areas go stale."""
		total = 0.0
		try:
			for path in layer.paths:
				for node in path.nodes:
					pos = node.position
					total += pos.x + pos.y
		except Exception:
			pass
		if depth <= 0:
			return total
		try:
			master_id = layer.associatedMasterId
			for component in layer.components:
				# transform captures the component's offset, scale and rotation,
				# so moving it changes the signature.
				try:
					total += sum(float(t) for t in component.transform)
				except Exception:
					try:
						pos = component.position
						total += pos.x + pos.y
					except Exception:
						pass
				try:
					total += len(component.componentName or "")
				except Exception:
					pass
				# Fold the referenced glyph's outline so editing/re-spacing the
				# base updates the composite's areas too.
				try:
					base_glyph = component.component
					base_layer = base_glyph.layers[master_id] if base_glyph is not None else None
				except Exception:
					base_layer = None
				if base_layer is not None and base_layer is not layer:
					total += self._outline_sig(base_layer, depth - 1)
		except Exception:
			pass
		return total

	@objc.python_method
	def _signature(self, layer, active):
		"""String fingerprint of everything that changes the areas: master
		params, path/component counts and the rules generation — plus, for the
		ACTIVE (edited) glyph only, the full outline checksum. Inactive glyphs
		skip the per-frame node walk: their outlines aren't being edited, so the
		cheap fingerprint is enough and the cached path is reused as-is."""
		master = layer.master

		def param(name, default):
			try:
				value = master.customParameters[name]
				return float(value) if value is not None else default
			except Exception:
				return default

		gen = Glyphs.defaults[RULES_GEN_KEY] or 0
		base = "%s|%s|%s|%s|%s|%s" % (
			param("paramArea", 400), param("paramDepth", 15), param("paramOver", 0),
			len(layer.paths), len(layer.components), int(gen),
		)
		if not active:
			return base
		# Reuse the checksum already computed by _note_active for this same
		# layer this frame; only fall back to walking if it's somehow stale.
		if self._active_name == layer.parent.name and self._active_sig is not None:
			coords = self._active_sig
		else:
			coords = self._outline_sig(layer)
		return "%s|%s" % (base, round(coords, 1))

	@objc.python_method
	def conditionalContextMenus(self):
		on = self._labels_on()
		title = Glyphs.localize({
			"en": "Hide HTLS Rule Labels" if on else "Show HTLS Rule Labels",
			"es": "Ocultar etiquetas de reglas HTLS" if on else "Mostrar etiquetas de reglas HTLS",
		})
		return [{"name": title, "action": self.toggleRuleLabels_}]

	def toggleRuleLabels_(self, sender):
		Glyphs.defaults[SHOW_LABEL_KEY] = not self._labels_on()
		try:
			Glyphs.redraw()
		except Exception:
			pass

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
