#MenuTitle: HT LetterSpacer
#
# Letterspacer, an auto-spacing tool
# Copyright (C) 2009 - 2018, The Letterspacer Project Authors
#
# Version 1.1

import HT_LetterSpacer_script
try:
	from importlib import reload
except:
	pass
reload(HT_LetterSpacer_script)

# ui, createProofGlyph
HT_LetterSpacer_script.HTLetterspacerScript(False, False)
