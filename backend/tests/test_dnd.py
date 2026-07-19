"""Tests for the DnD-adventure section (read-only views over the bot's tables)."""


def _seed_character(db, **overrides):
    from app.dnd.models import Player

    defaults = dict(
        user_id=1001, username="Bramsel", char_name="Thorin", discord_id=111,
        class_="fighter", subclass="champion", displayed_title="the Bold",
        level=5, xp=10, gold=250, hp=40, max_hp=40,
        strength=16, dexterity=12, constitution=14, intelligence=8, wisdom=10, charisma=10,
        current_zone="goblin_woods", bag_capacity=20,
        weapon="iron_sword", armor="leather_armor", active=True,
        abyss_best_floor=7, duel_wins=3, duel_losses=1,
    )
    defaults.update(overrides)
    p = Player(**defaults)
    db.add(p)
    db.commit()
    return p


def test_dnd_characters_list(client, db):
    _seed_character(db)
    rows = client.get("/api/dnd/characters").json()
    assert len(rows) == 1
    c = rows[0]
    assert c["key"] == "1001"
    assert c["char_name"] == "Thorin"
    assert c["discord_id"] == "111"
    assert c["class_name"] == "Fighter"        # resolved from classes.json
    assert c["subclass_name"] == "Champion"    # resolved from subclasses.json
    assert c["level"] == 5
    assert c["abyss_best_floor"] == 7


def test_dnd_character_detail(client, db):
    from app.dnd.models import Bestiary, Inventory, PlayerAchievement

    _seed_character(db)
    db.add(Inventory(user_id=1001, item_id="rat_tail", quantity=3))
    db.add(Bestiary(user_id=1001, monster_id="giant_rat", kills=4))
    db.add(PlayerAchievement(user_id=1001, achievement_id="first_blood"))
    db.commit()

    d = client.get("/api/dnd/characters/1001").json()

    # Derived stats.
    assert d["max_resource"] == 9          # base 4 + per_level 1 * level 5
    assert d["proficiency"] == 3           # 2 + (5-1)//4
    # AC = 10 + DEX mod (+1 at 12) + leather armor (+1) = 12.
    assert d["armor_class"] == 12
    abilities = {a["key"]: a for a in d["abilities"]}
    assert abilities["str"]["score"] == 16 and abilities["str"]["modifier"] == 3

    # Equipment names resolved from items.json.
    eq = {e["slot"]: e for e in d["equipment"]}
    assert eq["weapon"]["name"] == "Iron Sword"
    assert eq["armor"]["name"] == "Leather Armor"
    assert eq["charm"]["name"] is None     # empty slot

    # Inventory resolved.
    assert d["inventory"][0]["name"] == "Rat Tail"
    assert d["inventory"][0]["quantity"] == 3

    # Bestiary: only the killed monster is revealed; the rest are masked "????".
    discovered = [b for b in d["bestiary"] if b["discovered"]]
    masked = [b for b in d["bestiary"] if not b["discovered"]]
    assert len(discovered) == 1
    assert discovered[0]["monster_id"] == "giant_rat" and discovered[0]["kills"] == 4
    assert masked and all(b["name"] == "????" and b["cr"] is None for b in masked)

    # Achievements.
    assert [a["id"] for a in d["achievements"]] == ["first_blood"]
    assert d["achievements"][0]["name"] == "First Blood"


def test_dnd_character_404(client):
    assert client.get("/api/dnd/characters/999999").status_code == 404


def test_dnd_leaderboard(client, db):
    # A character with neither flag lands in the "normal" section.
    _seed_character(db)
    normal = client.get("/api/dnd/leaderboard").json()["normal"]
    assert normal["by_level"][0]["key"] == "1001"
    assert normal["by_level"][0]["value"] == 5
    assert normal["by_abyss"][0]["value"] == 7
    assert normal["by_duels"][0]["value"] == 3


def test_dnd_leaderboard_modes_are_disjoint(client, db):
    # One character per mode; each appears only in its own section. Speedrun
    # takes precedence over hardcore when both flags are set.
    _seed_character(db, user_id=1001, char_name="Plain")
    _seed_character(db, user_id=1002, char_name="Grit", hardcore=True)
    _seed_character(db, user_id=1003, char_name="Dash", speedrun=True)
    _seed_character(db, user_id=1004, char_name="Both", hardcore=True, speedrun=True)

    lb = client.get("/api/dnd/leaderboard").json()

    def keys(mode):
        return {r["key"] for r in lb[mode]["by_level"]}

    assert keys("normal") == {"1001"}
    assert keys("hardcore") == {"1002"}
    assert keys("speedrun") == {"1003", "1004"}


def test_dnd_leaderboard_speedrun(client, db):
    from datetime import datetime, timedelta

    base = datetime(2026, 1, 1, 12, 0, 0)
    # A faster run (1h) and a slower run (3h); only completed speedrun-mode runs appear.
    _seed_character(db, user_id=1001, char_name="Swift", speedrun=True,
                    created_at=base, reached_level_20_at=base + timedelta(hours=1))
    _seed_character(db, user_id=1002, char_name="Slow", speedrun=True,
                    created_at=base, reached_level_20_at=base + timedelta(hours=3))
    # Never reached 20 — excluded.
    _seed_character(db, user_id=1003, char_name="Unfinished", speedrun=True, created_at=base)
    # Reached 20 but not a speedrun character — excluded from the speedrun board.
    _seed_character(db, user_id=1004, char_name="Casual",
                    created_at=base, reached_level_20_at=base + timedelta(hours=2))

    speed = client.get("/api/dnd/leaderboard").json()["speedrun"]["by_speedrun"]
    assert [r["key"] for r in speed] == ["1001", "1002"]
    assert speed[0]["value"] == 3600          # 1 hour in seconds, fastest first


def test_dnd_worldboss(client, db):
    from app.dnd.models import BossDamage, WorldBoss

    _seed_character(db)
    db.add(WorldBoss(id=1, boss_id="wyrm", name="Ancient Wyrm", max_hp=1000, hp=600, ac=18, defeated=False))
    db.add(BossDamage(boss_id=1, user_id=1001, damage=150))
    db.commit()

    wb = client.get("/api/dnd/worldboss").json()
    assert wb["active"]["name"] == "Ancient Wyrm"
    assert wb["active"]["hp"] == 600
    assert wb["active"]["contributors"][0]["name"] == "Thorin"
    assert wb["active"]["contributors"][0]["damage"] == 150


def test_dnd_worldboss_none(client):
    wb = client.get("/api/dnd/worldboss").json()
    assert wb["active"] is None


def test_dnd_achievements_catalog(client, db):
    from app.dnd.models import PlayerAchievement

    _seed_character(db)
    db.add(PlayerAchievement(user_id=1001, achievement_id="first_blood"))
    db.commit()

    view = client.get("/api/dnd/achievements").json()
    assert view["total_players"] == 1
    fb = next(a for a in view["achievements"] if a["id"] == "first_blood")
    assert fb["name"] == "First Blood"
    assert fb["earned_count"] == 1
