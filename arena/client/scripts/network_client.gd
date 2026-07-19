extends Node
## WebSocket client for the server's Godot-facing event feed (PLAN.md §7).
##
## Autoloaded as `Net`. Connects to the server, polls the socket every frame,
## parses each JSON message, and re-broadcasts it as a Godot signal. Holds NO
## game state — it is a pure transport. Reconnects automatically if the server
## restarts or the socket drops (the server keeps simulating regardless).
##
## Remote servers: an optional `overlay.cfg` (user:// then res://; gitignored —
## copy overlay.cfg.example) supplies the wss:// URL + shared auth token, sent
## as an `Authorization: Bearer` handshake header. Without the file, the
## localhost defaults below apply (no token). `insecure_tls = true` skips cert
## verification — self-signed dev certs only, never production.

signal connection_changed(connected: bool)
signal sync_state(data: Dictionary)
signal round_start(data: Dictionary)
signal attack(data: Dictionary)
signal round_end(data: Dictionary)
signal countdown(data: Dictionary)
signal ticker(data: Dictionary)
signal ability(data: Dictionary)
signal arena_event(data: Dictionary)
signal panel(data: Dictionary)
# R4 co-op monster battles (docs/R4_R6_plan.md).
signal monster_spawn(data: Dictionary)
signal monster_hp(data: Dictionary)
signal monster_attack(data: Dictionary)
signal fighter_ko(data: Dictionary)
signal team_result(data: Dictionary)

@export var url: String = "ws://127.0.0.1:8765/ws"
const RECONNECT_DELAY_S := 2.0
const CFG_PATHS := ["user://overlay.cfg", "res://overlay.cfg"]

var _socket := WebSocketPeer.new()
var _was_open := false
var _retry_timer := 0.0
var _token: String = ""
var _insecure_tls: bool = false


func _ready() -> void:
	_load_overlay_cfg()
	_connect()


func _load_overlay_cfg() -> void:
	# First file found wins; absence just keeps the localhost defaults.
	for path in CFG_PATHS:
		var cfg := ConfigFile.new()
		if cfg.load(path) != OK:
			continue
		url = String(cfg.get_value("server", "url", url))
		_token = String(cfg.get_value("server", "token", ""))
		_insecure_tls = bool(cfg.get_value("server", "insecure_tls", false))
		print("D&D Arena: overlay config loaded from %s (%s)" % [path, url])
		return


func _connect() -> void:
	if _token != "":
		_socket.handshake_headers = PackedStringArray(["Authorization: Bearer " + _token])
	var tls: TLSOptions = null
	if url.begins_with("wss://") and _insecure_tls:
		tls = TLSOptions.client_unsafe()  # self-signed dev certs only
	var err := _socket.connect_to_url(url, tls)
	if err != OK:
		push_warning("D&D Arena: connect_to_url failed (%s); retrying" % err)


func _process(delta: float) -> void:
	_socket.poll()
	var state := _socket.get_ready_state()

	match state:
		WebSocketPeer.STATE_OPEN:
			if not _was_open:
				_was_open = true
				connection_changed.emit(true)
			while _socket.get_available_packet_count() > 0:
				_handle_packet(_socket.get_packet())
		WebSocketPeer.STATE_CLOSED:
			if _was_open:
				_was_open = false
				connection_changed.emit(false)
			_retry_timer -= delta
			if _retry_timer <= 0.0:
				_retry_timer = RECONNECT_DELAY_S
				_connect()


func _handle_packet(packet: PackedByteArray) -> void:
	var text := packet.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_warning("D&D Arena: ignoring non-object message: %s" % text)
		return
	var data: Dictionary = parsed
	match data.get("type", ""):
		"sync":
			sync_state.emit(data)
		"round_start":
			round_start.emit(data)
		"attack":
			attack.emit(data)
		"round_end":
			round_end.emit(data)
		"countdown":
			countdown.emit(data)
		"ticker":
			ticker.emit(data)
		"ability":
			ability.emit(data)
		"event":
			arena_event.emit(data)
		"panel":
			panel.emit(data)
		"monster_spawn":
			monster_spawn.emit(data)
		"monster_hp":
			monster_hp.emit(data)
		"monster_attack":
			monster_attack.emit(data)
		"fighter_ko":
			fighter_ko.emit(data)
		"team_result":
			team_result.emit(data)
		_:
			pass  # unknown / future message types
