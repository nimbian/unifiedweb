class_name Fighter
extends Node2D
## One arena fighter's visuals. Renders LPC layered sprites when art is present
## (PLAN.md §7, Option A) and falls back to colored placeholder shapes when it
## isn't — so the overlay runs with zero assets. The public interface
## (`setup` / `show_attack` / `set_winner`, plus `fighter_name` / `total`) is the
## same either way, so `main.gd` is unaware of which path is active.

var slot: int = 0
var fighter_name: String = "?"
var owner_name: String = ""
var owner_platform: String = ""
var char_class: String = ""
var sprite_set: String = ""
var dummy_sprite: String = ""
var personality: String = ""
var is_npc: bool = false
var total: int = 0
var gear: Dictionary = {}     # slot:String -> item_id:String (R5 paper-doll)
var is_ko: bool = false       # R4 monster round: knocked out this round
var face_left: bool = false   # true = fighter stands right of its target, flipped

var _avatar: Node2D          # the body node (LayeredSprite or placeholder diamond)
var _sprite: LayeredSprite   # non-null only when LPC art loaded
var _dummy: Node2D
var _name_label: Label
var _roll_label: Label
var _lunge_tween: Tween

const DUMMY_DIR := "res://assets/sprites/dummy/"
const SPRITE_DIR := "res://assets/sprites/"
const DUMMY_OFFSET := 84.0        # dummy stands beside the fighter, on the facing side
const LABEL_AWAY_SHIFT := 14.0    # nudge text away from the dummy side
const LUNGE_DIST := 12.0          # placeholder attack lunge distance (no-art path)

# R5 paper-doll: each gear slot maps to one LPC layer, loaded by convention from
# res://assets/sprites/<layer>/<item_id>.png. Trinkets have no body layer (their
# effect is stat-only), so they're intentionally absent here.
const GEAR_LAYER := {
	"weapon": "weapon",
	"armor": "torso",
}
const KO_TINT := Color(0.42, 0.42, 0.48)

# Platform badge glyph shown next to the owner (PLAN.md §6.5) — distinguishes
# same-named users across platforms.
const PLATFORM_GLYPH := {
	"twitch": "TW",
	"youtube": "YT",
	"tiktok": "TT",
}

const CLASS_COLORS := {
	"barbarian": Color(0.78, 0.28, 0.22),
	"fighter": Color(0.70, 0.55, 0.30),
	"rogue": Color(0.35, 0.35, 0.42),
	"monk": Color(0.85, 0.70, 0.35),
	"paladin": Color(0.85, 0.80, 0.55),
	"ranger": Color(0.30, 0.55, 0.30),
	"warlock": Color(0.45, 0.25, 0.55),
	"wizard": Color(0.30, 0.45, 0.75),
	"cleric": Color(0.90, 0.85, 0.60),
	"bard": Color(0.85, 0.45, 0.65),
	"artificer": Color(0.55, 0.60, 0.65),
	"druid": Color(0.40, 0.60, 0.35),
	"sorcerer": Color(0.70, 0.30, 0.40),
}


func setup(data: Dictionary, p_face_left: bool = false) -> void:
	face_left = p_face_left
	slot = int(data.get("slot", 0))
	fighter_name = String(data.get("name", "?"))
	owner_name = String(data.get("owner", "")) if data.get("owner") != null else ""
	owner_platform = String(data.get("platform", "")) if data.get("platform") != null else ""
	char_class = String(data.get("class", ""))
	sprite_set = String(data.get("sprite", "")) if data.get("sprite") != null else ""
	dummy_sprite = String(data.get("dummy_sprite", "")) if data.get("dummy_sprite") != null else ""
	personality = String(data.get("personality", "")) if data.get("personality") != null else ""
	is_npc = bool(data.get("is_npc", false))
	gear = data.get("gear", {}) if typeof(data.get("gear")) == TYPE_DICTIONARY else {}
	_build()


