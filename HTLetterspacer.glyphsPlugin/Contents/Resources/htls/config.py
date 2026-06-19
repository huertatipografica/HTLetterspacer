# encoding: utf-8
"""Config storage, import and export.

Storage model: the **font is the single source of truth at
runtime**. Spacing rules live in `font.userData` (per-master overrides in
master `userData`). `.yml`/`.py` files are import/export only and are never
read while spacing.

Rules are stored **flat**: `font.userData[FONT_RULES_KEY] = {rule_id: rule}`,
each rule carrying a (nullable) `category` field. This lets category — like
script/subcategory/case/filter — be "Any". Legacy eweracs data was bucketed by
category; we flatten it on read.

Namespace & backwards compatibility: we write the new
`com.htfonts.letterspacer` keys and read the legacy `com.eweracs.HTLSManager`
keys (the only legacy data in real fonts). On first save we migrate: write the
new key, delete the legacy one.

This module is intentionally free of GlyphsApp imports so the parser can be
unit-tested off-Glyphs; the font-touching functions only use duck typing.
"""
from __future__ import division, print_function, unicode_literals
import json
import uuid

# --- Storage namespace (new — we WRITE these) -----------------------------
NAMESPACE = "com.htfonts.letterspacer"

FONT_RULES_KEY = NAMESPACE + ".rules"            # font.userData
MASTER_RULES_KEY = NAMESPACE + ".masterRules"    # master.userData
LINKED_MASTER_KEY = NAMESPACE + ".linkedMaster"  # master.userData
DEFAULTS_PREFIX = NAMESPACE                       # Glyphs.defaults["…<prefix>.<name>"]

# --- Legacy keys (read-only; migrate on first save) -----------------------
LEGACY_FONT_RULES_KEY = "com.eweracs.HTLSManager.fontRules"
LEGACY_DEFAULTS_PREFIX = "com.eweracs.HTLSManager"
LEGACY_MASTER_RULES_KEY = "HTLSManagerMasterRules"
LEGACY_LINKED_MASTER_KEY = "HTLSManagerLinkedMaster"

ANY = "Any"
CATEGORIES = ["Letter", "Number", "Punctuation", "Symbol", "Mark"]

# Full-setup export (rules + per-master parameters + per-master overrides).
SETUP_FORMAT = "HTLetterspacer"
SETUP_VERSION = 2
MASTER_PARAMS = ("paramArea", "paramDepth", "paramOver")

# Case is stored as an int matching Glyphs' GSGlyph.case enum
# (0 = any/no-case, 1 = upper, 2 = lower, 3 = smallCaps, 4 = minor, 5 = other).
CASE_NAME_TO_INT = {"*": 0, "Any": 0, "upper": 1, "lower": 2, "smallCaps": 3, "minor": 4, "Other": 5}
INT_TO_CASE_NAME = {0: "*", 1: "upper", 2: "lower", 3: "smallCaps", 4: "minor", 5: "Other"}
# In the original (6-column) format the subcategory column carried the case.
LETTER_SUBCAT_AS_CASE = {"Uppercase": 1, "Lowercase": 2, "Smallcaps": 3}

DEFAULT_AREA = 400

# Keys that mark a dict as a rule (vs a category bucket) when loading.
_RULE_KEYS = ("area", "depth", "subcategory", "case", "sides", "glyphlist",
              "tabular", "reference", "value", "referenceGlyph", "category")


def new_rule_id():
	return uuid.uuid4().hex


def empty_rules():
	"""An empty flat rules dict."""
	return {}


def make_rule(**fields):
	"""A complete new-shape rule from partial fields (UI 'add')."""
	return _normalize_rule(fields)


