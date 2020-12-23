#
# HT Letterspacer, an auto-spacing tool
# Copyright (C) 2009 - 2018, The HT Letterspacer Project Authors
# Version 1.11


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
import objectsGS
import vanilla
from vanilla import dialogs
from defaultConfigFile import *

#  Functions
def setSidebearings(layer, newL, newR, width, color):
	layer.LSB = newL
	layer.RSB = newR

	# adjusts the tabular miscalculation
	if width:
		layer.width = width

	if color:
		layer.parent.color = color


# shape calculations
def rectCateto(angle, cat):
	angle = math.radians(angle)
	result = cat * (math.tan(angle))
	#result = round(result)
	return result

# to avoid numpy.arange
def arange(num,offset):
    arr = []
    for i in range(offset,num+offset):
        arr.append(i)
    return arr

# point list area
def area(points):
	s = 0
	for ii in arange(len(points),-1):
		s = s + (points[ii].x * points[ii + 1].y - points[ii + 1].x * points[ii].y)
	return abs(s) * 0.5

# get margins in Glyphs
def getMargins(layer, y):
	startPoint = NSMakePoint(NSMinX(layer.bounds), y)
	endPoint = NSMakePoint(NSMaxX(layer.bounds), y)

	result = layer.calculateIntersectionsStartPoint_endPoint_(startPoint, endPoint)
	count = len(result)
	if (count <= 2):
		return (None, None)

	left = 1
	right = count - 2
	return (result[left].pointValue().x, result[right].pointValue().x)

