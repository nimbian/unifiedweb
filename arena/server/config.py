"""Hot-reloadable game configuration.

All tunable game values — timings, XP tables, class coefficients, asset lists —
live in a TOML file (default ``config/game.toml``), never hardcoded. The server
watches the file's mtime and reloads on change so balance tweaks don't require a
code deploy.

This module only parses and validates config; game rules live in ``rules.py``.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

# Canonical stat names. INT is stored in Postgres as `intl` (see the schema) but
# is referred to as "INT" everywhere in game logic and config.
STAT_NAMES: tuple[str, ...] = ("STR", "DEX", "CON", "INT", "WIS", "CHA")

# The raw-d20 multiplier table covers rolls 2..19 only (rolls 1 and 20 are
# handled specially), so it must have exactly this many entries.
ROLL_TABLE_LEN = 18


@dataclass(frozen=True)
class Timings:
    intermission_seconds: int
    roster_lock_seconds: int
    combat_seconds: int
    results_seconds: int


@dataclass(frozen=True)
class ArenaConfig:
    """Boot-time arena gate. When False the arena boots CLOSED (idle, no rounds)
    until a mod types !start; !close idles it again after the current round.
    Boot default only — hot-reloading this key does not open/close a running
    arena; mods control that in chat."""

    open_on_launch: bool = False


@dataclass(frozen=True)
class RoundConfig:
    fighters_per_round: int
    roster_limit: int
    lifespan_battles: int
    # Probability that a round rolls a random arena event (PLAN.md §4.6, Phase 3);
    # 0.0 disables events entirely. When it fires, one event is picked uniformly.
    event_chance: float = 0.0


# Queue selection model (PLAN.md §13.1, R2).
#   "fifo" — the shipped model: first-in-first-out with carryover (unselected
#     characters keep their place and get picked next round).
#   "weighted_lottery" — R2: EventSub priority tokens are seated first, then the
#     remaining slots are filled by a server-side weighted lottery whose weight
#     climbs with each prior miss, so repeatedly-skipped characters trend toward a
#     guaranteed seat. Additive behind this flag (like [combat].engine).
QUEUE_SELECTIONS = ("fifo", "weighted_lottery")


@dataclass(frozen=True)
class QueueConfig:
    selection: str = "fifo"
    # Weight of a queued character in the lottery = 1 + misses * miss_weight.
    # miss_weight is an Opus-chosen tuning knob (owner may revise): 1.0 means a
    # character missed N times is (1+N)x as likely to be picked as a fresh one.
    miss_weight: float = 1.0


@dataclass(frozen=True)
class StatConfig:
    dice: int
    sides: int
    keep: int
    reroll_below: int


@dataclass(frozen=True)
class DamageConfig:
    # roll_multipliers[roll - 2] gives the multiplier for a raw d20 of `roll`
    # (valid for roll in 2..19).
    roll_multipliers: tuple[float, ...]
    crit_primary_mult: float
    crit_final_mult: float
    # Global multiplier applied when a raw float damage value crosses a display
    # or persistence boundary (PLAN.md §4.4.5). Internal accumulation stays float;
    # only the scaled value is rounded. ×10 lands per-hit numbers in ~80-400.
    display_scale: float
    # Mean of roll_multipliers — a representative "average hit" primary multiplier,
    # used to size flat bonuses (e.g. the Dragonborn breath hit) independently of
    # the specific roll. Derived at parse time, not configured.
    mean_multiplier: float = 0.0


@dataclass(frozen=True)
class CombatConfig:
    """MooreDnD combat-math constants (R1, docs/R1_combat_math.md). ``engine``
    selects the combat model: ``classic`` is the shipped multiplier-table formula
    (§4.4 / hard rule #7); ``moore`` is the Core-Stats / to-hit-vs-AC model. The
    new engine lands behind this switch so the rewrite never breaks a running
    stream — ``classic`` stays the default until the ``moore`` gate is green."""

    engine: str                 # "classic" | "moore"
    ap_per_point: float         # Attack Power per point of the governing ability (doc: 25)
    ap_cap: float               # Attack Power hard cap (doc: 1000)
    crit_pp_per_point: float    # crit-damage percentage points per point of crit ability (doc: 5)
    damage_variance: float      # +/- flat damage variance on a hit (doc: 75)
    health_base: float          # Health = health_base + CON * health_per_con
    health_per_con: float
    loot_base: float            # Loot Bonus % = loot_base + CHA * loot_per_cha
    loot_per_cha: float
    dummy_ac: int               # damage-race dummy AC (low -> near-auto hits, R1 §3)
    min_hit: float              # floor for a landed hit's raw damage
    # +/- variance as a FRACTION of Attack Power, added to the flat term. 0.0 =
    # doc-faithful flat variance. A proportional term equalizes each class's
    # relative per-hit swing (see R1 tuning notes) — set flat 0 + pct > 0 to use it.
    damage_variance_pct: float = 0.0


COMBAT_ENGINES = ("classic", "moore")

# How a monster picks its target each swing (PLAN.md §13.1 / docs/R4_R6_plan.md).
MONSTER_TARGETING = ("random", "aggro_top")


@dataclass(frozen=True)
class MonsterTier:
    """One tier (I–V) of the R4 monster ladder. HP is a fraction of the team's
    expected 90 s damage output so it scales with the roster's level/class mix;
    everything else is absolute. ``gold_mult`` is the R5 tier payout multiplier
    (§13.1: I–V = ×1.0/1.5/2.0/2.5/3.0)."""

    tier: int
    label: str
    hp_pct_of_team: float
    ac: int
    attack_mod: int
    attack_interval: float
    damage: float
    gold_mult: float = 1.0
    sprite: str = ""


@dataclass(frozen=True)
class MonsterConfig:
    """R4 tiered monster battles (docs/R4_R6_plan.md). Every ``every_n`` rounds is
    a co-op monster battle on an escalating tier ladder. ``every_n = 0`` disables
    them (the shipped default); when enabled the combat engine must be ``moore``
    (monsters need Health / AC / to-hit, validated at load)."""

    every_n: int = 0
    target_selection: str = "random"
    max_tier: int = 5
    tiers: dict[int, MonsterTier] = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return self.every_n > 0

    def tier(self, n: int) -> MonsterTier:
        return self.tiers[n]


@dataclass(frozen=True)
class RacePassives:
    """A race's passive, as tunable knobs (PLAN.md §4.3). Every field defaults to
    a no-op, so a race only sets what it changes and the simulator can tune the
    magnitudes. Passives split into: creation-time stat bumps
    (``all_stats_bonus``/``con_bonus``), per-hit combat modifiers
    (``crit_chance_bonus``/``first_hit_mult``/``attack_speed_mult``/
    ``damage_mult``/``lucky_reroll_ones``/``breath_*``), the meta ``xp_mult``, and
    event-conditional effects (``event_damage_bonus``/``event_tags``/
    ``curse_immune``) that stay inert until arena events + Curse land (Phase 2/3)."""

    name: str
    all_stats_bonus: int = 0        # Human: +N to every stat at creation
    con_bonus: int = 0              # Dwarf: +N CON at creation
    crit_chance_bonus: float = 0.0  # Elf: extra chance to upgrade a hit to a crit
    first_hit_mult: float = 1.0     # Orc: multiplier on the round's first swing
    attack_speed_mult: float = 1.0  # Goblin: >1 shortens the attack interval
    damage_mult: float = 1.0        # Goblin: per-hit damage multiplier
    lucky_reroll_ones: int = 0      # Halfling: natural-1 rerolls granted per round
    breath_every: int = 0           # Dragonborn: bonus fires on every Nth swing
    breath_bonus_mult: float = 0.0  # Dragonborn: bonus as a fraction of an avg hit
    xp_mult: float = 1.0            # Gnome: XP earned multiplier
    event_damage_bonus: float = 0.0     # Tiefling/Aasimar: +dmg during matching events
    event_tags: tuple[str, ...] = ()    # arena-event tags that trigger the bonus
    curse_immune: bool = False          # Dwarf: immune to Curse-type debuffs


@dataclass(frozen=True)
class EconomyConfig:
    """Chat-betting economy (PLAN.md §6.6). Free virtual "gold" only — never
    channel points/real currency. Bets pay out pari-mutuel: winners split the
    round's pool proportional to their stake (``rake`` is the house take, 0 =
    full pool returned)."""

    starting_gold: int      # granted to a user on first sight
    gold_per_round: int     # passive income to each chatter present that round
    min_bet: int
    rake: float             # 0.0..1.0 pari-mutuel take


GEAR_SLOTS = ("weapon", "armor", "trinket")


@dataclass(frozen=True)
class ShopItem:
    """One buyable, permanent-until-retirement equipment item (R5,
    docs/R4_R6_plan.md). Grants are additive; ``ap_mult`` / ``speed_mult`` are
    fractions of Attack Power / Attack Speed, the rest are flat. One item per slot
    per character; buying a slot replaces what's equipped, and the replaced item
    stays in the character's inventory (migration 0007)."""

    item_id: str
    slot: str
    name: str
    price: int
    ap_mult: float = 0.0
    ac_bonus: int = 0
    speed_mult: float = 0.0
    crit_pp: float = 0.0     # +percentage points of Critical Damage
    loot_pp: float = 0.0     # +percentage points of Loot Bonus