def default_rules():
	"""A minimal starter rule set for 'Reset to defaults'."""
	rules = {}
	rules[new_rule_id()] = _normalize_rule({
		"category": "Letter", "case": 1, "reference": "H",
		"area": {"mode": "percent", "value": 125}})
	rules[new_rule_id()] = _normalize_rule({
		"category": "Letter", "case": 2, "reference": "x",
		"area": {"mode": "percent", "value": 100}})
	rules[new_rule_id()] = _normalize_rule({
		"category": "Letter", "case": 3, "reference": "h.sc",
		"area": {"mode": "percent", "value": 110}})
	# Tabular figures (.tf / .tosf): keep the advance width fixed. Tabular used
	# to be hardcoded in the script; it is now a rule.
	rules[new_rule_id()] = _normalize_rule({
		"name": "Tabular figures", "category": "Number",
		"filter": ".tf, .tosf", "tabular": True,
		"area": {"mode": "percent", "value": 100}})
	return rules


# --- rule shape normalization ---------------------------------------------

def _normalize_rule(rule, category=None):
	"""Return a complete new-shape rule, filling any missing fields. `category`
	supplies a default when the rule has none (used when flattening buckets)."""
	r = dict(rule) if rule else {}
	out = {
		"name": str(r.get("name") or ""),
		"category": str(r.get("category") or category or ANY) or ANY,
		"script": str(r.get("script") or ANY) or ANY,
		"subcategory": str(r.get("subcategory") or ANY) or ANY,
		"case": int(r.get("case") or 0),
		"filter": str(r.get("filter") or ""),
		"reference": str(r.get("reference") or r.get("referenceGlyph") or ""),
		"area": _normalize_spec(r.get("area"), default_value=100.0),
		"depth": _normalize_spec(r.get("depth"), default_value=100.0),
		"tabular": bool(r.get("tabular") or False),
	}
	sides = r.get("sides") if isinstance(r.get("sides"), dict) else {}
	out["sides"] = {
		"LSB": bool(sides.get("LSB", True)),
		"RSB": bool(sides.get("RSB", True)),
	}
	glyphlist = r.get("glyphlist")
	out["glyphlist"] = [str(g) for g in glyphlist] if glyphlist else []
	return out


def _normalize_spec(spec, default_value):
	if not isinstance(spec, dict):
		return {"mode": "percent", "value": float(default_value)}
	mode = spec.get("mode") or "percent"
	mode = "absolute" if str(mode) == "absolute" else "percent"
	try:
		value = float(spec.get("value", default_value))
	except (TypeError, ValueError):
		value = float(default_value)
	return {"mode": mode, "value": round(value, 4)}


def _convert_legacy_rule(rule, category=None):
	"""Manager rule {subcategory, case, value, referenceGlyph, filter} -> new."""
	r = dict(rule) if rule else {}
	try:
		factor = float(r.get("value", 1))
	except (TypeError, ValueError):
		factor = 1.0
	return _normalize_rule({
		"category": category or ANY,
		"script": ANY,
		"subcategory": r.get("subcategory") or ANY,
		"case": r.get("case") or 0,
		"filter": r.get("filter") or "",
		"reference": r.get("referenceGlyph") or "",
		"area": {"mode": "percent", "value": factor * 100.0},
		"depth": {"mode": "percent", "value": 100.0},
	})


# --- legacy text parsing --------------------------------------------------

def parse_config_text(text):
	"""Parse a legacy `.yml`/`.py` config (comma-separated, two dialects) into
	a flat `{rule_id: rule}` dict. Pure / testable."""
	rules = {}
	for line in text.splitlines():
		rule = _parse_line(line)
		if rule is not None:
			rules[new_rule_id()] = rule
	return rules