# a list of margins
def marginList(layer):
	y = NSMinY(layer.bounds)
	listL = []
	listR = []
	# works over glyph copy
	cleanLayer = layer.copyDecomposedLayer()
	while y <= NSMaxY(layer.bounds):
		lpos, rpos = getMargins(cleanLayer, y)
		if lpos is not None:
			listL.append(NSMakePoint(lpos, y))
		if rpos is not None:
			listR.append(NSMakePoint(rpos, y))
		y += paramFreq
	return listL, listR

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
	directory, glyphsfile = os.path.split(GlyphsApp.Glyphs.font.filepath)
	confpath = getConfigPath(directory, glyphsfile, mastername)
	array = []
	
	if os.path.isfile(confpath) == True:
		print('Config file exists')
	else :
		createFilePrompt = dialogs.askYesNo(\
			messageText='\nMissing config file for this font.',\
			informativeText='want to create one?')
		if createFilePrompt == 1:
			newFile = open(confpath,'w')
			newFile.write(defaultConfigFile)
			newFile.close()
		elif createFilePrompt == 0 or createFilePrompt == -1:
			GlyphsApp.Message("Error :(", "HT Letterspacer can't work without a config file", OKButton="OK")
			return None

	with open(confpath) as f:
		for line in f:
			if line[0] != '#' and len(line) > 5:
				newline = line.split(",")
				del newline[-1]
				newline[3] = float(newline[3])
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

	def createAreasGlyph(self, font, layer, margins):
		layerId = layer.layerId

		# try to create glyph
		if '_areas' not in font.glyphs:
			try:
				font.glyphs.append(GlyphsApp.GSGlyph('_areas'))
			except Exception:
				pass

		destination = font.glyphs['_areas'].layers[layerId]
		destination.parent.export = False

		# Delete all paths in destination
		destination.clear()

		# Set width and draw
		destination.width = layer.width
		destination.paths.append(self.shape(margins[0]))
		destination.paths.append(self.shape(margins[1]))

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
		right = -10000
		left = 10000
		for p in points:
			if p.y >= minY and p.y <= maxY:
				if p.x > right:
					right = p.x
					righty = p.y
				if p.x < left:
					left = p.x
					lefty = p.y
		return NSMakePoint(left, lefty), NSMakePoint(right, righty)

	def processMargins(self, lMargin, rMargin):
		# deSlant if is italic
		lMargin = self.deSlant(lMargin)
		rMargin = self.deSlant(rMargin)

		# get extremes
		# lExtreme, rExtreme = self.maxPoints(lMargin + rMargin, self.minYref, self.maxYref)
		lExtreme, rExtreme = self.maxPoints(lMargin + rMargin, self.minYref, self.maxYref)

		# set depth
		lMargin, rMargin = self.setDepth(lMargin, rMargin, lExtreme, rExtreme)

		# close open counterforms at 45 degrees
		lMargin, rMargin = self.diagonize(lMargin, rMargin)
		lMargin = self.closeOpenCounters(lMargin, lExtreme)
		rMargin = self.closeOpenCounters(rMargin, rExtreme)

		lMargin = self.slant(lMargin)
		rMargin = self.slant(rMargin)
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
		total = len(marginsL) - 1

		valueFreq = paramFreq * 1.5
		for index in range(total):
			# left
			actualPoint = marginsL[index]
			nextPoint = marginsL[index + 1]
			diff=nextPoint.y - actualPoint.y
			if nextPoint.x > (actualPoint.x + diff) and nextPoint.y > actualPoint.y:
				marginsL[index + 1].x = actualPoint.x + diff
			# right
			actualPoint = marginsR[index]
			nextPoint = marginsR[index + 1]
			#if nextPoint.x < (actualPoint.x - valueFreq) and nextPoint.y > actualPoint.y:
			if nextPoint.x < (actualPoint.x - diff) and nextPoint.y > actualPoint.y:
				marginsR[index + 1].x = actualPoint.x - diff

			# left
			actualPoint = marginsL[total - index]
			nextPoint = marginsL[total - index - 1]
			diff=actualPoint.y-nextPoint.y
			if nextPoint.x > (actualPoint.x + valueFreq) and nextPoint.y < actualPoint.y:
				marginsL[total - index - 1].x = actualPoint.x + diff
			# right
			actualPoint = marginsR[total - index]
			nextPoint = marginsR[total - index - 1]
			if nextPoint.x < (actualPoint.x - diff) and nextPoint.y < actualPoint.y:
				marginsR[total - index - 1].x = actualPoint.x - diff

		return marginsL, marginsR

	# close counterforms, creating a polygon
	def closeOpenCounters(self, margin, extreme):
		initPoint = NSMakePoint(extreme.x, self.minYref)
		endPoint = NSMakePoint(extreme.x, self.maxYref)
		margin.insert(0, initPoint)
		margin.append(endPoint)
		return margin

	def _italicOnOffPoint(self, p, onoff):
		mline = self.xHeight / 2
		cateto = -p.y + mline
		if onoff == "off": cateto = -cateto
		xvar = -rectCateto(self.angle, cateto)
		return NSMakePoint(p.x+xvar, p.y)

	def deSlant(self, margin):
		return [self._italicOnOffPoint(p,"off") for p in margin]

	def slant(self, margin):
		return [self._italicOnOffPoint(p,"on") for p in margin]

	def calculateSBValue(self, polygon):
		amplitudeY = self.maxYref - self.minYref

		#recalculates area based on UPM
		areaUPM = self.paramArea*((self.upm/1000)**2)

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

		# bounds
		lFullMargin, rFullMargin = marginList(layer)

		lMargins = filter(lambda p: p.y >= self.minYref and p.y <= self.maxYref, lFullMargin)
		rMargins = filter(lambda p: p.y >= self.minYref and p.y <= self.maxYref, rFullMargin)

		# create a closed polygon
		lPolygon, rPolygon = self.processMargins(lMargins, rMargins)
		lMargins = self.deSlant(lMargins)
		rMargins = self.deSlant(rMargins)

		lFullMargin = self.deSlant(lFullMargin)
		rFullMargin = self.deSlant(rFullMargin)

		# get extreme points deitalized
		lFullExtreme, rFullExtreme = self.maxPoints(lFullMargin + rFullMargin, NSMinY(layer.bounds), NSMaxY(layer.bounds))
		# get zone extreme points
		lExtreme, rExtreme = self.maxPoints(lMargins + rMargins, self.minYref, self.maxYref)

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
				lp, rp = self.setSpace(layer, referenceLayer)
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

	def __init__(self, ui, drawAreas):

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
		self.w = vanilla.FloatingWindow((250, 180), "HT Letterspacer", minSize=(225, 180), maxSize=(225, 180), autosaveName="com.ht.spacer")
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
		self.engine.width = int(self.w.width.get())
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
			return False

		return True

	def findException(self):
		exception = False
		for item in self.config:
			if self.script == item[0] or item[0] == '*':
				if self.category == item[1] or item[1] == '*':
					if self.subCategory == item[2] or item[2] == '*':
						if not exception or item[5] in self.glyph.name:
							exception = item
		return exception

	def setG(self, layer):
		if layer.isKindOfClass_(objc.lookUpClass("GSControlLayer")):
			return
		self.output = '\\' + layer.parent.name + '\\\n' + self.output

		self.layerID = layer.associatedMasterId
		self.master = self.font.masters[self.layerID]

		self.glyph = layer.parent
		self.layer = layer
		self.category = layer.parent.category
		self.subCategory = layer.parent.subCategory
		self.script = layer.parent.script
		self.engine.reference = self.glyph.name

		exception = self.findException()
		if (exception):
			self.engine.factor = exception[3]
			item = exception[4]
			if item != '*':
				self.engine.reference = item
		
		self.engine.newWidth = False

		# check reference layer existance and contours
		if self.font.glyphs[self.engine.reference]:
			self.referenceLayer = self.font.glyphs[self.engine.reference].layers[self.layerID]
			if len(self.referenceLayer.paths) < 1:
				self.output += "WARNING: The reference glyph declared (" + self.engine.reference + ") doesn't have contours. Glyph " + self.layer.parent.name + " was spaced uses its own vertical range.\n"
				self.referenceLayer = self.layer
		else:
			self.referenceLayer = self.layer
			self.output += "WARNING: The reference glyph declared (" + self.engine.reference + ") doesn't exist. Glyph " + self.layer.parent.name + " was spaced uses its own vertical range.\n"

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
		copyText = """(
        {
        paramArea = %i;
    },
        {
        paramDepth = %.2f;
    },
        {
        paramOver = %i;
    }
)""" % (area, depth, over)
		if not self.setClipboard( copyText ):
			GlyphsApp.Message("Clipboard Error", "An error occurred: Could not copy the values into the clipboard. Please check Macro Window for details.", OKButton=None)
