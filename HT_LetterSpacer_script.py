#
# HT Letterspacer, an auto-spacing tool
# Copyright (C) 2009 - 2018, The HT Letterspacer Project Authors
# Version 1.11
from __future__ import division, print_function, unicode_literals

# Default parameters
paramArea = 400  # white area in thousand units
paramDepth = 15  # depth in open counterforms, from extreme points.
paramOver = 0  # overshoot in spacing vertical range
color = False  # mark color, False for no mark
paramFreq = 5  # frequency of vertical measuring. Higher values are faster but less accurate
drawAreas = False  # False if to avoid the creation of _areas glyph

# program dependencies
import GlyphsApp
import math
import os
import objc
from Foundation import NSMinX, NSMaxX, NSMinY, NSMaxY, NSMakePoint
from objectsGS import GSLINE
import vanilla
from vanilla import dialogs

DEFAULT_CONFIG_FILE = \
	"""
# Reference
# Script, Category, Subcategory, case, value, referenceGlyph, filter

# Letters
*,Letter,*,upper,1.25,H,*,
*,Letter,*,smallCaps,1.1,h.sc,*,
*,Letter,*,lower,1,x,*,
*,Letter,*,minor,0.7,m.sups,.sups,

# Numbers
*,Number,Decimal Digit,*,1.2,one,*,
*,Number,Decimal Digit,*,1.2,zero.osf,.osf,
*,Number,Fraction,minor,1.3,*,*,
*,Number,*,*,0.8,*,.dnom,
*,Number,*,*,0.8,*,.numr,
*,Number,*,*,0.8,*,.inferior,
*,Number,*,*,0.8,*,superior,

# Punctuation
*,Punctuation,Other,*,1.4,*,*,
*,Punctuation,Parenthesis,*,1.2,*,*,
*,Punctuation,Quote,*,1.2,*,*,
*,Punctuation,Dash,*,1,*,*,
*,Punctuation,*,*,1,*,slash,
*,Punctuation,*,*,1.2,*,*,

# Symbols
*,Symbol,Currency,*,1.6,*,*,
*,Symbol,*,*,1.5,*,*,
*,Mark,*,*,1,*,*,

# Devanagari
devanagari,Letter,Other,*,1,devaHeight,*,
devanagari,Letter,Ligature,*,1,devaHeight,*,
"""

COPY_PARAMETERS_GLYPHS2 = """(
    {
        paramArea = %i;
    },
    {
        paramDepth = %i;
    },
    {
        paramOver = %i;
    }
)"""

COPY_PARAMETERS_GLYPHS3 = """{
    customParameters = (
        {
            name = paramArea;
            value = %i;
        },
        {
            name = paramDepth;
            value = %i;
        },
        {
            name = paramOver;
            value = %i;
        }
    );
}"""


#  Functions
def set_sidebearings(layer, new_l, new_r, width, color):
	layer.LSB = new_l
	layer.RSB = new_r

	# adjusts the tabular miscalculation
	if width:
		layer.width = width

	if color:
		layer.parent.color = color


# point list area
def area(points):
	s = 0
	for ii in range(-1, len(points) - 1):
		s = s + (points[ii].x * points[ii + 1].y - points[ii + 1].x * points[ii].y)
	return abs(s) * 0.5


# get margins in Glyphs
def get_margins(layer, y):
	start_point = NSMakePoint(NSMinX(layer.bounds) - 1, y)
	end_point = NSMakePoint(NSMaxX(layer.bounds) + 1, y)

	result = layer.calculateIntersectionsStartPoint_endPoint_(start_point, end_point)
	count = len(result)
	if count <= 2:
		return None, None

	left = 1
	right = count - 2
	return result[left].pointValue().x, result[right].pointValue().x


def triangle(angle, y):
	angle = math.radians(angle)
	result = y * (math.tan(angle))
	# result = round(result)
	return result


