class_name HitEffect
extends Node2D
## One-shot hit-effect overlay played on the TARGET of an attack (the training
## dummy in races, the monster in monster battles).
##
## Effect selection is by convention (no config): the key is the attacker's
## equipped weapon item_id (e.g. "iron_sword") or "class_<class>" for ungeared
## fighters and NPCs — see Fighter.effect_key(). Art lives at
## `res://assets/sprites/effects/<key>.png` as a single-row strip of 64x64
## frames played one-shot at ~15 fps (same grid convention as the LPC stack).
##
## Fail-soft: with no PNG a procedural slash arc + flash plays instead, so the
## overlay works with zero art. Deterministic per (key, crit) — all game
## randomness is server-side (CLAUDE.md rule #1). Self-frees when done.

const EFFECT_DIR := "res://assets/sprites/effects/"
const FRAME := 64
const FPS := 15.0
const CRIT_COLOR := Color(1.0, 0.82, 0.25)


## Spawn the effect as a child of `parent` at local position `at` and play it.
static func play(parent: Node2D, at: Vector2, key: String, crit: bool) -> void:
	var fx := HitEffect.new()
	parent.add_child(fx)
	fx.position = at
	var path := EFFECT_DIR + key + ".png"
	if key != "" and ResourceLoader.exists(path):
		fx._play_strip(load(path), crit)
	else:
		fx._play_procedural(crit)


## Animate a single-row 64x64 strip one-shot, then free.
func _play_strip(texture: Texture2D, crit: bool) -> void:
	var spr := Sprite2D.new()
	spr.texture = texture
	spr.centered = true
	spr.hframes = maxi(1, texture.get_width() / FRAME)
	spr.vframes = 1
	var s: float = 1.6 if crit else 1.2
	spr.scale = Vector2(s, s)
	if crit:
		spr.modulate = CRIT_COLOR
	add_child(spr)

	var frames: int = spr.hframes
	var dur: float = float(frames) / FPS
	var tw := create_tween()
	tw.tween_method(func(f: float) -> void: spr.frame = clampi(int(f), 0, frames - 1),
			0.0, float(frames), dur)
	tw.tween_callback(queue_free)


## No art: a thin slash arc sweeping across the target plus a brief flash.
func _play_procedural(crit: bool) -> void:
	var color: Color = CRIT_COLOR if crit else Color(1, 1, 1, 0.95)
	var reach: float = 34.0 if crit else 26.0

	var slash := Polygon2D.new()
	slash.polygon = PackedVector2Array([
		Vector2(-reach, -3), Vector2(reach, -1.5), Vector2(reach, 1.5), Vector2(-reach, 3),
	])
	slash.color = color
	slash.rotation = -0.6
	add_child(slash)

	var flash := Polygon2D.new()
	var r: float = 10.0
	flash.polygon = PackedVector2Array([
		Vector2(0, -r), Vector2(r, 0), Vector2(0, r), Vector2(-r, 0),
	])
	flash.color = Color(color.r, color.g, color.b, 0.6)
	add_child(flash)

	var tw := create_tween()
	tw.tween_property(slash, "rotation", 0.6, 0.15)
	tw.parallel().tween_property(slash, "modulate:a", 0.0, 0.18)
	tw.parallel().tween_property(flash, "scale", Vector2(2.2, 2.2), 0.18)
	tw.parallel().tween_property(flash, "modulate:a", 0.0, 0.18)
	tw.tween_callback(queue_free)