@dataclass(frozen=True)
class ShopCaps:
    """Upper bounds on a *fully geared* character's grants, so the naked balance
    gate stays valid (docs/R4_R6_plan.md: full gear <= ~+15% DPS)."""

    max_ap_mult: float = 0.10
    max_speed_mult: float = 0.05
    max_ac_bonus: int = 2
    max_crit_pp: float = 20.0
    max_loot_pp: float = 40.0


@dataclass(frozen=True)
class ShopConfig:
    """R5 shop + performance-gold economy. ``enabled = false`` (default) keeps the
    shipped chat-betting + presence-stipend economy; enabling it turns on
    performance gold (damage x Loot Bonus x tier mult) and retires betting/stipend
    (their kill-switches live on EconomyConfig)."""

    enabled: bool = False
    items: dict[str, ShopItem] = field(default_factory=dict)
    caps: ShopCaps = field(default_factory=ShopCaps)

    def items_for_slot(self, slot: str) -> list[ShopItem]:
        return [it for it in self.items.values() if it.slot == slot]


@dataclass(frozen=True)
class TrainingConfig:
    """R6 cross-player co-training (docs/R4_R6_plan.md). ``enabled = false``
    (default) leaves retirement as-is. A child's starting stats are the two retired
    parents' final scores blended and regressed toward the sorted-4d6 expectation,
    with a small capped bonus + variance — bounded so the balance gate holds."""

    enabled: bool = False
    max_uses: int = 3          # times a retired character may mentor
    base_cost: int = 500       # trainee owner pays base_cost * (1 + mentor's prior uses)
    regression: float = 0.35   # pull toward the creation mean (0 = pure mean, 1 = parents)
    max_bonus_points: int = 1  # per-rank cap above the sorted-4d6 rank mean (bounds the
                               # DPS-driving primary; +1 -> ~+5% edge, the gate stays valid)
    variance: int = 2          # per-slot uniform(-variance, +variance) roll


