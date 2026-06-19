# encoding: utf-8
"""Inspector tab — a read-only view of the single selected glyph.

Shows its categorization (script / category / subcategory / case), a live glyph
preview (like the Manager), and the rules that match it: the rule the glyph is
actually using first, then the rules it would fall back to if that one didn't
exist. There is intentionally NO add/edit here — rules are edited in the Font /
Master rules tabs.
"""
from __future__ import division, print_function, unicode_literals

from vanilla import List, TextBox
from AppKit import NSColor

from htls import config, engine as engine_mod
from htls import rules as rules_mod
from htls.ui.rules import _fmt_spec, _num, CASE_LABELS, CHECK

try:
	from GlyphsApp.UI import GlyphView
except Exception:
	GlyphView = None

INSPECTOR_COLUMNS = [
	{"title": "▶", "key": "active", "width": 20},
	{"title": "Name", "key": "name", "width": 120},
	{"title": "Category", "key": "category", "width": 70},
	{"title": "Script", "key": "script", "width": 52},
	{"title": "Subcat", "key": "subcategory", "width": 80},
	{"title": "Case", "key": "case", "width": 64},
	{"title": "Filter", "key": "filter", "width": 60},
	{"title": "Ref", "key": "reference", "width": 50},
	{"title": "Area", "key": "area", "width": 48},
	{"title": "Depth", "key": "depth", "width": 48},
]

_CLEAR_FIELDS = ("scriptLbl", "categoryLbl", "subcatLbl", "caseLbl",
                 "areaLbl", "depthLbl", "refLbl")


class InspectorManager(object):

	def __init__(self, plugin, group):
		self.plugin = plugin
		self.group = group
		g = group

		g.glyphName = TextBox((10, 8, -10, 22), "")

		# Live glyph preview (Glyphs renders it — we just assign .layer).
		if GlyphView is not None:
			g.preview = GlyphView((10, 38, 220, 200), layer=None, backgroundColor=NSColor.clearColor())

		# Two columns beside the preview: categorization (left) + applied (right).
		xA, colA_w, xB = 246, 196, 452
		g.catHeader = TextBox((xA, 38, colA_w, 16), "Categorization", sizeStyle="small")
		g.scriptLbl = TextBox((xA, 62, colA_w, 16), "", sizeStyle="small")
		g.categoryLbl = TextBox((xA, 82, colA_w, 16), "", sizeStyle="small")
		g.subcatLbl = TextBox((xA, 102, colA_w, 16), "", sizeStyle="small")
		g.caseLbl = TextBox((xA, 122, colA_w, 16), "", sizeStyle="small")

		g.appliedHeader = TextBox((xB, 38, -10, 16), "Applied spacing", sizeStyle="small")
		g.areaLbl = TextBox((xB, 62, -10, 16), "", sizeStyle="small")
		g.depthLbl = TextBox((xB, 82, -10, 16), "", sizeStyle="small")
		g.refLbl = TextBox((xB, 102, -10, 16), "", sizeStyle="small")

		g.rulesHeader = TextBox((10, 250, -10, 16),
			"Matching rules — the one in use first, then fallbacks:", sizeStyle="small")
		g.rulesList = List(
			(10, 272, -10, -10),
			[],
			columnDescriptions=INSPECTOR_COLUMNS,
			showColumnTitles=True,
			allowsMultipleSelection=False,
			allowsEmptySelection=True,
			drawFocusRing=False,
		)
		# It's a ranking, not a sortable table — disable column sorting.
		try:
			for col in g.rulesList.getNSTableView().tableColumns():
				col.setSortDescriptorPrototype_(None)
		except Exception:
			pass

		self.refresh()

	# --- selection --------------------------------------------------------

	def _selected_layer(self):
		font = self.plugin.font
		if font is None:
			return None
		layers = font.selectedLayers
		if not layers or len(layers) != 1:
			return None
		return layers[0]

	def _overrides_for(self, master):
		try:
			raw = master.userData[config.MASTER_RULES_KEY]
		except Exception:
			raw = None
		return config._to_plain(raw) if raw else {}

	# --- refresh ----------------------------------------------------------

	def refresh(self):
		layer = self._selected_layer()
		if layer is None or layer.parent is None:
			self._show_empty()
			return
		glyph = layer.parent
		master = layer.master

		if GlyphView is not None:
			try:
				self.group.preview.layer = layer
			except Exception:
				pass

		self.group.glyphName.set(glyph.name or "—")
		self.group.scriptLbl.set("Script: %s" % (glyph.script or "—"))
		self.group.categoryLbl.set("Category: %s" % (glyph.category or "—"))
		self.group.subcatLbl.set("Subcategory: %s" % (glyph.subCategory or "—"))
		case_idx = int(glyph.case or 0)
		case = CASE_LABELS[case_idx] if 0 <= case_idx < len(CASE_LABELS) else "Any"
		self.group.caseLbl.set("Case: %s" % case)

		ranked = rules_mod.rank_rules(glyph, self.plugin.font_rules, master)
		overrides = self._overrides_for(master)

		# The winning rule's configured area/depth (override-aware) shown as the
		# rule value, then the resolved final value the engine actually applies.
		win_area = win_depth = None
		if ranked:
			_, win_id, win_rule = ranked[0]
			win_ov = overrides.get(win_id) or {}
			win_area = win_ov.get("area") if isinstance(win_ov.get("area"), dict) else win_rule.get("area")
			win_depth = win_ov.get("depth") if isinstance(win_ov.get("depth"), dict) else win_rule.get("depth")
		try:
			eng = engine_mod.HTLSEngine(layer, font_rules=self.plugin.font_rules)
			self.group.areaLbl.set("Area: %s → %s" % (_fmt_spec(win_area) or "—", _num(eng.effectiveArea)))
			self.group.depthLbl.set("Depth: %s → %s" % (_fmt_spec(win_depth) or "—", _num(eng.effectiveDepth)))
			ref_layer = eng.reference_layer
			if ref_layer is not None and ref_layer.parent is not None and ref_layer is not layer:
				self.group.refLbl.set("Reference: %s" % ref_layer.parent.name)
			else:
				self.group.refLbl.set("Reference: self")
		except Exception:
			for attr in ("areaLbl", "depthLbl", "refLbl"):
				getattr(self.group, attr).set("")
		rows = []
		for i, (_score, rule_id, rule) in enumerate(ranked):
			ov = overrides.get(rule_id)
			case_i = int(rule.get("case", 0))
			rows.append({
				"active": CHECK if i == 0 else "",
				"name": rule.get("name", "") or "",
				"category": rule.get("category", "Any") or "Any",
				"script": rule.get("script", "Any") or "Any",
				"subcategory": rule.get("subcategory", "Any") or "Any",
				"case": CASE_LABELS[case_i] if 0 <= case_i < len(CASE_LABELS) else "Any",
				"filter": rule.get("filter", "") or "",
				"reference": rule.get("reference", "") or "",
				"area": _fmt_spec((ov or {}).get("area") if (ov and (ov or {}).get("area")) else rule.get("area")),
				"depth": _fmt_spec((ov or {}).get("depth") if (ov and (ov or {}).get("depth")) else rule.get("depth")),
			})
		self.group.rulesList.set(rows)

	def _show_empty(self):
		if GlyphView is not None:
			try:
				self.group.preview.layer = None
			except Exception:
				pass
		self.group.glyphName.set("Select a single glyph")
		for attr in _CLEAR_FIELDS:
			getattr(self.group, attr).set("")
		self.group.rulesList.set([])
