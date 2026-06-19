# encoding: utf-8
"""Spacing engine.

Faithful port of the standalone script's `HTLetterspacerLib`
(`_original/HT Letterspacer/HT_Letterspacer_script.py`) — the *good* logic,
NOT the Manager's diverged `HTLSEngine`. The geometry/area math below is kept
identical to the script so spacing matches it exactly, including:

  * `applyPrepareLayerCallbacks` — expands native strokes / HT Stroker paths
    into outlines before measuring (the Manager dropped this);
  * `paramOver` (overshoot) support (the Manager hardcoded 0);
  * `paramFreq = 5` (the Manager used 4).

Only the *inputs/orchestration* layer differs from the script: instead of
reading a sidecar config file, the per-layer `HTLSEngine` resolves its factor
and reference glyph from the font's rules via `rules.find_rule`.
`calculate_polygons()` returns the L/R area polygons WITHOUT writing anything —
reused by the aux scripts, the areas reporter and the Parameters preview.
"""
from __future__ import division, print_function, unicode_literals

import math
from collections import deque

import objc
import GlyphsApp
from Foundation import NSMinX, NSMaxX, NSMinY, NSMaxY, NSMakePoint

from htls import config, rules

# Frequency of vertical measuring. The script uses 5 (the Manager used 4).
paramFreq = 5


# --- point list area (verbatim from the script) ---------------------------
def area(points):
	s = 0
	for ii in range(-1, len(points) - 1):
		s = s + (points[ii].x * points[ii + 1].y - points[ii + 1].x * points[ii].y)
	return abs(s) * 0.5


# --- expand strokes/attributes into rendered outlines, in place -----------
def applyPrepareLayerCallbacks(layer):
	"""Run Glyphs' prepare-layer processing on `layer` (a scratch copy!).

	`copyDecomposedLayer` only decomposes COMPONENTS. Stroke skeletons —
	Glyphs' native stroke path attributes, HT Stroker paths, and anything
	else registered as a GSPrepareLayerCallback — are expanded into their
	rendered outlines by the same callback chain Glyphs runs for drawing
	and metrics. Without this, stroked glyphs measure as zero-height
	skeleton centerlines. Safe no-op when no callbacks are registered.
	"""
	try:
		handler = objc.lookUpClass('GSCallbackHandler')
		callbacks = handler.callbacksForType_('GSPrepareLayerCallback')
		if callbacks:
			handler.applyLayerCallbacks_toLayer_error_(callbacks, layer, None)
	except Exception:
		import traceback
		print(traceback.format_exc())


# --- get margins in Glyphs (verbatim) -------------------------------------
def getMargins(layer, y):
	startPoint = NSMakePoint(NSMinX(layer.bounds) - 1, y)
	endPoint = NSMakePoint(NSMaxX(layer.bounds) + 1, y)

	result = layer.calculateIntersectionsStartPoint_endPoint_(startPoint, endPoint)
	count = len(result)
	if count <= 2:
		return (None, None)

	left = 1
	right = count - 2
	return (result[left].pointValue().x, result[right].pointValue().x)


def triangle(angle, y):
	angle = math.radians(angle)
	return y * (math.tan(angle))


def totalMarginList(layer, minY, maxY, angle, minYref, maxYref):
	# the list of margins
	y = minY
	listL = []
	listR = []

	# calculate default depth, otherwise measurement is None
	# calculate paralelogram extremes
	origin = NSMinX(layer.bounds)
	endpointx = NSMaxX(layer.bounds)
	endpointy = NSMaxY(layer.bounds)

	# calculate paralelogram top left
	xpos = triangle(angle, endpointy) + origin
	# paralelogram top side width
	slantWidth = (endpointx - xpos)
	# default depth
	dfltDepth = slantWidth

	# result is False if all the measured margins are empty (no outlines in reference zone)
	result = False

	while y <= maxY:
		lpos, rpos = getMargins(layer, y)

		# get the default margin measure at a given y position
		slantPosL = origin + triangle(angle, y) + dfltDepth
		slantPosR = origin + triangle(angle, y)

		if lpos is not None:
			listL.append(NSMakePoint(lpos, y))
			if minYref <= y <= maxYref:
				result = True
		else:
			listL.append(NSMakePoint(slantPosL, y))

		if rpos is not None:
			listR.append(NSMakePoint(rpos, y))
			if minYref <= y <= maxYref:
				result = True
		else:
			listR.append(NSMakePoint(slantPosR, y))

		y += paramFreq

	# if no measurements are taken, returns false and will abort in main function
	if result:
		return listL, listR
	else:
		return False, False