@dataclass(frozen=True)
class RewardsConfig:
    """Twitch EventSub reward mapping (PLAN.md §6.2). ``titles`` maps a
    channel-point reward title (lowercased) to a game action
    (``extra_slot`` | ``stat_reroll`` | ``priority_queue``); ``gold_per_tier``
    converts a normalized support event (subs/bits) into gold."""

    gold_per_tier: int
    titles: dict[str, str]  # lowercased reward title -> action key

    def action_for(self, title: str) -> str | None:
        return self.titles.get(title.strip().casefold())


REWARD_ACTIONS = ("extra_slot", "stat_reroll", "priority_queue")

# Leveling model (PLAN.md §13.1, R-migration).
#   "placement" — the shipped model: placement XP on a triangular curve (§4.5).
#   "per_battle" — R3: every completed battle grants exactly 1 level, capped at
#     ``levels_max``; placement XP, the curve, and xp-multiplier passives/events
#     retire. Additive behind this flag (like [combat].engine) so live play keeps
#     the placement model until the owner flips it alongside the moore engine.
LEVELING_MODES = ("placement", "per_battle")


@dataclass(frozen=True)
class XpConfig:
    levels_max: int
    base_per_round: int
    placement_bonus: tuple[int, ...]  # index 0 == 1st place
    curve_coeff: int
    per_level_primary_bonus: int
    mode: str = "placement"


@dataclass(frozen=True)
class AbilityDef:
    """A class's signature ability (PLAN.md §4.2), auto-cast once per round at a
    random mid-round moment. Four ``kind``s cover all eight v1 abilities:

    * ``damage_buff`` — swings in the next ``duration`` s deal ×(1+``magnitude``).
      (Barbarian Rage +40%/10s, Warlock Curse +20%/15s.)
    * ``no_miss`` — the next ``count`` swings can't miss (a natural 1 lands as the
      minimum hit). (Fighter Second Wind, 3.)
    * ``crit_buff`` — the next ``count`` landed swings get +``magnitude`` crit
      chance. (Rogue Backstab, +50% on 1.)
    * ``burst`` — an instant flourish of ``hits`` bonus hits, each worth
      ``hit_mult`` of an average hit. (Monk Flurry 5×0.4, Ranger Volley 3×0.6,
      Paladin Smite 1×3.0, Wizard Fireball 1×2.5.)
    """

    name: str          # display name shown on the overlay ("Rage", "Fireball")
    kind: str          # damage_buff | no_miss | crit_buff | burst
    magnitude: float = 0.0
    duration: float = 0.0
    count: int = 0
    hits: int = 0
    hit_mult: float = 0.0


ABILITY_KINDS = ("damage_buff", "no_miss", "crit_buff", "burst")


