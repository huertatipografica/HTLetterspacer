# encoding: utf-8
"""Font-rules manager UI.

A two-column list + detail editor, modeled on HT Stroker's Style Manager but
embedded in a tab of the plugin window (not a separate floating window). The
left column is a wide `vanilla.List`; the right column is a narrower
`RuleEditor` for the selected rule.

Rules are stored flat (`{rule_id: rule}`, each carrying a nullable `category`);
category, script and subcategory are all "Any"-able. The list refresh is a
lightweight `List.set` of plain dicts so editing stays responsive.
"""
from __future__ import division, print_function, unicode_literals

import objc
from vanilla import (
	Group, List, Button, PopUpButton, EditText, CheckBox, TextBox, TextEditor, Sheet, Window,
)
from AppKit import NSMenuItem, NSSortDescriptor, NSColor
from Foundation import NSObject
from GlyphsApp import Glyphs, GetOpenFile, GetSaveFile, Message

from htls import config, rules as rules_mod

CASE_LABELS = ["Any", "Uppercase", "Lowercase", "Smallcaps", "Minor", "Other"]
MODE_LABELS = ["%", "abs"]
CATEGORY_ITEMS = ["Any"] + config.CATEGORIES

COLUMNS = [
	{"title": "Name", "key": "name", "width": 64},
	{"title": "✓", "key": "mark", "width": 18},
	{"title": "Ovr", "key": "ovr", "width": 28},
	{"title": "Script", "key": "script", "width": 50},
	{"title": "Category", "key": "category", "width": 74},
	{"title": "Case", "key": "case", "width": 64},
	{"title": "Subcat", "key": "subcategory", "width": 86},
	{"title": "Filter", "key": "filter", "width": 56},
	{"title": "Ref", "key": "reference", "width": 54},
	{"title": "Area", "key": "area", "width": 44},
	{"title": "Depth", "key": "depth", "width": 46},
	{"title": "LSB", "key": "lsb", "width": 32},
	{"title": "RSB", "key": "rsb", "width": 32},
	{"title": "Fixed", "key": "tab", "width": 44},
	{"title": "List", "key": "glyphs", "width": 32},
]

MENU_ITEMS = [
	("import_setup", "Import setup…"),
	("export_setup", "Export setup…"),
	(None, None),
	("import", "Import rules (v1 legacy)…"),
	("export", "Export rules (v1 legacy)…"),
	(None, None),
	("reset", "Reset to defaults…"),
]

CHECK = "✓"


def _num(value):
	f = float(value)
	return str(int(f)) if f == int(f) else str(round(f, 3))


def _fmt_spec(spec):
	if not isinstance(spec, dict):
		return ""
	if spec.get("mode") == "absolute":
		return _num(spec.get("value", 0))
	value = spec.get("value", 100)
	# 100% is the neutral/inherited value (no spacing change) — show a dash
	# rather than a noisy "100%".
	try:
		if float(value) == 100:
			return "—"
	except (TypeError, ValueError):
		pass
	return _num(value) + "%"


def _spec_num(spec):
	"""Numeric value of an area/depth spec, for sorting the column."""
	if isinstance(spec, dict):
		try:
			return float(spec.get("value", 0))
		except (TypeError, ValueError):
			return 0.0
	return 0.0


def parse_glyphlist(text):
	out = []
	for chunk in (text or "").replace("\n", ",").replace(" ", ",").split(","):
		name = chunk.strip()
		if name:
			out.append(name)
	return out


def format_glyphlist(names):
	return "\n".join(names or [])


def _item_get(item, key):
	"""Read a key from a List row, which may be a dict or an NSDictionary."""
	if item is None:
		return None
	try:
		return item[key]
	except Exception:
		pass
	try:
		return item.objectForKey_(key)
	except Exception:
		return None


# --------------------------------------------------------------------------
# Detail editor
# --------------------------------------------------------------------------

class _GlyphListDialog(object):
	"""Small window to edit a rule's glyph list, committed all at once on OK
	(so typing doesn't re-run a rules match per keystroke)."""

	def __init__(self, text, on_ok):
		self.on_ok = on_ok
		self.w = Window((360, 300), "Edit glyph list", minSize=(260, 200))
		self.w.hint = TextBox((14, 12, -14, 30),
			"Glyph names separated by space, comma or newline.", sizeStyle="small")
		self.w.editor = TextEditor((14, 46, -14, -44), text or "")
		self.w.cancelBtn = Button((-170, -32, 70, 20), "Cancel", callback=self._cancel, sizeStyle="small")
		self.w.okBtn = Button((-90, -32, 76, 20), "OK", callback=self._ok, sizeStyle="small")
		try:
			self.w.setDefaultButton(self.w.okBtn)
		except Exception:
			pass

	def open(self):
		self.w.open()

	def _cancel(self, sender):
		self.w.close()

	def _ok(self, sender):
		text = self.w.editor.get()
		self.w.close()
		self.on_ok(text)


