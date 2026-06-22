# encoding: utf-8

# HT Letterspacer
# A new plugin combining the HT Letterspacer engine with a management UI.

from __future__ import division, print_function, unicode_literals
import objc
import os
import sys

from GlyphsApp import Glyphs, GLYPH_MENU, UPDATEINTERFACE, Message
from GlyphsApp.plugins import GeneralPlugin
from AppKit import NSMenuItem
from vanilla import FloatingWindow, Tabs, TextBox, Button, CheckBox

# Make the shared `htls` package (this Resources dir) importable, so the
# plugin, the aux scripts and the areas reporter all run the same engine.
_RESOURCES = os.path.dirname(os.path.realpath(os.path.abspath(__file__)))
if _RESOURCES not in sys.path:
	sys.path.insert(0, _RESOURCES)

from htls import config
from htls import engine as engine_mod
from htls.ui.rules import FontRulesManager, MasterRulesManager
from htls.ui.parameters import ParametersManager
from htls.ui.inspector import InspectorManager

PLUGIN_NAME = "HT Letterspacer"
WINDOW_SIZE = (900, 560)        # initial
WINDOW_MIN = (640, 560)         # width-resizable, height fixed
WINDOW_MAX = (3000, 560)

# Bumped on every rule/override change so the areas reporter invalidates its
# cache (it reads this from Glyphs.defaults).
RULES_GEN_KEY = "com.htfonts.letterspacer.rulesGen"

# "Keep components in place" footer toggle (persisted; defaults to on).
KEEP_COMPONENTS_KEY = "com.htfonts.letterspacer.keepComponents"