def _parse_line(line):
	stripped = line.strip()
	if not stripped or stripped.startswith("#"):
		return None
	parts = line.split(",")
	while parts and parts[-1].strip() == "":
		parts.pop()
	parts = [p.strip() for p in parts]
	if len(parts) < 6:
		return None

	script = parts[0]
	category = parts[1]

	if len(parts) >= 7:
		# Manager 7-col: script,category,subcategory,case,value,reference,filter
		subcategory = parts[2]
		case = CASE_NAME_TO_INT.get(parts[3], 0)
		value = parts[4]
		reference = parts[5]
		filt = parts[6]
	else:
		# original 6-col: script,category,subcategory,value,reference,filter
		subcat_col = parts[2]
		value = parts[3]
		reference = parts[4]
		filt = parts[5]
		if subcat_col in LETTER_SUBCAT_AS_CASE:
			case = LETTER_SUBCAT_AS_CASE[subcat_col]
			subcategory = ANY
		else:
			case = 0
			subcategory = subcat_col

	try:
		factor = float(value)
	except (TypeError, ValueError):
		return None

	category = ANY if category in ("*", "") else category
	subcategory = ANY if subcategory in ("*", "") else subcategory
	reference = "" if reference == "*" else reference
	# multi-value filters are stored ';'-separated in the CSV column (comma is
	# the field delimiter); restore them to comma-separated in the model.
	filt = "" if filt == "*" else filt.replace(";", ",")
	script = ANY if script in ("*", "") else script

	return _normalize_rule({
		"category": category,
		"script": script,
		"subcategory": subcategory,
		"case": case,
		"filter": filt,
		"reference": reference,
		"area": {"mode": "percent", "value": factor * 100.0},
		"depth": {"mode": "percent", "value": 100.0},
	})


# --- NS -> plain conversion -----------------------------------------------

def _to_plain(obj):
	"""Recursively convert NSDictionary/NSArray to plain dict/list."""
	if isinstance(obj, dict):
		return {str(k): _to_plain(v) for k, v in obj.items()}
	if isinstance(obj, (list, tuple)):
		return [_to_plain(v) for v in obj]
	if hasattr(obj, "allKeys") and hasattr(obj, "objectForKey_"):
		return {str(k): _to_plain(obj.objectForKey_(k)) for k in obj.allKeys()}
	if hasattr(obj, "objectAtIndex_") and hasattr(obj, "count"):
		return [_to_plain(obj.objectAtIndex_(i)) for i in range(obj.count())]
	return obj


def _is_rule(value):
	return isinstance(value, dict) and any(k in value for k in _RULE_KEYS)


def _load_rules(raw, convert):
	"""Load a flat `{rule_id: rule}`. Accepts both the new flat shape and a
	legacy/older bucketed `{category: {rule_id: rule}}` shape."""
	plain = _to_plain(raw)
	rules = {}
	if not isinstance(plain, dict):
		return rules
	for key, value in plain.items():
		if _is_rule(value):
			rules[str(key)] = convert(value, None)
		elif isinstance(value, dict):
			# `key` is a category bucket; flatten it.
			for rule_id, rule in value.items():
				if isinstance(rule, dict):
					rules[str(rule_id)] = convert(rule, str(key))
	return rules


# --- font I/O -------------------------------------------------------------

def read_font_rules(font):
	"""Return the font's flat rules `{rule_id: rule}`, preferring the new
	namespace and falling back to the legacy eweracs key (converted). Never
	returns None. Does not mutate the font."""
	raw = font.userData[FONT_RULES_KEY]
	if raw:
		return _load_rules(raw, _normalize_rule)
	legacy = font.userData[LEGACY_FONT_RULES_KEY]
	if legacy:
		return _load_rules(legacy, _convert_legacy_rule)
	return {}


def write_font_rules(font, rules):
	"""Persist rules under the new key and remove the legacy key (one-way
	migration)."""
	font.userData[FONT_RULES_KEY] = rules
	if font.userData[LEGACY_FONT_RULES_KEY] is not None:
		del font.userData[LEGACY_FONT_RULES_KEY]