class RuleEditor(object):
	"""Builds the rule-detail fields into `box` (a vanilla Group). Calls
	`on_change()` whenever a field changes (unless loading). `scripts` and
	`subcategories` populate the (nullable) selects."""

	def __init__(self, box, on_change, scripts, subcategories):
		self.box = box
		self.on_change = on_change
		self._loading = False
		self.script_items = ["Any"] + list(scripts)
		self.subcat_items = ["Any"] + list(subcategories)
		# the items currently shown in each select (may include a stored value
		# not present in the font); used to read the selection back
		self._cur_script_items = list(self.script_items)
		self._cur_subcat_items = list(self.subcat_items)
		self._cur_cat_items = list(CATEGORY_ITEMS)

		row_h = 27

		def row(i):
			return 6 + i * row_h

		def label(i, text):
			setattr(self.box, "lbl%d" % i, TextBox((0, row(i) + 2, 78, 18), text, sizeStyle="small"))

		box = self.box
		# Text fields commit on end-of-edit (continuous=False): a continuous
		# EditText reads its value one keystroke STALE in the callback, which
		# corrupted multi-keystroke entries like a filter ".tf".
		label(0, "Name")
		box.name = EditText((82, row(0), -6, 21), callback=self._fire, continuous=False, sizeStyle="small")
		label(1, "Script")
		box.script = PopUpButton((82, row(1), -6, 21), self.script_items, callback=self._fire, sizeStyle="small")
		label(2, "Category")
		box.category = PopUpButton((82, row(2), -6, 21), CATEGORY_ITEMS, callback=self._fire, sizeStyle="small")
		label(3, "Subcategory")
		box.subcat = PopUpButton((82, row(3), -6, 21), self.subcat_items, callback=self._fire, sizeStyle="small")
		label(4, "Case")
		box.case = PopUpButton((82, row(4), -6, 21), CASE_LABELS, callback=self._fire, sizeStyle="small")
		label(5, "Filter")
		box.filt = EditText((82, row(5), -6, 21), placeholder=".tf, .tosf", callback=self._fire, continuous=False, sizeStyle="small")
		label(6, "Reference")
		box.ref = EditText((82, row(6), -6, 21), placeholder="self", callback=self._fire, continuous=False, sizeStyle="small")
		label(7, "Area")
		box.areaMode = PopUpButton((82, row(7), 52, 21), MODE_LABELS, callback=self._fire, sizeStyle="small")
		box.areaVal = EditText((140, row(7), -6, 21), callback=self._fire, continuous=False, sizeStyle="small")
		label(8, "Depth")
		box.depthMode = PopUpButton((82, row(8), 52, 21), MODE_LABELS, callback=self._fire, sizeStyle="small")
		box.depthVal = EditText((140, row(8), -6, 21), callback=self._fire, continuous=False, sizeStyle="small")
		box.tab = CheckBox((82, row(9), -6, 21), "Fixed width", callback=self._fire, sizeStyle="small")
		box.lsb = CheckBox((82, row(10), 70, 21), "LSB", value=True, callback=self._fire, sizeStyle="small")
		box.rsb = CheckBox((156, row(10), 70, 21), "RSB", value=True, callback=self._fire, sizeStyle="small")
		label(11, "Glyph list")
		# The glyph list is shown read-only and edited in a dialog committed all
		# at once — a live TextEditor here re-ran a rules match + respace on every
		# keystroke, which was slow.
		box.glyphsEditBtn = Button((-86, row(11), 80, 20), "Edit…", callback=self._edit_glyphs, sizeStyle="small")
		box.glyphs = TextEditor((6, row(11) + 22, -6, -6), readOnly=True)

		self.name = box.name
		self.script = box.script
		self.category = box.category
		self.subcat = box.subcat
		self.case = box.case
		self.filt = box.filt
		self.ref = box.ref
		self.areaMode = box.areaMode
		self.areaVal = box.areaVal
		self.depthMode = box.depthMode
		self.depthVal = box.depthVal
		self.tab = box.tab
		self.lsb = box.lsb
		self.rsb = box.rsb
		self.glyphs = box.glyphs
		self.glyphsEditBtn = box.glyphsEditBtn
		self._glyph_dialog = None

		# Note: self.glyphs is NOT here — it's a read-only display, and enable()
		# would flip it back to editable. The Edit… button is gated instead.
		self._widgets = [
			self.name, self.script, self.category, self.subcat, self.case,
			self.filt, self.ref, self.areaMode, self.areaVal, self.depthMode,
			self.depthVal, self.tab, self.lsb, self.rsb, self.glyphsEditBtn,
		]

	def _fire(self, sender=None):
		if not self._loading:
			self.on_change()

	def _edit_glyphs(self, sender):
		"""Open a dialog to edit the whole glyph list, committing once on OK."""
		if self._loading:
			return
		self._glyph_dialog = _GlyphListDialog(self.glyphs.get(), self._commit_glyphs)
		self._glyph_dialog.open()

	def _commit_glyphs(self, text):
		self._loading = True
		try:
			self.glyphs.set(text)
		finally:
			self._loading = False
		self._fire()   # a single rules match / write for the whole list

	def update_font_values(self, scripts, subcategories):
		"""Refresh the base items for the script/subcategory selects (used when
		the frontmost font changes). Applied on the next `load`."""
		self.script_items = ["Any"] + list(scripts)
		self.subcat_items = ["Any"] + list(subcategories)

	@staticmethod
	def _set_popup(popup, base_items, value):
		"""Show `base_items` plus `value` if it isn't already there (so a stored
		value not present in the font stays selectable), select it, and return
		the resulting item list."""
		items = list(base_items)
		if value and value not in items:
			items.append(value)
		popup.setItems(items)
		popup.set(items.index(value) if value in items else 0)
		return items

	@staticmethod
	def _popup_value(popup, items):
		idx = popup.get()
		if 0 <= idx < len(items):
			return items[idx]
		return "Any"

	def set_enabled(self, flag):
		for widget in self._widgets:
			widget.enable(flag)
		if not flag:
			self._loading = True
			try:
				for widget in (self.name, self.filt, self.ref, self.areaVal, self.depthVal, self.glyphs):
					widget.set("")
				for popup in (self.script, self.category, self.subcat, self.case):
					popup.set(0)
				self.tab.set(False)
				self.lsb.set(True)
				self.rsb.set(True)
			finally:
				self._loading = False

	def load(self, rule):
		r = config._normalize_rule(rule)
		self._loading = True
		try:
			self.name.set(r["name"])
			self._cur_script_items = self._set_popup(self.script, self.script_items, r["script"])
			self._cur_cat_items = self._set_popup(self.category, CATEGORY_ITEMS, r["category"])
			self._cur_subcat_items = self._set_popup(self.subcat, self.subcat_items, r["subcategory"])
			self.case.set(int(r["case"]) if 0 <= int(r["case"]) < len(CASE_LABELS) else 0)
			self.filt.set(r["filter"])
			self.ref.set(r["reference"])
			self.areaMode.set(1 if r["area"]["mode"] == "absolute" else 0)
			self.areaVal.set(_num(r["area"]["value"]))
			self.depthMode.set(1 if r["depth"]["mode"] == "absolute" else 0)
			self.depthVal.set(_num(r["depth"]["value"]))
			self.tab.set(bool(r["tabular"]))
			self.lsb.set(bool(r["sides"]["LSB"]))
			self.rsb.set(bool(r["sides"]["RSB"]))
			self.glyphs.set(format_glyphlist(r["glyphlist"]))
		finally:
			self._loading = False

	def read(self):
		def spec(mode_pop, val_edit):
			mode = "absolute" if mode_pop.get() == 1 else "percent"
			# An empty field means "no change": 100% in percent mode (the
			# inherited/neutral value), 0 in absolute mode.
			try:
				value = float(val_edit.get())
			except (TypeError, ValueError):
				value = 100.0 if mode == "percent" else 0.0
			return {"mode": mode, "value": value}

		return config.make_rule(
			name=self.name.get(),
			category=self._popup_value(self.category, self._cur_cat_items),
			script=self._popup_value(self.script, self._cur_script_items),
			subcategory=self._popup_value(self.subcat, self._cur_subcat_items),
			case=self.case.get(),
			filter=self.filt.get(),
			reference=self.ref.get().strip(),
			area=spec(self.areaMode, self.areaVal),
			depth=spec(self.depthMode, self.depthVal),
			tabular=bool(self.tab.get()),
			sides={"LSB": bool(self.lsb.get()), "RSB": bool(self.rsb.get())},
			glyphlist=parse_glyphlist(self.glyphs.get()),
		)