def zoneMargins(lMargins, rMargins, minY, maxY):
	# filter those outside the range
	pointsFilteredL = [x for x in lMargins if minY <= x.y <= maxY]
	pointsFilteredR = [x for x in rMargins if minY <= x.y <= maxY]

	return pointsFilteredL, pointsFilteredR


class HTLSEngine(object):
	"""Per-layer spacing engine. Construct with a layer; it resolves the
	master parameters and the matching rule, then computes polygons and
	sidebearings on demand — without writing to the font.

	Pass `font_rules` to avoid re-reading them per layer, or `factor` /
	`reference_layer` to override rule resolution (used for parity tests
	against the script).
	"""

	# Script defaults (HT_Letterspacer_script.py).
	DEFAULT_AREA = 400
	DEFAULT_DEPTH = 15
	DEFAULT_OVER = 0

	def __init__(self, layer, font_rules=None, factor=None, reference_layer=None,
	             param_overrides=None, force=False):
		self.layer = layer
		self.glyph = layer.parent
		self.font = self.glyph.parent if self.glyph is not None else None
		self.master = layer.master
		# Preview/force: still compute areas + sidebearings for glyphs the real
		# spacing path skips (metric keys, automatic alignment) so the Parameters
		# preview can show them. Never used by the destructive write path.
		self._force = bool(force)

		self.output = ""

		# master-derived constants
		self.upm = int(self.font.upm) if self.font is not None else 1000
		self.angle = self.master.italicAngle
		self.xHeight = self.master.xHeight
		self.paramArea = self._master_param("paramArea", self.DEFAULT_AREA)
		self.paramDepth = self._master_param("paramDepth", self.DEFAULT_DEPTH)
		self.paramOver = self._master_param("paramOver", self.DEFAULT_OVER)
		# Non-destructive parameter test: override the master params in-memory
		# without writing them to the font (used by the Parameters "Live Tab
		# Test"). Rule scaling below resolves against these overridden bases.
		self._param_overrides = param_overrides or None
		if param_overrides:
			self.paramArea = float(param_overrides.get("paramArea", self.paramArea))
			self.paramDepth = float(param_overrides.get("paramDepth", self.paramDepth))
			self.paramOver = float(param_overrides.get("paramOver", self.paramOver))
		self.paramFreq = paramFreq

		# flags (engine-side; UI/aux scripts may toggle before computing)
		self.tabVersion = False
		self.LSB = True
		self.RSB = True
		self.width = None

		# results
		self.newL = None
		self.newR = None
		self.newWidth = False
		self.factor = 1.0
		# the font rule that matched this glyph (id, dict), or None — exposed so
		# the reporter / inspector can label the glyph with its rule.
		self.matched_rule_id = None
		self.matched_rule = None

		# effective area/depth: default to the master params, so
		# with no matching rule the spacing matches the script (factor 1).
		self.effectiveArea = self.paramArea
		self.effectiveDepth = self.paramDepth

		# y-range, filled by setSpace
		self.minYref = self.maxYref = self.minY = self.maxY = None

		# compute cache
		self._computed = False
		self._lp = None
		self._rp = None

		self.reference_layer = reference_layer
		if reference_layer is not None and factor is not None:
			# explicit override (used by the parity harness): area = paramArea
			# * factor, depth = paramDepth, reference kept as given.
			self.factor = float(factor)
			self.effectiveArea = self.paramArea * self.factor
		else:
			self._resolve_rule(font_rules)

	# --- input resolution --------------------------------------------------

	def _master_param(self, name, default):
		try:
			value = self.master.customParameters[name]
			return float(value) if value is not None else float(default)
		except Exception:
			return float(default)

	def _resolve_rule(self, font_rules):
		"""Default reference = the glyph itself and effective area/depth = the
		master params; the matching font rule (and any per-master override)
		overrides reference, area, depth, tabular and the LSB/RSB sides."""
		self.reference_layer = self.layer
		self.effectiveArea = self.paramArea
		self.effectiveDepth = self.paramDepth
		if self.glyph is None:
			return
		if font_rules is None and self.font is not None:
			font_rules = config.read_font_rules(self.font)
		match = rules.find_rule(self.glyph, font_rules, self.master) if font_rules else None
		if not match:
			return
		rule_id, rule = match
		self.matched_rule_id = rule_id
		self.matched_rule = rule
		override = self._master_override(rule_id)

		# effective area/depth (absolute or percent, with master override).
		# Pass the engine's param bases so a non-destructive override scales the
		# percent rules too (base == master value when no override is active).
		self.effectiveArea = rules.resolve_area(rule, self.master, override, base=self.paramArea)
		self.effectiveDepth = rules.resolve_depth(rule, self.master, override, base=self.paramDepth)
		self.factor = (self.effectiveArea / self.paramArea) if self.paramArea else 1.0

		# reference glyph
		ref_name = rule.get("reference") or rule.get("referenceGlyph") or ""
		if ref_name and self.font is not None and self.font.glyphs[ref_name]:
			ref_layer = self.font.glyphs[ref_name].layers[self.layer.associatedMasterId]
			if len(ref_layer.paths) > 0 or len(ref_layer.components) > 0:
				self.reference_layer = ref_layer

		# tabular: force fixed advance width
		if rule.get("tabular"):
			self.tabVersion = True

		# sides: an unchecked side is never touched (newL/newR keep layer SB)
		sides = rule.get("sides") or {}
		self.LSB = bool(sides.get("LSB", True))
		self.RSB = bool(sides.get("RSB", True))

	def _master_override(self, rule_id):
		"""Per-master override `{area?, depth?}` for `rule_id`, or None. An
		omitted area/depth key means 'inherit the font rule'."""
		try:
			raw = self.master.userData[config.MASTER_RULES_KEY]
		except Exception:
			raw = None
		if not raw:
			return None
		data = config._to_plain(raw)
		if not isinstance(data, dict):
			return None
		return data.get(rule_id)

	# --- geometry (verbatim from the script) ------------------------------

	def overshoot(self):
		return self.xHeight * self.paramOver / 100

	def maxPoints(self, points, minY, maxY):
		# returns the extremes for a given set of points (minY/maxY unused,
		# kept for parity with the script's call sites)
		sortPointsByXL = sorted(points[0], key=lambda tup: tup[0])
		sortPointsByXR = sorted(points[1], key=lambda tup: tup[0])

		left, lefty = sortPointsByXL[0]
		right, righty = sortPointsByXR[-1]

		return NSMakePoint(left, lefty), NSMakePoint(right, righty)

	def processMargins(self, lMargin, rMargin, lExtreme, rExtreme):
		# set depth
		lMargin, rMargin = self.setDepth(lMargin, rMargin, lExtreme, rExtreme)

		# close open counterforms at 45 degrees
		lMargin, rMargin = self.diagonize(lMargin, rMargin)
		lMargin = self.closeOpenCounters(lMargin, lExtreme)
		rMargin = self.closeOpenCounters(rMargin, rExtreme)

		return lMargin, rMargin

	def setDepth(self, marginsL, marginsR, lExtreme, rExtreme):
		# process lists with depth, proportional to xheight
		depth = self.xHeight * self.effectiveDepth / 100
		maxdepth = lExtreme.x + depth
		mindepth = rExtreme.x - depth
		marginsL = [NSMakePoint(min(p.x, maxdepth), p.y) for p in marginsL]
		marginsR = [NSMakePoint(max(p.x, mindepth), p.y) for p in marginsR]

		# add all the points at maximum depth if glyph is shorter than overshoot
		y = marginsL[0].y - self.paramFreq
		while y > self.minYref:
			marginsL.insert(0, NSMakePoint(maxdepth, y))
			marginsR.insert(0, NSMakePoint(mindepth, y))
			y -= self.paramFreq

		y = marginsL[-1].y + self.paramFreq
		while y < self.maxYref:
			marginsL.append(NSMakePoint(maxdepth, y))
			marginsR.append(NSMakePoint(mindepth, y))
			y += self.paramFreq

		return marginsL, marginsR

	def diagonize(self, marginsL, marginsR):
		# close counters at 45 degrees
		ystep = abs(marginsL[0].y - marginsL[1].y)
		for i in range(len(marginsL) - 1):
			if marginsL[i + 1].x - marginsL[i].x > ystep:
				marginsL[i + 1].x = marginsL[i].x + ystep
			if marginsR[i + 1].x - marginsR[i].x < -ystep:
				marginsR[i + 1].x = marginsR[i].x - ystep

		for i in reversed(range(len(marginsL) - 1)):
			if marginsL[i].x - marginsL[i + 1].x > ystep:
				marginsL[i].x = marginsL[i + 1].x + ystep
			if marginsR[i].x - marginsR[i + 1].x < -ystep:
				marginsR[i].x = marginsR[i + 1].x - ystep

		return marginsL, marginsR

	def closeOpenCounters(self, margin, extreme):
		# close counterforms, creating a polygon
		initPoint = NSMakePoint(extreme.x, self.minYref)
		endPoint = NSMakePoint(extreme.x, self.maxYref)
		margin.insert(0, initPoint)
		margin.append(endPoint)
		return margin

	def deslant(self, margin):
		"""De-slant a list of points at angle, origin at half the xheight."""
		mline = self.xHeight / 2
		return [
			NSMakePoint(p.x - (p.y - mline) * math.tan(math.radians(self.angle)), p.y)
			for p in margin
		]

	def slant(self, margin):
		"""Slant a list of points at angle, origin at half the xheight."""
		mline = self.xHeight / 2
		return [
			NSMakePoint(p.x - (p.y - mline) * math.tan(math.radians(self.angle * (-1))), p.y)
			for p in margin
		]

	def calculateSBValue(self, polygon):
		amplitudeY = self.maxYref - self.minYref

		# recalculates area based on UPM. effectiveArea already folds in the
		# rule factor (or override), so there is no separate * factor here —
		# with no rule, effectiveArea == paramArea, matching the script.
		areaUPM = self.effectiveArea * ((self.upm / 1000) ** 2)
		whiteArea = areaUPM * 100

		propArea = (amplitudeY * whiteArea) / self.xHeight

		valor = propArea - area(polygon)
		return valor / amplitudeY

	def setSpace(self, layer, referenceLayer):
		# get reference glyph maximum points
		overshoot = self.overshoot()

		# store min and max y
		self.minYref = NSMinY(referenceLayer.bounds) - overshoot
		self.maxYref = NSMaxY(referenceLayer.bounds) + overshoot

		self.minY = NSMinY(layer.bounds)
		self.maxY = NSMaxY(layer.bounds)

		# get the margins for the full outline
		lTotalMargins, rTotalMargins = totalMarginList(
			layer, self.minY, self.maxY, self.angle, self.minYref, self.maxYref
		)

		# margins are False, False if there is no measure in the reference zone
		if not lTotalMargins and not rTotalMargins:
			self.output += "The glyph outlines are outside the reference zone. No match with %s\n" % \
				referenceLayer.parent.name
			return

		# filter all the margins to the reference zone
		lZoneMargins, rZoneMargins = zoneMargins(lTotalMargins, rTotalMargins, self.minYref, self.maxYref)

		# if the font has an angle, we need to deslant
		if self.angle:
			lZoneMargins = self.deslant(lZoneMargins)
			rZoneMargins = self.deslant(rZoneMargins)
			lTotalMargins = self.deslant(lTotalMargins)
			rTotalMargins = self.deslant(rTotalMargins)

		# full shape extreme points
		lFullExtreme, rFullExtreme = self.maxPoints([lTotalMargins, rTotalMargins], self.minY, self.maxY)
		# zone extreme points
		lExtreme, rExtreme = self.maxPoints([lZoneMargins, rZoneMargins], self.minYref, self.maxYref)

		# create a closed polygon
		lPolygon, rPolygon = self.processMargins(lZoneMargins, rZoneMargins, lExtreme, rExtreme)

		# dif between extremes full and zone
		distanceL = math.ceil(lExtreme.x - lFullExtreme.x)
		distanceR = math.ceil(rFullExtreme.x - rExtreme.x)

		# set new sidebearings
		self.newL = math.ceil(0 - distanceL + self.calculateSBValue(lPolygon))
		self.newR = math.ceil(0 - distanceR + self.calculateSBValue(rPolygon))

		# tabular version — driven by the rule's `tabular` field, NOT the glyph
		# name. (The script hardcoded '.tf'/'.tosf'; that is now a rule.)
		if self.tabVersion:
			if self.width:
				self.layerWidth = self.width
			else:
				self.layerWidth = layer.width

			widthShape = rFullExtreme.x - lFullExtreme.x
			widthActual = widthShape + self.newL + self.newR
			widthDiff = (self.layerWidth - widthActual) / 2

			self.newL += widthDiff
			self.newR += widthDiff
			self.newWidth = self.layerWidth
		# metric-rule / skipped-side handling
		else:
			if layer.parent.leftMetricsKey is not None or self.LSB is False:
				self.newL = layer.LSB
			if layer.parent.rightMetricsKey is not None or self.RSB is False:
				self.newR = layer.RSB

		return lPolygon, rPolygon

	# --- public API --------------------------------------------------------

	def _compute(self):
		"""Run the spacing once (decompose + expand strokes + setSpace) and
		cache the polygons. Does NOT write to the layer."""
		if self._computed:
			return self._lp, self._rp
		self._computed = True

		layer = self.layer
		lp, rp = None, None
		try:
			if not layer.name:
				pass
			elif len(layer.paths) < 1 and len(layer.components) < 1:
				self.output += "No paths in glyph %s\n" % (layer.parent.name or "")
			elif layer.hasAlignedWidth() and not self._force:
				self.output += "Glyph %s has automatic alignment. Spacing not set.\n" % layer.parent.name
			elif (layer.parent.leftMetricsKey is not None and layer.parent.rightMetricsKey is not None
			      and not self._force):
				self.output += "Glyph %s has metric keys. Spacing not set.\n" % layer.parent.name
			else:
				# Decompose for analysis (the deeper plumbing assumes outlines),
				# then expand stroke skeletons (native strokes, HT Stroker, ...).
				layer_decomposed = layer.copyDecomposedLayer()
				layer_decomposed.parent = layer.parent
				applyPrepareLayerCallbacks(layer_decomposed)

				space = self.setSpace(layer_decomposed, self.reference_layer)
				if space:
					lp, rp = space
					del layer_decomposed
		except Exception:
			import traceback
			print(traceback.format_exc())

		self._lp, self._rp = lp, rp
		return lp, rp

	def calculate_polygons(self):
		"""Return (l_polygon, r_polygon) for the layer in the layer's drawing
		space, or None. No writes. Used by the areas reporter and the
		Parameters-tab preview.

		The polygons are computed de-slanted (for the area math); on an italic
		master we slant them back so they overlay the actual glyph.
		"""
		lp, rp = self._compute()
		if lp is None or rp is None:
			return None
		if self.angle:
			lp = self.slant(lp)
			rp = self.slant(rp)
		return lp, rp

	def current_layer_sidebearings(self):
		"""Return (newL, newR) for the layer, or None. No writes — the caller
		applies the values. For tabular glyphs, `self.newWidth` holds the
		adjusted advance width.
		"""
		lp, rp = self._compute()
		if lp is None or rp is None:
			return None
		return self.newL, self.newR