def total_margin_list(layer, min_y, max_y, angle, min_y_ref, max_y_ref):
	# totalMarginList(layer,minY,maxY,angle,minYref,maxYref)
	# the list of margins
	y = min_y
	list_l = []
	list_r = []

	# calculate default depth, otherwise measurement is None
	# calculate paralelogram extremes
	origin = NSMinX(layer.bounds)
	endpointx = NSMaxX(layer.bounds)
	endpointy = NSMaxY(layer.bounds)

	# calculate paralelogram top left
	xpos = triangle(angle, endpointy) + origin
	# paralelogram top side width
	slant_width = (endpointx - xpos)
	# default depth
	dflt_depth = slant_width

	# result will be false if all the measured margins are emtpy (no outlines in reference zone)
	result = False

	while y <= max_y:
		lpos, rpos = get_margins(layer, y)

		# get the default margin measure at a given y position
		slant_pos_l = origin + triangle(angle, y) + dflt_depth
		slant_pos_r = origin + triangle(angle, y)

		if lpos is not None:
			list_l.append(NSMakePoint(lpos, y))
			if min_y_ref <= y <= max_y_ref:
				result = True
		else:
			list_l.append(NSMakePoint(slant_pos_l, y))

		if rpos is not None:
			list_r.append(NSMakePoint(rpos, y))
			if min_y_ref <= y <= max_y_ref:
				result = True
		else:
			list_r.append(NSMakePoint(slant_pos_r, y))

		y += paramFreq

	# if no measurements are taken, returns false and will abort in main function
	if result:
		return list_l, list_r
	else:
		return False, False


def zone_margins(l_margins, r_margins, min_y, max_y):
	# filter those outside the range
	points_filtered_l = [x for x in l_margins if min_y <= x.y <= max_y]
	points_filtered_r = [x for x in r_margins if min_y <= x.y <= max_y]

	return points_filtered_l, points_filtered_r


# get appropriate config file path
def get_config_path(directory, glyphsfile, mastername):
	masterconffile = glyphsfile.split('.')[0] + "_" + mastername + "_autospace.py"
	masterconfpath = os.path.join(directory, masterconffile)

	if os.path.isfile(masterconfpath):
		return masterconfpath

	globalconffile = glyphsfile.split('.')[0] + "_autospace.py"

	return os.path.join(directory, globalconffile)


def read_config(mastername):
	GlyphsApp.Glyphs.clearLog()
	filepath = GlyphsApp.Glyphs.font.filepath
	if filepath is None:
		GlyphsApp.Message("Or I'm lost :(", "Please save the file first.", OKButton="OK")
		return None
	directory, glyphsfile = os.path.split(filepath)
	confpath = get_config_path(directory, glyphsfile, mastername)
	array = []

	if os.path.isfile(confpath):
		print("Config file exists\n")
	else:
		create_file_prompt = dialogs.askYesNo(
			messageText='\nMissing config file for this font.',
			informativeText='want to create one?')
		if create_file_prompt == 1:
			new_file = open(confpath, 'w')
			new_file.write(DEFAULT_CONFIG_FILE)
			new_file.close()
		elif create_file_prompt == 0 or create_file_prompt == -1:
			GlyphsApp.Message("Error :(", "HT Letterspacer can't work without a config file", OKButton="OK")
			return None

	with open(confpath) as f:
		for line in f:
			if line[0] != '#' and len(line) > 5:
				newline = line.split(",")
				del newline[-1]
				newline[4] = float(newline[4])
				array.append(newline)
	return array


def width_avg(selection):
	width = 0
	for g in selection:
		width += g.width
	width = width / len(selection)
	width = int(round(width, 0))
	return width