# --------------------------------------------------------------------------
# Font-rules manager
# --------------------------------------------------------------------------

class _RuleListMixin(object):
	"""Selection helpers shared by the rule managers. Requires `self.group.list`
	(a vanilla List whose rows carry a hidden "_id") and `self._loading`.
	Reads selection via the array controller so it stays correct after the user
	sorts a column (display order then differs from content order)."""

	def _arranged(self):
		try:
			return self.group.list._arrayController.arrangedObjects()
		except Exception:
			return None

	def _selected_key(self):
		try:
			objs = self.group.list._arrayController.selectedObjects()
			if objs and len(objs):
				return _item_get(objs[0], "_id")
		except Exception:
			pass
		try:
			sel = self.group.list.getSelection()
			if sel:
				return _item_get(self.group.list[sel[0]], "_id")
		except Exception:
			pass
		return None

	def _index_of(self, rule_id):
		if not rule_id:
			return None
		arranged = self._arranged()
		rows = arranged if arranged is not None else self.group.list
		try:
			for i in range(len(rows)):
				if _item_get(rows[i], "_id") == rule_id:
					return i
		except Exception:
			pass
		return None

	def _select(self, rule_id):
		idx = self._index_of(rule_id)
		if idx is None:
			return
		self._loading = True
		try:
			self.group.list.setSelection([idx])
		finally:
			self._loading = False
		# Keep the shared selection in sync: setSelection ran under the _loading
		# guard, so _selection_cb (which saves it) was suppressed. Without this,
		# a later refresh_list re-selects the STALE shared id, yanking the list
		# off a just-added rule while the editor keeps editing it — the next
		# edit then overwrites the wrong rule.
		self.plugin._shared_sel_id = rule_id

	def _live_apply_blocks_edit(self):
		"""Adding, duplicating or removing a rule changes which rules match the
		glyphs in the tab; with "Live tab apply" on that would immediately
		re-space the whole current tab — unexpected, destructive writes. Warn
		and block the change until the user turns it off."""
		if self.plugin.live_apply_enabled():
			Message(
				title="Turn off “Live tab apply”",
				message="You can't add, duplicate or remove a rule while “Live "
				"tab apply” is on: changing the rule set would immediately "
				"re-space the current tab. Uncheck “Live tab apply” first, then "
				"make the change.",
			)
			return True
		return False

	def _matched_rule_id(self):
		"""The id of the rule matching the single selected glyph, or None —
		drives the ✓ match column in both managers."""
		font = self.plugin.font
		if font is None or not font.selectedLayers or len(font.selectedLayers) != 1:
			return None
		layer = font.selectedLayers[0]
		match = rules_mod.find_rule(layer.parent, self.plugin.font_rules, layer.master)
		return match[0] if match else None

	# --- cross-tab shared sort + selection --------------------------------
	# Both rule tabs list the same rules, so a column sort or a selected row on
	# one tab is mirrored on the other (stored on the plugin), letting the user
	# switch tabs to compare the same rule's font vs. master values side by side.

	def _shared_selection_id(self):
		return getattr(self.plugin, "_shared_sel_id", None)

	def _save_shared_selection(self):
		sid = self._selected_key()
		if sid:
			self.plugin._shared_sel_id = sid

	def _save_state(self):
		"""Capture this tab's sort + selection into the shared state (called when
		leaving the tab, so the other tab can mirror it)."""
		try:
			self.plugin._shared_sort = self.group.list.getNSTableView().sortDescriptors()
		except Exception:
			pass
		self._save_shared_selection()

	def apply_shared_sort(self):
		"""Mirror the shared column sort onto this tab's list. Sort keys are the
		column keys (plus the hidden _area_sort/_depth_sort), shared by both
		tabs; a descriptor for a column this tab lacks is a harmless no-op."""
		desc = getattr(self.plugin, "_shared_sort", None)
		if not desc:
			return
		try:
			self.group.list.getNSTableView().setSortDescriptors_(desc)
			self.group.list._arrayController.setSortDescriptors_(desc)
		except Exception:
			pass