func _build() -> void:
	_build_dummy()
	_build_body()
	_build_labels()


func _build_dummy() -> void:
	# Real dummy sheet if present, else a small brown placeholder post. The dummy
	# stands BESIDE the fighter on the facing side (left-half fighters face right,
	# so their dummy is at +x; right-half fighters are mirrored).
	var dummy_x: float = -DUMMY_OFFSET if face_left else DUMMY_OFFSET
	var path := DUMMY_DIR + dummy_sprite + ".png"
	if dummy_sprite != "" and ResourceLoader.exists(path):
		var s := Sprite2D.new()
		s.texture = load(path)
		s.position = Vector2(dummy_x, -14)
		_dummy = s
	else:
		var poly := Polygon2D.new()
		poly.polygon = PackedVector2Array([
			Vector2(-8, -18), Vector2(8, -18), Vector2(8, 18), Vector2(-8, 18)
		])
		poly.color = Color(0.45, 0.32, 0.20)
		poly.position = Vector2(dummy_x, -14)
		_dummy = poly
	add_child(_dummy)


func set_dummy_visible(v: bool) -> void:
	# Monster rounds hide the training dummies — the shared monster is the target.
	if _dummy != null:
		_dummy.visible = v


## Which hit-effect the target shows for this fighter's attacks: the equipped
## weapon's item_id when geared, else a per-class default (convention-based —
## see hit_effect.gd; ungeared fighters and NPCs use the class key).
func effect_key() -> String:
	var weapon := String(gear.get("weapon", ""))
	return weapon if weapon != "" else "class_" + char_class


func _build_body() -> void:
	# Preferred path: LPC layered sprite stack for this sprite set.
	var stack := LayeredSprite.new()
	add_child(stack)
	if stack.load_body(sprite_set):
		stack.set_facing(face_left)
		_sprite = stack
		_avatar = stack
		_apply_gear()
		return
	# Fallback: colored class diamond (no art yet).
	stack.queue_free()
	var body := Polygon2D.new()
	body.polygon = PackedVector2Array([
		Vector2(0, -26), Vector2(18, 0), Vector2(0, 26), Vector2(-18, 0)
	])
	body.color = CLASS_COLORS.get(char_class, Color(0.6, 0.6, 0.6))
	add_child(body)
	_avatar = body


func _apply_gear() -> void:
	# R5 paper-doll: stack each equipped item's sprite onto the shared LPC frame
	# grid (PLAN.md §7, Option A). Convention-based and fail-soft — a slot with no
	# mapped layer or no matching PNG is simply skipped, so gear renders only where
	# art exists and the fighter otherwise shows bare. Needs the layered body.
	if _sprite == null:
		return
	for slot in gear:
		var layer: String = GEAR_LAYER.get(slot, "")
		var item_id := String(gear[slot])
		if layer == "" or item_id == "":
			continue
		var path := SPRITE_DIR + layer + "/" + item_id + ".png"
		if ResourceLoader.exists(path):
			_sprite.set_layer(layer, load(path))


func _build_labels() -> void:
	# Name + owner (with platform badge) under the fighter.
	_name_label = Label.new()
	var owner_tag: String
	if is_npc:
		owner_tag = " (NPC)"
	else:
		var badge: String = PLATFORM_GLYPH.get(owner_platform, "")
		owner_tag = " (@%s)" % owner_name if badge == "" else " [%s] @%s" % [badge, owner_name]
	# Nudge text away from the dummy side so it never underlaps the target.
	var shift: float = LABEL_AWAY_SHIFT if face_left else -LABEL_AWAY_SHIFT
	_name_label.text = fighter_name + owner_tag
	_name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_name_label.position = Vector2(-70 + shift, 30)
	_name_label.size = Vector2(140, 20)
	_name_label.add_theme_font_size_override("font_size", 13)
	add_child(_name_label)

	# Cosmetic personality trait under the name (PLAN.md §7).
	if personality != "":
		var trait_label := Label.new()
		trait_label.text = personality
		trait_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		trait_label.position = Vector2(-70 + shift, 45)
		trait_label.size = Vector2(140, 16)
		trait_label.add_theme_font_size_override("font_size", 11)
		trait_label.modulate = Color(0.75, 0.75, 0.8)
		add_child(trait_label)

	# d20 roll indicator above the head.
	_roll_label = Label.new()
	_roll_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_roll_label.position = Vector2(-20, -52)
	_roll_label.size = Vector2(40, 22)
	_roll_label.add_theme_font_size_override("font_size", 20)
	add_child(_roll_label)