class HTLetterspacerLib(object):

	def __init__(self):
		self.paramArea = paramArea
		self.paramDepth = paramDepth
		self.paramOver = paramOver
		self.tabVersion = False
		self.width = None

	def create_areas_glyph(self, font, layer, margins):
		layer_id = layer.layerId

		# try to create glyph
		if '_areas' not in font.glyphs:
			try:
				font.glyphs.append(GlyphsApp.GSGlyph('_areas'))
			except Exception:
				import traceback
				print(traceback.format_exc())

		destination = font.glyphs['_areas'].layers[layer_id]
		destination.parent.export = False

		# Delete all paths in destination
		destination.clear()

		# Set width and draw

		destination.width = layer.width
		destination.paths.append(self.shape(margins[0]))
		destination.paths.append(self.shape(margins[1]))
		destination.LSB = 0
		destination.RSB = 0

	def shape(self, points):
		shape = GlyphsApp.GSPath()
		for xy in points:
			newnode = GlyphsApp.GSNode()
			newnode.type = GSLINE
			newnode.position = (xy[0], xy[1])
			shape.nodes.append(newnode)
		shape.closed = True

		return shape

	def overshoot(self):
		return self.xHeight * self.paramOver / 100

	def max_points(self, points, min_y, max_y):
		# this function returns the extremes for a given set of points in a given zone

		# filter those outside the range
		# pointsFilteredL = [ x for x in points[0] if x.y>=minY and x.y<=maxY]
		# pointsFilteredR = [ x for x in points[0] if x.y>=minY and x.y<=maxY]

		# sort all given points by x
		sort_points_by_xl = sorted(points[0], key=lambda tup: tup[0])
		sort_points_by_xr = sorted(points[1], key=lambda tup: tup[0])

		# get the extremes position, first and last in the list
		left, lefty = sort_points_by_xl[0]
		right, righty = sort_points_by_xr[-1]

		return NSMakePoint(left, lefty), NSMakePoint(right, righty)

	def process_margins(self, l_margin, r_margin, l_extreme, r_extreme):
		# set depth
		l_margin, r_margin = self.set_depth(l_margin, r_margin, l_extreme, r_extreme)

		# close open counterforms at 45 degrees
		l_margin, r_margin = self.diagonize(l_margin, r_margin)
		l_margin = self.close_open_counters(l_margin, l_extreme)
		r_margin = self.close_open_counters(r_margin, r_extreme)

		return l_margin, r_margin

	# process lists with depth, proportional to xheight
	def set_depth(self, margins_l, margins_r, l_extreme, r_extreme):
		depth = self.xHeight * self.paramDepth / 100
		maxdepth = l_extreme.x + depth
		mindepth = r_extreme.x - depth
		margins_l = [NSMakePoint(min(p.x, maxdepth), p.y) for p in margins_l]
		margins_r = [NSMakePoint(max(p.x, mindepth), p.y) for p in margins_r]

		# add all the points at maximum depth if glyph is shorter than overshoot
		y = margins_l[0].y - paramFreq
		while y > self.minYref:
			margins_l.insert(0, NSMakePoint(maxdepth, y))
			margins_r.insert(0, NSMakePoint(mindepth, y))
			y -= paramFreq

		y = margins_l[-1].y + paramFreq
		while y < self.maxYref:
			margins_l.append(NSMakePoint(maxdepth, y))
			margins_r.append(NSMakePoint(mindepth, y))
			y += paramFreq

		# if marginsL[-1].y<(self.maxYref-paramFreq):
		# 	marginsL.append(NSMakePoint(min(p.x, maxdepth), self.maxYref))
		# 	marginsR.append(NSMakePoint(max(p.x, mindepth), self.maxYref))
		# if marginsL[0].y>(self.minYref):
		# 	marginsL.insert(0,NSMakePoint(min(p.x, maxdepth), self.minYref))
		# 	marginsR.insert(0,NSMakePoint(max(p.x, mindepth), self.minYref))

		return margins_l, margins_r

	# close counters at 45 degrees
	def diagonize(self, margins_l, margins_r):
		ystep = abs(margins_l[0].y - margins_l[1].y)
		for i in range(len(margins_l) - 1):
			if margins_l[i + 1].x - margins_l[i].x > ystep:
				margins_l[i + 1].x = margins_l[i].x + ystep
			if margins_r[i + 1].x - margins_r[i].x < -ystep:
				margins_r[i + 1].x = margins_r[i].x - ystep

		for i in reversed(range(len(margins_l) - 1)):
			if margins_l[i].x - margins_l[i + 1].x > ystep:
				margins_l[i].x = margins_l[i + 1].x + ystep
			if margins_r[i].x - margins_r[i + 1].x < -ystep:
				margins_r[i].x = margins_r[i + 1].x - ystep

		return margins_l, margins_r

	# close counterforms, creating a polygon
	def close_open_counters(self, margin, extreme):
		init_point = NSMakePoint(extreme.x, self.minYref)
		end_point = NSMakePoint(extreme.x, self.maxYref)
		margin.insert(0, init_point)
		margin.append(end_point)
		return margin

	def deslant(self, margin):
		"""De-slant a list of points (contour) at angle with the point of origin
		at half the xheight."""
		mline = self.xHeight / 2
		return [
			NSMakePoint(p.x - (p.y - mline) * math.tan(math.radians(self.angle)), p.y)
			for p in margin
		]

	def calculate_sb_value(self, polygon):
		amplitude_y = self.maxYref - self.minYref

		# recalculates area based on UPM
		area_upm = self.paramArea * ((self.upm / 1000) ** 2)
		# calculates proportional area
		white_area = area_upm * self.factor * 100

		prop_area = (amplitude_y * white_area) / self.xHeight

		valor = prop_area - area(polygon)
		return valor / amplitude_y

	def set_space(self, layer, reference_layer):
		# get reference glyph maximum points
		overshoot = self.overshoot()

		# store min and max y
		self.minYref = NSMinY(reference_layer.bounds) - overshoot
		self.maxYref = NSMaxY(reference_layer.bounds) + overshoot

		self.minY = NSMinY(layer.bounds)
		self.maxY = NSMaxY(layer.bounds)

		self.output += "Glyph: " + str(layer.parent.name) + "\n"
		self.output += "Reference layer: " + reference_layer.parent.name + " | Factor: " + str(self.factor) + "\n"

		# get the margins for the full outline
		# will take measure from minY to maxY. minYref and maxYref are passed to check reference match
		# totalMarginList(layer,minY,maxY,angle,minYref,maxYref)
		l_total_margins, r_total_margins = total_margin_list(layer, self.minY, self.maxY, self.angle, self.minYref,
		                                                     self.maxYref)

		# margins will be False, False if there is no measure in the reference zone, and then function stops
		if not l_total_margins and not r_total_margins:
			self.output += 'The glyph outlines are outside the reference layer zone/height. No match with ' \
			               + reference_layer.parent.name + "\n"
			return

		# filtes all the margins to the reference zone
		l_zone_margins, r_zone_margins = zone_margins(l_total_margins, r_total_margins, self.minYref, self.maxYref)

		# if the font has an angle, we need to deslant
		if self.angle:
			self.output += "Using angle: " + str(self.angle) + "\n"
			l_zone_margins = self.deslant(l_zone_margins)
			r_zone_margins = self.deslant(r_zone_margins)

			l_total_margins = self.deslant(l_total_margins)
			r_total_margins = self.deslant(r_total_margins)

		# full shape extreme points
		l_full_extreme, r_full_extreme = self.max_points([l_total_margins, r_total_margins], self.minY, self.maxY)
		# get zone extreme points
		l_extreme, r_extreme = self.max_points([l_zone_margins, r_zone_margins], self.minYref, self.maxYref)

		# create a closed polygon
		l_polygon, r_polygon = self.process_margins(l_zone_margins, r_zone_margins, l_extreme, r_extreme)

		# return

		# dif between extremes full and zone
		distance_l = math.ceil(l_extreme.x - l_full_extreme.x)
		distance_r = math.ceil(r_full_extreme.x - r_extreme.x)

		# set new sidebearings
		self.newL = math.ceil(0 - distance_l + self.calculate_sb_value(l_polygon))
		self.newR = math.ceil(0 - distance_r + self.calculate_sb_value(r_polygon))

		# tabVersion
		if '.tosf' in layer.parent.name or '.tf' in layer.parent.name or self.tabVersion:
			if self.width:
				self.layerWidth = self.width
			else:
				self.layerWidth = layer.width

			width_shape = r_full_extreme.x - l_full_extreme.x
			width_actual = width_shape + self.newL + self.newR
			width_diff = (self.layerWidth - width_actual) / 2

			self.newL += width_diff
			self.newR += width_diff
			self.newWidth = self.layerWidth

			self.output += layer.parent.name + ' is tabular and adjusted at width = ' + str(self.layerWidth)
		# end tabVersion

		# if there is a metric rule
		else:
			if layer.parent.leftMetricsKey is not None or self.LSB is False:
				self.newL = layer.LSB

			if layer.parent.rightMetricsKey is not None or self.RSB is False:
				self.newR = layer.RSB
		return l_polygon, r_polygon

	def space_main(self, layer, reference_layer):
		lp, rp = None, None
		try:
			self.output = ""
			if not layer.name:
				self.output += 'Something went wrong!'
			elif len(layer.paths) < 1 and len(layer.components) < 1:
				self.output += 'No paths in glyph ' + layer.parent.name + "\n"
			# both sidebearings with metric keys
			elif layer.hasAlignedWidth():
				self.output += 'Glyph ' + layer.parent.name + ' has automatic alignment. Spacing not set.\n'
			elif layer.parent.leftMetricsKey is not None and layer.parent.rightMetricsKey is not None:
				self.output += 'Glyph ' + layer.parent.name + " has metric keys. Spacing not set.\n"
			# if it is tabular
			# elif '.tosf' in layer.parent.name or '.tf' in layer.parent.name:
			# self.output+='Glyph '+layer.parent.name +' se supone tabular..'+"\n"
			# if it is fraction / silly condition
			elif 'fraction' in layer.parent.name:
				self.output += 'Glyph ' + layer.parent.name + ': should be checked and done manually.\n'
			# if not...
			else:
				# Decompose layer for analysis, as the deeper plumbing assumes to be looking at outlines.
				layer_decomposed = layer.copyDecomposedLayer()
				layer_decomposed.parent = layer.parent

				# run the spacing
				space = self.set_space(layer_decomposed, reference_layer)

				# if it worked
				if space:
					lp, rp = space
					del layer_decomposed
					# store values in a list
					set_sidebearings(layer, self.newL, self.newR, self.newWidth, color)

			print(self.output)
			self.output = ''
		# traceback
		except Exception:
			import traceback
			print(traceback.format_exc())
		return lp, rp


