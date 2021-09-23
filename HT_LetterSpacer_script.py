#
# HT Letterspacer, an auto-spacing tool
# Copyright (C) 2009 - 2018, The HT Letterspacer Project Authors
# Version 1.11
from __future__ import division, print_function, unicode_literals

# Default parameters
paramArea = 400  # white area in thousand units
paramDepth = 15  # depth in open counterforms, from extreme points.
paramOver = 0    # overshoot in spacing vertical range
color = False 	 # mark color, False for no mark
paramFreq = 5    # frequency of vertical measuring. Higher values are faster but less accurate
drawAreas = False # False if to avoid the creation of _areas glyph

# program dependencies
import GlyphsApp
import math
import os
import objc
from Foundation import NSMinX, NSMaxX, NSMinY, NSMaxY, NSMakePoint
from objectsGS import GSLINE
import vanilla
from vanilla import dialogs

DEFAULT_CONFIG_FILE =\
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
            name = paramOver;
            value = %i;
        },
        {
            name = paramDepth;
            value = %i;
        },
        {
            name = paramArea;
            value = %i;
        }
    );
}"""

#  Functions
def setSidebearings(layer, newL, newR, width, color):
	layer.LSB = newL
	layer.RSB = newR

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
def getMargins(layer, y):
	startPoint = NSMakePoint(NSMinX(layer.bounds) - 1, y)
	endPoint = NSMakePoint(NSMaxX(layer.bounds) + 1, y)

	result = layer.calculateIntersectionsStartPoint_endPoint_(startPoint, endPoint)
	count = len(result)
	if (count <= 2):
		return (None, None)

	left = 1
	right = count - 2
	return (result[left].pointValue().x, result[right].pointValue().x)

def triangle(angle, y):
	angle = math.radians(angle)
	result = y * (math.tan(angle))
	#result = round(result)
	return result

def totalMarginList(layer,minY,maxY,angle,minYref,maxYref):
# totalMarginList(layer,minY,maxY,angle,minYref,maxYref)
	#the list of margins
	y = minY
	listL = []
	listR = []

	#calculate default depth, otherwise measurement is None
	#calculate paralelogram extremes
	origin=NSMinX(layer.bounds)
	endpointx=NSMaxX(layer.bounds)
	endpointy=NSMaxY(layer.bounds)

	#calculate paralelogram top left
	xpos=triangle(angle,endpointy)+origin
	#paralelogram top side width
	slantWidth=(endpointx-xpos)
	#default depth
	dfltDepth=slantWidth

	#result will be false if all the measured margins are emtpy (no outlines in reference zone)
	result=False

	while y <= maxY:
		lpos, rpos = getMargins(layer, y)

		#get the default margin measure at a given y position
		slantPosL=origin+triangle(angle,y)+dfltDepth
		slantPosR=origin+triangle(angle,y)

		if lpos is not None:
			listL.append(NSMakePoint(lpos, y))
			if minYref<=y<=maxYref:
				result=True
		else:
			listL.append(NSMakePoint(slantPosL, y))

		if rpos is not None:
			listR.append(NSMakePoint(rpos, y))
			if minYref<=y<=maxYref:
				result=True
		else:
			listR.append(NSMakePoint(slantPosR, y))

		y += paramFreq

	#if no measurements are taken, returns false and will abort in main function
	if result:
		return listL, listR
	else:
		return False,False


def zoneMargins(lMargins,rMargins,minY,maxY):
	#filter those outside the range
	pointsFilteredL = [ x for x in lMargins if x.y>=minY and x.y<=maxY]
	pointsFilteredR = [ x for x in rMargins if x.y>=minY and x.y<=maxY]

	return pointsFilteredL,pointsFilteredR

# get appropriate config file path
def getConfigPath(directory, glyphsfile, mastername):
	masterconffile = glyphsfile.split('.')[0] + "_" + mastername + "_autospace.py"
	masterconfpath = os.path.join(directory, masterconffile)

	if os.path.isfile(masterconfpath) == True:
		return masterconfpath

	globalconffile = glyphsfile.split('.')[0] + "_autospace.py"

	return os.path.join(directory, globalconffile)


def readConfig(mastername):
	GlyphsApp.Glyphs.clearLog()
	filepath = GlyphsApp.Glyphs.font.filepath
	if filepath is None:
		GlyphsApp.Message("Or I'm lost :(", "Please save the file first.", OKButton="OK")
		return None
	directory, glyphsfile = os.path.split(filepath)
	confpath = getConfigPath(directory, glyphsfile, mastername)
	array = []

	if os.path.isfile(confpath) == True:
		print("Config file exists\n")
	else :
		createFilePrompt = dialogs.askYesNo(\
			messageText='\nMissing config file for this font.',\
			informativeText='want to create one?')
		if createFilePrompt == 1:
			newFile = open(confpath,'w')
			newFile.write(DEFAULT_CONFIG_FILE)
			newFile.close()
		elif createFilePrompt == 0 or createFilePrompt == -1:
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

def widthAvg(selection):
	width = 0
	for g in selection:
		width+=g.width
	width = width/len(selection)
	width = int(round(width, 0))
	return width


class HTLetterspacerLib(object):

	def __init__(self):
		self.paramArea = paramArea
		self.paramDepth = paramDepth
		self.paramOver = paramOver
		self.tabVersion = False
		self.width = None

	def createAreasGlyph(self, font, layer, margins):
		layerId = layer.layerId

		# try to create glyph
		if '_areas' not in font.glyphs:
			try:
				font.glyphs.append(GlyphsApp.GSGlyph('_areas'))
			except Exception:
				import traceback
				print(traceback.format_exc())

		destination = font.glyphs['_areas'].layers[layerId]
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
			shape.nodes.append( newnode )
		shape.closed = True

		return shape


	def overshoot(self):
		return self.xHeight * self.paramOver / 100

	def maxPoints(self, points, minY, maxY):
		#this function returns the extremes for a given set of points in a given zone

		#filter those outside the range
		# pointsFilteredL = [ x for x in points[0] if x.y>=minY and x.y<=maxY]
		# pointsFilteredR = [ x for x in points[0] if x.y>=minY and x.y<=maxY]

		#sort all given points by x
		sortPointsByXL = sorted(points[0], key=lambda tup: tup[0])
		sortPointsByXR = sorted(points[1], key=lambda tup: tup[0])


		#get the extremes position, first and last in the list
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

	# process lists with depth, proportional to xheight
	def setDepth(self, marginsL, marginsR, lExtreme, rExtreme):
		depth = self.xHeight * self.paramDepth / 100
		maxdepth = lExtreme.x + depth
		mindepth = rExtreme.x - depth
		marginsL = [NSMakePoint(min(p.x, maxdepth), p.y) for p in marginsL]
		marginsR = [NSMakePoint(max(p.x, mindepth), p.y) for p in marginsR]

		#add all the points at maximum depth if glyph is shorter than overshoot
		y=marginsL[0].y-paramFreq
		while y>self.minYref:
			marginsL.insert(0,NSMakePoint(maxdepth, y))
			marginsR.insert(0,NSMakePoint(mindepth, y))
			y-=paramFreq

		y=marginsL[-1].y+paramFreq
		while y<self.maxYref:
			marginsL.append(NSMakePoint(maxdepth, y))
			marginsR.append(NSMakePoint(mindepth, y))
			y+=paramFreq

		# if marginsL[-1].y<(self.maxYref-paramFreq):
		# 	marginsL.append(NSMakePoint(min(p.x, maxdepth), self.maxYref))
		# 	marginsR.append(NSMakePoint(max(p.x, mindepth), self.maxYref))
		# if marginsL[0].y>(self.minYref):
		# 	marginsL.insert(0,NSMakePoint(min(p.x, maxdepth), self.minYref))
		# 	marginsR.insert(0,NSMakePoint(max(p.x, mindepth), self.minYref))

		return marginsL, marginsR

	# close counters at 45 degrees
	def diagonize(self, marginsL, marginsR):
		ystep = abs(marginsL[0].y - marginsL[1].y)
		for i in range(len(marginsL)-1):
			if marginsL[i+1].x - marginsL[i].x > ystep: marginsL[i+1].x = marginsL[i].x + ystep
			if marginsR[i+1].x - marginsR[i].x < -ystep: marginsR[i+1].x = marginsR[i].x - ystep

		for i in reversed(range(len(marginsL)-1)):
			if marginsL[i].x - marginsL[i+1].x > ystep: marginsL[i].x = marginsL[i+1].x + ystep
			if marginsR[i].x - marginsR[i+1].x < -ystep: marginsR[i].x = marginsR[i+1].x - ystep

		return marginsL, marginsR

	# close counterforms, creating a polygon
	def closeOpenCounters(self, margin, extreme):
		initPoint = NSMakePoint(extreme.x, self.minYref)
		endPoint = NSMakePoint(extreme.x, self.maxYref)
		margin.insert(0, initPoint)
		margin.append(endPoint)
		return margin

	def deslant(self, margin):
		"""De-slant a list of points (contour) at angle with the point of origin
		at half the xheight."""
		mline = self.xHeight / 2
		return [
			NSMakePoint(p.x - (p.y - mline) * math.tan(math.radians(self.angle)), p.y)
			for p in margin
		]

	def calculateSBValue(self, polygon):
		amplitudeY = self.maxYref - self.minYref

		#recalculates area based on UPM
		areaUPM = self.paramArea * ((self.upm / 1000) **2)
		# calculates proportional area
		whiteArea = areaUPM * self.factor * 100

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

		self.output+="Glyph: " + str(layer.parent.name)+"\n"
		self.output+="Reference layer: " + referenceLayer.parent.name+ " | Factor: " + str(self.factor) + "\n"

		#get the margins for the full outline
		#will take measure from minY to maxY. minYref and maxYref are passed to check reference match
		# totalMarginList(layer,minY,maxY,angle,minYref,maxYref)
		lTotalMargins, rTotalMargins = totalMarginList(layer,self.minY,self.maxY,self.angle,self.minYref,self.maxYref)

		#margins will be False, False if there is no measure in the reference zone, and then function stops
		if not lTotalMargins and not rTotalMargins:
			self.output += 'The glyph outlines are outside the reference layer zone/height. No match with '+referenceLayer.parent.name+"\n"
			return

		# filtes all the margins to the reference zone
		lZoneMargins, rZoneMargins = zoneMargins(lTotalMargins,rTotalMargins,self.minYref,self.maxYref)


		#if the font has an angle, we need to deslant
		if self.angle:
			self.output+="Using angle: " + str(self.angle)+"\n"
			lZoneMargins = self.deslant(lZoneMargins)
			rZoneMargins = self.deslant(rZoneMargins)

			lTotalMargins = self.deslant(lTotalMargins)
			rTotalMargins = self.deslant(rTotalMargins)


		#full shape extreme points
		lFullExtreme, rFullExtreme = self.maxPoints([lTotalMargins,rTotalMargins], self.minY, self.maxY)
		# get zone extreme points
		lExtreme, rExtreme = self.maxPoints([lZoneMargins,rZoneMargins], self.minYref, self.maxYref)


		# create a closed polygon
		lPolygon, rPolygon = self.processMargins(lZoneMargins, rZoneMargins, lExtreme, rExtreme)

		# return

		# dif between extremes full and zone
		distanceL = math.ceil(lExtreme.x - lFullExtreme.x)
		distanceR = math.ceil(rFullExtreme.x - rExtreme.x)

		# set new sidebearings
		self.newL = math.ceil(0 - distanceL + self.calculateSBValue(lPolygon))
		self.newR = math.ceil(0 - distanceR + self.calculateSBValue(rPolygon))

		# tabVersion
		if '.tosf' in layer.parent.name or '.tf' in layer.parent.name or self.tabVersion:
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

			self.output += layer.parent.name + ' is tabular and adjusted at width = ' + str(self.layerWidth)
		# end tabVersion

		# if there is a metric rule
		else:
			if layer.parent.leftMetricsKey is not None or self.LSB == False:
				self.newL = layer.LSB

			if layer.parent.rightMetricsKey is not None or self.RSB == False:
				self.newR = layer.RSB
		return lPolygon, rPolygon

	def spaceMain(self, layer, referenceLayer):
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
				#self.output+='Glyph '+layer.parent.name +' se supone tabular..'+"\n"
			# if it is fraction / silly condition
			elif 'fraction' in layer.parent.name:
				self.output += 'Glyph ' + layer.parent.name + ': should be checked and done manually.\n'
			# if not...
			else:
				# Decompose layer for analysis, as the deeper plumbing assumes to be looking at outlines.
				layer_decomposed = layer.copyDecomposedLayer()
				layer_decomposed.parent = layer.parent

				#run the spacing
				space = self.setSpace(layer_decomposed, referenceLayer)

				#if it worked
				if space:
					lp, rp = space
					del layer_decomposed
					# store values in a list
					setSidebearings(layer, self.newL, self.newR, self.newWidth, color)

			print(self.output)
			self.output = ''
		# traceback
		except Exception:
			import traceback
			print(traceback.format_exc())
		return lp, rp



class HTLetterspacerScript(object):

	def __init__(self, ui):

		self.engine = HTLetterspacerLib()

		self.font = GlyphsApp.Glyphs.font

		selectedLayers = GlyphsApp.Glyphs.font.selectedLayers
		self.ui = ui

		if selectedLayers is None or len(selectedLayers)<1:
			GlyphsApp.Message("Error :(", "Nothing selected", OKButton="OK")
			return
		self.mySelection = list(set(selectedLayers))

		self.output = ''
		self.layerID = self.mySelection[0].associatedMasterId
		self.master = self.font.masters[self.layerID]
		self.config = readConfig(self.master.name)


		self.engine.upm = self.font.upm
		self.engine.angle = self.master.italicAngle
		self.engine.xHeight = self.master.xHeight

		if self.config :
			self.getParams()

			self.engine.tabVersion = False
			self.engine.LSB = True
			self.engine.RSB = True

			if self.ui:
				self.window()
			else:
				self.spaceMain()

	def getParams(self):
		for param in ["paramArea", "paramDepth", "paramOver"]:
			customParam = self.master.customParameters[param]
			if customParam:
				setattr(self.engine, param, float(customParam))
				self.output += 'Using master custom parameter, %s: %s\n' % (param, float(customParam))
			else:
				self.output += 'Using default parameter %s: %i\n' % (param, getattr(self.engine, param))

	def window(self):
		self.w = vanilla.FloatingWindow((250, 164), "HT Letterspacer", minSize=(250, 180), maxSize=(250, 180), autosaveName="com.ht.spacer")
		self.w.text_3 = vanilla.TextBox((210, 25, -170, 14), "%", sizeStyle='small')
		self.w.text_4 = vanilla.TextBox((15, 50, 100, 14), "Area", sizeStyle='small')
		self.w.text_4b = vanilla.TextBox((120, 50, 50, 14), self.engine.paramArea, sizeStyle='small')
		self.w.text_5 = vanilla.TextBox((15, 75, 100, 14), "Depth", sizeStyle='small')
		self.w.text_5b = vanilla.TextBox((120, 75, 50, 14), self.engine.paramDepth, sizeStyle='small')
		self.w.text_6 = vanilla.TextBox((15, 100, 100, 14), "Overshoot", sizeStyle='small')
		self.w.text_6b = vanilla.TextBox((120, 100, 50, 14), self.engine.paramOver, sizeStyle='small')
		self.w.LSB = vanilla.CheckBox((15, 15, 40, 18), "LSB", value=True, sizeStyle='small', callback=self.SavePreferences)
		self.w.RSB = vanilla.CheckBox((15 + 45, 15, 40, 18), "RSB", value=True, sizeStyle='small', callback=self.SavePreferences)
		self.w.tab = vanilla.CheckBox((15 + 45 + 45, 15, 60, 18), "Tabular", value=False, sizeStyle='small', callback=self.SavePreferences)
		self.w.width = vanilla.EditText((170, 15, 40, 18), widthAvg(self.mySelection), sizeStyle='small')
		self.w.area = vanilla.EditText((170, 50 - 3, 40, 18), "430", sizeStyle='small')
		self.w.prof = vanilla.EditText((170, 75 - 3, 40, 18), "20", sizeStyle='small')
		self.w.ex = vanilla.EditText((170, 100 - 3, 40, 18), "0", sizeStyle='small')

		self.w.copyButton = vanilla.Button((15, 125, -90, 30), "Copy Parameters", sizeStyle='small', callback=self.copyParameters)
		self.w.runButton = vanilla.Button((-80, 125, -15, 30), "Apply", sizeStyle='small', callback=self.dialogCallback)

		self.w.setDefaultButton(self.w.runButton)

		if not self.LoadPreferences():
			GlyphsApp.Message("Error :(", "Could not load preferences. Will resort to defaults.", OKButton="OK")

		self.w.open()
		self.w.makeKey()

	def dialogCallback(self, sender):
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
		self.spaceMain()

		if not self.SavePreferences(self):
			GlyphsApp.Message("Note", "Couldn't save preferences.", OKButton="OK")

	def SavePreferences(self, sender):
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

	def LoadPreferences(self):
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

	def findException(self):
		exception = False
		for item in self.config:
			if self.script == item[0] or item[0] == '*':
				if self.category == item[1] or item[1] == '*':
					if self.subCategory == item[2] or item[2] == '*':
						if self.case == item[3] or item[3] == '*':
							if not exception or item[6] in self.glyph.name:
								exception = item
		return exception

	def setG(self, layer):
		if layer.isKindOfClass_(objc.lookUpClass("GSControlLayer")):
			return
		self.output = '\\' + layer.parent.name + '\\\n' + self.output

		self.layerID = layer.associatedMasterId
		self.master = self.font.masters[self.layerID]
		self.layer = layer
		glyph = layer.parent
		self.glyph = glyph
		self.category = glyph.category
		self.subCategory = glyph.subCategory
		self.case = GlyphsApp.GSGlyphInfo.stringFromCase_(glyph.case)
		self.script = glyph.script
		self.engine.reference = glyph.name
		self.engine.factor = 1.0

		exception = self.findException()
		if (exception):
			self.engine.factor = exception[4]
			item = exception[5]
			if item != '*':
				self.engine.reference = item
		self.engine.newWidth = False

		# check reference layer existance and contours
		if self.font.glyphs[self.engine.reference]:
			self.referenceLayer = self.font.glyphs[self.engine.reference].layers[self.layerID]
			if len(self.referenceLayer.paths) < 1 and len(self.referenceLayer.components)<1:
				self.output += "WARNING: The reference glyph declared (" + self.engine.reference + ") doesn't have contours. Glyph " + self.glyph.name + " was spaced based on its own vertical range.\n"
				self.referenceLayer = layer
		else:
			self.referenceLayer = layer
			self.output += "WARNING: The reference glyph declared (" + self.engine.reference + ") doesn't exist. Glyph " + self.glyph.name + " was spaced based on its own vertical range.\n"

	def spaceMain(self):
		for layer in self.mySelection:
			self.setG(layer)
			lpolygon, rpolygon = self.engine.spaceMain(layer, self.referenceLayer)
		print(self.output)
		if len(self.mySelection) < 2 and drawAreas == True and lpolygon is not None:
			self.engine.createAreasGlyph(self.font, self.mySelection[0], [lpolygon, rpolygon])
		if self.font.currentTab:
			self.font.currentTab.forceRedraw()


	def setClipboard( self, myText ):
		"""
		Sets the contents of the clipboard to myText.
		Returns True if successful, False if unsuccessful.
		"""
		from AppKit import NSPasteboard, NSStringPboardType
		try:
			myClipboard = NSPasteboard.generalPasteboard()
			myClipboard.declareTypes_owner_( [NSStringPboardType], None )
			myClipboard.setString_forType_( myText, NSStringPboardType )
			return True
		except Exception as e:
			import traceback
			print(traceback.format_exc())
			print()
			print(e)
			return False

	def copyParameters(self,sender):
		"""Copy the custom parameters to the clipboard"""
		area  = float(self.w.area.get())
		depth = float(self.w.prof.get())
		over  = float(self.w.ex.get())
		if GlyphsApp.Glyphs.versionNumber < 3.0:
			copyText = COPY_PARAMETERS_GLYPHS2 % (area, depth, over)
		else:
			copyText = COPY_PARAMETERS_GLYPHS3 % (area, depth, over)
		if not self.setClipboard( copyText ):
			GlyphsApp.Message("Clipboard Error", "An error occurred: Could not copy the values into the clipboard. Please check Macro Window for details.", OKButton=None)