@dataclass(frozen=True)
class ArenaEvent:
    """A random arena event (PLAN.md §4.6, Phase 3): one small GLOBAL round
    modifier chosen at round start and applied to every fighter, so its knobs are
    tunable and the simulator can confirm class win rates stay in band with events
    stacked on. A purely uniform multiplier (Fire/Curse) leaves the win-rate
    distribution unchanged — its balance effect comes only through the matching
    race passive (Tiefling/Aasimar ``event_damage_bonus``, Dwarf ``curse_immune``),
    which is exactly what activates those otherwise-inert passives (PLAN.md §4.3).

    Knobs (all default to a no-op):
    * ``damage_mult`` — per-hit ×multiplier for all (Fire 1.10, Curse 0.90).
    * ``curse`` — if set, ``curse_immune`` races ignore ``damage_mult`` (Dwarf).
    * ``crit_chance_bonus`` — added to every fighter's crit-upgrade chance; may be
      negative (Rain −0.03 dampens the chance-based crits; natural 20s still crit).
    * ``crit_damage_mult`` — ×multiplier on a crit's damage (Fog 0.5, Blood Moon 1.5).
    * ``no_miss`` — natural 1s land as the minimum hit for everyone (Blessing).
    * ``xp_mult`` — round XP ×multiplier (Crowd 1.25); meta only, no DPS impact.
    * ``tag`` — matched against a race's ``event_tags`` to trigger its
      ``event_damage_bonus`` (Fire/Blood Moon → Tiefling, Blessing → Aasimar).
    """

    name: str               # config key / persisted value ("fire", "curse", ...)
    label: str              # display banner text ("Fire Storm")
    tag: str = ""           # race event_tags match; "" = no race hook
    damage_mult: float = 1.0
    curse: bool = False
    crit_chance_bonus: float = 0.0
    crit_damage_mult: float = 1.0
    no_miss: bool = False
    xp_mult: float = 1.0


@dataclass(frozen=True)
class ClassDef:
    name: str
    primary: str  # a STAT_NAMES value
    secondary: str  # a STAT_NAMES value
    attack_interval: float
    coeff: float
    ability: AbilityDef | None = None  # signature ability (Phase 2); None until set
    # MooreDnD combat model (R1, docs/R1_combat_math.md). Inert under the classic
    # engine. ``crit_ability`` governs Critical Damage (defaults to ``secondary``
    # at parse); ``base_ac`` is the class's armor floor (DEX modifier adds on top).
    # ``moore_coeff`` is the Attack-Power scaling factor under the moore engine —
    # separate from the classic ``coeff`` so both engines' tuned balance coexist
    # during the R1 transition; 0.0 falls back to ``coeff``.
    crit_ability: str = ""
    base_ac: int = 10
    moore_coeff: float = 0.0

    def attack_speed(self) -> int:
        """Per-class base Attack Speed (0–1000): 100 = 1 attack / 10s, so a class's
        current ``attack_interval`` maps to ``round(1000 / interval)`` (R1 §0.2)."""
        return round(1000.0 / self.attack_interval)

    def ap_coeff(self) -> float:
        """Attack-Power scaling coefficient for the moore engine, falling back to
        the classic ``coeff`` when ``moore_coeff`` is unset (R1)."""
        return self.moore_coeff if self.moore_coeff > 0 else self.coeff


class ConfigError(ValueError):
    """Raised when a config file is structurally invalid."""


# A do-nothing passive set for house NPCs and any race missing from config.
NEUTRAL_RACE = RacePassives(name="neutral")


@dataclass
class Config:
    """Parsed, validated game config with mtime-based hot reload."""

    path: Path
    mtime: float
    timings: Timings
    arena: ArenaConfig
    round: RoundConfig
    queue: QueueConfig
    stats: StatConfig
    damage: DamageConfig
    xp: XpConfig
    economy: EconomyConfig
    rewards: RewardsConfig
    combat: CombatConfig
    monsters: MonsterConfig
    shop: ShopConfig
    training: TrainingConfig
    classes: dict[str, ClassDef]
    races: dict[str, RacePassives]  # race -> passive knobs (PLAN.md §4.3)
    events: dict[str, ArenaEvent]   # arena event -> global modifier (PLAN.md §4.6)
    assets: dict  # renderer-facing lists; kept raw, server selects from them

    # -- loading -----------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> Config:
        path = Path(path)
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        cfg = _parse(path, path.stat().st_mtime, data)
        return cfg

    def maybe_reload(self) -> bool:
        """Reload from disk if the file changed since last load.

        Returns True if a reload happened. On a parse/validation error the old
        config is kept and the error is re-raised (callers should log and carry
        on with the last-good config rather than crash the round loop).
        """
        try:
            current = self.path.stat().st_mtime
        except OSError:
            return False
        if current == self.mtime:
            return False
        fresh = Config.load(self.path)
        # Copy fields over in place so existing references see the new values.
        for f in ("mtime", "timings", "arena", "round", "queue", "stats", "damage", "xp",
                  "economy", "rewards", "combat", "monsters", "shop", "training", "classes",
                  "races", "events", "assets"):
            setattr(self, f, getattr(fresh, f))
        return True

    # -- convenience -------------------------------------------------------
    def class_def(self, name: str) -> ClassDef:
        try:
            return self.classes[name]
        except KeyError:
            raise ConfigError(f"unknown class {name!r}") from None

    def race_passives(self, name: str | None) -> RacePassives:
        """Passives for a race; a neutral (all no-op) set for unknown races and
        house NPCs (``race = 'npc'``), so callers never special-case them."""
        return self.races.get(name or "", NEUTRAL_RACE)

    def arena_event(self, name: str | None) -> ArenaEvent | None:
        """The event modifier for a persisted round-event name, or None (no event
        / unknown name), so callers can pass it straight into combat resolution."""
        return self.events.get(name or "")


