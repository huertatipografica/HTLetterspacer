# MenuTitle: Apply HTLS Config
# -*- coding: utf-8 -*-
"""Space the current selection using the rules stored in the font.

Reads the font's rules (and the current master's overrides) and applies the
computed sidebearings to every selected layer. Headless config-runner — the
windowed equivalent comes later (Parameters tab / Apply values).

Run from the Macro panel or the Scripts menu with some glyphs selected.
"""
from __future__ import division, print_function, unicode_literals
import os
import sys

# Find the shared `htls` package inside the plugin bundle. Prefer discovering it
# relative to this script (which lives at <repo>/HT Letterspacer Scripts/),
# resolving symlinks so it still works when the script is symlinked into Glyphs'
# Scripts folder; fall back to the installed Plugins bundle.
_BUNDLE = "HTLetterspacer.glyphsPlugin/Contents/Resources"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_CANDIDATES = [
	os.path.join(_REPO_ROOT, _BUNDLE),
	os.path.expanduser("~/Library/Application Support/Glyphs 3/Plugins/" + _BUNDLE),
]
for _PLUGIN_RESOURCES in _CANDIDATES:
	if os.path.isdir(_PLUGIN_RESOURCES):
		if _PLUGIN_RESOURCES not in sys.path:
			sys.path.insert(0, _PLUGIN_RESOURCES)
		break

from GlyphsApp import Glyphs, Message
from htls import engine as engine_mod


def main():
	font = Glyphs.font
	if font is None:
		Message("No font", "Open a font first.")
		return
	layers = font.selectedLayers
	if not layers:
		Message("Nothing selected", "Select some glyphs to space.")
		return

	# space_layers dedupes repeated glyphs, reads the rules once, and wraps the
	# writes in disableUpdateInterface. preserve_components keeps composites in
	# place: a glyph used as a component shifts its referencing components back.
	results = engine_mod.space_layers(layers, preserve_components=True)

	# Build the whole report, then print ONCE (per-layer prints are slow).
	lines = ["Applying HTLS config…\n"]
	spaced = 0
	for layer, engine, sb in results:
		name = layer.parent.name
		if sb is None:
			lines.append("%-16s skipped (no spacing)" % name)
			continue
		spaced += 1
		ref = engine.reference_layer.parent.name if engine.reference_layer else "self"
		lines.append("%-16s LSB=%-5g RSB=%-5g  (factor %.3g, ref %s)" % (
			name, sb[0], sb[1], engine.factor, ref))
	lines.append("\nDone. Spaced %d glyph(s)." % spaced)

	Glyphs.clearLog()
	print("\n".join(lines))


main()