class _ImportSetupSheet(object):
	"""Modal sheet for importing a v2 setup: map each master in the file onto a
	master in the current font (default = same-name match), choose replace vs
	merge for the rules, then apply."""

	def __init__(self, manager, data):
		self.manager = manager
		self.plugin = manager.plugin
		self.data = data
		self.font_masters = list(self.plugin.font.masters)
		self.cfg_names = config.setup_master_names(data)

		target_labels = ["(Don't import)"] + [m.name for m in self.font_masters]
		name_to_idx = {}
		for i, m in enumerate(self.font_masters):
			name_to_idx.setdefault(m.name, i + 1)   # +1: slot 0 is "Don't import"

		pad, row_h, top = 20, 28, 78
		n = max(1, len(self.cfg_names))
		height = top + n * row_h + 104

		self.sheet = Sheet((480, height), self.plugin.w)
		s = self.sheet
		s.title = TextBox((pad, 16, -pad, 18),
			"Import setup — assign the file's masters to this font:", sizeStyle="small")
		s.rulesHint = TextBox((pad, 40, -pad, 30),
			"%d rule(s) will be imported. Choose a target master for each set "
			"of parameters + overrides." % len(self.data.get("rules", [])),
			sizeStyle="small")

		self.popups = []
		y = top
		for name in self.cfg_names:
			i = len(self.popups)
			setattr(s, "lbl_%d" % i, TextBox((pad, y + 2, 190, 18), name or "(unnamed)", sizeStyle="small"))
			popup = PopUpButton((216, y, -pad, 20), target_labels, sizeStyle="small")
			popup.set(name_to_idx.get(name, 0))
			setattr(s, "pop_%d" % i, popup)
			self.popups.append(popup)
			y += row_h

		s.replaceBox = CheckBox((pad, y + 10, -pad, 20),
			"Replace existing rules (uncheck to merge)", value=True, sizeStyle="small")
		s.paramsBox = CheckBox((pad, y + 34, -pad, 20),
			"Import master parameters (Area / Depth / Overshoot)", value=False, sizeStyle="small")
		s.cancelBtn = Button((-190, -32, 80, 20), "Cancel", callback=self._cancel, sizeStyle="small")
		s.importBtn = Button((-100, -32, 80, 20), "Import", callback=self._do_import, sizeStyle="small")
		try:
			s.setDefaultButton(s.importBtn)
		except Exception:
			pass

	def open(self):
		self.sheet.open()

	def _cancel(self, sender):
		self.sheet.close()

	def _do_import(self, sender):
		master_map = {}
		for name, popup in zip(self.cfg_names, self.popups):
			idx = popup.get()
			if idx > 0:
				master_map[name] = self.font_masters[idx - 1].id
		replace = bool(self.sheet.replaceBox.get())
		import_params = bool(self.sheet.paramsBox.get())
		try:
			config.import_setup(self.plugin.font, self.data, master_map=master_map,
				replace_rules=replace, import_params=import_params)
		except Exception as exc:
			Message(title="Import failed", message=str(exc))
			return
		self.sheet.close()
		# Refresh in-memory state + every tab, and invalidate the reporter cache.
		self.plugin.reload_rules()
		self.plugin._bump_rules_gen()
		self.manager._clear_usage()
		self.manager.refresh()
		for attr in ("masterRules", "parameters"):
			mgr = getattr(self.plugin, attr, None)
			if mgr is not None:
				mgr.refresh()
		self.plugin.respace()