def _require(mapping: dict, key: str, ctx: str):
    if key not in mapping:
        raise ConfigError(f"missing required config key [{ctx}].{key}")
    return mapping[key]


def _parse(path: Path, mtime: float, data: dict) -> Config:
    t = _require(data, "timings", "root")
    timings = Timings(
        intermission_seconds=int(_require(t, "intermission_seconds", "timings")),
        roster_lock_seconds=int(_require(t, "roster_lock_seconds", "timings")),
        combat_seconds=int(_require(t, "combat_seconds", "timings")),
        results_seconds=int(_require(t, "results_seconds", "timings")),
    )

    r = _require(data, "round", "root")
    rnd = RoundConfig(
        fighters_per_round=int(_require(r, "fighters_per_round", "round")),
        roster_limit=int(_require(r, "roster_limit", "round")),
        lifespan_battles=int(_require(r, "lifespan_battles", "round")),
        event_chance=float(r.get("event_chance", 0.0)),
    )
    if not 0.0 <= rnd.event_chance <= 1.0:
        raise ConfigError("[round].event_chance must be in [0.0, 1.0]")

    ar = data.get("arena", {})
    arena = ArenaConfig(open_on_launch=bool(ar.get("open_on_launch", False)))

    q = data.get("queue", {})
    queue = QueueConfig(
        selection=str(q.get("selection", "fifo")),
        miss_weight=float(q.get("miss_weight", 1.0)),
    )
    if queue.selection not in QUEUE_SELECTIONS:
        raise ConfigError(
            f"[queue].selection = {queue.selection!r} must be one of {QUEUE_SELECTIONS}"
        )
    if queue.miss_weight < 0:
        raise ConfigError("[queue].miss_weight must be >= 0")

    s = _require(data, "stats", "root")
    stats = StatConfig(
        dice=int(_require(s, "dice", "stats")),
        sides=int(_require(s, "sides", "stats")),
        keep=int(_require(s, "keep", "stats")),
        reroll_below=int(_require(s, "reroll_below", "stats")),
    )
    if not (0 < stats.keep <= stats.dice):
        raise ConfigError("[stats].keep must be between 1 and [stats].dice")
    if not (1 <= stats.reroll_below <= stats.sides):
        raise ConfigError("[stats].reroll_below must be within 1..sides")

    d = _require(data, "damage", "root")
    mults = tuple(float(x) for x in _require(d, "roll_multipliers", "damage"))
    if len(mults) != ROLL_TABLE_LEN:
        raise ConfigError(
            f"[damage].roll_multipliers must have exactly {ROLL_TABLE_LEN} entries "
            f"(rolls 2..19); got {len(mults)}"
        )
    display_scale = float(_require(d, "display_scale", "damage"))
    if display_scale <= 0:
        raise ConfigError("[damage].display_scale must be > 0")
    damage = DamageConfig(
        roll_multipliers=mults,
        crit_primary_mult=float(_require(d, "crit_primary_mult", "damage")),
        crit_final_mult=float(_require(d, "crit_final_mult", "damage")),
        display_scale=display_scale,
        mean_multiplier=sum(mults) / len(mults),
    )

    x = _require(data, "xp", "root")
    leveling_mode = str(x.get("mode", "placement"))
    if leveling_mode not in LEVELING_MODES:
        raise ConfigError(f"[xp].mode = {leveling_mode!r} must be one of {LEVELING_MODES}")
    xp = XpConfig(
        levels_max=int(_require(x, "levels_max", "xp")),
        base_per_round=int(_require(x, "base_per_round", "xp")),
        placement_bonus=tuple(int(v) for v in _require(x, "placement_bonus", "xp")),
        curve_coeff=int(_require(x, "curve_coeff", "xp")),
        per_level_primary_bonus=int(_require(x, "per_level_primary_bonus", "xp")),
        mode=leveling_mode,
    )

    ec = data.get("economy", {})
    economy = EconomyConfig(
        starting_gold=int(ec.get("starting_gold", 100)),
        gold_per_round=int(ec.get("gold_per_round", 10)),
        min_bet=int(ec.get("min_bet", 1)),
        rake=float(ec.get("rake", 0.0)),
    )
    if not 0.0 <= economy.rake < 1.0:
        raise ConfigError("[economy].rake must be in [0.0, 1.0)")
    if economy.min_bet < 1:
        raise ConfigError("[economy].min_bet must be >= 1")

    rw = data.get("rewards", {})
    titles_raw = rw.get("titles", {})
    titles: dict[str, str] = {}
    for title, action in titles_raw.items():
        if action not in REWARD_ACTIONS:
            raise ConfigError(
                f"[rewards.titles] {title!r} -> {action!r} is not one of {REWARD_ACTIONS}"
            )
        titles[str(title).strip().casefold()] = action
    rewards = RewardsConfig(gold_per_tier=int(rw.get("gold_per_tier", 5)), titles=titles)

    combat = _parse_combat(data.get("combat", {}))
    monsters = _parse_monsters(data.get("monsters", {}))
    if monsters.enabled and combat.engine != "moore":
        raise ConfigError(
            "[monsters].every_n > 0 requires [combat].engine = 'moore' "
            "(monster battles need Health/AC/to-hit; docs/R4_R6_plan.md)"
        )
    shop = _parse_shop(data.get("shop", {}))
    tr = data.get("training", {})
    training = TrainingConfig(
        enabled=bool(tr.get("enabled", False)),
        max_uses=int(tr.get("max_uses", 3)),
        base_cost=int(tr.get("base_cost", 500)),
        regression=float(tr.get("regression", 0.35)),
        max_bonus_points=int(tr.get("max_bonus_points", 1)),
        variance=int(tr.get("variance", 2)),
    )
    if not 0.0 <= training.regression <= 1.0:
        raise ConfigError("[training].regression must be in [0.0, 1.0]")

    abilities = _parse_abilities(data.get("abilities", {}))

    classes_raw = _require(data, "classes", "root")
    classes: dict[str, ClassDef] = {}
    for name, c in classes_raw.items():
        ctx = f"classes.{name}"
        primary = str(_require(c, "primary", ctx)).upper()
        secondary = str(_require(c, "secondary", ctx)).upper()
        # Crit-damage ability (R1) defaults to the secondary when unset.
        crit_ability = str(c.get("crit_ability", secondary)).upper()
        for label, val in (
            ("primary", primary), ("secondary", secondary), ("crit_ability", crit_ability)
        ):
            if val not in STAT_NAMES:
                raise ConfigError(f"[{ctx}].{label} = {val!r} is not a valid stat")
        classes[name] = ClassDef(
            name=name,
            primary=primary,
            secondary=secondary,
            attack_interval=float(_require(c, "attack_interval", ctx)),
            coeff=float(_require(c, "coeff", ctx)),
            ability=abilities.get(name),
            crit_ability=crit_ability,
            base_ac=int(c.get("base_ac", 10)),
            moore_coeff=float(c.get("moore_coeff", 0.0)),
        )
    if not classes:
        raise ConfigError("no [classes.*] defined")

    races = _parse_races(data.get("races", {}))
    arena_events = _parse_events(data.get("events", {}))

    assets = dict(data.get("assets", {}))

    return Config(
        path=path,
        mtime=mtime,
        timings=timings,
        arena=arena,
        round=rnd,
        queue=queue,
        stats=stats,
        damage=damage,
        xp=xp,
        economy=economy,
        rewards=rewards,
        combat=combat,
        monsters=monsters,
        shop=shop,
        training=training,
        classes=classes,
        races=races,
        events=arena_events,
        assets=assets,
    )


