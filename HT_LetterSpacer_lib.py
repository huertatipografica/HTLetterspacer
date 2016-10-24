#
# HT Letterspacer, an auto-spacing tool
# Copyright (C) 2009 - 2016, The Letterspacer Project Authors
#
# Version 1.0.0

# Default parameters
paramArea = 400  # white area in thousand units
paramDepth = 15  # depth in open counterforms, from extreme points.
paramOver = 0    # overshoot in spacing vertical range
color = 1 	 # mark color
paramFreq = 5    # frequency of vertical measuring. Higher values are faster but less accurate

# program dependencies
import GlyphsApp
import math
import numpy as np
from Foundation import NSMinX, NSMaxX, NSMinY, NSMaxY, NSMakePoint
from objectsGS import *

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

# point list area
def area(points):
	s = 0
	for ii in np.arange(len(points)) - 1:
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

# draw outlines on areas glyph
def drawArea(origen, destination, puntos):
	destination.width = origen.width
	# pen
	pen = destination.getPen()

	# Tell the pen to draw things
	pen.moveTo(puntos[0])
	for p in puntos:
		pen.lineTo(p)

	# Done drawing: close the path
	pen.closePath()
	print 'Glyph named /'+destination.name+' was created with area preview.'
	# destination.update()


class HTLetterpacerLib(object):

	def __init__(self):
		self.paramArea = paramArea
		self.paramDepth = paramDepth
		self.paramOver = paramOver
		self.tabVersion = False

	def createAreasGlyph(self, font, origenLayer, layerIndex, margins):
		from robofab.pens.marginPen import MarginPen
		f = CurrentFont()
		if 'areas' in f:
			areaLayer = font.glyphs['areas'].layers[layerIndex]
			# f.removeGlyph('areas')
			#del font.glyphs["areas"]
			# removeSegment(index)

			for i in range(len(areaLayer.paths))[::-1]:
				del areaLayer.paths[i]
		else:
			f.newGlyph("areas")
		origen = f[origenLayer.parent.name]

		drawArea(origen, f['areas'], margins[0])
		drawArea(origen, f['areas'], margins[1])


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
		# lMargin, rMargin = self.diagonize(lMargin, rMargin)
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

		#make overshoot work / under development
		y=marginsL[0].y-paramFreq
		while y>self.minYref:
			marginsL.insert(0,NSMakePoint(min(p.x, maxdepth), y))
			marginsR.insert(0,NSMakePoint(max(p.x, mindepth), y))
			y-=paramFreq

		y=marginsL[-1].y+paramFreq
		while y<self.maxYref:
			marginsL.append(NSMakePoint(min(p.x, maxdepth), y))
			marginsR.append(NSMakePoint(max(p.x, mindepth), y))
			y+=paramFreq

		# if marginsL[-1].y<(self.maxYref-paramFreq):
		# 	marginsL.append(NSMakePoint(min(p.x, maxdepth), self.maxYref))
		# 	marginsR.append(NSMakePoint(max(p.x, mindepth), self.maxYref))
		# if marginsL[0].y>(self.minYref):
		# 	marginsL.insert(0,NSMakePoint(min(p.x, maxdepth), self.minYref))
		# 	marginsR.insert(0,NSMakePoint(max(p.x, mindepth), self.minYref))
		
		return marginsL, marginsR

	# close counterforms at 45 degrees
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
		# calculates proportional area
		whiteArea = self.paramArea * self.factor * 100
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
		# fin tabVersion

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
			# if it is fraction
			elif 'fraction' in layer.parent.name:
				self.output += 'Glyph ' + layer.parent.name + ': should be checked and done manually.\n'
			# if not...
			else:
				lp, rp = self.setSpace(layer, referenceLayer)
				# store values in a list
				setSidebearings(layer, self.newL, self.newR, self.newWidth, color)

			print self.output
			self.output = ''
		# traceback
		except Exception as ex:
			import traceback
			print traceback.format_exc()
		return lp, rp