class FontRulesManager(_RuleListMixin):

	def __init__(self, plugin, group, scripts, subcategories):
		self.plugin = plugin
		self.group = group
		self._loading = False
		# Set of rule ids found "in use" by the last "Mark usage" run; None means
		# usage hasn't been marked (nothing greyed). Cleared on any rule change.
		self._used_ids = None

		# The list flexes with the window width; the editor (below) is a fixed
		# width pinned to the right. EDITOR_W = 260, gutter 10.
		group.list = List(
			(10, 10, -270, -44),
			[],
			columnDescriptions=COLUMNS,
			showColumnTitles=True,
			allowsMultipleSelection=False,
			allowsEmptySelection=True,
			selectionCallback=self._selection_cb,
			drawFocusRing=False,
		)
		# Column sort tweaks: the ✓ column isn't sortable; Area/Depth sort by
		# their numeric value (hidden keys) rather than the displayed string.
		try:
			for col in group.list.getNSTableView().tableColumns():
				ident = str(col.identifier())
				if ident in ("mark", "ovr"):
					col.setSortDescriptorPrototype_(None)
				elif ident == "area":
					col.setSortDescriptorPrototype_(
						NSSortDescriptor.sortDescriptorWithKey_ascending_("_area_sort", True))
				elif ident == "depth":
					col.setSortDescriptorPrototype_(
						NSSortDescriptor.sortDescriptorWithKey_ascending_("_depth_sort", True))
		except Exception:
			pass
		# Grey out rules marked "not in use" (delegate reads each row's _greyed).
		self._delegate = _MasterListDelegate.alloc().initWithManager_(self)
		try:
			group.list.getNSTableView().setDelegate_(self._delegate)
		except Exception:
			pass

		group.addBtn = Button((10, -36, 28, 22), "+", callback=self._add_cb, sizeStyle="small")
		group.addSelBtn = Button((42, -36, 34, 22), "+=", callback=self._add_from_selection_cb, sizeStyle="small")
		group.removeBtn = Button((80, -36, 28, 22), "−", callback=self._remove_cb, sizeStyle="small")
		group.dupBtn = Button((112, -36, 86, 22), "Duplicate", callback=self._dup_cb, sizeStyle="small")
		group.markBtn = Button((204, -36, 124, 22), "Check unused rules", callback=self._mark_usage_cb, sizeStyle="small")
		self._build_menu(group)

		# Right-column header: font name (no master needed on this tab).
		group.fontName = TextBox((-260, 8, -8, 18), "", sizeStyle="small")
		group.editorBox = Group((-260, 30, -8, -8))
		self.editor = RuleEditor(group.editorBox, self._editor_changed, scripts, subcategories)

		self.refresh()

	def set_font_label(self):
		font = self.plugin.font
		self.group.fontName.set(font.familyName if font else "—")

	def set_font_values(self, scripts, subcategories):
		"""Update the editor's script/subcategory selects after a font switch."""
		self.editor.update_font_values(scripts, subcategories)

	# --- menu -------------------------------------------------------------

	def _build_menu(self, group):
		labels = ["⋯"] + [(label or "") for _, label in MENU_ITEMS]
		# pinned to the right edge of the (flexing) list
		group.menuBtn = PopUpButton((-300, -36, 30, 22), labels, callback=self._menu_cb, sizeStyle="small")
		try:
			ns = group.menuBtn.getNSPopUpButton()
			ns.setPullsDown_(True)
			menu = ns.menu()
			for slot, (action, _) in reversed(list(enumerate(MENU_ITEMS))):
				if action is None:
					idx = slot + 1
					menu.removeItemAtIndex_(idx)
					menu.insertItem_atIndex_(NSMenuItem.separatorItem(), idx)
		except Exception:
			pass

	def _menu_cb(self, sender):
		slot = sender.get() - 1
		if 0 <= slot < len(MENU_ITEMS):
			action = MENU_ITEMS[slot][0]
			handler = {
				"import_setup": self._import_setup,
				"export_setup": self._export_setup,
				"import": self._import,
				"export": self._export,
				"reset": self._reset,
			}.get(action)
			if handler:
				handler()
		sender.set(0)

	# --- data binding -----------------------------------------------------

	def _row(self, rule, mark, has_override=False):
		case_idx = int(rule.get("case", 0))
		sides = rule.get("sides") or {}
		return {
			"name": rule.get("name", "") or "",
			"mark": mark,
			"ovr": "●" if has_override else "",
			"script": rule.get("script", "Any") or "Any",
			"category": rule.get("category", "Any") or "Any",
			"case": CASE_LABELS[case_idx] if 0 <= case_idx < len(CASE_LABELS) else "Any",
			"subcategory": rule.get("subcategory", "Any") or "Any",
			"filter": rule.get("filter", "") or "",
			"reference": rule.get("reference", "") or "",
			"area": _fmt_spec(rule.get("area")),
			"depth": _fmt_spec(rule.get("depth")),
			"lsb": CHECK if sides.get("LSB", True) else "",
			"rsb": CHECK if sides.get("RSB", True) else "",
			"tab": CHECK if rule.get("tabular") else "",
			"glyphs": CHECK if (rule.get("glyphlist") or []) else "",
			"_area_sort": _spec_num(rule.get("area")),
			"_depth_sort": _spec_num(rule.get("depth")),
		}

	def refresh_list(self):
		"""Rebuild rows + marks. Preserves selection. Does NOT reload the
		editor (safe to call while typing)."""
		target = self._shared_selection_id() or self._selected_key()
		matched = self._matched_rule_id()
		ovr_ids = self.plugin.rule_ids_with_overrides()
		used = self._used_ids
		rows = []
		for rule_id, rule in self.plugin.font_rules.items():
			row = self._row(rule, CHECK if rule_id == matched else "", rule_id in ovr_ids)
			row["_id"] = rule_id   # hidden (not a column) — identifies the row
			# grey the row if usage has been marked and this rule matched nothing
			row["_greyed"] = used is not None and rule_id not in used
			rows.append(row)
		self._loading = True
		try:
			self.group.list.set(rows)
			idx = self._index_of(target)
			if idx is not None:
				self.group.list.setSelection([idx])
		finally:
			self._loading = False

	def refresh(self):
		self.set_font_label()
		self.refresh_list()
		self._sync_editor()

	# --- rule usage (on demand) -------------------------------------------

	def _mark_usage_cb(self, sender):
		"""Grey out rules that win for no glyph in the font. One O(glyphs×rules)
		pass on request; the result is a snapshot that clears on any rule edit."""
		font = self.plugin.font
		rules = self.plugin.font_rules
		if font is None or not rules:
			return
		used = set()
		for glyph in font.glyphs:
			match = rules_mod.find_rule(glyph, rules)
			if match:
				used.add(match[0])
		self._used_ids = used
		self.refresh_list()
		total = len(rules)
		Glyphs.showNotification(
			"HT Letterspacer", "%d of %d rule(s) not in use (greyed)." % (total - len(used), total))

	def _clear_usage(self):
		"""Drop the usage snapshot (any rule change makes it stale)."""
		self._used_ids = None

	def _sync_editor(self):
		rule_id = self._selected_key()
		rule = self.plugin.font_rules.get(rule_id) if rule_id else None
		if rule is None:
			self.editor.set_enabled(False)
			return
		self.editor.set_enabled(True)
		self.editor.load(rule)

	# --- callbacks --------------------------------------------------------

	def _selection_cb(self, sender):
		if self._loading:
			return
		self._save_shared_selection()
		self._sync_editor()

	def _editor_changed(self):
		rule_id = self._selected_key()
		if not rule_id:
			return
		self.plugin.font_rules[rule_id] = self.editor.read()
		self._clear_usage()
		self.plugin.write_rules()
		self.refresh_list()   # editor stays as-is; only rows/marks update
		self.plugin.respace()
		self.plugin.live_apply_tab()

	def _unique_name(self, base="New rule"):
		"""`base`, else `base 2`, `base 3`, … so new rules get a fresh name."""
		existing = {(rule.get("name") or "") for rule in self.plugin.font_rules.values()}
		if base not in existing:
			return base
		i = 2
		while "%s %d" % (base, i) in existing:
			i += 1
		return "%s %d" % (base, i)

	def _add_cb(self, sender):
		if self._live_apply_blocks_edit():
			return
		rule_id = config.new_rule_id()
		self.plugin.font_rules[rule_id] = config.make_rule(name=self._unique_name())
		self._clear_usage()
		self.plugin.write_rules()
		self.refresh_list()
		self._select(rule_id)
		self._sync_editor()

	def _add_from_selection_cb(self, sender):
		"""Add a rule pre-filled from the first selected glyph (script,
		category, subcategory, case)."""
		if self._live_apply_blocks_edit():
			return
		font = self.plugin.font
		if font is None or not font.selectedLayers:
			Message(title="No glyph selected", message="Select a glyph to base a rule on.")
			return
		glyph = font.selectedLayers[0].parent
		rule_id = config.new_rule_id()
		self.plugin.font_rules[rule_id] = config.make_rule(
			name=self._unique_name(),
			category=glyph.category or "Any",
			script=glyph.script or "Any",
			subcategory=glyph.subCategory or "Any",
			case=glyph.case or 0,
		)
		self._clear_usage()
		self.plugin.write_rules()
		self.refresh_list()
		self._select(rule_id)
		self._sync_editor()

	def _remove_cb(self, sender):
		if self._live_apply_blocks_edit():
			return
		rule_id = self._selected_key()
		if not rule_id:
			return
		self.plugin.font_rules.pop(rule_id, None)
		self._clear_usage()
		self.plugin.write_rules()
		self.refresh()

	def _dup_cb(self, sender):
		if self._live_apply_blocks_edit():
			return
		rule_id = self._selected_key()
		source = self.plugin.font_rules.get(rule_id) if rule_id else None
		if source is None:
			return
		new_id = config.new_rule_id()
		copy = config._normalize_rule(source)
		if copy["name"]:
			copy["name"] = copy["name"] + " copy"
		self.plugin.font_rules[new_id] = copy
		self._clear_usage()
		self.plugin.write_rules()
		self.refresh_list()
		self._select(new_id)
		self._sync_editor()

	# --- menu actions -----------------------------------------------------

	def _export_setup(self):
		font = self.plugin.font
		if font is None:
			return
		proposed = (font.familyName or "font").replace(" ", "") + "_HTLS.json"
		path = GetSaveFile(message="Export HTLS setup", ProposedFileName=proposed, filetypes=["json"])
		if not path:
			return
		try:
			config.export_setup_file(path, font)
		except Exception as exc:
			Message(title="Export failed", message=str(exc))

	def _import_setup(self):
		font = self.plugin.font
		if font is None:
			return
		path = GetOpenFile(message="Import HTLS setup (.json)", filetypes=["json"])
		if not path:
			return
		try:
			with open(path) as handle:
				data = config.parse_setup_text(handle.read())
		except Exception as exc:
			Message(title="Import failed", message=str(exc))
			return
		# Let the user map the file's masters onto this font's masters before
		# applying anything.
		_ImportSetupSheet(self, data).open()

	def _import(self):
		font = self.plugin.font
		if font is None:
			return
		path = GetOpenFile(message="Import HTLS config (.yml / .py)", filetypes=["yml", "py"])
		if not path:
			return
		try:
			config.import_config_file(path, font, replace=False)
		except Exception as exc:
			Message(title="Import failed", message=str(exc))
			return
		self.plugin.reload_rules()
		self._clear_usage()
		self.refresh()
		# Refresh the areas reporter too, exactly as a value edit does: bump the
		# rules generation (invalidates its cache) and redraw the edit view.
		self.plugin._bump_rules_gen()
		self.plugin.respace()

	def _export(self):
		font = self.plugin.font
		if font is None:
			return
		proposed = (font.familyName or "font").replace(" ", "") + "_autospace.yml"
		path = GetSaveFile(message="Export HTLS config", ProposedFileName=proposed, filetypes=["yml"])
		if not path:
			return
		try:
			config.export_config_file(path, font)
		except Exception as exc:
			Message(title="Export failed", message=str(exc))

	def _reset(self):
		from vanilla.dialogs import askYesNo
		if not askYesNo(
			messageText="Reset all rules to defaults?",
			informativeText="This replaces the current font's rules with the default set. This cannot be undone.",
		):
			return
		self.plugin.font_rules = config.default_rules()
		self._clear_usage()
		self.plugin.write_rules()   # persists + bumps the rules generation
		self.refresh()
		self.plugin.respace()       # redraw the edit view / areas reporter