def _parse_abilities(abilities_raw: dict) -> dict[str, AbilityDef]:
    """Parse the optional ``[abilities.<class>]`` tables (PLAN.md §4.2)."""
    abilities: dict[str, AbilityDef] = {}
    for class_name, a in abilities_raw.items():
        ctx = f"abilities.{class_name}"
        kind = str(_require(a, "kind", ctx))
        if kind not in ABILITY_KINDS:
            raise ConfigError(f"[{ctx}].kind = {kind!r} must be one of {ABILITY_KINDS}")
        abilities[class_name] = AbilityDef(
            name=str(a.get("name", class_name.title())),
            kind=kind,
            magnitude=float(a.get("magnitude", 0.0)),
            duration=float(a.get("duration", 0.0)),
            count=int(a.get("count", 0)),
            hits=int(a.get("hits", 0)),
            hit_mult=float(a.get("hit_mult", 0.0)),
        )
    return abilities


def _parse_races(races_raw: dict) -> dict[str, RacePassives]:
    """Parse the optional ``[races.*]`` tables. Every knob is optional (defaults
    to a no-op), so a race table lists only the fields it changes."""
    races: dict[str, RacePassives] = {}
    for name, r in races_raw.items():
        ctx = f"races.{name}"
        tags = r.get("event_tags", [])
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            raise ConfigError(f"[{ctx}].event_tags must be a list of strings")
        passives = RacePassives(
            name=name,
            all_stats_bonus=int(r.get("all_stats_bonus", 0)),
            con_bonus=int(r.get("con_bonus", 0)),
            crit_chance_bonus=float(r.get("crit_chance_bonus", 0.0)),
            first_hit_mult=float(r.get("first_hit_mult", 1.0)),
            attack_speed_mult=float(r.get("attack_speed_mult", 1.0)),
            damage_mult=float(r.get("damage_mult", 1.0)),
            lucky_reroll_ones=int(r.get("lucky_reroll_ones", 0)),
            breath_every=int(r.get("breath_every", 0)),
            breath_bonus_mult=float(r.get("breath_bonus_mult", 0.0)),
            xp_mult=float(r.get("xp_mult", 1.0)),
            event_damage_bonus=float(r.get("event_damage_bonus", 0.0)),
            event_tags=tuple(tags),
            curse_immune=bool(r.get("curse_immune", False)),
        )
        if passives.attack_speed_mult <= 0:
            raise ConfigError(f"[{ctx}].attack_speed_mult must be > 0")
        races[name] = passives
    return races