class HTLetterspacerScript(object):

	def __init__(self, ui, all_masters):

		self.engine = HTLetterspacerLib()

		self.font = GlyphsApp.Glyphs.font

		self.allMasters = all_masters

		for master in GlyphsApp.Glyphs.font.masters:
			if self.allMasters is False and self.font.selectedFontMaster is not master:
				continue

			selected_layers = [layer.parent.layers[master.id] for layer in
			                   GlyphsApp.Glyphs.font.selectedLayers if layer.isSpecialLayer is False]
			self.ui = ui

			if selected_layers is None or len(selected_layers) < 1:
				GlyphsApp.Message("Error :(", "Nothing selected", OKButton="OK")
				return
			self.mySelection = list(set(selected_layers))

			self.output = ''
			self.layerID = self.mySelection[0].associatedMasterId
			self.master = master
			self.config = read_config(self.master.name)

			self.engine.upm = self.font.upm
			self.engine.angle = self.master.italicAngle
			self.engine.xHeight = self.master.xHeight

			if self.config:
				self.get_params()

				self.engine.tabVersion = False
				self.engine.LSB = True
				self.engine.RSB = True

				if self.ui:
					self.window()
				else:
					self.space_main()

	def get_params(self):
		for param in ["paramArea", "paramDepth", "paramOver"]:
			custom_param = self.master.customParameters[param]
			if custom_param:
				setattr(self.engine, param, float(custom_param))
				self.output += 'Using master custom parameter, %s: %s\n' % (param, float(custom_param))
			else:
				self.output += 'Using default parameter %s: %i\n' % (param, getattr(self.engine, param))

	def window(self):
		self.w = vanilla.FloatingWindow((250, 189), "HT Letterspacer", minSize=(250, 180), maxSize=(250, 180),
		                                autosaveName="com.ht.spacer")
		self.w.text_3 = vanilla.TextBox((210, 25, -170, 14), "%", sizeStyle='small')
		self.w.text_4 = vanilla.TextBox((15, 50, 100, 14), "Area", sizeStyle='small')
		self.w.text_4b = vanilla.TextBox((120, 50, 50, 14), self.engine.paramArea, sizeStyle='small')
		self.w.text_5 = vanilla.TextBox((15, 75, 100, 14), "Depth", sizeStyle='small')
		self.w.text_5b = vanilla.TextBox((120, 75, 50, 14), self.engine.paramDepth, sizeStyle='small')
		self.w.text_6 = vanilla.TextBox((15, 100, 100, 14), "Overshoot", sizeStyle='small')
		self.w.text_6b = vanilla.TextBox((120, 100, 50, 14), self.engine.paramOver, sizeStyle='small')
		self.w.LSB = vanilla.CheckBox((15, 15, 40, 18), "LSB", value=True, sizeStyle='small',
		                              callback=self.save_preferences)
		self.w.RSB = vanilla.CheckBox((15 + 45, 15, 40, 18), "RSB", value=True, sizeStyle='small',
		                              callback=self.save_preferences)
		self.w.tab = vanilla.CheckBox((15 + 45 + 45, 15, 60, 18), "Tabular", value=False, sizeStyle='small',
		                              callback=self.save_preferences)
		self.w.width = vanilla.EditText((170, 15, 40, 18), width_avg(self.mySelection), sizeStyle='small')
		self.w.area = vanilla.EditText((170, 50 - 3, 40, 18), "430", sizeStyle='small')
		self.w.prof = vanilla.EditText((170, 75 - 3, 40, 18), "20", sizeStyle='small')
		self.w.ex = vanilla.EditText((170, 100 - 3, 40, 18), "0", sizeStyle='small')
		# self.w.allMasters = vanilla.CheckBox((15, 125, -10, 18), "Apply to all Masters", value=self.allMasters,
		# sizeStyle="small", callback=self.selectAllMasters)

		self.w.copyButton = vanilla.Button((15, 150, -90, 30), "Copy Parameters", sizeStyle='small',
		                                   callback=self.copy_parameters)
		self.w.runButton = vanilla.Button((-80, 150, -15, 30), "Apply", sizeStyle='small',
		                                  callback=self.dialog_callback)

		self.w.setDefaultButton(self.w.runButton)

		if not self.load_preferences():
			GlyphsApp.Message("Error :(", "Could not load preferences. Will resort to defaults.", OKButton="OK")

		self.w.open()
		self.w.makeKey()

	# def selectAllMasters(self, sender):
	# 	self.allMasters = sender.get()

	def dialog_callback(self, sender):
		self.output = ""
		self.engine.paramArea = float(self.w.area.get())
		self.engine.paramDepth = float(self.w.prof.get())
		self.engine.paramOver = float(self.w.ex.get())
		self.engine.tabVersion = self.w.tab.get()
		self.engine.LSB = self.w.LSB.get()
		self.engine.RSB = self.w.RSB.get()
		if bool(self.engine.tabVersion) is True:
			self.engine.width = int(self.w.width.get())
		else:
			self.engine.width = None
		self.mySelection = list(set(GlyphsApp.Glyphs.font.selectedLayers))
		self.space_main()

		if not self.save_preferences(self):
			GlyphsApp.Message("Note", "Couldn't save preferences.", OKButton="OK")

	def save_preferences(self, sender):
		try:
			GlyphsApp.Glyphs.defaults["com.ht.spacer.LSB"] = self.w.LSB.get()
			GlyphsApp.Glyphs.defaults["com.ht.spacer.RSB"] = self.w.RSB.get()
			GlyphsApp.Glyphs.defaults["com.ht.spacer.tab"] = self.w.tab.get()
			# GlyphsApp.Glyphs.defaults["com.ht.spacer.width"] = self.w.width.get()
			GlyphsApp.Glyphs.defaults["com.ht.spacer.area"] = self.w.area.get()
			GlyphsApp.Glyphs.defaults["com.ht.spacer.depth"] = self.w.prof.get()
			GlyphsApp.Glyphs.defaults["com.ht.spacer.over"] = self.w.ex.get()
		except:
			import traceback
			print(traceback.format_exc())
			return False

		return True

	def load_preferences(self):
		try:
			self.w.LSB.set(GlyphsApp.Glyphs.defaults["com.ht.spacer.LSB"])
			self.w.RSB.set(GlyphsApp.Glyphs.defaults["com.ht.spacer.RSB"])
			self.w.tab.set(GlyphsApp.Glyphs.defaults["com.ht.spacer.tab"])
			# self.w.width.set(GlyphsApp.Glyphs.defaults["com.ht.spacer.width"])
			self.w.area.set(GlyphsApp.Glyphs.defaults["com.ht.spacer.area"])
			self.w.prof.set(GlyphsApp.Glyphs.defaults["com.ht.spacer.depth"])
			self.w.ex.set(GlyphsApp.Glyphs.defaults["com.ht.spacer.over"])
		except:
			import traceback
			print(traceback.format_exc())
			return False

		return True

	def find_exception(self):
		exception = False
		for item in self.config:
			if self.script == item[0] or item[0] == '*':
				if self.category == item[1] or item[1] == '*':
					if self.subCategory == item[2] or item[2] == '*':
						if self.case == item[3] or item[3] == '*':
							if not exception or item[6] in self.glyph.name:
								exception = item
		return exception

	def set_g(self, layer):
		if layer.isKindOfClass_(objc.lookUpClass("GSControlLayer")):
			return
		self.output = '\\' + layer.parent.name + '\\\n' + self.output

		self.layerID = layer.associatedMasterId
		self.glyph = layer.parent
		self.category = self.glyph.category
		self.subCategory = self.glyph.subCategory
		self.case = GlyphsApp.GSGlyphInfo.stringFromCase_(self.glyph.case)
		self.script = self.glyph.script
		self.engine.reference = self.glyph.name
		self.engine.factor = 1.0

		exception = self.find_exception()
		if exception:
			self.engine.factor = exception[4]
			item = exception[5]
			if item != '*':
				self.engine.reference = item
		self.engine.newWidth = False

		# check reference layer existance and contours
		if self.font.glyphs[self.engine.reference]:
			self.referenceLayer = self.font.glyphs[self.engine.reference].layers[self.layerID]
			if len(self.referenceLayer.paths) < 1 and len(self.referenceLayer.components) < 1:
				self.output += \
					"WARNING: The reference glyph declared (" + self.engine.reference \
					+ ") doesn't have contours. Glyph " + self.glyph.name \
					+ " was spaced based on its own vertical range.\n"
				self.referenceLayer = layer
		else:
			self.referenceLayer = layer
			self.output += \
				"WARNING: The reference glyph declared (" + self.engine.reference \
				+ ") doesn't exist. Glyph " + self.glyph.name + " was spaced based on its own vertical range.\n"

	def space_main(self):
		for layer in self.mySelection:
			self.set_g(layer)
			lpolygon, rpolygon = self.engine.space_main(layer, self.referenceLayer)
		print(self.output)
		if len(self.mySelection) < 2 and drawAreas is True and lpolygon is not None:
			self.engine.create_areas_glyph(self.font, self.mySelection[0], [lpolygon, rpolygon])
		if self.font.currentTab:
			self.font.currentTab.forceRedraw()

	def set_clipboard(self, my_text):
		"""
		Sets the contents of the clipboard to myText.
		Returns True if successful, False if unsuccessful.
		"""
		from AppKit import NSPasteboard, NSStringPboardType
		try:
			my_clipboard = NSPasteboard.generalPasteboard()
			my_clipboard.declareTypes_owner_([NSStringPboardType], None)
			my_clipboard.setString_forType_(my_text, NSStringPboardType)
			return True
		except Exception as e:
			import traceback
			print(traceback.format_exc())
			print(e)
			return False

	def copy_parameters(self, sender):
		"""Copy the custom parameters to the clipboard"""
		area = float(self.w.area.get())
		depth = float(self.w.prof.get())
		over = float(self.w.ex.get())
		if GlyphsApp.Glyphs.versionNumber < 3.0:
			copy_text = COPY_PARAMETERS_GLYPHS2 % (area, depth, over)
		else:
			copy_text = COPY_PARAMETERS_GLYPHS3 % (area, depth, over)
		if not self.set_clipboard(copy_text):
			GlyphsApp.Message("Clipboard Error",
			                  "An error occurred: Could not copy the values into the clipboard."
			                  "Please check Macro Window for details.", OKButton=None)
