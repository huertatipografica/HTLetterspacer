# encoding: utf-8
"""Rule model and resolution.

A rule carries: script, category, subcategory, case, filter, reference,
area {mode, value}, depth {mode, value}, tabular, sides {LSB, RSB},
glyphlist, name. `area`/`depth` are each absolute OR a percentage of the
master's base parameter (`paramArea`/`paramDepth`).

`find_rule` is one deterministic best-match function — it scores each rule in
the glyph's category by specificity (glyphlist, subcategory, case, filter) and
returns `(rule_id, rule)` for the most specific compatible rule, or None.
`glyphlist` is a hard filter: a rule with a non-empty list only applies to the
glyphs it names.

`resolve_area`/`resolve_depth` return the effective absolute value, applying an
optional per-master override (whose omitted area/depth keys mean "inherit").
"""
from __future__ import division, print_function, unicode_literals

ANY = "Any"

DEFAULT_AREA = 400
DEFAULT_DEPTH = 15


# --- matching -------------------------------------------------------------

def find_rule(glyph, font_rules, master=None):
	"""Return `(rule_id, rule)` for the best-matching rule, or None.

	`font_rules` is the flat dict from `config.read_font_rules`:
	`{rule_id: rule}`, each rule carrying a (nullable) `category` field.
	"""
	if not font_rules or glyph is None:
		return None

	name = glyph.name or ""
	category = glyph.category
	subcategory = glyph.subCategory
	case = glyph.case
	script = glyph.script

	best_id = None
	best = None
	best_score = -1
	for rule_id, rule in font_rules.items():
		score = _match_score(rule, name, category, subcategory, case, script)
		if score is None:
			continue
		if score > best_score:
			best_score = score
			best_id = rule_id
			best = rule
	if best is None:
		return None
	return best_id, best


def rank_rules(glyph, font_rules, master=None):
	"""Every rule that matches `glyph`, most-specific first, as
	`[(score, rule_id, rule), …]`. The first entry is the rule the glyph
	actually uses (same winner as `find_rule`); the rest are the fallbacks it
	would follow if the winner didn't exist. Ties keep insertion order, so
	`rank_rules(...)[0]` matches `find_rule`."""
	if not font_rules or glyph is None:
		return []
	name = glyph.name or ""
	category = glyph.category
	subcategory = glyph.subCategory
	case = glyph.case
	script = glyph.script
	matches = []
	for rule_id, rule in font_rules.items():
		score = _match_score(rule, name, category, subcategory, case, script)
		if score is not None:
			matches.append((score, rule_id, rule))
	matches.sort(key=lambda t: t[0], reverse=True)   # stable: ties keep order
	return matches


def _match_score(rule, name, category, subcategory, case, script):
	"""Return a specificity score (higher = more specific) if `rule` is
	compatible with the glyph, else None. Each criterion is either "Any"
	(wildcard, no constraint) or must match exactly."""
	score = 0

	# glyphlist is a hard filter and the most specific criterion
	glyphlist = rule.get("glyphlist") or []
	if glyphlist:
		if name not in glyphlist:
			return None
		score += 8

	rule_category = rule.get("category") or ANY
	if rule_category != ANY:
		if rule_category != category:
			return None
		score += 4

	rule_script = rule.get("script") or ANY
	if rule_script != ANY:
		if rule_script != script:
			return None
		score += 2

	rule_sub = rule.get("subcategory") or ANY
	if rule_sub != ANY:
		if rule_sub != subcategory:
			return None
		score += 2

	rule_case = rule.get("case")
	if rule_case not in (None, 0, ANY, ""):
		# TODO(later): reconcile Glyphs' case enum with stored case values.
		if rule_case != case:
			return None
		score += 2

	# filter may hold several comma-separated substrings; match if ANY is in
	# the glyph name (e.g. ".tf, .tosf" matches both tabular suffixes).
	rule_filter = rule.get("filter") or ""
	if rule_filter:
		tokens = [t.strip() for t in rule_filter.split(",") if t.strip()]
		if tokens:
			if not any(token in name for token in tokens):
				return None
			score += 1

	return score


# --- effective area / depth -----------------------------------------------

def _master_param(master, name, default):
	if master is None:
		return float(default)
	try:
		value = master.customParameters[name]
		return float(value) if value is not None else float(default)
	except Exception:
		return float(default)


def _resolve_spec(spec, base):
	"""Effective value from an {mode, value} spec: absolute -> value;
	percent -> base * value/100. A non-dict spec means 'use the base'."""
	if isinstance(spec, dict):
		mode = spec.get("mode", "percent")
		try:
			value = float(spec.get("value", 100))
		except (TypeError, ValueError):
			return base
		if mode == "absolute":
			return value
		return base * value / 100.0
	return base


def _effective(rule, master_override, key, base):
	"""Pick the override's spec when present, else the rule's spec, then
	resolve against `base`. An omitted override key means 'inherit the rule'."""
	spec = None
	if master_override and isinstance(master_override.get(key), dict):
		spec = master_override.get(key)
	elif rule:
		spec = rule.get(key)
	return _resolve_spec(spec, base)


def resolve_area(rule, master, master_override=None, base=None):
	"""Effective white-area value (thousand units). `base` overrides the
	master's paramArea (used for non-destructive parameter testing)."""
	if base is None:
		base = _master_param(master, "paramArea", DEFAULT_AREA)
	return _effective(rule, master_override, "area", base)


def resolve_depth(rule, master, master_override=None, base=None):
	"""Effective depth. `base` overrides the master's paramDepth."""
	if base is None:
		base = _master_param(master, "paramDepth", DEFAULT_DEPTH)
	return _effective(rule, master_override, "depth", base)
