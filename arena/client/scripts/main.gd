extends Node2D
## Arena overlay controller. Subscribes to the `Net` event feed and renders the
## round: fighter+dummy pairs on a circle facing inward (right-half fighters
## are flipped), the d20 head-rolls and floating damage, a sorted damage meter
## (numbers, no bars) in the middle of the circle, a phase countdown, and the
## winner highlight. Monster rounds put the monster at the circle center
## (dummies hidden, meter moves top-left). Holds only view state derived from
## server events (the server is authoritative; this is a dumb renderer).

const FighterScript := preload("res://scripts/fighter.gd")

# Layout (fractions of the viewport; seed values — tune from screenshots).
const ARENA_CENTER := Vector2(0.5, 0.55)  # circle center (below the countdown/banner)
const CIRCLE_RADIUS := 0.36               # fraction of min(viewport w, h)
const ARC_SPAN := PI * 0.75               # each side's arc (poles left empty — no
										  # fighter at the exact top/bottom)
const FIGHTER_SCALE := 1.5                # bigger fighters + dummies (labels scale too)
# Damage meter: sorted "Name  total" rows, centered in the circle (race mode)
# or pinned top-left when the monster owns the center.
const METER_ROW_H := 26.0
const METER_WIDTH := 340.0
const METER_TOP_LEFT := Vector2(24, 90)
const METER_LEADER_COLOR := Color(1.0, 0.85, 0.2)
const METER_SLIDE_S := 0.6                # row slide when the ranking changes (seconds)

# The overlay event ticker is the PRIMARY command-feedback channel (PLAN.md
# §6.1): every command outcome arrives here as a {type:"ticker"} message.
const TICKER_MAX_LINES := 6
const TICKER_KIND_COLORS := {
	"create": Color(0.55, 0.9, 0.55),
	"enter": Color(0.5, 0.8, 1.0),
	"retire": Color(0.82, 0.7, 0.95),
	"winner": Color(1.0, 0.85, 0.2),
	"error": Color(1.0, 0.5, 0.4),
	"bet": Color(0.95, 0.8, 0.35),
	"reward": Color(0.65, 0.9, 0.95),
	"event": Color(0.95, 0.55, 0.85),
	"mod": Color(0.7, 0.78, 0.85),
	"info": Color(0.85, 0.85, 0.85),
}
const EVENT_BANNER_COLOR := Color(0.95, 0.55, 0.85)
# R4 co-op monster battle overlay (docs/R4_R6_plan.md): a tiered monster with an
# HP bar sits top-center; the team whittles it down while it knocks fighters out.
const MONSTER_DIR := "res://assets/sprites/monster/"
const MONSTER_HP_COLOR := Color(0.85, 0.25, 0.25)
const TIER_ROMAN := ["", "I", "II", "III", "IV", "V"]
# Small platform badge so viewers can tell same-named users apart (PLAN.md §6.5).
const PLATFORM_GLYPH := {
	"twitch": "TW",
	"youtube": "YT",
	"tiktok": "TT",
}

var _fighters: Dictionary = {}       # slot:int -> Fighter
var _meter_labels: Dictionary = {}   # slot:int -> Label (one damage-meter row)
var _meter_targets: Dictionary = {}  # slot:int -> Vector2 (row's settled position)
var _meter_tweens: Dictionary = {}   # slot:int -> Tween (in-flight row slide)

var _arena_layer: Node2D
var _background: ColorRect
var _ui: CanvasLayer
var _countdown_label: Label
var _status_label: Label
var _event_label: Label
var _bars_root: Control
var _ticker_root: VBoxContainer

# Monster-battle overlay nodes (built once, shown only on monster rounds).
# HUD (label + HP bar + banner) stays top-center; the monster BODY lives on
# _monster_anchor, a Node2D mid-arena that the fighters flank.
var _monster_root: Control
var _monster_anchor: Node2D
var _monster_body: ColorRect        # placeholder blob, shown when no per-tier art
var _monster_art: TextureRect        # per-tier PNG when present (lazily built)
var _monster_label: Label
var _monster_hp_bg: ColorRect
var _monster_hp_fill: ColorRect
var _team_banner: Label
var _monster_hp_max: int = 1
var _monster_mode: bool = false      # current round is a monster battle
var _last_fighters: Array = []       # last round_start/sync roster (for re-flow)