func show_attack(roll: int, damage: int, crit: bool, miss: bool, running_total: int) -> void:
	total = running_total

	if _sprite != null:
		_sprite.play("attack")  # layered art: play the swing clip
	else:
		_lunge()  # no art: placeholder lunge toward the target

	# d20 head-roll: red for 1, yellow for 20, white otherwise (PLAN.md §4.4).
	_roll_label.text = str(roll)
	if roll == 1:
		_roll_label.modulate = Color(1.0, 0.25, 0.25)
	elif roll == 20:
		_roll_label.modulate = Color(1.0, 0.9, 0.2)
	else:
		_roll_label.modulate = Color(1, 1, 1)

	# Hit effect + shake on the target (race mode: the dummy). Misses show nothing
	# on the target; monster-mode effects are driven by main.gd on the monster.
	var on_dummy: bool = _dummy != null and _dummy.visible
	if on_dummy and not miss:
		HitEffect.play(self, _dummy.position + Vector2(0, -14), effect_key(), crit)
		_shake_dummy()

	# Floating damage number — above the dummy when it's the target, else above
	# the fighter (monster mode keeps 8 fighters' numbers off the one monster).
	var dmg := Label.new()
	dmg.text = "MISS" if miss else ("%d!" % damage if crit else str(damage))
	var base: Vector2 = _dummy.position + Vector2(-30, -46) if on_dummy else Vector2(-30, -30)
	dmg.position = base
	dmg.size = Vector2(60, 20)
	dmg.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	dmg.add_theme_font_size_override("font_size", 22 if crit else 16)
	if miss:
		dmg.modulate = Color(0.7, 0.7, 0.7)
	elif crit:
		dmg.modulate = Color(1.0, 0.9, 0.2)
	else:
		dmg.modulate = Color(1, 1, 1)
	add_child(dmg)
	var tw := create_tween()
	tw.tween_property(dmg, "position:y", dmg.position.y - 45.0, 0.8)
	tw.parallel().tween_property(dmg, "modulate:a", 0.0, 0.8)
	tw.tween_callback(dmg.queue_free)

	if crit:
		var pop := create_tween()
		pop.tween_property(_avatar, "scale", Vector2(1.4, 1.4), 0.08)
		pop.tween_property(_avatar, "scale", Vector2(1, 1), 0.12)


func _lunge() -> void:
	# Placeholder attack motion for the no-art path: a quick step toward the
	# target and back. Absolute endpoints on position (never scale) so it can't
	# compound with itself or collide with the crit scale pop.
	if _lunge_tween != null and _lunge_tween.is_valid():
		_lunge_tween.kill()
	var dir: float = -1.0 if face_left else 1.0
	_lunge_tween = create_tween()
	_lunge_tween.tween_property(_avatar, "position:x", dir * LUNGE_DIST, 0.08)
	_lunge_tween.tween_property(_avatar, "position:x", 0.0, 0.12)


func _shake_dummy() -> void:
	# Absolute endpoints around the dummy's resting x so repeated hits never drift.
	var base_x: float = -DUMMY_OFFSET if face_left else DUMMY_OFFSET
	var shake := create_tween()
	shake.tween_property(_dummy, "position:x", base_x + 4.0, 0.05)
	shake.tween_property(_dummy, "position:x", base_x - 4.0, 0.05)
	shake.tween_property(_dummy, "position:x", base_x, 0.05)