def _apply_engine(engine, layer):
	"""Write one engine's computed sidebearings (and tabular width). Returns
	(newL, newR) or None when the glyph was skipped. Does NOT syncMetrics —
	metric keys are synced after the whole batch (see space_layers), so that
	a glyph keyed to another in the selection resolves against final metrics."""
	sb = engine.current_layer_sidebearings()
	if sb is None:
		return None
	layer.LSB, layer.RSB = sb[0], sb[1]
	if engine.newWidth:
		layer.width = engine.newWidth
	return sb


# --- component-position preservation --------------------------------------
#
# When a glyph that is used as a component elsewhere is re-spaced, its outline
# shifts relative to the origin (its LSB changed). A composite that places that
# glyph as a *manually positioned* component would therefore visually move. To
# keep such composites looking identical, each referencing component is shifted
# back by the same amount (`left_diff = LSB_before - LSB_after`) — the Glyphs
# equivalent of the UFO "move the component to the opposite direction" trick.
#
# Two Glyphs-specific rules:
#   * **Auto-aligned components are skipped** — Glyphs repositions them itself,
#     so a manual shift is overwritten and only causes fighting. They already
#     stay consistent with their base.
#   * **Composites that are themselves being re-spaced are skipped** — they get
#     fresh sidebearings from the engine, so preserving their old position would
#     be pointless (and is what the topological ordering below handles instead).