func _ready() -> void:
	_build_static_ui()
	Net.connection_changed.connect(_on_connection_changed)
	Net.sync_state.connect(_on_sync)
	Net.round_start.connect(_on_round_start)
	Net.attack.connect(_on_attack)
	Net.round_end.connect(_on_round_end)
	Net.countdown.connect(_on_countdown)
	Net.ticker.connect(_on_ticker)
	Net.ability.connect(_on_ability)
	Net.arena_event.connect(_on_arena_event)
	Net.monster_spawn.connect(_on_monster_spawn)
	Net.monster_hp.connect(_on_monster_hp)
	Net.monster_attack.connect(_on_monster_attack)
	Net.fighter_ko.connect(_on_fighter_ko)
	Net.team_result.connect(_on_team_result)


func _build_static_ui() -> void:
	var size := get_viewport_rect().size

	_background = ColorRect.new()
	_background.color = Color(0.0, 0.5, 0.0)  # chroma-key green; swap for art later
	_background.size = size
	_background.z_index = -100
	add_child(_background)

	_arena_layer = Node2D.new()
	add_child(_arena_layer)

	_ui = CanvasLayer.new()
	add_child(_ui)

	_countdown_label = Label.new()
	_countdown_label.position = Vector2(size.x / 2 - 200, 20)
	_countdown_label.size = Vector2(400, 40)
	_countdown_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_countdown_label.add_theme_font_size_override("font_size", 28)
	_ui.add_child(_countdown_label)

	_status_label = Label.new()
	_status_label.position = Vector2(24, 20)
	_status_label.add_theme_font_size_override("font_size", 16)
	_status_label.text = "connecting..."
	_ui.add_child(_status_label)

	# Arena-event banner (PLAN.md §4.6): shows the round's global modifier under
	# the countdown for the whole round; cleared when a round has no event.
	_event_label = Label.new()
	_event_label.position = Vector2(size.x / 2 - 200, 58)
	_event_label.size = Vector2(400, 30)
	_event_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_event_label.add_theme_font_size_override("font_size", 20)
	_event_label.modulate = EVENT_BANNER_COLOR
	_ui.add_child(_event_label)

	_bars_root = Control.new()
	_ui.add_child(_bars_root)

	# Event ticker: a stack of the most recent outcome lines along the bottom.
	_ticker_root = VBoxContainer.new()
	_ticker_root.position = Vector2(24, size.y - 150)
	_ticker_root.size = Vector2(size.x - 48, 140)
	_ticker_root.add_theme_constant_override("separation", 2)
	_ui.add_child(_ticker_root)

	_build_monster_ui(size)


func _build_monster_ui(size: Vector2) -> void:
	# HUD (name + HP bar) top-center; hidden until a monster round spawns one.
	var cx := size.x / 2.0
	_monster_root = Control.new()
	_monster_root.visible = false
	_ui.add_child(_monster_root)

	# The monster body sits mid-arena on its own anchor so the fighters can
	# flank it (attack effects and recoil play here too).
	_monster_anchor = Node2D.new()
	_monster_anchor.position = Vector2(size.x * ARENA_CENTER.x, size.y * ARENA_CENTER.y)
	_monster_anchor.visible = false
	_arena_layer.add_child(_monster_anchor)

	# Placeholder blob; swapped for per-tier art in _on_monster_spawn when present.
	var placeholder := ColorRect.new()
	placeholder.position = Vector2(-80, -80)
	placeholder.size = Vector2(160, 160)
	placeholder.color = Color(0.35, 0.12, 0.14)
	_monster_anchor.add_child(placeholder)
	_monster_body = placeholder

	_monster_label = Label.new()
	_monster_label.position = Vector2(cx - 200, 74)
	_monster_label.size = Vector2(400, 22)
	_monster_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_monster_label.add_theme_font_size_override("font_size", 18)
	_monster_root.add_child(_monster_label)

	_monster_hp_bg = ColorRect.new()
	_monster_hp_bg.position = Vector2(cx - 160, 100)
	_monster_hp_bg.size = Vector2(320, 18)
	_monster_hp_bg.color = Color(0, 0, 0, 0.5)
	_monster_root.add_child(_monster_hp_bg)

	_monster_hp_fill = ColorRect.new()
	_monster_hp_fill.position = _monster_hp_bg.position
	_monster_hp_fill.size = Vector2(320, 18)
	_monster_hp_fill.color = MONSTER_HP_COLOR
	_monster_root.add_child(_monster_hp_fill)

	# Team victory/defeat banner, popped over the arena at round end.
	_team_banner = Label.new()
	_team_banner.position = Vector2(cx - 260, 130)
	_team_banner.size = Vector2(520, 40)
	_team_banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_team_banner.add_theme_font_size_override("font_size", 34)
	_team_banner.visible = false
	_ui.add_child(_team_banner)