# --------------------------------------------------------------------------
# Master-rules manager (per-master area/depth overrides)
# --------------------------------------------------------------------------

MASTER_COLUMNS = [
	{"title": "✓", "key": "mark", "width": 18},
	{"title": "Ovr", "key": "ovr", "width": 28},
	{"title": "Name", "key": "name", "width": 90},
	{"title": "Script", "key": "script", "width": 50},
	{"title": "Category", "key": "category", "width": 74},
	{"title": "Case", "key": "case", "width": 64},
	{"title": "Subcat", "key": "subcategory", "width": 86},
	{"title": "Filter", "key": "filter", "width": 56},
	{"title": "Area", "key": "area", "width": 56},
	{"title": "Depth", "key": "depth", "width": 56},
]


class _MasterListDelegate(NSObject):
	"""Table-view delegate for the master-rules list: greys out the rows that
	have NO per-master override (they show the inherited font value), so the
	overridden rows stand out. The row's hidden `_greyed` flag drives it."""

	def initWithManager_(self, manager):
		self = objc.super(_MasterListDelegate, self).init()
		if self is None:
			return None
		self._manager = manager
		return self

	def tableView_willDisplayCell_forTableColumn_row_(self, tableView, cell, column, row):
		greyed = False
		try:
			item = tableView.dataSource().arrangedObjects().objectAtIndex_(row)
			greyed = bool(item.objectForKey_("_greyed"))
		except Exception:
			greyed = False
		try:
			if cell.backgroundStyle() == 1:        # selected/emphasized row
				cell.setTextColor_(NSColor.alternateSelectedControlTextColor())
			elif greyed:
				cell.setTextColor_(NSColor.disabledControlTextColor())
			else:
				cell.setTextColor_(NSColor.controlTextColor())
		except Exception:
			pass


