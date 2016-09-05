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
	if (count > 2):
		left = 1
		right = count - 2
		margins = (result[left].pointValue().x, result[right].pointValue().x)
	else:
		margins = (None, None)
	return margins


# a list of margins
def marginList(layer, bottom, top):
	y = bottom
	listL = []
	listR = []
	# works over glyph copy
	cleanLayer = layer.copyDecomposedLayer()
	while y <= top:
		margins = getMargins(cleanLayer, y)
		lpos = margins[0]
		rpos = margins[1]
		listL.append([lpos, y])
		listR.append([rpos, y])
		y += paramFreq
	lista = [listL, listR]
	return lista


def marginsZone(margins, bottom, top):
	marginsNew = [[], []]
	for index in range(len(margins[0])):
		if margins[0][index][1] >= bottom and margins[0][index][1] <= top:
			marginsNew[0].append(margins[0][index])
			marginsNew[1].append(margins[1][index])
	return marginsNew


# sets depth for each point in list
# left
def setDepthInListL(lista, depth, puntosExtremos):
	list = []
	for p in lista:
		# si es nulo lo pone a la profundiad
		if p[0] is not None:
			x = p[0]
			if p[0] > (puntosExtremos[0][0] + depth):
				x = puntosExtremos[0][0] + depth
		else:
			x = puntosExtremos[0][0] + depth
		list.append([x, p[1]])
	return list


# right
def setDepthInListR(lista, depth, puntosExtremos):
	list = []
	for p in lista:
		if p[0] is not None:
			x = p[0]
			if p[0] < (puntosExtremos[1][0] - depth):
				x = puntosExtremos[1][0] - depth
		else:
			x = puntosExtremos[1][0] - depth
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
		return ((left, lefty), (right, righty))

	def processMargins(self, margins):
		# deSlant if is italic
		margins = self.deSlant(margins)
		# get extremes
		puntosExtremos = self.maxPoints(margins[0] + margins[1], self.minYref, self.maxYref)

		# set depth
		margins = self.setDepth(margins[0], margins[1], puntosExtremos)
		# close open counterforms at 45 degrees
		margins = self.diagonize(margins[0], margins[1])
		margins = self.closeOpenCounters(margins[0], margins[1], puntosExtremos)
		margins = self.slant(margins)
		return margins[0], margins[1]

	# process lists with depth, proportional to xheight
	def setDepth(self, marginsL, marginsR, puntosExtremos):
		depth = self.xHeight * self.paramDepth / 100
		marginsL = setDepthInListL(marginsL, depth, puntosExtremos)
		marginsR = setDepthInListR(marginsR, depth, puntosExtremos)
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
	def closeOpenCounters(self, marginsL, marginsR, puntosExtremos):
		initPoint = puntosExtremos[0][0], self.minYref
		endPoint = puntosExtremos[0][0], self.maxYref
		marginsL.insert(0, initPoint)
		marginsL.append(endPoint)

		initPoint = puntosExtremos[1][0], self.minYref
		endPoint = puntosExtremos[1][0], self.maxYref
		marginsR.insert(0, initPoint)
		marginsR.append(endPoint)
		return marginsL, marginsR

	def italizePoint(self, p):
		if p[0] is not None:
			px = p[0]
			py = p[1]
			cateto = self.mline - p[1]
			xvar = -rectCateto(self.angle, cateto)
			p = [px + xvar, py]
		return p

	def deItalizePoint(self, p):
		if p[0] is not None:
			px = p[0]
			py = p[1]
			cateto = p[1] - self.mline
			xvar = -rectCateto(self.angle, cateto)
			p = [px + xvar, py]
		return p

	def deSlant(self, margins):
		if self.angle > 0:
			for index in range(len(margins[0])):
				margins[0][index] = self.deItalizePoint(margins[0][index])
				margins[1][index] = self.deItalizePoint(margins[1][index])
		return margins

	def slant(self, margins):
		for index in range(len(margins[0])):
			margins[0][index] = self.italizePoint(margins[0][index])
			margins[1][index] = self.italizePoint(margins[1][index])
		return margins

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

		# all the margins
		marginsOne = marginList(self.layer, NSMinY(bounds), NSMaxY(bounds))

		# creates a list with left and right margins
		marginsFull = [marginsOne[0], marginsOne[1]]

		# filter values between min and max
		margins = marginsZone(marginsFull, self.minYref, self.maxYref)

		# create a closed polygon
		poligonos = self.processMargins(margins)

		# deitalize margins
		marginsFull = self.deSlant(marginsFull)
		# get extreme points deitalized
		extremosFull = self.maxPoints(marginsFull[0] + marginsFull[1], NSMinY(bounds), NSMaxY(bounds))
		# get zone extreme points
		extremos = self.maxPoints(margins[0] + margins[1], self.minYref, self.maxYref)

		# dif between extremes full and zone
		distanciaL = math.ceil(extremos[0][0] - extremosFull[0][0])
		distanciaR = math.ceil(extremosFull[1][0] - extremos[1][0])

		# set new sidebearings
		self.newL = math.ceil(0 - distanciaL + self.calcularValorSb(poligonos[0]))
		self.newR = math.ceil(0 - distanciaR + self.calcularValorSb(poligonos[1]))

		# tabVersion
		if '.tosf' in layer.parent.name or '.tf' in layer.parent.name or self.tab or self.tabVersion:
			if not window:
				self.ancho = self.layer.width
			anchoForma = extremosFull[1][0] - extremosFull[0][0]
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
