#
# LetterSpacer, an auto-spacing tool
# Copyright (C) 2009 - 2016, The LetterSpacer Project Authors
#
# This script can only be used with permission
# 
# Version 1.0.0

# Default parameters
paramArea = 400  # white area in thousand units
paramDepth = 15  # depth in open counterforms, from extreme points.
paramOver = 0    # overshoot in spacing vertical range

# ADVANCED CONFIG
# mark color
color = 1
# creates -areas- glyph, with a drawing of the white space in letter. Requires robofab.
createProofGlyph = False
# frequency of vertical measuring. Higher values are faster but less accurate
paramFreq = 10


# program
#  Dependencies
import GlyphsApp
import math
import numpy as np
from Foundation import NSMinX, NSMaxX, NSMinY, NSMaxY, NSMakePoint
if createProofGlyph:
	from objectsGS import *
	f = CurrentFont()

#  Functions

def setSidebearings(layer, newL, newR, width, color):
	layer.LSB = newL
	layer.RSB = newR

	# ajusta el error de calculo tabular
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
def marginList(layer, bottom, top):
	y = bottom
	listL = []
	listR = []
	# works over glyph copy
	cleanLayer = layer.copyDecomposedLayer()
	while y <= top:
		lpos, rpos = getMargins(cleanLayer, y)
		listL.append(NSMakePoint(lpos, y))
		listR.append(NSMakePoint(rpos, y))
		y += paramFreq
	return listL, listR

def marginsZone(margins, bottom, top):
	return filter(lambda p: p.y >= bottom and p.y <= top, margins)

# sets depth for each point in list
# left
def setDepthInListL(lista, depth, lExtreme):
	list = []
	maxdepth = lExtreme.x + depth
	for p in lista:
		if p.x is not None:
			x = min(p.x, maxdepth)
		else:
			x = maxdepth
		list.append(NSMakePoint(x, p.y))
	return list


# right
def setDepthInListR(lista, depth, rExtreme):
	list = []
	mindepth = rExtreme.x - depth
	for p in lista:
		if p[0] is not None:
			x = max(p[0], mindepth)
		else:
			x = mindepth
		list.append(NSMakePoint(x, p.y))
	return list


# creates proof glyph
def createAreasGlyph(font, origenLayer, layerIndex, margins):
	from robofab.pens.marginPen import MarginPen
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
	print destination
	# destination.update()


