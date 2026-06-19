# encoding: utf-8
"""Parameters tab.

Edits the current master's `paramArea` / `paramDepth` / `paramOver` (master
custom parameters; rules scale these), with:

  * a full-width text preview — type a word (up to 5 glyphs, slashed names like
    /A/space allowed) and see the glyphs laid out with their HTLS spacing,
    area polygons, margin lines, and per-glyph numbers (LSB/RSB at the inner
    corners, previous width top-centre, new width bottom-centre). Non-destructive;
  * Save / Reset parameters (Save rebaselines, Reset reverts to it);
  * an Actions menu: Copy parameters from another master, or Interpolate this
    master's parameters between two others along an axis.

With "Live tab apply" on (window footer), editing a value also re-spaces the
current Edit tab — the Manager's "live preview" equivalent.
"""
from __future__ import division, print_function, unicode_literals

import objc
from vanilla import (
	TextBox, EditText, Slider, HorizontalLine, CheckBox, Button, PopUpButton, Sheet, Group,
)
from AppKit import (
	NSColor, NSView, NSRectFill, NSGraphicsContext, NSAffineTransform, NSBezierPath,
)
from GlyphsApp import Message

from htls import engine as engine_mod
from htls import rules as rules_mod
from htls import drawing
from htls.ui.rules import _num

AREA_MAX = 1000
DEPTH_MAX = 50

DEFAULTS = {"paramArea": 400, "paramDepth": 15, "paramOver": 0}
PARAMS = ("paramArea", "paramDepth", "paramOver")
MAX_GLYPHS = 5
DEFAULT_TEXT = "noon"
_LINE_COLOR = (0.15, 0.4, 0.95, 0.7)


def _sb(value):
	try:
		return int(round(float(value)))
	except (TypeError, ValueError):
		return "—"


def _param(master, name):
	"""A master's HTLS parameter as a float, defaulting when absent."""
	if master is None:
		return float(DEFAULTS[name])
	try:
		value = master.customParameters[name]
		return float(value) if value is not None else float(DEFAULTS[name])
	except Exception:
		return float(DEFAULTS[name])


def _label_attrs():
	from AppKit import NSFont, NSFontAttributeName, NSForegroundColorAttributeName
	return {
		NSFontAttributeName: NSFont.systemFontOfSize_(9.0),
		NSForegroundColorAttributeName: NSColor.secondaryLabelColor(),
	}


# --------------------------------------------------------------------------
# Preview strip (custom-drawn: glyphs + areas + margin lines + numbers)
# --------------------------------------------------------------------------