class HTLetterspacer(GeneralPlugin):

	@objc.python_method
	def settings(self):
		self.name = Glyphs.localize({
			"en": PLUGIN_NAME,
			"es": PLUGIN_NAME,
		})

	@objc.python_method
	def start(self):
		if Glyphs.buildNumber >= 3320:
			from GlyphsApp.UI import MenuItem
			menu_item = MenuItem(self.name, action=self.showWindow_, target=self)
		else:
			menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
				self.name, self.showWindow_, ""
			)
			menu_item.setTarget_(self)
		Glyphs.menu[GLYPH_MENU].append(menu_item)

	# --- rules access (used by the UI managers) ---------------------------

	@objc.python_method
	def reload_rules(self):
		"""(Re)load the font's rules into the in-memory working copy."""
		self.font_rules = config.read_font_rules(self.font)

	@objc.python_method
	def collect_font_values(self):
		"""Gather the scripts and subcategories present in the font, for the
		(nullable) selects in the rule editor."""
		scripts = set()
		subcategories = set()
		for glyph in self.font.glyphs:
			if glyph.script:
				scripts.add(glyph.script)
			if glyph.subCategory:
				subcategories.add(glyph.subCategory)
		self.scripts = sorted(scripts)
		self.subcategories = sorted(subcategories)

	@objc.python_method
	def _bump_rules_gen(self):
		"""Invalidate the areas reporter's cache after a rule/override change."""
		Glyphs.defaults[RULES_GEN_KEY] = (Glyphs.defaults[RULES_GEN_KEY] or 0) + 1

	@objc.python_method
	def write_rules(self):
		"""Persist the working rules to the font (migrates legacy on write)."""
		config.write_font_rules(self.font, self.font_rules)
		self._bump_rules_gen()

	@objc.python_method
	def rule_ids_with_overrides(self):
		"""Set of rule ids that have a per-master override in ANY master — used
		by the Font rules tab's "Ovr" column to flag rules tweaked per master."""
		ids = set()
		font = self.font
		if font is None:
			return ids
		for master in font.masters:
			raw = master.userData[config.MASTER_RULES_KEY]
			if not raw:
				continue
			data = config._to_plain(raw)
			if isinstance(data, dict):
				for rid, ov in data.items():
					if ov:
						ids.add(rid)
		return ids

	@objc.python_method
	def read_master_overrides(self):
		"""Per-master area/depth overrides `{rule_id: {area?, depth?}}` for the
		currently selected master."""
		master = self.font.selectedFontMaster
		raw = master.userData[config.MASTER_RULES_KEY] if master else None
		return config._to_plain(raw) if raw else {}

	@objc.python_method
	def write_master_overrides(self, overrides):
		master = self.font.selectedFontMaster
		if master is None:
			return
		if overrides:
			master.userData[config.MASTER_RULES_KEY] = overrides
		elif master.userData[config.MASTER_RULES_KEY] is not None:
			del master.userData[config.MASTER_RULES_KEY]
		self._bump_rules_gen()

	@objc.python_method
	def respace(self):
		"""Refresh the edit view after a rule change (the areas reporter and
		any preview redraw from here). Full re-spacing is opt-in elsewhere."""
		Glyphs.redraw()

	# --- shared apply footer (works from any tab) -------------------------

	@objc.python_method
	def _tab_layers(self):
		"""Glyph layers shown in the active Edit view tab, skipping control
		layers (spaces / line breaks) which aren't spaceable."""
		font = self.font
		tab = font.currentTab if font is not None else None
		if tab is None:
			return []
		layers = []
		for layer in tab.layers:
			if type(layer).__name__ == "GSControlLayer" or layer.parent is None:
				continue
			layers.append(layer)
		return layers

	@objc.python_method
	def live_apply_enabled(self):
		try:
			return bool(self.w.liveApply.get())
		except Exception:
			return False

	@objc.python_method
	def all_masters_enabled(self):
		try:
			return bool(self.w.allMasters.get())
		except Exception:
			return False

	@objc.python_method
	def _scope_layers(self, layers):
		"""When "All masters" is on, expand each glyph in `layers` to EVERY
		spaceable layer it has — all master layers PLUS all special (bracket /
		brace) layers, across all masters — so they're all spaced no matter which
		layer is currently active. Otherwise the layers are returned unchanged.
		Dedupe by layerId (NOT associated master) so a special layer is never
		collapsed into the master it belongs to."""
		if not self.all_masters_enabled():
			return layers
		font = self.font
		if font is None:
			return layers
		out, seen = [], set()

		def add(layer):
			glyph = layer.parent
			if glyph is None:
				return
			key = (glyph.name, layer.layerId)
			if key in seen:
				return
			seen.add(key)
			out.append(layer)

		def spaceable(layer):
			# master layers + bracket layers; skip brace (intermediate) layers,
			# which spacing ignores, and colour / backup layers.
			try:
				if engine_mod.is_brace_layer(layer):
					return False
				return bool(layer.isMasterLayer or layer.isSpecialLayer)
			except Exception:
				return False

		for layer in layers:
			add(layer)   # keep the selected layer itself even if it's atypical
			glyph = layer.parent
			if glyph is None:
				continue
			for gl in glyph.layers:
				if spaceable(gl):
					add(gl)
		return out

	@objc.python_method
	def space_current_tab(self, param_overrides=None, preserve_components=False):
		"""Re-space every glyph in the current tab (no notification).
		`param_overrides` lets the caller test parameter values WITHOUT writing
		them to the master. space_layers dedupes, batches and forceRedraws, so
		this is cheap to call repeatedly."""
		layers = self._scope_layers(self._tab_layers())
		if layers:
			engine_mod.space_layers(
				layers, font_rules=self.font_rules, param_overrides=param_overrides,
				preserve_components=preserve_components)

	@objc.python_method
	def live_apply_tab(self):
		"""If "Live tab apply" is on, re-space the current tab. Called by the
		rule + parameter editors on every value change."""
		if self.live_apply_enabled():
			self.space_current_tab(preserve_components=self.keep_components_enabled())

	@objc.python_method
	def _apply_selection(self, sender):
		font = self.font
		layers = font.selectedLayers if font is not None else None
		if not layers:
			Message(title="Nothing selected", message="Select some glyphs to space.")
			return
		results = engine_mod.space_layers(
			self._scope_layers(layers), font_rules=self.font_rules,
			preserve_components=self.keep_components_enabled())
		count = sum(1 for (_, _, sb) in results if sb is not None)
		self.respace()
		Glyphs.showNotification("HT Letterspacer", "Spaced %d glyph(s)." % count)

	@objc.python_method
	def _apply_tab(self, sender):
		layers = self._scope_layers(self._tab_layers())
		if not layers:
			Message(title="No Edit tab", message="Open an Edit view with some glyphs to space.")
			return
		results = engine_mod.space_layers(
			layers, font_rules=self.font_rules,
			preserve_components=self.keep_components_enabled())
		count = sum(1 for (_, _, sb) in results if sb is not None)
		self.respace()
		Glyphs.showNotification("HT Letterspacer", "Spaced %d glyph(s) in the current tab." % count)

	@objc.python_method
	def _live_toggle(self, sender):
		# Turning it on applies the current values to the tab right away.
		if sender.get():
			self.live_apply_tab()

	@objc.python_method
	def _keep_components_toggle(self, sender):
		Glyphs.defaults[KEEP_COMPONENTS_KEY] = bool(sender.get())

	@objc.python_method
	def keep_components_enabled(self):
		"""Whether spacing should shift referencing components to keep composites
		in place (footer "Keep components in place"). Defaults to on."""
		try:
			return bool(self.w.keepComponents.get())
		except Exception:
			return True

	# --- window -----------------------------------------------------------

	def showWindow_(self, sender):
		# If the window is already open, just bring it to the front.
		if getattr(self, "w", None) is not None:
			try:
				self.w.makeKey()
				self.w.getNSWindow().makeKeyAndOrderFront_(None)
			except Exception:
				pass
			return

		self.font = Glyphs.font
		if self.font is None:
			Message("Select a font project!", "No font selected")
			return

		self.reload_rules()
		self.collect_font_values()

		self.w = FloatingWindow(
			WINDOW_SIZE, PLUGIN_NAME, minSize=WINDOW_MIN, maxSize=WINDOW_MAX,
			autosaveName="com.htfonts.letterspacer.window",
		)
		# Tabs leave a strip at the bottom for the shared apply footer.
		self.w.tabs = Tabs(
			(10, 10, -10, -42),
			["Parameters", "Font rules", "Master rules", "Inspector"],
			callback=self.tabChanged_,
		)

		# Shared footer — visible under every tab. Spacing actions and the live
		# "apply as you edit" toggle apply regardless of which tab is shown.
		self.w.applyBtn = Button(
			(10, -32, 150, 22), "Apply to selection", callback=self._apply_selection, sizeStyle="small")
		self.w.applyTabBtn = Button(
			(168, -32, 150, 22), "Apply to current tab", callback=self._apply_tab, sizeStyle="small")
		self.w.liveApply = CheckBox(
			(334, -31, 130, 20), "Live tab apply", callback=self._live_toggle, sizeStyle="small")
		self.w.allMasters = CheckBox(
			(470, -31, 95, 20), "All masters", sizeStyle="small")
		keep = Glyphs.defaults[KEEP_COMPONENTS_KEY]
		self.w.keepComponents = CheckBox(
			(572, -31, -10, 20), "Keep components in place",
			value=(True if keep is None else bool(keep)),
			callback=self._keep_components_toggle, sizeStyle="small")

		self.currentMasterID = self.font.selectedFontMaster.id if self.font.selectedFontMaster else None

		# Tab 0 — Parameters; Tab 1 — Font rules; Tab 2 — Master rules; Tab 3 — Inspector
		self.parameters = ParametersManager(self, self.w.tabs[0])
		self.fontRules = FontRulesManager(self, self.w.tabs[1], self.scripts, self.subcategories)
		self.masterRules = MasterRulesManager(self, self.w.tabs[2])
		self.inspector = InspectorManager(self, self.w.tabs[3])
		self._prevTab = 0   # Parameters is the initial tab

		self.w.open()
		self.w.makeKey()
		self.w.bind("close", self.windowClosed_)
		Glyphs.addCallback(self.updateInterface_, UPDATEINTERFACE)

	@objc.python_method
	def _selection_signature(self):
		"""The currently-selected glyph name, used to drive the ✓ match marks.
		The mark only matters when exactly one glyph is selected."""
		layers = self.font.selectedLayers if self.font else None
		if not layers or len(layers) != 1:
			return None
		return layers[0].parent.name

	def tabChanged_(self, sender):
		# Refresh only the tab being shown (cheap, on demand).
		idx = sender.get()
		try:
			# Carry the sort + selection from the tab we're leaving onto the one
			# we're entering, so Font/Master rules stay aligned for comparison.
			prev = getattr(self, "_prevTab", 0)
			leaving = {1: getattr(self, "fontRules", None),
			           2: getattr(self, "masterRules", None)}.get(prev)
			if leaving is not None:
				leaving._save_state()
			self._prevTab = idx
			if idx == 0 and hasattr(self, "parameters"):
				self.parameters.refresh()
			elif idx == 1 and hasattr(self, "fontRules"):
				self.fontRules.apply_shared_sort()
				self.fontRules.refresh_list()
			elif idx == 2 and hasattr(self, "masterRules"):
				self.masterRules.apply_shared_sort()
				self.masterRules.refresh()
			elif idx == 3 and hasattr(self, "inspector"):
				self.inspector.refresh()
		except Exception:
			import traceback
			print(traceback.format_exc())

	@objc.python_method
	def _rebind_font(self, font):
		"""Rebind the whole window to a newly-frontmost font: reload its rules,
		its scripts/subcategories (the editor selects), and refresh every tab."""
		self.font = font
		self.reload_rules()
		self.collect_font_values()
		self.currentMasterID = font.selectedFontMaster.id if font.selectedFontMaster else None
		self._lastSelectionSig = None
		if hasattr(self, "fontRules"):
			self.fontRules.set_font_values(self.scripts, self.subcategories)
			self.fontRules.refresh()
		if hasattr(self, "masterRules"):
			self.masterRules.refresh()
		if hasattr(self, "parameters"):
			self.parameters.refresh()
		if hasattr(self, "inspector"):
			self.inspector.refresh()

	@objc.python_method
	def _close_window(self):
		try:
			if getattr(self, "w", None) is not None:
				self.w.close()
		except Exception:
			pass

	@objc.python_method
	def updateInterface_(self, sender):
		# UPDATEINTERFACE fires very often, so do the minimum: only act on an
		# actual font / master / selection change, and only touch the visible
		# tab.
		try:
			current = Glyphs.font
			if current is None:
				# close only when there are genuinely no open documents (not a
				# transient None mid-switch)
				if not Glyphs.fonts:
					self._close_window()
				return
			if current != self.font:
				# the frontmost font changed — rebind everything to it
				self._rebind_font(current)
				return

			master = self.font.selectedFontMaster
			master_id = master.id if master else None
			master_changed = master_id != getattr(self, "currentMasterID", None)
			if master_changed:
				self.currentMasterID = master_id
				if hasattr(self, "masterRules"):
					self.masterRules.refresh()
				if hasattr(self, "parameters"):
					self.parameters.refresh()

			# ✓ match marks / inspector: only when the glyph selection changed,
			# and only for the visible tab (Font rules = 1, Master rules = 2,
			# Inspector = 3).
			sig = self._selection_signature()
			if sig != getattr(self, "_lastSelectionSig", None) or master_changed:
				self._lastSelectionSig = sig
				visible = self.w.tabs.get()
				if visible == 1 and hasattr(self, "fontRules"):
					self.fontRules.refresh_list()
				elif visible == 2 and hasattr(self, "masterRules"):
					self.masterRules.refresh_list()
				elif visible == 3 and hasattr(self, "inspector"):
					self.inspector.refresh()
		except Exception:
			import traceback
			print(traceback.format_exc())

	@objc.python_method
	def windowClosed_(self, sender):
		Glyphs.removeCallback(self.updateInterface_)
		self.w = None

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