class HTSpacerLib(object):

	def __init__(self):
		self.paramArea = paramArea
		self.paramDepth = paramDepth
		self.paramOver = paramOver
		self.tabVersion = False

	def overshoot(self):
		return self.xHeight * self.paramOver / 100

	def maxPoints(self, points, minY, maxY):
		right = -10000
		left = 10000
		for p in points:
			if p.y >= minY and p.y <= maxY:
				if p.x > right and p.x is not None:
					right = p.x
					righty = p.y
				if p.x < left and p.x is not None:
					left = p.x
					lefty = p.y
		return NSMakePoint(left, lefty), NSMakePoint(right, righty)

	def processMargins(self, lMargin, rMargin):
		# deSlant if is italic
		lMargin = self.deSlant(lMargin)
		rMargin = self.deSlant(rMargin)

		# get extremes
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
		marginsL = setDepthInListL(marginsL, depth, lExtreme)
		marginsR = setDepthInListR(marginsR, depth, rExtreme)
		return marginsL, marginsR

	# close counterforms at 45 degrees
	def diagonize(self, marginsL, marginsR):
		total = len(marginsL) - 1

		valueFreq = paramFreq * 1.5
		for index in range(total):
			# left
			actualPoint = marginsL[index]
			nextPoint = marginsL[index + 1]
			if nextPoint.x > (actualPoint.x + valueFreq) and nextPoint.y > actualPoint.y:
				marginsL[index + 1].x = actualPoint.x + valueFreq
			# right
			actualPoint = marginsR[index]
			nextPoint = marginsR[index + 1]
			if nextPoint.x < (actualPoint.x - valueFreq) and nextPoint.y > actualPoint.y:
				marginsR[index + 1].x = actualPoint.x - valueFreq

			# left
			actualPoint = marginsL[total - index]
			nextPoint = marginsL[total - index - 1]
			if nextPoint.x > (actualPoint.x + valueFreq) and nextPoint.y < actualPoint.y:
				marginsL[total - index - 1].x = actualPoint.x + valueFreq
			# right
			actualPoint = marginsR[total - index]
			nextPoint = marginsR[total - index - 1]
			if nextPoint.x < (actualPoint.x - valueFreq) and nextPoint.y < actualPoint.y:
				marginsR[total - index - 1].x = actualPoint.x - valueFreq

		return marginsL, marginsR

	# close counterforms, creating a polygon
	def closeOpenCounters(self, margin, extreme):
		initPoint = NSMakePoint(extreme.x, self.minYref)
		endPoint = NSMakePoint(extreme.x, self.maxYref)
		margin.insert(0, initPoint)
		margin.append(endPoint)
		return margin

	def _italicOnOffPoint(self, p, onoff):
		if p.x is None: return p
		cateto = -p.y + self.mline
		if onoff == "off": cateto = -cateto
		xvar = -rectCateto(self.angle, cateto)
		return NSMakePoint(p.x+xvar, p.y)

	def deSlant(self, margin):
		return [self._italicOnOffPoint(p,"off") for p in margin]

	def slant(self, margin):
		return [self._italicOnOffPoint(p,"on") for p in margin]

	def calcularValorSb(self, poligono):
		amplitudeY = self.maxYref - self.minYref
		# calculates proportional area
		whiteArea = self.paramArea * self.factor * 100
		areaProporcional = (amplitudeY * whiteArea) / self.xHeight

		areaPoligono = area(poligono)
		valor = areaProporcional - areaPoligono
		nuevoValor = valor / amplitudeY
		return nuevoValor

	def setSpace(self, layer, referenceLayer):
		# get reference glyph maximum points
		overshoot = self.overshoot()

		# store min and max y
		self.minYref = NSMinY(referenceLayer.bounds) - overshoot
		self.maxYref = NSMaxY(referenceLayer.bounds) + overshoot

		# bounds
		lFullMargin, rFullMargin = marginList(layer, NSMinY(layer.bounds), NSMaxY(layer.bounds))

		# filter values between min and max
		lMargins = marginsZone(lFullMargin, self.minYref, self.maxYref)
		rMargins = marginsZone(rFullMargin, self.minYref, self.maxYref)

		# create a closed polygon
		lPolygon, rPolygon = self.processMargins(lMargins, rMargins)

		# deitalize margins
		lFullMargin = self.deSlant(lFullMargin)
		rFullMargin = self.deSlant(rFullMargin)

		# get extreme points deitalized
		lFullExtreme, rFullExtreme = self.maxPoints(lFullMargin + rFullMargin, NSMinY(layer.bounds), NSMaxY(layer.bounds))
		# get zone extreme points
		lExtreme, rExtreme = self.maxPoints(lMargins + rMargins, self.minYref, self.maxYref)

		# dif between extremes full and zone
		distanciaL = math.ceil(lExtreme.x - lFullExtreme.x)
		distanciaR = math.ceil(rFullExtreme.x - rExtreme.x)

		# set new sidebearings
		self.newL = math.ceil(0 - distanciaL + self.calcularValorSb(lPolygon))
		self.newR = math.ceil(0 - distanciaR + self.calcularValorSb(rPolygon))

		# tabVersion
		if '.tosf' in layer.parent.name or '.tf' in layer.parent.name or self.tab or self.tabVersion:
			if not window:
				self.ancho = layer.width
			anchoForma = rFullExtreme.x - lFullExtreme.x
			anchoActual = anchoForma + self.newL + self.newR
			anchoDiff = (self.ancho - anchoActual) / 2

			self.newL += anchoDiff
			self.newR += anchoDiff
			self.newWidth = self.ancho

			self.output += layer.parent.name + ' Fue ajustado tabularmente a ' + str(self.ancho)
		# fin tabVersion

		# if there is a metric rule
		else:
			if layer.parent.leftMetricsKey is not None or self.LSB == False:
				self.newL = layer.LSB

			if layer.parent.rightMetricsKey is not None or self.RSB == False:
				self.newR = layer.RSB

	def spaceMain(self, layer, referenceLayer):
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
				self.setSpace(layer, referenceLayer)
				# store values in a list
				setSidebearings(layer, self.newL, self.newR, self.newWidth, color)
			
			print self.output
			self.output = ''
			
		# traceback
		except Exception as ex:
			import traceback
			print traceback.format_exc()