class _StripNSView(NSView):
	"""A row of glyphs laid out with their HTLS spacing (a tiny Edit view):
	outlines + area polygons + margin lines, plus per-glyph numbers. Rendered
	under a transform we control so font-unit polygons and lines land exactly
	on the glyphs (GlyphsApp's GlyphView exposes no transform)."""

	def drawRect_(self, rect):
		try:
			self._draw()
		except Exception:
			import traceback
			print(traceback.format_exc())

	@objc.python_method
	def _draw(self):
		bounds = self.bounds()
		bg = getattr(self, "_bgColor", None)
		if bg is not None:
			bg.set()
			NSRectFill(bounds)
		cells = getattr(self, "_cells", None)
		master = getattr(self, "_master", None)
		if not cells or master is None:
			return
		try:
			asc, desc = float(master.ascender), float(master.descender)
		except Exception:
			asc, desc = 800.0, -200.0
		if asc <= desc:
			asc, desc = 800.0, -200.0

		strip_w = sum(max(c["new_w"], 1.0) for c in cells)
		if strip_w <= 0:
			return
		w, h = bounds.size.width, bounds.size.height
		pad_x, label_h = 16.0, 18.0
		scale = min((w - 2 * pad_x) / strip_w, (h - 2 * label_h) / (asc - desc))
		if scale <= 0:
			scale = (h - 2 * label_h) / 1000.0
		tx = (w - strip_w * scale) / 2.0
		ty = label_h - desc * scale

		# 1) glyphs + areas + margin lines, under the strip transform
		t = NSAffineTransform.transform()
		t.translateXBy_yBy_(tx, ty)
		t.scaleBy_(scale)
		ctx = NSGraphicsContext.currentContext()
		ctx.saveGraphicsState()
		fg = getattr(self, "_fgColor", None) or NSColor.textColor()
		area_color = getattr(self, "_areaColor", None)
		try:
			t.concat()
			pen = 0.0
			boundaries = [0.0]
			for c in cells:
				layer, sb, polys, new_w = c["layer"], c["sb"], c["polys"], c["new_w"]
				dx = pen + (sb[0] if sb else 0.0) - c["ink_l"]
				ctx.saveGraphicsState()
				try:
					off = NSAffineTransform.transform()
					off.translateXBy_yBy_(dx, 0.0)
					off.concat()
					if polys:
						drawing.draw_areas(polys, area_color)
					try:
						path = layer.completeBezierPath
						if path is not None:
							fg.set()
							path.fill()
					except Exception:
						pass
				finally:
					ctx.restoreGraphicsState()
				pen += new_w
				boundaries.append(pen)
			# margin lines at every advance boundary
			line = NSBezierPath.bezierPath()
			line.setLineWidth_(1.0 / scale)
			top, bottom = asc + 80, desc - 80
			for bx in boundaries:
				line.moveToPoint_((bx, bottom))
				line.lineToPoint_((bx, top))
			NSColor.colorWithCalibratedRed_green_blue_alpha_(*_LINE_COLOR).set()
			line.stroke()
		finally:
			ctx.restoreGraphicsState()

		# 2) numeric labels in view space (so the text isn't scaled)
		attrs = _label_attrs()
		pen = 0.0
		for c in cells:
			left_v = tx + pen * scale
			right_v = tx + (pen + c["new_w"]) * scale
			center_v = (left_v + right_v) / 2.0
			self._text("%s" % _sb(c["prev_w"]), center_v, h - label_h + 2, attrs, "center")
			self._text("%s" % _sb(c["new_w"]), center_v, 3, attrs, "center")
			if c["sb"]:
				self._text("%s" % _sb(c["sb"][0]), left_v + 3, 3, attrs, "left")
				self._text("%s" % _sb(c["sb"][1]), right_v - 3, 3, attrs, "right")
			pen += c["new_w"]

	@objc.python_method
	def _text(self, s, x, y, attrs, align):
		from AppKit import NSString
		ns = NSString.stringWithString_(s)
		size = ns.sizeWithAttributes_(attrs)
		if align == "center":
			x -= size.width / 2.0
		elif align == "right":
			x -= size.width
		ns.drawAtPoint_withAttributes_((x, y), attrs)


class _StripView(Group):
	"""Vanilla wrapper around `_StripNSView`."""

	nsViewClass = _StripNSView

	def __init__(self, posSize, backgroundColor=None, foregroundColor=None, areaColor=None):
		self._setupView(self.nsViewClass, posSize)
		v = self.getNSView()
		v._bgColor = backgroundColor
		v._fgColor = foregroundColor or NSColor.textColor()
		v._areaColor = areaColor
		v._cells = None
		v._master = None

	def set_cells(self, cells, master):
		v = self.getNSView()
		v._cells = cells
		v._master = master
		v.setNeedsDisplay_(True)


class _InterpolateSheet(object):
	"""Sheet to interpolate the current master's parameters between two others
	along a chosen axis (linear, by the masters' positions on that axis)."""

	def __init__(self, manager, masters):
		self.manager = manager
		self.masters = masters
		font = manager.plugin.font
		self.axes = list(font.axes)

		self.sheet = Sheet((330, 210), manager.plugin.w)
		s = self.sheet
		s.title = TextBox((20, 18, -20, 18), "Interpolate this master's parameters:", sizeStyle="small")
		s.axisLbl = TextBox((20, 50, 70, 18), "Axis", sizeStyle="small")
		s.axis = PopUpButton((96, 48, -20, 20), [a.name for a in self.axes], sizeStyle="small")
		s.m1Lbl = TextBox((20, 78, 70, 18), "From", sizeStyle="small")
		s.m1 = PopUpButton((96, 76, -20, 20), [m.name for m in masters], sizeStyle="small")
		s.m2Lbl = TextBox((20, 106, 70, 18), "To", sizeStyle="small")
		s.m2 = PopUpButton((96, 104, -20, 20), [m.name for m in masters], sizeStyle="small")
		s.m2.set(1)
		s.cancelBtn = Button((-200, -32, 90, 20), "Cancel", callback=self._cancel, sizeStyle="small")
		s.okBtn = Button((-100, -32, 80, 20), "Interpolate", callback=self._ok, sizeStyle="small")
		try:
			s.setDefaultButton(s.okBtn)
		except Exception:
			pass

	def open(self):
		self.sheet.open()

	def _cancel(self, sender):
		self.sheet.close()

	def _ok(self, sender):
		axis_index = self.sheet.axis.get()
		m1 = self.masters[self.sheet.m1.get()]
		m2 = self.masters[self.sheet.m2.get()]
		self.sheet.close()
		if m1 is m2:
			Message(title="Two masters needed", message="Please pick two different masters.")
			return
		self.manager._interpolate(axis_index, m1, m2)