def migrate_master_rules(font):
	"""Migrate the un-prefixed Manager master keys to the new namespace. The
	legacy single factor becomes an area-only override (omitted depth = inherit;
	plist/userData can't store None)."""
	for master in font.masters:
		legacy = master.userData[LEGACY_MASTER_RULES_KEY]
		if legacy is not None and master.userData[MASTER_RULES_KEY] is None:
			converted = {}
			for rule_id, value in _to_plain(legacy).items():
				try:
					factor = float(value)
				except (TypeError, ValueError):
					continue
				converted[str(rule_id)] = {
					"area": {"mode": "percent", "value": round(factor * 100.0, 4)},
				}
			master.userData[MASTER_RULES_KEY] = converted
		if master.userData[LEGACY_MASTER_RULES_KEY] is not None:
			del master.userData[LEGACY_MASTER_RULES_KEY]

		legacy_link = master.userData[LEGACY_LINKED_MASTER_KEY]
		if legacy_link is not None and master.userData[LINKED_MASTER_KEY] is None:
			master.userData[LINKED_MASTER_KEY] = legacy_link
		if master.userData[LEGACY_LINKED_MASTER_KEY] is not None:
			del master.userData[LEGACY_LINKED_MASTER_KEY]


def migrate_font(font):
	"""One-shot migration when a font is loaded. Returns the rules dict."""
	rules = read_font_rules(font)
	write_font_rules(font, rules)
	migrate_master_rules(font)
	return rules


# --- import / export ------------------------------------------------------

def import_config_file(path, font, replace=False):
	"""Parse a legacy `.yml`/`.py` config and merge it into the font's rules
	(or replace them). Writes to the font. Returns the resulting rules dict."""
	with open(path) as handle:
		text = handle.read()
	parsed = parse_config_text(text)
	if replace:
		rules = parsed
	else:
		rules = read_font_rules(font)
		rules.update(parsed)
	write_font_rules(font, rules)
	return rules


def export_config_file(path, font):
	"""Write the font's rules to a sidecar file (legacy-compatible 7-col CSV)."""
	rules = read_font_rules(font)
	text = serialize_config_text(rules)
	with open(path, "w") as handle:
		handle.write(text)
	return path


def serialize_config_text(rules):
	"""Serialize a flat rules dict to the legacy-compatible 7-column CSV,
	grouped by category. NOTE: depth/absolute-area aren't representable. Pure."""
	lines = [
		"# Script, Category, Subcategory, Case, Value, Reference Glyph, Filter",
		"# Exported by HT Letterspacer. Depth/absolute-area are not "
		"represented in this legacy format.",
	]
	by_category = {}
	for rule in rules.values():
		rule = _normalize_rule(rule)
		by_category.setdefault(rule["category"], []).append(rule)

	for category in sorted(by_category.keys()):
		lines.append("")
		lines.append("# %s" % category)
		cat_token = "*" if category in (ANY, "") else category
		for rule in by_category[category]:
			script = rule["script"]
			script = "*" if script in (ANY, "") else script
			subcat = rule["subcategory"]
			subcat = "*" if subcat in (ANY, "") else subcat
			case = INT_TO_CASE_NAME.get(int(rule["case"]), "*")
			area = rule["area"]
			factor = area["value"] / 100.0 if area["mode"] == "percent" else area["value"] / DEFAULT_AREA
			reference = rule["reference"] or "*"
			# encode multi-value filters with ';' so the comma-delimited row stays intact
			filt = rule["filter"].replace(",", ";").replace(" ", "") if rule["filter"] else "*"
			lines.append(
				"%s,%s,%s,%s,%s,%s,%s," % (
					script, cat_token, subcat, case, round(factor, 3), reference, filt,
				)
			)
	return "\n".join(lines) + "\n"


# --- full setup (v2 JSON: rules + master params + master overrides) -------

def _master_params(master):
	"""The HTLS custom parameters set on `master`, as plain ints (only the ones
	actually present — an absent param means 'inherit the engine default')."""
	params = {}
	for name in MASTER_PARAMS:
		try:
			value = master.customParameters[name]
		except Exception:
			value = None
		if value is not None:
			try:
				params[name] = int(float(value))
			except (TypeError, ValueError):
				pass
	return params


