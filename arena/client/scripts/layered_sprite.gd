class_name LayeredSprite
extends Node2D
## LPC-style layered "paper-doll" sprite stack (PLAN.md §7, Option A).
##
## A character is a stack of `Sprite2D` layers that share ONE 64×64 frame grid
## and are advanced by a single frame clock, so every layer animates in lockstep.
## Equipping an item in Phase 3 is then just `set_layer(slot, texture)` — no
## combinatorial sprite explosion. In Phase 1 only the "body" layer is used; the
## other slots are empty hooks.
##
## Art-agnostic and fail-soft: it renders whatever PNGs exist under
## `res://assets/sprites/` and renders NOTHING when they're absent
## (`has_art()` stays false), so the overlay still runs with zero assets and the
## caller (`fighter.gd`) falls back to placeholder shapes. Drop LPC sheets in,
## named per the convention below, and fighters start rendering as sprites with
## no code change.

const FRAME := 64                 # LPC frame cell is 64×64 px
const DISPLAY_HEIGHT := 76.0      # on-screen body height; tune to the arena scale
const BODY_DIR := "res://assets/sprites/body/"

# Draw order, back to front. "body" is Phase 1; the rest are Phase 3 equipment
# hooks that stay empty until then (they compose for free on the shared grid).
const LAYER_ORDER := ["body", "boots", "legs", "torso", "arms", "hair", "helmet", "weapon"]

# clip -> {row, frames, fps, loop}. `row` indexes into the sheet (whose column
# count = texture_width / FRAME). Defaults assume a single-direction sheet with
# idle/attack/hurt on rows 0/1/2 — RETUNE to your actual LPC layout (a full
# Universal LPC sheet has 4 direction rows per action; point these rows at the
# facing you use). Unknown/short clips fall back safely.
const CLIPS := {
	"idle": {"row": 0, "frames": 1, "fps": 1.0, "loop": true},
	"attack": {"row": 1, "frames": 6, "fps": 14.0, "loop": false},
	"hurt": {"row": 2, "frames": 6, "fps": 12.0, "loop": false},
	"victory": {"row": 0, "frames": 1, "fps": 3.0, "loop": true},
}

var _layers: Dictionary = {}      # slot:String -> Sprite2D
var _has_body := false
var _clip := "idle"
var _clip_time := 0.0
var _face_left := false


## Face the stack left (true) or right (false). Uses per-layer flip_h — NOT a
## negative node scale, which would be stomped by fighter.gd's scale tweens
## (crit pop / ability cast). Layers added later inherit the facing.
func set_facing(face_left: bool) -> void:
	_face_left = face_left
	for slot in _layers:
		var spr: Sprite2D = _layers[slot]
		spr.flip_h = face_left


func _ready() -> void:
	set_process(_has_body)


## Try to load the body layer for a server-assigned sprite set (e.g. "barb_01").
## Returns false (and stays inert) when the art isn't present.
func load_body(sprite_set: String) -> bool:
	var path := BODY_DIR + sprite_set + ".png"
	if sprite_set == "" or not ResourceLoader.exists(path):
		return false
	set_layer("body", load(path))
	_has_body = true
	play("idle")
	set_process(true)
	return true


func has_art() -> bool:
	return _has_body


## Set (or replace) one layer's texture — the Phase 3 equip hook. All layers must
## share the body's frame grid so they stay in lockstep.
func set_layer(slot: String, texture: Texture2D) -> void:
	var spr: Sprite2D = _layers.get(slot)
	if spr == null:
		spr = Sprite2D.new()
		spr.centered = true
		spr.z_index = LAYER_ORDER.find(slot)
		add_child(spr)
		_layers[slot] = spr
	spr.texture = texture
	spr.hframes = maxi(1, texture.get_width() / FRAME)
	spr.vframes = maxi(1, texture.get_height() / FRAME)
	spr.flip_h = _face_left  # gear layers arrive after set_facing
	var s := DISPLAY_HEIGHT / float(FRAME)
	spr.scale = Vector2(s, s)
	spr.position = Vector2(0, -DISPLAY_HEIGHT * 0.5)  # feet near this node's origin
	_apply_frame(0)


func play(clip_name: String) -> void:
	_clip = clip_name if CLIPS.has(clip_name) else "idle"
	_clip_time = 0.0
	_apply_frame(0)


func _process(delta: float) -> void:
	if not _has_body:
		return
	var clip: Dictionary = CLIPS[_clip]
	_clip_time += delta
	var frames := int(clip["frames"])
	var idx := int(_clip_time * float(clip["fps"]))
	if idx >= frames:
		if bool(clip["loop"]):
			idx = idx % frames
		else:
			_apply_frame(frames - 1)
			play("idle")  # one-shot done -> back to idle
			return
	_apply_frame(idx)


func _apply_frame(col: int) -> void:
	var row := int(CLIPS[_clip]["row"])
	for slot in _layers:
		var spr: Sprite2D = _layers[slot]
		var c := clampi(col, 0, spr.hframes - 1)
		var r := clampi(row, 0, spr.vframes - 1)
		spr.frame = r * spr.hframes + c