func _on_connection_changed(connected: bool) -> void:
	_status_label.text = "LIVE" if connected else "reconnecting..."
	_status_label.modulate = Color(0.4, 1, 0.4) if connected else Color(1, 0.6, 0.3)


func _clear_round() -> void:
	for child in _arena_layer.get_children():
		if child == _monster_anchor:
			continue  # persistent monster body anchor; only hidden, never freed
		child.queue_free()
	for child in _bars_root.get_children():
		child.queue_free()
	for tw in _meter_tweens.values():
		if tw != null and (tw as Tween).is_valid():
			(tw as Tween).kill()  # never tween a freed label
	_fighters.clear()
	_meter_labels.clear()
	_meter_targets.clear()
	_meter_tweens.clear()


func _spawn_fighters(fighters: Array, monster_round: bool = false) -> void:
	_clear_round()
	var size := get_viewport_rect().size
	var center := Vector2(size.x * ARENA_CENTER.x, size.y * ARENA_CENTER.y)
	var radius: float = min(size.x, size.y) * CIRCLE_RADIUS

	# Fighter+dummy pairs on the circle, mirrored 4/4: the first half sits on a
	# left arc (facing right), the second half on the mirrored right arc
	# (flipped, dummy toward the middle). Each side spreads across ARC_SPAN
	# centered on the horizontal, so nobody lands at the awkward top/bottom
	# poles. Monster rounds use the same circle with dummies hidden — the
	# monster owns the center.
	var sorted := fighters.duplicate()
	sorted.sort_custom(func(a, b): return int(a.get("slot", 0)) < int(b.get("slot", 0)))
	var half: int = int(ceil(float(sorted.size()) / 2.0))

	for i in range(sorted.size()):
		var data: Dictionary = sorted[i]
		var slot := int(data.get("slot", 0))
		var on_left: bool = i < half
		var side_count: int = half if on_left else sorted.size() - half
		var row: int = i if on_left else i - half
		var offset: float = ((float(row) + 0.5) / float(max(1, side_count)) - 0.5) * ARC_SPAN
		var angle: float = PI + offset if on_left else -offset
		var face_left: bool = not on_left

		var node: Fighter = FighterScript.new()
		node.position = center + Vector2(cos(angle), sin(angle)) * radius
		node.scale = Vector2(FIGHTER_SCALE, FIGHTER_SCALE)
		_arena_layer.add_child(node)
		node.setup(data, face_left)
		if monster_round:
			node.set_dummy_visible(false)
		_fighters[slot] = node
		_add_meter_row(slot, node.fighter_name)
	_refresh_meter()


func _add_meter_row(slot: int, name: String) -> void:
	var label := Label.new()
	label.text = name
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.size = Vector2(METER_WIDTH, METER_ROW_H)
	label.add_theme_font_size_override("font_size", 18)
	_bars_root.add_child(label)
	_meter_labels[slot] = label


func _meter_origin(rows: int) -> Vector2:
	# Monster rounds: the monster owns the circle center, so the meter moves
	# top-left. Races: centered in the middle of the fighter circle.
	if _monster_mode:
		return METER_TOP_LEFT
	var size := get_viewport_rect().size
	return Vector2(
		size.x * ARENA_CENTER.x - METER_WIDTH / 2.0,
		size.y * ARENA_CENTER.y - float(rows) * METER_ROW_H / 2.0,
	)