def _parse_combat(combat_raw: dict) -> CombatConfig:
    """Parse the optional ``[combat]`` table (R1, docs/R1_combat_math.md). Every
    knob defaults to the MooreDnD doc value, and ``engine`` defaults to
    ``classic`` so an unchanged config keeps the shipped combat model."""
    engine = str(combat_raw.get("engine", "classic")).lower()
    if engine not in COMBAT_ENGINES:
        raise ConfigError(f"[combat].engine = {engine!r} must be one of {COMBAT_ENGINES}")
    combat = CombatConfig(
        engine=engine,
        ap_per_point=float(combat_raw.get("ap_per_point", 25.0)),
        ap_cap=float(combat_raw.get("ap_cap", 1000.0)),
        crit_pp_per_point=float(combat_raw.get("crit_pp_per_point", 5.0)),
        damage_variance=float(combat_raw.get("damage_variance", 75.0)),
        health_base=float(combat_raw.get("health_base", 100.0)),
        health_per_con=float(combat_raw.get("health_per_con", 25.0)),
        loot_base=float(combat_raw.get("loot_base", 0.0)),
        loot_per_cha=float(combat_raw.get("loot_per_cha", 2.0)),
        dummy_ac=int(combat_raw.get("dummy_ac", 5)),
        min_hit=float(combat_raw.get("min_hit", 1.0)),
        damage_variance_pct=float(combat_raw.get("damage_variance_pct", 0.0)),
    )
    if combat.ap_per_point <= 0 or combat.ap_cap <= 0:
        raise ConfigError("[combat].ap_per_point and ap_cap must be > 0")
    if combat.damage_variance < 0:
        raise ConfigError("[combat].damage_variance must be >= 0")
    return combat


def _parse_monsters(monsters_raw: dict) -> MonsterConfig:
    """Parse the optional ``[monsters]`` table + ``[monsters.tiers.N]`` blocks (R4,
    docs/R4_R6_plan.md). Absent / ``every_n = 0`` -> disabled (the shipped default),
    and no tiers are required. When enabled, tiers 1..max_tier must all be present."""
    every_n = int(monsters_raw.get("every_n", 0))
    if every_n < 0:
        raise ConfigError("[monsters].every_n must be >= 0")
    targeting = str(monsters_raw.get("target_selection", "random")).lower()
    if targeting not in MONSTER_TARGETING:
        raise ConfigError(
            f"[monsters].target_selection = {targeting!r} must be one of {MONSTER_TARGETING}"
        )
    max_tier = int(monsters_raw.get("max_tier", 5))
    if max_tier < 1:
        raise ConfigError("[monsters].max_tier must be >= 1")

    tiers_raw = monsters_raw.get("tiers", {})
    tiers: dict[int, MonsterTier] = {}
    for key, t in tiers_raw.items():
        n = int(key)
        ctx = f"monsters.tiers.{key}"
        tiers[n] = MonsterTier(
            tier=n,
            label=str(t.get("label", f"Tier {n} Monster")),
            hp_pct_of_team=float(_require(t, "hp_pct_of_team", ctx)),
            ac=int(_require(t, "ac", ctx)),
            attack_mod=int(_require(t, "attack_mod", ctx)),
            attack_interval=float(_require(t, "attack_interval", ctx)),
            damage=float(_require(t, "damage", ctx)),
            gold_mult=float(t.get("gold_mult", 1.0)),
            sprite=str(t.get("sprite", "")),
        )
    cfg = MonsterConfig(
        every_n=every_n, target_selection=targeting, max_tier=max_tier, tiers=tiers
    )
    if cfg.enabled:
        missing = [n for n in range(1, max_tier + 1) if n not in tiers]
        if missing:
            raise ConfigError(
                f"[monsters] enabled but tiers {missing} are missing (need 1..{max_tier})"
            )
        for n in range(1, max_tier + 1):
            if tiers[n].hp_pct_of_team <= 0.0:
                raise ConfigError(f"[monsters.tiers.{n}].hp_pct_of_team must be > 0")
    return cfg