def _is_manual_component(component):
	"""True for a component Glyphs does NOT auto-position (so a manual shift
	sticks). Auto-aligned components are managed by Glyphs and left alone."""
	try:
		return not bool(component.automaticAlignment)
	except Exception:
		return False


def _build_component_graph(font, master_ids):
	"""One pass over the font. Returns `(forward, reverse_manual)`:

	  * `forward[(glyph_name, master_id)]` = set of base glyph names that glyph
	    references via ANY component (used to order spacing: base before
	    composite);
	  * `reverse_manual[(base_name, master_id)]` = list of *manually positioned*
	    components (across the whole font) that reference that base (used to
	    shift them when the base is re-spaced).
	"""
	forward = {}
	reverse_manual = {}
	mids = set(master_ids)
	for glyph in font.glyphs:
		gname = glyph.name
		for mid in mids:
			layer = glyph.layers[mid]
			if layer is None:
				continue
			components = layer.components
			if not components:
				continue
			for component in components:
				base = component.componentName
				if not base:
					continue
				forward.setdefault((gname, mid), set()).add(base)
				if _is_manual_component(component):
					reverse_manual.setdefault((base, mid), []).append(component)
	return forward, reverse_manual


def _topo_order(layers, forward):
	"""Order the spaced `layers` so a glyph used as a component comes before the
	composite that uses it (within the spaced set, per master) — so a composite
	is measured with its bases already in their final positions. Kahn's
	algorithm; on a (degenerate) cycle the leftovers keep their input order."""
	key_of = {}
	for layer in layers:
		glyph = layer.parent
		if glyph is not None:
			key_of[(glyph.name, layer.associatedMasterId)] = layer
	spaced = set(key_of)

	indeg = {k: 0 for k in spaced}
	adj = {k: [] for k in spaced}
	for composite in spaced:
		name, mid = composite
		for base in forward.get(composite, ()):
			base_key = (base, mid)
			if base_key in spaced:
				adj[base_key].append(composite)
				indeg[composite] += 1

	queue = deque(sorted((k for k in spaced if indeg[k] == 0)))
	ordered = []
	while queue:
		k = queue.popleft()
		ordered.append(k)
		for nb in adj[k]:
			indeg[nb] -= 1
			if indeg[nb] == 0:
				queue.append(nb)
	if len(ordered) != len(spaced):
		ordered += [k for k in spaced if k not in set(ordered)]

	ordered_layers = [key_of[k] for k in ordered]
	# parentless layers (no glyph) carry no dependencies — append as-is.
	ordered_layers += [l for l in layers if l.parent is None]
	return ordered_layers