func _meter_order(a: int, b: int) -> bool:
	# Highest damage first; tiebreak on slot so equal totals keep a stable
	# order (sort_custom isn't stable — without this, ties would jitter).
	var ta: int = _fighters[a].total
	var tb: int = _fighters[b].total
	if ta != tb:
		return ta > tb
	return a < b


func _refresh_meter() -> void:
	# Numbers-only damage meter, sorted highest first; the leader reads gold.
	# Rows that change rank glide to their new spot instead of snapping.
	var order := _fighters.keys()
	order.sort_custom(_meter_order)
	var origin := _meter_origin(order.size())
	for i in range(order.size()):
		var slot: int = order[i]
		var label: Label = _meter_labels.get(slot)
		if label == null:
			continue
		label.text = "%s  %d" % [_fighters[slot].fighter_name, _fighters[slot].total]
		var leading: bool = i == 0 and _fighters[slot].total > 0
		label.modulate = METER_LEADER_COLOR if leading else Color(1, 1, 1)
		_place_meter_row(slot, label, origin + Vector2(0, float(i) * METER_ROW_H))


func _place_meter_row(slot: int, label: Label, target: Vector2) -> void:
	# First layout of the round snaps into place; later rank changes slide.
	# The settled target is tracked per row so a refresh that doesn't move the
	# row never restarts an in-flight glide.
	if not _meter_targets.has(slot):
		_meter_targets[slot] = target
		label.position = target
		return
	if _meter_targets[slot] == target:
		return
	_meter_targets[slot] = target
	var prev: Tween = _meter_tweens.get(slot)
	if prev != null and prev.is_valid():
		prev.kill()
	var tw := create_tween()
	tw.set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_CUBIC)
	tw.tween_property(label, "position", target, METER_SLIDE_S)
	_meter_tweens[slot] = tw


# --- server events ---------------------------------------------------------
func _set_event_banner(event: Variant) -> void:
	# `event` is {"name","label"} or null; the banner persists for the round.
	if typeof(event) == TYPE_DICTIONARY:
		_event_label.text = "* %s *" % String((event as Dictionary).get("label", ""))
	else:
		_event_label.text = ""


func _on_sync(data: Dictionary) -> void:
	var phase := String(data.get("phase", ""))
	if phase == "idle":
		# Arena closed: clear everything and show the closed screen.
		_clear_round()
		_hide_monster()
		_monster_mode = false
		_set_event_banner(null)
		_countdown_label.text = "ARENA CLOSED"
		return

	var kind := "race"
	var tier := 0
	var monster_info: Variant = null
	var round_info: Variant = data.get("round")
	if typeof(round_info) == TYPE_DICTIONARY:
		var rd := round_info as Dictionary
		kind = String(rd.get("kind", "race")) if rd.get("kind") != null else "race"
		tier = int(rd.get("tier", 0)) if rd.get("tier") != null else 0
		monster_info = rd.get("monster")
		_set_event_banner(rd.get("event"))
	_monster_mode = kind == "monster"

	if data.has("fighters") and (data["fighters"] as Array).size() > 0:
		_hide_monster()
		_last_fighters = data["fighters"]
		_spawn_fighters(_last_fighters, _monster_mode)

	# Late join mid-monster-round: restore the monster UI. The bar starts full
	# and self-corrects on the next monster_hp event (absolute remaining).
	if _monster_mode and typeof(monster_info) == TYPE_DICTIONARY:
		var m := monster_info as Dictionary
		_monster_hp_max = max(1, int(m.get("hp", 1)))
		_monster_hp_fill.size.x = _monster_hp_bg.size.x
		_monster_label.text = "Tier %s  %s" % [_roman(tier), String(m.get("label", "Monster"))]
		_apply_monster_art(tier)
		_team_banner.visible = false
		_monster_root.visible = true
		_monster_root.modulate.a = 1.0
		_monster_anchor.visible = true
		_monster_anchor.modulate.a = 1.0

	_countdown_label.text = phase.to_upper()