def _set_placeholder(edit, text):
	try:
		edit.getNSTextField().cell().setPlaceholderString_(text)
	except Exception:
		pass


class MasterOverrideEditor(object):
	"""Editor for one rule's per-master area/depth override. An empty value
	means 'inherit the font rule' (the field omits that key)."""

	def __init__(self, box, on_change):
		self.box = box
		self.on_change = on_change
		self._loading = False
		box.ruleName = TextBox((0, 6, -6, 18), "", sizeStyle="small")
		box.hdr = TextBox((0, 32, -6, 18), "Master overrides (empty = inherit):", sizeStyle="small")
		box.areaLbl = TextBox((0, 60, 78, 18), "Area", sizeStyle="small")
		box.areaMode = PopUpButton((82, 58, 52, 21), MODE_LABELS, callback=self._fire, sizeStyle="small")
		box.areaVal = EditText((140, 58, -6, 21), callback=self._fire, continuous=False, sizeStyle="small")
		box.depthLbl = TextBox((0, 88, 78, 18), "Depth", sizeStyle="small")
		box.depthMode = PopUpButton((82, 86, 52, 21), MODE_LABELS, callback=self._fire, sizeStyle="small")
		box.depthVal = EditText((140, 86, -6, 21), callback=self._fire, continuous=False, sizeStyle="small")
		box.clearBtn = Button((82, 118, -6, 22), "Clear overrides", callback=self._clear, sizeStyle="small")

		self.ruleName = box.ruleName
		self.areaMode = box.areaMode
		self.areaVal = box.areaVal
		self.depthMode = box.depthMode
		self.depthVal = box.depthVal
		self.clearBtn = box.clearBtn
		self._widgets = [box.areaMode, box.areaVal, box.depthMode, box.depthVal, box.clearBtn]

	def _fire(self, sender=None):
		if not self._loading:
			self.on_change()

	def _clear(self, sender):
		self._loading = True
		try:
			self.areaVal.set("")
			self.depthVal.set("")
		finally:
			self._loading = False
		self.on_change()

	def set_enabled(self, flag):
		for widget in self._widgets:
			widget.enable(flag)
		if not flag:
			self._loading = True
			try:
				self.ruleName.set("")
				self.areaVal.set("")
				self.depthVal.set("")
			finally:
				self._loading = False

	def load(self, rule, override):
		self._loading = True
		try:
			self.ruleName.set("Rule: %s" % (rule.get("name") or "(unnamed)"))
			ov = override or {}
			a = ov.get("area") if isinstance(ov.get("area"), dict) else None
			d = ov.get("depth") if isinstance(ov.get("depth"), dict) else None
			self.areaMode.set(1 if (a and a.get("mode") == "absolute") else 0)
			self.areaVal.set(_num(a["value"]) if a else "")
			_set_placeholder(self.areaVal, "inherit (%s)" % _fmt_spec(rule.get("area")))
			self.depthMode.set(1 if (d and d.get("mode") == "absolute") else 0)
			self.depthVal.set(_num(d["value"]) if d else "")
			_set_placeholder(self.depthVal, "inherit (%s)" % _fmt_spec(rule.get("depth")))
		finally:
			self._loading = False

	def read(self):
		ov = {}
		area = self.areaVal.get().strip()
		if area:
			try:
				value = float(area)
			except (TypeError, ValueError):
				value = None
			if value is not None:
				ov["area"] = {"mode": "absolute" if self.areaMode.get() == 1 else "percent", "value": value}
		depth = self.depthVal.get().strip()
		if depth:
			try:
				value = float(depth)
			except (TypeError, ValueError):
				value = None
			if value is not None:
				ov["depth"] = {"mode": "absolute" if self.depthMode.get() == 1 else "percent", "value": value}
		return ov