def _shift_components(reverse_manual, base_name, master_id, left_diff):
	"""Shift every manually positioned component that references `base_name`
	(on `master_id`) by `left_diff` in x — so its composite keeps position after
	the base's LSB changed — then re-sync each owning composite so any
	auto-aligned sibling (e.g. an accent) follows the shifted base.

	Called right after the base is spaced and BEFORE any composite that uses it,
	so a composite that is itself being spaced is measured with its components
	already repositioned. This is the in-order equivalent of spacing the base by
	hand, then the composite: doing it all at the end instead would space the
	composite while its base component was still in the wrong place.
	"""
	owners = []
	for component in reverse_manual.get((base_name, master_id), ()):
		try:
			pos = component.position
			component.position = NSMakePoint(pos.x + left_diff, pos.y)
			owner = component.parent
			if owner is not None:
				owners.append(owner)
		except Exception:
			pass
	for owner in owners:
		try:
			owner.syncMetrics()
		except Exception:
			pass


def space_layers(layers, font_rules=None, param_overrides=None, preserve_components=False):
	"""Space a selection efficiently and return `[(layer, engine, sidebearings)]`
	WITHOUT printing (per-layer prints are slow in Glyphs — the caller builds
	one report). Performance:

	  * **dedupes** by (glyph, master) — a glyph repeated in an edit view is the
	    same layer, so "HHHa" spaces H once, not three times;
	  * reads the font rules **once** (not per layer);
	  * wraps the writes in `disableUpdateInterface` so the UI redraws once.

	`preserve_components` keeps composites in place: when a glyph used as a
	component is re-spaced, every manually positioned component referencing it
	(font-wide) is shifted back so the composite does not move. Glyphs are
	ordered bases-first and the shift happens interleaved — right after a base is
	spaced and before any composite that uses it — so composites that are
	themselves in the batch are measured with their components already in place.
	"""
	seen = set()
	unique = []
	for layer in layers:
		glyph = layer.parent
		key = (glyph.name if glyph else id(layer), layer.associatedMasterId)
		if key in seen:
			continue
		seen.add(key)
		unique.append(layer)

	if not unique:
		return []

	font = unique[0].parent.parent if unique[0].parent else None

	if font_rules is None:
		font_rules = config.read_font_rules(font) if font is not None else {}

	# Component preservation: build the graph and order bases before composites.
	reverse_manual = None
	ordered = unique
	if preserve_components and font is not None:
		master_ids = {l.associatedMasterId for l in unique}
		forward, reverse_manual = _build_component_graph(font, master_ids)
		ordered = _topo_order(unique, forward)

	results = []
	if font is not None:
		font.disableUpdateInterface()
	try:
		if preserve_components and reverse_manual is not None:
			# Bases first, interleaved: space a glyph, then shift the components
			# that reference it BEFORE the composites using it are reached.
			for layer in ordered:
				glyph = layer.parent
				master_id = layer.associatedMasterId
				# Refresh this glyph's own (auto-aligned) components from bases
				# already spaced earlier, so it is measured up to date.
				try:
					layer.syncMetrics()
				except Exception:
					pass
				lsb_before = layer.LSB
				engine = HTLSEngine(layer, font_rules=font_rules, param_overrides=param_overrides)
				sb = _apply_engine(engine, layer)
				results.append((layer, engine, sb))
				if sb is None or glyph is None:
					continue
				# Finalize this glyph's own metric keys before measuring its
				# shift, then shift the components that reference it.
				try:
					layer.syncMetrics()
				except Exception:
					pass
				left_diff = lsb_before - layer.LSB
				if left_diff:
					_shift_components(reverse_manual, glyph.name, master_id, left_diff)
			# Final sweep: resolve metric keys that cross the batch (e.g. a glyph
			# keyed to another spaced glyph) against the now-final metrics.
			for layer in ordered:
				try:
					layer.syncMetrics()
				except Exception:
					pass
		else:
			for layer in ordered:
				engine = HTLSEngine(layer, font_rules=font_rules, param_overrides=param_overrides)
				results.append((layer, engine, _apply_engine(engine, layer)))
			# Sync metric keys only AFTER every glyph is spaced, so a glyph keyed
			# to another in the selection (e.g. "e" keyed to "o") resolves against
			# the final metrics rather than a stale value.
			for layer in ordered:
				layer.syncMetrics()
	finally:
		if font is not None:
			font.enableUpdateInterface()

	# Repaint the edit view: metric changes don't refresh until forced
	# (Glyphs.redraw() alone isn't enough — the original script forceRedraw'd).
	try:
		if font is not None and font.currentTab:
			font.currentTab.forceRedraw()
	except Exception:
		pass

	return results


def space_layer(layer, font_rules=None):
	"""Space a single layer; returns (newL, newR) or None. For many layers use
	`space_layers` (it reads the rules once, dedupes, and batches metric sync)."""
	sb = _apply_engine(HTLSEngine(layer, font_rules=font_rules), layer)
	layer.syncMetrics()
	return sb