class ParametersManager(object):

	def __init__(self, plugin, group):
		self.plugin = plugin
		self.group = group
		self._loading = False
		self._action_masters = []
		self._uni = {}
		g = group

		g.fontName = TextBox((10, 8, -10, 16), "", sizeStyle="small")
		g.masterName = TextBox((10, 26, -10, 16), "", sizeStyle="small")
		g.divider = HorizontalLine((10, 46, -10, 1))

		g.areaLbl = TextBox((10, 54, 76, 18), "Area")
		g.areaSlider = Slider((92, 52, -210, 22), minValue=0, maxValue=AREA_MAX, value=400, callback=self._area_slider)
		g.areaField = EditText((-200, 51, 56, 22), "400", callback=self._area_field, continuous=False, sizeStyle="small")
		g.areaHint = TextBox((-138, 54, -10, 18), "", sizeStyle="small")

		g.depthLbl = TextBox((10, 88, 76, 18), "Depth")
		g.depthSlider = Slider((92, 86, -210, 22), minValue=0, maxValue=DEPTH_MAX, value=15, callback=self._depth_slider)
		g.depthField = EditText((-200, 85, 56, 22), "15", callback=self._depth_field, continuous=False, sizeStyle="small")
		g.depthHint = TextBox((-138, 88, -10, 18), "% of x-height", sizeStyle="small")

		g.overLbl = TextBox((10, 122, 76, 18), "Overshoot")
		g.overField = EditText((92, 120, 60, 22), "0", callback=self._over_field, continuous=False, sizeStyle="small")
		# Live Tab Test moved onto the overshoot row (right) to save vertical space.
		g.liveTest = CheckBox(
			(168, 122, -10, 20), "Live Tab Test (apply values without updating master custom parameters)",
			callback=self._test_toggle, sizeStyle="small")

		g.saveBtn = Button((10, 152, 124, 22), "Save parameters", callback=self._save_params, sizeStyle="small")
		g.resetBtn = Button((140, 152, 124, 22), "Reset parameters", callback=self._reset_params, sizeStyle="small")
		g.actionBtn = PopUpButton((272, 152, 120, 22), ["Actions"], callback=self._action_cb, sizeStyle="small")
		try:
			g.actionBtn.getNSPopUpButton().setPullsDown_(True)
		except Exception:
			pass

		g.textLbl = TextBox((10, 184, 34, 18), "Text", sizeStyle="small")
		g.textField = EditText((48, 182, -10, 22), DEFAULT_TEXT, callback=self._text_cb,
			continuous=False, sizeStyle="small")

		g.strip = _StripView((10, 210, -10, -10),
			backgroundColor=NSColor.textBackgroundColor(), foregroundColor=NSColor.textColor())

		# Baseline for Save/Reset: each master's params as they are now.
		self._saved = self._snapshot_all()
		self.load()

	# --- master params ----------------------------------------------------

	def _master(self):
		# Read the font ONCE: self.plugin.font is a live property that can flip
		# to None between the truth-check and the attribute access.
		font = self.plugin.font
		return font.selectedFontMaster if font is not None else None

	def _get(self, name):
		return _param(self._master(), name)

	def _snapshot_all(self):
		out = {}
		font = self.plugin.font
		if font is not None:
			for master in font.masters:
				out[master.id] = {p: int(_param(master, p)) for p in PARAMS}
		return out

	def _area_units(self, value):
		"""The real white-area target in font units² for `paramArea` = `value`."""
		font = self.plugin.font
		upm = int(font.upm) if font and font.upm else 1000
		return int(round(value * 100 * (upm / 1000.0) ** 2))

	def _update_area_hint(self, value):
		self.group.areaHint.set("= %d units²" % self._area_units(value))

	def _current_values(self):
		"""The values currently shown in the fields."""
		def num(field, default):
			try:
				return int(float(field.get()))
			except (TypeError, ValueError):
				return default
		return {
			"paramArea": num(self.group.areaField, int(DEFAULTS["paramArea"])),
			"paramDepth": num(self.group.depthField, int(DEFAULTS["paramDepth"])),
			"paramOver": num(self.group.overField, int(DEFAULTS["paramOver"])),
		}

	def _set(self, name, value):
		if self._test_enabled():
			# Non-destructive test: DON'T write the master; re-space the current
			# tab using the current field values as overrides.
			self.plugin.space_current_tab(self._current_values())
		else:
			master = self._master()
			if master is not None:
				master.customParameters[name] = int(value)
				# Repaint (reporter cache keys on these params); with "Live tab
				# apply" on, the footer also re-spaces the tab.
				self.plugin.respace()
				self.plugin.live_apply_tab()
		self.update_previews()
		self._update_reset_enabled()

	# --- save / reset ------------------------------------------------------

	def _save_params(self, sender):
		"""Commit the field values to the master and rebaseline the snapshot."""
		master = self._master()
		if master is not None:
			vals = self._current_values()
			for p in PARAMS:
				master.customParameters[p] = int(vals[p])
		self._saved = self._snapshot_all()
		self.plugin.respace()
		self.plugin.live_apply_tab()
		self.update_previews()
		self._update_reset_enabled()

	def _reset_params(self, sender):
		"""Revert the current master's params to the last saved snapshot."""
		master = self._master()
		snap = self._saved.get(master.id) if master else None
		if master is not None and snap:
			for p, v in snap.items():
				master.customParameters[p] = int(v)
		self.load()
		self.plugin.respace()
		self.plugin.live_apply_tab()

	def _update_reset_enabled(self):
		master = self._master()
		snap = self._saved.get(master.id) if master else None
		differ = bool(master and snap and any(
			int(self._current_values()[p]) != int(snap[p]) for p in PARAMS))
		try:
			self.group.resetBtn.enable(differ)
		except Exception:
			pass

	# --- actions menu (copy / interpolate) --------------------------------

	def _build_actions(self):
		font = self.plugin.font
		current = self._master()
		others = [m for m in font.masters if m is not current] if font else []
		self._action_masters = others
		labels = ["Actions", "Interpolate parameters…"] + ["Copy from %s" % m.name for m in others]
		try:
			self.group.actionBtn.setItems(labels)
			self.group.actionBtn.set(0)
		except Exception:
			pass

	def _action_cb(self, sender):
		idx = sender.get()
		try:
			if idx == 1:
				self._open_interpolate()
			elif idx >= 2 and (idx - 2) < len(self._action_masters):
				self._copy_from(self._action_masters[idx - 2])
		finally:
			sender.set(0)

	def _copy_from(self, source):
		master = self._master()
		if master is None or source is None:
			return
		for p in PARAMS:
			master.customParameters[p] = int(_param(source, p))
		self.load()
		self.plugin.respace()
		self.plugin.live_apply_tab()

	def _open_interpolate(self):
		font = self.plugin.font
		if font is None:
			return
		current = self._master()
		others = [m for m in font.masters if m is not current]
		if len(others) < 2 or not font.axes:
			Message(title="Need two masters",
				message="Interpolation needs at least two other masters and an axis.")
			return
		self._interp_sheet = _InterpolateSheet(self, others)
		self._interp_sheet.open()

	def _interpolate(self, axis_index, m1, m2):
		master = self._master()
		if master is None:
			return
		try:
			a1, a2, at = m1.axes[axis_index], m2.axes[axis_index], master.axes[axis_index]
		except Exception:
			return
		if a2 == a1:
			Message(title="Can't interpolate",
				message="The two masters share the same position on that axis.")
			return
		factor = (at - a1) / float(a2 - a1)
		for p in PARAMS:
			v1, v2 = _param(m1, p), _param(m2, p)
			master.customParameters[p] = int(round(v1 + factor * (v2 - v1)))
		self.load()
		self.plugin.respace()
		self.plugin.live_apply_tab()

	# --- live tab test (non-destructive) ----------------------------------

	def _test_enabled(self):
		try:
			return bool(self.group.liveTest.get())
		except Exception:
			return False

	def _test_toggle(self, sender):
		on = bool(sender.get())
		try:
			live = self.plugin.w.liveApply
			if on:
				live.set(False)
			live.enable(not on)
		except Exception:
			pass
		if on:
			self.plugin.space_current_tab(self._current_values())
		else:
			self.load()
			self.plugin.space_current_tab()

	# --- preview text ------------------------------------------------------

	def _build_unicode_cache(self, font):
		self._uni = {}
		if font is None:
			return
		for glyph in font.glyphs:
			try:
				u = glyph.unicode
			except Exception:
				u = None
			if u:
				self._uni.setdefault(str(u).upper(), glyph.name)

	def _char_to_name(self, c, font):
		if font is None:
			return None
		if font.glyphs[c] is not None:
			return c
		return self._uni.get("%04X" % ord(c))

	def _parse_text(self, text, font):
		"""Glyph names from an edit string: literal chars (by name/unicode),
		spaces -> 'space', and /slashed names (terminated by space or '/').
		Capped at MAX_GLYPHS; missing glyphs are dropped."""
		names = []
		s = text or ""
		i, n = 0, len(s)
		while i < n and len(names) < MAX_GLYPHS:
			c = s[i]
			if c == "/":
				j = i + 1
				while j < n and s[j] not in "/ ":
					j += 1
				name = s[i + 1:j]
				if name and font is not None and font.glyphs[name] is not None:
					names.append(name)
				i = j + 1 if (j < n and s[j] == " ") else j
			elif c == " ":
				if font is not None and font.glyphs["space"] is not None:
					names.append("space")
				i += 1
			else:
				name = self._char_to_name(c, font)
				if name and font.glyphs[name] is not None:
					names.append(name)
				i += 1
		return names

	def _build_cells(self, font, master, overrides):
		cells = []
		if font is None or master is None:
			return cells
		for name in self._parse_text(self.group.textField.get(), font):
			glyph = font.glyphs[name]
			if glyph is None:
				continue
			layer = glyph.layers[master.id]
			if layer is None:
				continue
			sb = polys = None
			new_w = layer.width
			try:
				eng = engine_mod.HTLSEngine(
					layer, font_rules=self.plugin.font_rules, param_overrides=overrides, force=True)
				sb = eng.current_layer_sidebearings()
				polys = eng.calculate_polygons()
				ink_w = layer.bounds.size.width
				if eng.newWidth:
					new_w = eng.newWidth
				elif sb:
					new_w = sb[0] + ink_w + sb[1]
			except Exception:
				pass
			cells.append({
				"layer": layer, "sb": sb, "polys": polys,
				"ink_l": layer.bounds.origin.x, "prev_w": layer.width, "new_w": new_w,
			})
		return cells

	# --- load / refresh ----------------------------------------------------

	def load(self):
		master = self._master()
		font = self.plugin.font
		self._loading = True
		try:
			self.group.fontName.set(font.familyName if font else "—")
			self.group.masterName.set("Master: %s" % (master.name if master else "—"))
			area = int(self._get("paramArea"))
			depth = int(self._get("paramDepth"))
			over = int(self._get("paramOver"))
			self.group.areaSlider.set(min(area, AREA_MAX))
			self.group.areaField.set(str(area))
			self._update_area_hint(area)
			self.group.depthSlider.set(min(depth, DEPTH_MAX))
			self.group.depthField.set(str(depth))
			self.group.overField.set(str(over))
		finally:
			self._loading = False
		self._build_unicode_cache(font)
		# Re-baseline Save/Reset if the snapshot is for a different font.
		if font is not None and not any(m.id in self._saved for m in font.masters):
			self._saved = self._snapshot_all()
		self._build_actions()
		self.update_previews()
		self._update_reset_enabled()

	def refresh(self):
		self.load()

	def update_previews(self):
		font = self.plugin.font
		master = self._master()
		cells = self._build_cells(font, master, self._current_values())
		self.group.strip.set_cells(cells, master)

	def _text_cb(self, sender):
		if self._loading:
			return
		self.update_previews()

	# --- callbacks --------------------------------------------------------

	def _area_slider(self, sender):
		if self._loading:
			return
		value = int(sender.get())
		self.group.areaField.set(str(value))
		self._update_area_hint(value)
		self._set("paramArea", value)

	def _area_field(self, sender):
		if self._loading:
			return
		try:
			value = int(float(sender.get()))
		except (TypeError, ValueError):
			return
		self.group.areaSlider.set(min(value, AREA_MAX))
		self._update_area_hint(value)
		self._set("paramArea", value)

	def _depth_slider(self, sender):
		if self._loading:
			return
		value = int(sender.get())
		self.group.depthField.set(str(value))
		self._set("paramDepth", value)

	def _depth_field(self, sender):
		if self._loading:
			return
		try:
			value = int(float(sender.get()))
		except (TypeError, ValueError):
			return
		self.group.depthSlider.set(min(value, DEPTH_MAX))
		self._set("paramDepth", value)

	def _over_field(self, sender):
		if self._loading:
			return
		try:
			value = int(float(sender.get()))
		except (TypeError, ValueError):
			return
		self._set("paramOver", value)
