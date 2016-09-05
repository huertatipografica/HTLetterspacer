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
from Foundation import NSMinY, NSMaxY, NSMakePoint
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
		s = s + (points[ii][0] * points[ii + 1][1] - points[ii + 1][0] * points[ii][1])
	return abs(s) * 0.5


# get margins in Glyphs
def getMargins(layer, y):
	startPoint = NSMakePoint(-1000, y)
	endPoint = NSMakePoint(3000, y)

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
		listL.append([lpos, y])
		listR.append([rpos, y])
		y += paramFreq
	return listL, listR

def marginsZone(margins, bottom, top):
	return filter(lambda p: p[1] >= bottom and p[1] <= top, margins)

# sets depth for each point in list
# left
def setDepthInListL(lista, depth, lExtreme):
	list = []
	maxdepth = lExtreme[0] + depth
	for p in lista:
		if p[0] is not None:
			x = min(p[0], maxdepth)
		else:
			x = maxdepth
		list.append([x, p[1]])
	return list


# right
def setDepthInListR(lista, depth, rExtreme):
	list = []
	mindepth = rExtreme[0] - depth
	for p in lista:
		if p[0] is not None:
			x = max(p[0], mindepth)
		else:
			x = mindepth
		list.append([x, p[1]])
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
			if p[1] >= minY and p[1] <= maxY:
				if p[0] > right and p[0] is not None:
					right = p[0]
					righty = p[1]
				if p[0] < left and p[0] is not None:
					left = p[0]
					lefty = p[1]
		return (left, lefty), (right, righty)

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
		lMargin, rMargin = self.closeOpenCounters(lMargin, rMargin, lExtreme, rExtreme)

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
			if nextPoint[0] > (actualPoint[0] + valueFreq) and nextPoint[1] > actualPoint[1]:
				marginsL[index + 1][0] = actualPoint[0] + valueFreq
			# right
			actualPoint = marginsR[index]
			nextPoint = marginsR[index + 1]
			if nextPoint[0] < (actualPoint[0] - valueFreq) and nextPoint[1] > actualPoint[1]:
				marginsR[index + 1][0] = actualPoint[0] - valueFreq

			# left
			actualPoint = marginsL[total - index]
			nextPoint = marginsL[total - index - 1]
			if nextPoint[0] > (actualPoint[0] + valueFreq) and nextPoint[1] < actualPoint[1]:
				marginsL[total - index - 1][0] = actualPoint[0] + valueFreq
			# right
			actualPoint = marginsR[total - index]
			nextPoint = marginsR[total - index - 1]
			if nextPoint[0] < (actualPoint[0] - valueFreq) and nextPoint[1] < actualPoint[1]:
				marginsR[total - index - 1][0] = actualPoint[0] - valueFreq

		return marginsL, marginsR

	# close counterforms, creating a polygon
	def closeOpenCounters(self, marginsL, marginsR, lExtreme, rExtreme):
		initPoint = lExtreme[0], self.minYref
		endPoint = lExtreme[0], self.maxYref
		marginsL.insert(0, initPoint)
		marginsL.append(endPoint)

		initPoint = rExtreme[0], self.minYref
		endPoint = rExtreme[0], self.maxYref
		marginsR.insert(0, initPoint)
		marginsR.append(endPoint)
		return marginsL, marginsR

	def _italicOnOffPoint(self, p, onoff):
		if p[0] is None: return p
		px, py = p[0], p[1]
		cateto = -py + self.mline
		if onoff == "off": cateto = -cateto
		xvar = -rectCateto(self.angle, cateto)
		return [px+xvar, py]

	def deSlant(self, margin):
		return [self._italicOnOffPoint(p,"off") for p in margin]

	def slant(self, margin):
		return [self._italicOnOffPoint(p,"on") for p in margin]

	def calcularValorSb(self, poligono):
		amplitudeY = self.maxYref - self.minYref
		# calculates proportional area
		areaProporcional = (amplitudeY * self.area) / self.xHeight
		areaPoligono = area(poligono)
		valor = areaProporcional - areaPoligono
		nuevoValor = valor / amplitudeY
		return nuevoValor

	def setSpace(self, layer, referenceLayer):
		self.layer = layer
		self.area = self.paramArea * self.factor * 100

		# get reference glyph maximum points
		bounds = referenceLayer.bounds
		overshoot = self.overshoot()

		# store min and max y
		self.minYref = NSMinY(bounds) - overshoot
		self.maxYref = NSMaxY(bounds) + overshoot

		# bounds
		bounds = self.layer.bounds

		lFullMargin, rFullMargin = marginList(self.layer, NSMinY(bounds), NSMaxY(bounds))

		# filter values between min and max
		lMargins = marginsZone(lFullMargin, self.minYref, self.maxYref)
		rMargins = marginsZone(rFullMargin, self.minYref, self.maxYref)

		# create a closed polygon
		lPolygon, rPolygon = self.processMargins(lMargins, rMargins)

		# deitalize margins
		lFullMargin = self.deSlant(lFullMargin)
		rFullMargin = self.deSlant(rFullMargin)

		# get extreme points deitalized
		lFullExtreme, rFullExtreme = self.maxPoints(lFullMargin + rFullMargin, NSMinY(bounds), NSMaxY(bounds))
		# get zone extreme points
		lExtreme, rExtreme = self.maxPoints(lMargins + rMargins, self.minYref, self.maxYref)

		# dif between extremes full and zone
		distanciaL = math.ceil(lExtreme[0] - lFullExtreme[0])
		distanciaR = math.ceil(rFullExtreme[0] - rExtreme[0])

		# set new sidebearings
		self.newL = math.ceil(0 - distanciaL + self.calcularValorSb(lPolygon))
		self.newR = math.ceil(0 - distanciaR + self.calcularValorSb(rPolygon))

		# tabVersion
		if '.tosf' in layer.parent.name or '.tf' in layer.parent.name or self.tab or self.tabVersion:
			if not window:
				self.ancho = self.layer.width
			anchoForma = rFullExtreme[0] - lFullExtreme[0]
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
				self.newL = self.layer.LSB

			if layer.parent.rightMetricsKey is not None or self.RSB == False:
				self.newR = self.layer.RSB

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