func _on_round_start(data: Dictionary) -> void:
	_hide_monster()  # monster_spawn (right after round_start) re-shows it
	_monster_mode = String(data.get("kind", "race")) == "monster"
	_last_fighters = data.get("fighters", [])
	_spawn_fighters(_last_fighters, _monster_mode)
	_set_event_banner(data.get("event"))
	_countdown_label.text = "ROUND %d" % int(data.get("round_id", 0))


func _on_arena_event(data: Dictionary) -> void:
	# The round's arena event announcement: set the banner and pop it so the
	# modifier registers even for viewers not watching the ticker.
	_set_event_banner(data)
	_event_label.scale = Vector2(1.6, 1.6)
	create_tween().tween_property(_event_label, "scale", Vector2.ONE, 0.4)


func _on_attack(data: Dictionary) -> void:
	var slot := int(data.get("slot", -1))
	var node: Fighter = _fighters.get(slot)
	if node == null:
		return
	var total := int(data.get("running_total", 0))
	var crit := bool(data.get("crit", false))
	var miss := bool(data.get("miss", false))
	node.show_attack(int(data.get("roll", 0)), int(data.get("damage", 0)), crit, miss, total)
	# Monster rounds: the shared monster is the target — play the attacker's hit
	# effect on it (keyed by weapon/class) plus a small recoil. Misses show nothing.
	if _monster_mode and not miss and _monster_anchor.visible:
		HitEffect.play(_monster_anchor, Vector2(0, -10), node.effect_key(), crit)
		_recoil_monster()
	_refresh_meter()


func _recoil_monster() -> void:
	# Absolute endpoints around the anchor's resting x so bursts never drift it.
	var base_x: float = get_viewport_rect().size.x * ARENA_CENTER.x
	var tw := create_tween()
	tw.tween_property(_monster_anchor, "position:x", base_x + 5.0, 0.05)
	tw.tween_property(_monster_anchor, "position:x", base_x - 5.0, 0.05)
	tw.tween_property(_monster_anchor, "position:x", base_x, 0.05)


func _on_round_end(data: Dictionary) -> void:
	var standings: Array = data.get("standings", [])
	for s in standings:
		var entry: Dictionary = s
		if int(entry.get("placement", 0)) == 1:
			var node: Fighter = _fighters.get(int(entry.get("slot", -1)))
			if node != null:
				node.set_winner()
	if standings.size() > 0:
		var w: Dictionary = standings[0]
		_countdown_label.text = "WINNER: %s (%d)" % [w.get("name", "?"), int(w.get("total", 0))]


func _on_countdown(data: Dictionary) -> void:
	var phase := String(data.get("phase", ""))
	var secs := int(data.get("seconds_left", 0))
	if phase == "idle":
		_countdown_label.text = "ARENA CLOSED — mods: !start"
		return
	if phase == "combat":
		_countdown_label.text = "FIGHT!  %ds" % secs
		return
	_countdown_label.text = "%s  %ds" % [phase.to_upper(), secs]


func _on_ability(data: Dictionary) -> void:
	# A signature ability fired mid-round: play the fighter's "big animation"
	# (PLAN.md §4.2). Damage lands via later attacks' running totals.
	var node: Fighter = _fighters.get(int(data.get("slot", -1)))
	if node != null:
		node.cast_ability(String(data.get("ability", "")))


func _on_ticker(data: Dictionary) -> void:
	# Primary command-feedback channel: append the outcome, keep the last few,
	# tint by kind, and prefix a platform badge (PLAN.md §6.1, §6.5).
	var kind := String(data.get("kind", "info"))
	var text := String(data.get("text", ""))
	var glyph: String = PLATFORM_GLYPH.get(String(data.get("platform", "")), "")

	var line := Label.new()
	line.text = "[%s] %s" % [glyph, text] if glyph != "" else text
	line.add_theme_font_size_override("font_size", 15)
	line.modulate = TICKER_KIND_COLORS.get(kind, Color(1, 1, 1))
	_ticker_root.add_child(line)

	while _ticker_root.get_child_count() > TICKER_MAX_LINES:
		var oldest := _ticker_root.get_child(0)
		_ticker_root.remove_child(oldest)
		oldest.queue_free()

	line.modulate.a = 0.0
	create_tween().tween_property(line, "modulate:a", 1.0, 0.25)