def serialize_setup(font):
	"""Serialize the whole setup to a v2 JSON string: the flat font rules (each
	carrying its id, so overrides can reference it) plus, per master, its
	paramArea/Depth/Over and its rule overrides. Lossless and portable — masters
	are keyed by name so the file can be imported into a different font."""
	rules = read_font_rules(font)
	rule_list = []
	for rule_id, rule in rules.items():
		entry = _normalize_rule(rule)
		entry["id"] = str(rule_id)
		rule_list.append(entry)

	masters = []
	for master in font.masters:
		raw = master.userData[MASTER_RULES_KEY]
		overrides = _to_plain(raw) if raw else {}
		masters.append({
			"name": master.name,
			"id": master.id,
			"parameters": _master_params(master),
			"overrides": overrides if isinstance(overrides, dict) else {},
		})

	doc = {
		"format": SETUP_FORMAT,
		"version": SETUP_VERSION,
		"familyName": getattr(font, "familyName", "") or "",
		"rules": rule_list,
		"masters": masters,
	}
	return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def export_setup_file(path, font):
	"""Write the font's full setup to a `.json` sidecar (v2)."""
	with open(path, "w") as handle:
		handle.write(serialize_setup(font))
	return path


def parse_setup_text(text):
	"""Parse + validate a v2 setup JSON string. Raises ValueError on a file that
	isn't an HT Letterspacer setup (e.g. a legacy `.yml`)."""
	try:
		data = json.loads(text)
	except ValueError:
		raise ValueError("Not a valid JSON setup file.")
	if not isinstance(data, dict) or data.get("format") != SETUP_FORMAT:
		raise ValueError("Not an HT Letterspacer setup file.")
	if int(data.get("version", 0) or 0) < 2:
		raise ValueError("Unsupported setup version (expected 2+).")
	return data


def setup_master_names(data):
	"""The master names present in a parsed setup, in file order (used to build
	the import mapping UI)."""
	out = []
	for m in data.get("masters", []):
		if isinstance(m, dict):
			out.append(str(m.get("name", "")))
	return out


def import_setup(font, data, master_map=None, replace_rules=True, import_params=False):
	"""Apply a parsed v2 setup to `font`.

	`master_map` maps a config master NAME -> a target `master.id` in this font
	(or omit / None to skip that config master's params + overrides). Rules are
	replaced or merged per `replace_rules`; their ids are kept so the overrides
	still resolve. When `import_params` is False the masters' paramArea/Depth/Over
	are left untouched (only the rule overrides are applied). Returns the
	resulting font rules dict."""
	parsed_rules = {}
	for r in data.get("rules", []):
		if not isinstance(r, dict):
			continue
		rule_id = str(r.get("id") or new_rule_id())
		parsed_rules[rule_id] = _normalize_rule(r)

	if replace_rules:
		rules = parsed_rules
	else:
		rules = read_font_rules(font)
		rules.update(parsed_rules)
	write_font_rules(font, rules)

	master_map = master_map or {}
	masters_by_id = {m.id: m for m in font.masters}
	for cm in data.get("masters", []):
		if not isinstance(cm, dict):
			continue
		target_id = master_map.get(str(cm.get("name", "")))
		target = masters_by_id.get(target_id) if target_id else None
		if target is None:
			continue
		# parameters (only those present in the file) — opt-in
		if import_params:
			params = cm.get("parameters") or {}
			for name in MASTER_PARAMS:
				if params.get(name) is not None:
					try:
						target.customParameters[name] = int(params[name])
					except (TypeError, ValueError):
						pass
		# overrides — keep only those pointing at a rule we actually imported
		raw_ov = cm.get("overrides") or {}
		clean = {rid: spec for rid, spec in raw_ov.items() if spec and rid in rules}
		if clean:
			target.userData[MASTER_RULES_KEY] = clean
		elif target.userData[MASTER_RULES_KEY] is not None:
			del target.userData[MASTER_RULES_KEY]

	return rules
