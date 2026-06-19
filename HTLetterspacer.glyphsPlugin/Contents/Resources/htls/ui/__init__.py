# encoding: utf-8
"""Vanilla UI elements for the management window.

The rules manager follows HT Stroker's Style Manager: a two-column list +
detail editor, embedded as a tab in the single plugin window (NOT a separate
floating window). Add/Remove/Duplicate + a `⋯` pull-down menu live in a
bottom toolbar; the row indicator shows a check when the rule applies to the
selected glyph.
"""
from __future__ import division, print_function, unicode_literals