def _parse_shop(shop_raw: dict) -> ShopConfig:
    """Parse the optional ``[shop]`` table + ``[shop.items.<id>]`` / ``[shop.caps]``
    (R5, docs/R4_R6_plan.md). Absent / ``enabled = false`` -> disabled default.
    Validates that a *fully geared* character (best item per slot) can't exceed the
    caps, so the naked balance gate stays valid."""
    caps_raw = shop_raw.get("caps", {})
    caps = ShopCaps(
        max_ap_mult=float(caps_raw.get("max_ap_mult", 0.10)),
        max_speed_mult=float(caps_raw.get("max_speed_mult", 0.05)),
        max_ac_bonus=int(caps_raw.get("max_ac_bonus", 2)),
        max_crit_pp=float(caps_raw.get("max_crit_pp", 20.0)),
        max_loot_pp=float(caps_raw.get("max_loot_pp", 40.0)),
    )
    items: dict[str, ShopItem] = {}
    for item_id, it in shop_raw.get("items", {}).items():
        ctx = f"shop.items.{item_id}"
        slot = str(_require(it, "slot", ctx)).lower()
        if slot not in GEAR_SLOTS:
            raise ConfigError(f"[{ctx}].slot = {slot!r} must be one of {GEAR_SLOTS}")
        price = int(_require(it, "price", ctx))
        if price < 0:
            raise ConfigError(f"[{ctx}].price must be >= 0")
        items[item_id] = ShopItem(
            item_id=item_id, slot=slot, name=str(it.get("name", item_id)), price=price,
            ap_mult=float(it.get("ap_mult", 0.0)), ac_bonus=int(it.get("ac_bonus", 0)),
            speed_mult=float(it.get("speed_mult", 0.0)), crit_pp=float(it.get("crit_pp", 0.0)),
            loot_pp=float(it.get("loot_pp", 0.0)),
        )
    cfg = ShopConfig(enabled=bool(shop_raw.get("enabled", False)), items=items, caps=caps)

    # Best-case full gear (max grant per slot, summed) must fit under the caps.
    def _slot_max(attr: str) -> float:
        total = 0.0
        for slot in GEAR_SLOTS:
            slot_items = [it for it in items.values() if it.slot == slot]
            total += max((getattr(it, attr) for it in slot_items), default=0.0)
        return total

    if _slot_max("ap_mult") > caps.max_ap_mult + 1e-9:
        raise ConfigError("[shop] full-gear ap_mult exceeds [shop.caps].max_ap_mult")
    if _slot_max("speed_mult") > caps.max_speed_mult + 1e-9:
        raise ConfigError("[shop] full-gear speed_mult exceeds [shop.caps].max_speed_mult")
    if _slot_max("ac_bonus") > caps.max_ac_bonus + 1e-9:
        raise ConfigError("[shop] full-gear ac_bonus exceeds [shop.caps].max_ac_bonus")
    if _slot_max("crit_pp") > caps.max_crit_pp + 1e-9:
        raise ConfigError("[shop] full-gear crit_pp exceeds [shop.caps].max_crit_pp")
    if _slot_max("loot_pp") > caps.max_loot_pp + 1e-9:
        raise ConfigError("[shop] full-gear loot_pp exceeds [shop.caps].max_loot_pp")
    return cfg


def _parse_events(events_raw: dict) -> dict[str, ArenaEvent]:
    """Parse the optional ``[events.*]`` tables (PLAN.md §4.6). Every knob is
    optional (defaults to a no-op), so an event lists only what it changes."""
    events: dict[str, ArenaEvent] = {}
    for name, e in events_raw.items():
        ctx = f"events.{name}"
        event = ArenaEvent(
            name=name,
            label=str(e.get("label", name.title())),
            tag=str(e.get("tag", "")),
            damage_mult=float(e.get("damage_mult", 1.0)),
            curse=bool(e.get("curse", False)),
            crit_chance_bonus=float(e.get("crit_chance_bonus", 0.0)),
            crit_damage_mult=float(e.get("crit_damage_mult", 1.0)),
            no_miss=bool(e.get("no_miss", False)),
            xp_mult=float(e.get("xp_mult", 1.0)),
        )
        if event.damage_mult < 0 or event.crit_damage_mult < 0 or event.xp_mult < 0:
            raise ConfigError(f"[{ctx}] multipliers must be >= 0")
        events[name] = event
    return events


def with_coeffs(cfg: Config, coeffs: dict[str, float]) -> Config:
    """Return a copy of `cfg` with class coefficients overridden.

    Used by the simulator's tuner to evaluate candidate coefficients without
    touching the file on disk. Engine-aware: under the moore engine it overrides
    ``moore_coeff`` (the AP-scaling factor the moore math reads via ``ap_coeff``),
    so re-tuning moore doesn't silently no-op once ``moore_coeff`` is set.
    """
    field = "moore_coeff" if cfg.combat.engine == "moore" else "coeff"
    new_classes = {
        name: (replace(cd, **{field: coeffs[name]}) if name in coeffs else cd)
        for name, cd in cfg.classes.items()
    }
    return replace(cfg, classes=new_classes)