# --- R4 monster battle -----------------------------------------------------
func _roman(tier: int) -> String:
	return TIER_ROMAN[tier] if tier >= 0 and tier < TIER_ROMAN.size() else str(tier)


func _hide_monster() -> void:
	if _monster_root != null:
		_monster_root.visible = false
	if _monster_anchor != null:
		_monster_anchor.visible = false
	if _team_banner != null:
		_team_banner.visible = false


func _apply_monster_art(tier: int) -> void:
	# Per-tier PNG by convention (res://assets/sprites/monster/tier<N>.png), with a
	# tinted placeholder blob when the art isn't present — same fail-soft rule as
	# the fighters, so the overlay runs with zero monster art. Lives mid-arena on
	# the anchor so the flanking fighters' effects land on it.
	var path := MONSTER_DIR + "tier%d.png" % tier
	var has_art := ResourceLoader.exists(path)
	if _monster_art == null:
		_monster_art = TextureRect.new()
		_monster_art.position = _monster_body.position
		_monster_art.size = _monster_body.size
		_monster_art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		_monster_anchor.add_child(_monster_art)
	_monster_art.texture = load(path) if has_art else null
	_monster_art.visible = has_art
	_monster_body.visible = not has_art
	# Redder placeholder as the ladder climbs, so tiers read at a glance.
	_monster_body.color = Color(0.28 + 0.11 * float(tier) / 5.0, 0.12, 0.14)


func _on_monster_spawn(data: Dictionary) -> void:
	if not _monster_mode:
		# Fail-soft for a round_start payload without `kind`: re-flow the roster
		# into the monster layout now (monster_spawn arrives right after it).
		_monster_mode = true
		_spawn_fighters(_last_fighters, true)
	_monster_hp_max = max(1, int(data.get("hp", 1)))
	_monster_hp_fill.size.x = _monster_hp_bg.size.x
	var tier := int(data.get("tier", 0))
	_monster_label.text = "Tier %s  %s" % [_roman(tier), String(data.get("label", "Monster"))]
	_apply_monster_art(tier)
	_team_banner.visible = false
	_monster_root.visible = true
	_monster_root.modulate.a = 0.0
	create_tween().tween_property(_monster_root, "modulate:a", 1.0, 0.3)
	_monster_anchor.visible = true
	_monster_anchor.modulate.a = 0.0
	create_tween().tween_property(_monster_anchor, "modulate:a", 1.0, 0.3)


func _on_monster_hp(data: Dictionary) -> void:
	if not _monster_root.visible:
		return
	var remaining := int(data.get("remaining", 0))
	var frac: float = clampf(float(remaining) / float(_monster_hp_max), 0.0, 1.0)
	create_tween().tween_property(
		_monster_hp_fill, "size:x", _monster_hp_bg.size.x * frac, 0.15
	)


func _on_monster_attack(data: Dictionary) -> void:
	# The monster swung at a fighter (damage 0 = a miss); the KO, if any, arrives as
	# a separate fighter_ko event.
	var node: Fighter = _fighters.get(int(data.get("target_slot", -1)))
	if node != null:
		node.take_monster_hit(int(data.get("damage", 0)))


func _on_fighter_ko(data: Dictionary) -> void:
	var node: Fighter = _fighters.get(int(data.get("slot", -1)))
	if node != null:
		node.set_ko()


func _on_team_result(data: Dictionary) -> void:
	var victory := bool(data.get("victory", false))
	var tier: Variant = data.get("tier")
	var tier_txt := "" if tier == null else " (Tier %s)" % _roman(int(tier))
	_team_banner.text = ("TEAM VICTORY!" + tier_txt) if victory else ("TEAM DEFEAT" + tier_txt)
	_team_banner.modulate = Color(1.0, 0.85, 0.25) if victory else Color(1.0, 0.45, 0.4)
	_team_banner.visible = true
	_team_banner.scale = Vector2(1.4, 1.4)
	create_tween().tween_property(_team_banner, "scale", Vector2.ONE, 0.35)
