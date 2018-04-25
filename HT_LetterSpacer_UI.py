#MenuTitle: HT LetterSpacer UI
#
# Letterspacer, an auto-spacing tool
# Copyright (C) 2009 - 2016, The Letterspacer Project Authors
#
# Version 1.0.0

# Basic config
# if window = True, scripts run with a UI
window = True
createProofGlyph = False

# program
#  Dependencies
import GlyphsApp
import vanilla
from vanilla import dialogs

import HT_LetterSpacer_lib
reload(HT_LetterSpacer_lib)

from defaultConfigFile import *

def readConfig():
	directory, glyphsfile = os.path.split(Glyphs.font.filepath)
	conffile = glyphsfile.split('.')[0] + "_autospace.py"
	confpath = os.path.join(directory, conffile)
	array = []

	if os.path.isfile(confpath) == True:
		print 'Config file exists'
	else :
		createFilePrompt = dialogs.askYesNo(\
			messageText='\nMissing config file for this font.',\
			informativeText='want to create one?')
		if createFilePrompt == 1:
			newFile = open(confpath,'w')
			newFile.write(defaultConfigFile)
			newFile.close()
		elif createFilePrompt == 0 or createFilePrompt == -1:
			Message("Error :(", "HT Letterspacer can't work without a config file", OKButton="OK")
			return None

	with open(confpath) as f:
		for line in f:
			if line[0] != '#' and len(line) > 5:
				newline = line.split(",")
				del newline[-1]
				newline[3] = float(newline[3])
				array.append(newline)
	return array

class HTLetterspacerScript(object):

	def __init__(self):

		self.engine = HT_LetterSpacer_lib.HTLetterpacerLib()

		self.font = Glyphs.font

		selectedLayers = Glyphs.font.selectedLayers
		if selectedLayers is None:
			Message("Error :(", "Nothing selected", OKButton="OK")
			return
		self.mySelection = list(set(selectedLayers))
		self.output = ''
		self.layerID = self.mySelection[0].associatedMasterId
		self.master = self.font.masters[self.layerID]
		self.config = readConfig()

		self.engine.upm = self.font.upm
		self.engine.angle = self.master.italicAngle
		self.engine.xHeight = self.master.xHeight

		if self.config :
			self.getParams()

			self.engine.tabVersion = False
			self.engine.LSB = True
			self.engine.RSB = True

			if window:
				self.window()
			else:
				self.spaceMain()

	def getParams(self):
		for param in ["paramArea", "paramDepth", "paramOver"]:
			customParam = self.master.customParameters[param]
			if customParam:
				setattr(self.engine, param, float(customParam))
				self.output += 'Using master custom parameter, %s: %s\n' % (param, float(customParam))
				# print float(customParam)
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
		self.w.width = vanilla.EditText((170, 15, 40, 18), self.mySelection[0].width, sizeStyle='small')
		self.w.area = vanilla.EditText((170, 50 - 3, 40, 18), "430", sizeStyle='small')
		self.w.prof = vanilla.EditText((170, 75 - 3, 40, 18), "20", sizeStyle='small')
		self.w.ex = vanilla.EditText((170, 100 - 3, 40, 18), "0", sizeStyle='small')

		self.w.copyButton = vanilla.Button((15, 125, -90, 30), "Copy Parameters", sizeStyle='small', callback=self.copyParameters)
		self.w.runButton = vanilla.Button((-80, 125, -15, 30), "Apply", sizeStyle='small', callback=self.dialogCallback)

		self.w.setDefaultButton(self.w.runButton)

		if not self.LoadPreferences():
			Message("Error :(", "Could not load preferences. Will resort to defaults.", OKButton="OK")

		self.w.open()
		self.w.makeKey()

	def dialogCallback(self, sender):
		self.output = ""
		self.engine.paramArea = int(self.w.area.get())
		self.engine.paramDepth = float(self.w.prof.get())
		self.engine.paramOver = int(self.w.ex.get())
		self.engine.tabVersion = self.w.tab.get()
		self.engine.LSB = self.w.LSB.get()
		self.engine.RSB = self.w.RSB.get()
		self.engine.width = float(self.w.width.get())
		self.mySelection = list(set(Glyphs.font.selectedLayers))
		self.spaceMain()

		if not self.SavePreferences(self):
			Message("Note", "Couldn't save preferences.", OKButton="OK")

	def SavePreferences(self, sender):
		try:
			Glyphs.defaults["com.ht.spacer.LSB"] = self.w.LSB.get()
			Glyphs.defaults["com.ht.spacer.RSB"] = self.w.RSB.get()
			Glyphs.defaults["com.ht.spacer.tab"] = self.w.tab.get()
			Glyphs.defaults["com.ht.spacer.area"] = self.w.area.get()
			Glyphs.defaults["com.ht.spacer.depth"] = self.w.prof.get()
			Glyphs.defaults["com.ht.spacer.over"] = self.w.ex.get()
		except:
			return False

		return True

	def LoadPreferences(self):
		try:
			self.w.LSB.set(Glyphs.defaults["com.ht.spacer.LSB"])
			self.w.RSB.set(Glyphs.defaults["com.ht.spacer.RSB"])
			self.w.tab.set(Glyphs.defaults["com.ht.spacer.tab"])
			self.w.area.set(Glyphs.defaults["com.ht.spacer.area"])
			self.w.prof.set(Glyphs.defaults["com.ht.spacer.depth"])
			self.w.ex.set(Glyphs.defaults["com.ht.spacer.over"])
		except:
			return False

		return True

	def findException(self):
		exception = False
		items = []
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
		if len(self.mySelection) < 2 and createProofGlyph and lpolygon is not None:
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
			print traceback.format_exc()
			print
			print e
			return False

	def copyParameters(self,sender):
		"""Copy the custom parameters to the clipboard"""
		area  = int(self.w.area.get())
		depth = float(self.w.prof.get())
		over  = int(self.w.ex.get())
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
			Message("Clipboard Error", "An error occurred: Could not copy the values into the clipboard. Please check Macro Window for details.", OKButton=None)


HTLetterspacerScript()
