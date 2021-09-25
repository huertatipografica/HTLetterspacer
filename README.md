
# Huerta Tipográfica Letterspacer

HT Letterspacer is a tool for spacing fonts, that works on finished fonts as well as during development.
The first public version works as a macro for [Glyphs](https://glyphsapp.com) and uses that application's glyph categories and subcategories feature, but the method is adaptable to any editor or programming language.

# Glyphs 3 update and good GlyphData practices

If you are migrating from Glyphs 2 to Glyphs 3, categories and subcategories are different, so your spacing results will be different especially for punctuation, but it might include other categories/subcategories. If you want to keep your spacing working the same way, please include G2 GlyphData.xml in your project. 

Otherwise you would need to update the config with new categories matching.

To roll your own Glyph data follow this tutorial: https://glyphsapp.com/learn/roll-your-own-glyph-data
This is very recommended as you can have your own categories and spacing schemes.

For Glyphs 3 (if default glyph data is not overriden), letters Subcategory has been removed and replaced with new case category. HT Letterspacer automatically takes the case and evaluate it as a subCategory value: upper [1], smallCaps [3] and lowercase [2], unless subCategory has been updated. The case value minor [4] is ignored as it still keeps the same values.



### [Visit the project homepage](https://huertatipografica.github.io/HTLetterspacer/)

### Change Log

Version 1.20
- Improve code simplicity and syntax by Nikolaus and Georg
- Add Glyphs 3 compatibility
- Improve diagonize and drawing calculations
- Fix bugs with reference zones
- Improve performance with less measurements
- Restore original configuration for both G2 and G3

Version 1.11
- Code merged in one script file
- createProofGlyph renamed to drawAreas
- Fixed bug with empty tabular field
- parameters can be float, tabular value is integer

Version 1.10
- Copy parameters to clipboard (thanks mekkablue)
- Robofab no longer required for drawing _areas
- No more code repetition

### TO DO

tabVersion for suffixes:
- This part is not working and returns error when .tf or .tosf is present
- Suffixes intended to be tabular ('.tf', '.tosf', etc) need to be in a list in the initial config and not in the middle of the code
- When the UI, if Tabular is activated it should change the boxes width even for glyphs with suffixes
- TabVersion should be easily fixed from config, to work in monospaced fonts