func cast_ability(ability_name: String) -> void:
	# Signature-ability "big animation" (PLAN.md §4.2, §7): a bright pop on the
	# body plus the ability name flashing above the head. Placeholder until the
	# per-ability effect spritesheets/particles land.
	var pop := create_tween()
	pop.tween_property(_avatar, "scale", Vector2(1.6, 1.6), 0.12)
	pop.tween_property(_avatar, "scale", Vector2(1.0, 1.0), 0.18)

	var flash := Label.new()
	flash.text = ability_name.to_upper() + "!"
	flash.position = Vector2(-70, -78)
	flash.size = Vector2(140, 24)
	flash.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	flash.add_theme_font_size_override("font_size", 22)
	flash.modulate = Color(1.0, 0.85, 0.25)
	add_child(flash)
	var tw := create_tween()
	tw.tween_property(flash, "position:y", flash.position.y - 26.0, 1.0)
	tw.parallel().tween_property(flash, "modulate:a", 0.0, 1.0)
	tw.tween_callback(flash.queue_free)


func set_winner() -> void:
	if _sprite != null:
		_sprite.play("victory")
		_sprite.modulate = Color(1.0, 0.95, 0.7)  # warm winner glow
	elif _avatar is Polygon2D:
		(_avatar as Polygon2D).color = Color(1.0, 0.85, 0.2)
	var t := create_tween().set_loops()
	t.tween_property(_avatar, "scale", Vector2(1.25, 1.25), 0.4)
	t.tween_property(_avatar, "scale", Vector2(1.0, 1.0), 0.4)


func take_monster_hit(damage: int) -> void:
	# R4 monster round: the monster swung at this fighter (damage 0 = a miss).
	# Float the number and, on a hit, play the hurt clip + a small recoil shake.
	var lbl := Label.new()
	lbl.text = "MISS" if damage <= 0 else "-%d" % damage
	lbl.position = Vector2(-30, -30)
	lbl.size = Vector2(60, 20)
	lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lbl.add_theme_font_size_override("font_size", 16)
	lbl.modulate = Color(0.7, 0.7, 0.7) if damage <= 0 else Color(1.0, 0.4, 0.35)
	add_child(lbl)
	var tw := create_tween()
	tw.tween_property(lbl, "position:y", lbl.position.y - 40.0, 0.7)
	tw.parallel().tween_property(lbl, "modulate:a", 0.0, 0.7)
	tw.tween_callback(lbl.queue_free)
	if damage > 0 and not is_ko:
		if _sprite != null:
			_sprite.play("hurt")
		# Absolute endpoints around 0 (the avatar's resting x) so the recoil can't
		# compound with an in-flight lunge or a previous shake.
		var shake := create_tween()
		shake.tween_property(_avatar, "position:x", -6.0, 0.05)
		shake.tween_property(_avatar, "position:x", 6.0, 0.05)
		shake.tween_property(_avatar, "position:x", 0.0, 0.05)


func set_ko() -> void:
	# R4 monster round: this fighter dropped. Grey everything out, stop reacting,
	# and pin a KO marker over the head for the rest of the round.
	if is_ko:
		return
	is_ko = true
	if _sprite != null:
		_sprite.play("hurt")
	_avatar.modulate = KO_TINT
	if _dummy != null:
		_dummy.modulate = KO_TINT
	var ko := Label.new()
	ko.text = "KO"
	ko.position = Vector2(-20, -54)
	ko.size = Vector2(40, 22)
	ko.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	ko.add_theme_font_size_override("font_size", 20)
	ko.modulate = Color(1.0, 0.35, 0.3)
	add_child(ko)
	create_tween().tween_property(_avatar, "rotation_degrees", -12.0, 0.25)
