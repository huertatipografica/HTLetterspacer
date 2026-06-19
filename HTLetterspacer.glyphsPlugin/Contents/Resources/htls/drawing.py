# encoding: utf-8
"""Non-destructive area drawing.

Renders the engine's area polygons as a Cocoa overlay (`NSBezierPath`,
translucent fill) — it NEVER writes to a layer or background (unlike the
script's destructive `createAreasBg`). Used by the areas reporter and (later)
the Parameters-tab preview.

Reference: eweracs' ShowHTLetterspacerAreas (green @ 0.4 alpha).
"""
from __future__ import division, print_function, unicode_literals

from AppKit import (
	NSBezierPath, NSColor, NSFont, NSAttributedString,
	NSFontAttributeName, NSForegroundColorAttributeName,
)


# 20 well-spread hues (golden-ratio spacing → adjacent indices look distinct).
# Rules are colour-indexed by sort order; >20 rules loop the palette.
_GOLDEN = 0.61803398875
_PALETTE_HSB = [((i * _GOLDEN) % 1.0, 0.62, 0.95) for i in range(20)]


def _default_color():
	"""Grey fill — used when no rule matches the glyph."""
	return NSColor.colorWithCalibratedWhite_alpha_(0.5, 0.30)


def _default_label_color():
	"""Grey text for the report (independent of the per-rule area colour)."""
	return NSColor.colorWithCalibratedWhite_alpha_(0.35, 0.9)


def area_color(index, alpha=0.35):
	"""Translucent fill colour for area `index` (a rule's sort position), looping
	the 20-colour palette. `index is None` → grey (no matching rule)."""
	if index is None:
		return _default_color()
	h, s, b = _PALETTE_HSB[int(index) % len(_PALETTE_HSB)]
	return NSColor.colorWithCalibratedHue_saturation_brightness_alpha_(h, s, b, alpha)


def draw_label(text, x, y, scale=1.0, color=None, align_right=True):
	"""Draw `text` near (x, y) in the layer's coordinate space. `scale` is the
	edit-view scale (`reporter.getScale()`) so the label keeps a constant on-
	screen size. When `align_right`, (x, y) is the *right* edge / baseline."""
	if not text:
		return
	size = 11.0 / (scale or 1.0)
	attrs = {
		NSFontAttributeName: NSFont.systemFontOfSize_(size),
		NSForegroundColorAttributeName: color or _default_label_color(),
	}
	s = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
	if align_right:
		x = x - s.size().width
	s.drawAtPoint_((x, y))


def draw_lines(lines, x, y_top, scale=1.0, color=None, align_right=False):
	"""Draw `lines` (a list of strings) stacked downward, the first line's top
	at `y_top`. `scale` is the edit-view scale so the block keeps a constant
	on-screen size. Lines are left-aligned at `x` (or right-aligned to `x`)."""
	if not lines:
		return
	size = 11.0 / (scale or 1.0)
	line_h = size * 1.3
	attrs = {
		NSFontAttributeName: NSFont.systemFontOfSize_(size),
		NSForegroundColorAttributeName: color or _default_label_color(),
	}
	y = y_top - size
	for line in lines:
		s = NSAttributedString.alloc().initWithString_attributes_(line, attrs)
		xx = (x - s.size().width) if align_right else x
		s.drawAtPoint_((xx, y))
		y -= line_h


def build_area_path(polygons):
	"""Build a single `NSBezierPath` from the L/R area polygons (each a list of
	NSPoints in the layer's coordinate space), or None if there's nothing to
	draw. Cache the result and re-fill it each frame instead of rebuilding —
	rebuilding per frame is a real cost when many glyphs are shown."""
	if not polygons:
		return None
	path = NSBezierPath.alloc().init()
	drew = False
	for polygon in polygons:
		if not polygon or len(polygon) < 2:
			continue
		first = polygon[0]
		path.moveToPoint_((first.x, first.y))
		for point in polygon[1:]:
			path.lineToPoint_((point.x, point.y))
		path.closePath()
		drew = True
	return path if drew else None


def fill_path(path, color=None):
	"""Fill a prebuilt area path (from `build_area_path`)."""
	if path is None:
		return
	(color or _default_color()).set()
	path.fill()


def draw_areas(polygons, color=None):
	"""Build + fill in one call. `polygons` is the (l_polygon, r_polygon) tuple
	from `HTLSEngine.calculate_polygons()`. The reporter caches the path and
	uses `build_area_path`/`fill_path` directly; this stays for the Parameters
	preview, which rebuilds anyway."""
	fill_path(build_area_path(polygons), color)
