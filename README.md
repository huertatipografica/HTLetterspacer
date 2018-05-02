
# Huerta Tipográfica Letterspacer

HT Letterspacer is a tool for spacing fonts, that works on finished fonts as well as during development.
The first public version works as a macro for [Glyphs](https://glyphsapp.com) and uses that application's glyph categories and subcategories feature, but the method is adaptable to any editor or programming language.

### [Visit the project homepage](https://huertatipografica.github.io/HTLetterspacer/)

### Change Log

Version 1.10
- Copy parameters to clipboard (thanks mekkablue)
- Robofab no longer required for drawing _areas
- No more code repetition

Version 1.11
- Code merged in one script file
- createProofGlyph renamed to drawAreas
- Fixed bug with empty tabular field
- parameters can be float, tabular value is integer

### TO DO

tabVersion for suffixes:
- This part is not working and returns error when .tf or .tosf is present
- Suffixes intended to be tabular ('.tf', '.tosf', etc) need to be in a list in the initial config and not in the middle of the code
- When the UI, if Tabular is activated it should change the boxes width even for glyphs with suffixes
- TabVersion should be easily fixed from config, to work in monospaced fonts