class MasterRulesManager(_RuleListMixin):
	"""Per-master overrides for the same rules. Same list, a simpler editor."""

	def __init__(self, plugin, group):
		self.plugin = plugin
		self.group = group
		self._loading = False

		group.list = List(
			(10, 10, -270, -10),
			[],
			columnDescriptions=MASTER_COLUMNS,
			showColumnTitles=True,
			allowsMultipleSelection=False,
			allowsEmptySelection=True,
			selectionCallback=self._selection_cb,
			drawFocusRing=False,
		)
		# Match the font tab's sort behaviour so a sort mirrors across tabs:
		# Area/Depth sort by their numeric value (hidden keys), the ✓/● marker
		# columns aren't sortable.
		try:
			for col in group.list.getNSTableView().tableColumns():
				ident = str(col.identifier())
				if ident in ("mark", "ovr"):
					col.setSortDescriptorPrototype_(None)
				elif ident == "area":
					col.setSortDescriptorPrototype_(
						NSSortDescriptor.sortDescriptorWithKey_ascending_("_area_sort", True))
				elif ident == "depth":
					col.setSortDescriptorPrototype_(
						NSSortDescriptor.sortDescriptorWithKey_ascending_("_depth_sort", True))
		except Exception:
			pass

		# Grey out rows with no override (they show inherited font values).
		self._delegate = _MasterListDelegate.alloc().initWithManager_(self)
		try:
			group.list.getNSTableView().setDelegate_(self._delegate)
		except Exception:
			pass

		# Right-column header: font name (line 1) + master name (line 2).
		group.fontName = TextBox((-260, 8, -8, 18), "", sizeStyle="small")
		group.masterName = TextBox((-260, 26, -8, 18), "", sizeStyle="small")
		group.editorBox = Group((-260, 52, -8, -10))
		self.editor = MasterOverrideEditor(group.editorBox, self._editor_changed)
		self.refresh()

	def set_master_label(self):
		font = self.plugin.font
		master = font.selectedFontMaster if font else None
		self.group.fontName.set(font.familyName if font else "—")
		self.group.masterName.set(master.name if master else "—")

	def _row(self, rule_id, rule, overrides, matched):
		ov = overrides.get(rule_id) or {}
		oa = ov.get("area") if isinstance(ov.get("area"), dict) else None
		od = ov.get("depth") if isinstance(ov.get("depth"), dict) else None
		# Single Area/Depth column: show the override if there is one, otherwise
		# the inherited font value (the row is then greyed via _greyed).
		area = oa if oa else rule.get("area")
		depth = od if od else rule.get("depth")
		case_idx = int(rule.get("case", 0))
		return {
			"mark": CHECK if rule_id == matched else "",
			"ovr": "●" if ov else "",
			"name": rule.get("name", "") or "",
			"script": rule.get("script", "Any") or "Any",
			"category": rule.get("category", "Any") or "Any",
			"case": CASE_LABELS[case_idx] if 0 <= case_idx < len(CASE_LABELS) else "Any",
			"subcategory": rule.get("subcategory", "Any") or "Any",
			"filter": rule.get("filter", "") or "",
			"area": _fmt_spec(area),
			"depth": _fmt_spec(depth),
			"_area_sort": _spec_num(area),
			"_depth_sort": _spec_num(depth),
			"_greyed": not ov,
			"_id": rule_id,
		}

	def refresh_list(self):
		target = self._shared_selection_id() or self._selected_key()
		overrides = self.plugin.read_master_overrides()
		matched = self._matched_rule_id()
		rows = [self._row(rid, rule, overrides, matched) for rid, rule in self.plugin.font_rules.items()]
		self._loading = True
		try:
			self.group.list.set(rows)
			idx = self._index_of(target)
			if idx is not None:
				self.group.list.setSelection([idx])
		finally:
			self._loading = False

	def refresh(self):
		self.set_master_label()
		self.refresh_list()
		self._sync_editor()

	def _sync_editor(self):
		rule_id = self._selected_key()
		rule = self.plugin.font_rules.get(rule_id) if rule_id else None
		if rule is None:
			self.editor.set_enabled(False)
			return
		overrides = self.plugin.read_master_overrides()
		self.editor.set_enabled(True)
		self.editor.load(rule, overrides.get(rule_id))

	def _selection_cb(self, sender):
		if self._loading:
			return
		self._save_shared_selection()
		self._sync_editor()

	def _editor_changed(self):
		rule_id = self._selected_key()
		if not rule_id:
			return
		ov = self.editor.read()
		overrides = self.plugin.read_master_overrides()
		if ov:
			overrides[rule_id] = ov
		else:
			overrides.pop(rule_id, None)
		self.plugin.write_master_overrides(overrides)
		self.refresh_list()
		self.plugin.respace()
		self.plugin.live_apply_tab()
