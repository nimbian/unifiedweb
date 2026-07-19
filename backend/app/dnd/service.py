"""DnD-adventure business logic: resolve ids to names, compute derived stats,
and assemble the response schemas. Read-only."""

from fastapi import HTTPException, status

from app.dnd import content
from app.dnd.models import Player
from app.dnd.repository import DndRepository, Mode
from app.dnd.schemas import (
    Ability,
    AchievementInfo,
    AchievementsView,
    ActiveBoss,
    BestiaryEntry,
    BossContributor,
    CharacterDetail,
    CharacterSummary,
    DefeatedBoss,
    DndLeaderboard,
    EarnedAchievement,
    EquipmentSlot,
    InventoryItem,
    LeaderEntry,
    ModeLeaderboard,
    WorldBossView,
)

# (schema key, players column) for the six ability scores, in display order.
_ABILITIES = [
    ("str", "strength"), ("dex", "dexterity"), ("con", "constitution"),
    ("int", "intelligence"), ("wis", "wisdom"), ("cha", "charisma"),
]


def _name(p: Player) -> str:
    return p.char_name or p.username or str(p.user_id)


class DndService:
    def __init__(self, repo: DndRepository) -> None:
        self.repo = repo

    # ── characters ───────────────────────────────────────────────────────────
    def list_characters(self) -> list[CharacterSummary]:
        return [self._summary(p) for p in self.repo.list_characters()]

    def _summary(self, p: Player) -> CharacterSummary:
        return CharacterSummary(
            key=str(p.user_id),
            char_name=p.char_name,
            username=p.username,
            discord_id=str(p.discord_id) if p.discord_id is not None else None,
            class_id=p.class_,
            class_name=content.class_name(p.class_),
            subclass_name=content.subclass_name(p.subclass),
            title=p.displayed_title,
            level=p.level,
            xp=p.xp,
            gold=p.gold,
            abyss_best_floor=p.abyss_best_floor,
            duel_wins=p.duel_wins,
            duel_losses=p.duel_losses,
            active=p.active,
        )

    def character_detail(self, key: int) -> CharacterDetail:
        p = self.repo.get_character(key)
        if p is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Character not found")

        affixes = p.affix_bonuses or {}
        abilities = [
            Ability(key=k, score=getattr(p, col), modifier=content.ability_modifier(getattr(p, col)))
            for k, col in _ABILITIES
        ]

        equipment = [
            self._equip_slot("weapon", p.weapon, p.weapon_gear_id),
            self._equip_slot("armor", p.armor, p.armor_gear_id),
            self._equip_slot("charm", p.charm, p.charm_gear_id),
        ]
        # AC = base 10 + DEX mod + equipped armor's AC + affix AC.
        armor_base = self._slot_base_item("armor", p.armor, p.armor_gear_id)
        base_ac = int((content.item_def(armor_base) or {}).get("ac_bonus", 0)) if armor_base else 0
        armor_class = 10 + content.ability_modifier(p.dexterity) + base_ac + int(affixes.get("ac", 0))

        inventory = [
            InventoryItem(
                item_id=row.item_id,
                name=content.item_name(row.item_id),
                type=(content.item_def(row.item_id) or {}).get("type"),
                rarity=(content.item_def(row.item_id) or {}).get("rarity"),
                quantity=row.quantity,
                value=int((content.item_def(row.item_id) or {}).get("value", 0)),
            )
            for row in self.repo.get_inventory(p.user_id)
        ]

        bestiary = self._bestiary(p.user_id)

        achievements = [
            self._earned(pa.achievement_id, pa.earned_at)
            for pa in self.repo.earned_achievements(p.user_id)
        ]

        return CharacterDetail(
            key=str(p.user_id),
            char_name=p.char_name,
            username=p.username,
            discord_id=str(p.discord_id) if p.discord_id is not None else None,
            class_id=p.class_,
            class_name=content.class_name(p.class_),
            subclass_name=content.subclass_name(p.subclass),
            title=p.displayed_title,
            active=p.active,
            level=p.level,
            xp=p.xp,
            gold=p.gold,
            hp=p.hp,
            max_hp=p.max_hp,
            resource=p.resource,
            max_resource=content.max_resource(p.level),
            abilities=abilities,
            armor_class=armor_class,
            proficiency=content.proficiency_bonus(p.level),
            current_zone=p.current_zone.replace("_", " ").title() if p.current_zone else None,
            bag_used=self.repo.inventory_used(p.user_id),
            bag_capacity=p.bag_capacity,
            abyss_best_floor=p.abyss_best_floor,
            abyss_weekly_floor=p.abyss_weekly_floor,
            duel_wins=p.duel_wins,
            duel_losses=p.duel_losses,
            daily_streak=p.daily_streak,
            affix_bonuses=affixes,
            equipment=equipment,
            inventory=inventory,
            bestiary=bestiary,
            achievements=achievements,
        )

    def _slot_base_item(self, slot: str, base_item_id: str | None, gear_id: int | None) -> str | None:
        """The base item id occupying a slot — the affixed instance's base, or the
        plain base item, or None."""
        if gear_id:
            g = self.repo.get_gear(gear_id)
            return g.base_item_id if g else None
        return base_item_id

    def _equip_slot(self, slot: str, base_item_id: str | None, gear_id: int | None) -> EquipmentSlot:
        if gear_id:
            g = self.repo.get_gear(gear_id)
            if g:
                base = content.item_def(g.base_item_id) or {}
                return EquipmentSlot(
                    slot=slot, name=g.name, rarity=g.rarity, affixed=True,
                    detail=base.get("description"), affixes=g.affixes or [],
                )
        if base_item_id:
            it = content.item_def(base_item_id) or {}
            return EquipmentSlot(
                slot=slot, name=content.item_name(base_item_id), rarity=it.get("rarity"),
                affixed=False, detail=it.get("description"), affixes=[],
            )
        return EquipmentSlot(slot=slot, name=None, rarity=None, affixed=False, detail=None, affixes=[])

    def _bestiary(self, user_id: int) -> list[BestiaryEntry]:
        kills = self.repo.bestiary_kills(user_id)
        entries: list[BestiaryEntry] = []
        for mid, mdef in content.monsters().items():
            if mid in kills:
                entries.append(BestiaryEntry(
                    monster_id=mid, name=mdef.get("name", mid), discovered=True,
                    kills=kills[mid], cr=mdef.get("cr"), family=mdef.get("family"),
                ))
            else:
                # Masked like the bot until the player has killed one.
                entries.append(BestiaryEntry(
                    monster_id=mid, name="????", discovered=False, kills=0, cr=None, family=None,
                ))
        entries.sort(key=lambda b: (not b.discovered, -b.kills, b.monster_id))
        return entries

    def _earned(self, achievement_id: str, earned_at) -> EarnedAchievement:  # noqa: ANN001
        d = content.achievement_def(achievement_id) or {}
        return EarnedAchievement(
            id=achievement_id, name=d.get("name", achievement_id), description=d.get("description"),
            emoji=d.get("emoji"), category=d.get("category"), earned_at=earned_at,
        )

    # ── leaderboard ──────────────────────────────────────────────────────────
    def leaderboard(self) -> DndLeaderboard:
        """Boards split across the three character modes, each self-contained."""
        return DndLeaderboard(
            normal=self._mode_board("normal"),
            hardcore=self._mode_board("hardcore"),
            speedrun=self._mode_board("speedrun"),
        )

    def _mode_board(self, mode: Mode) -> ModeLeaderboard:
        def entries(players, value) -> list[LeaderEntry]:  # noqa: ANN001
            return [
                LeaderEntry(
                    key=str(p.user_id), name=_name(p),
                    class_name=content.class_name(p.class_), level=p.level, value=value(p),
                )
                for p in players
            ]

        # Speedrun board: rank by elapsed seconds from creation to hitting level
        # 20, fastest first. Durations are computed here (DB-agnostic) and limited.
        speed = sorted(
            (
                (p, (p.reached_level_20_at - p.created_at).total_seconds())
                for p in self.repo.speedrun_completions(mode)
            ),
            key=lambda t: t[1],
        )[:10]

        return ModeLeaderboard(
            by_level=entries(self.repo.top_by_level(mode), lambda p: p.level),
            by_gold=entries(self.repo.top_by_gold(mode), lambda p: p.gold),
            by_abyss=entries(self.repo.top_by_abyss(mode), lambda p: p.abyss_best_floor),
            by_duels=entries(self.repo.top_by_duels(mode), lambda p: p.duel_wins),
            by_speedrun=[
                LeaderEntry(
                    key=str(p.user_id), name=_name(p),
                    class_name=content.class_name(p.class_), level=p.level, value=int(secs),
                )
                for p, secs in speed
            ],
        )

    # ── world boss ───────────────────────────────────────────────────────────
    def world_boss(self) -> WorldBossView:
        boss = self.repo.active_boss()
        active = None
        if boss is not None:
            contributors = [
                BossContributor(
                    key=str(r.key) if r.key is not None else "0",
                    name=(r.char_name or r.username or "Unknown"),
                    damage=r.damage,
                )
                for r in self.repo.boss_contributors(boss.id)
            ]
            active = ActiveBoss(
                id=boss.id, name=boss.name, max_hp=boss.max_hp, hp=boss.hp, ac=boss.ac,
                spawned_at=boss.spawned_at, contributors=contributors,
            )
        recent = [
            DefeatedBoss(name=b.name, max_hp=b.max_hp, defeated_at=b.defeated_at)
            for b in self.repo.recent_defeated()
        ]
        return WorldBossView(active=active, recent=recent)

    # ── achievements ─────────────────────────────────────────────────────────
    def achievements(self) -> AchievementsView:
        counts = self.repo.achievement_counts()
        items = [
            AchievementInfo(
                id=a["id"], name=a["name"], description=a.get("description"), emoji=a.get("emoji"),
                category=a.get("category"), threshold=a.get("threshold"),
                earned_count=counts.get(a["id"], 0),
            )
            for a in content.achievements()
        ]
        return AchievementsView(total_players=self.repo.player_count(), achievements=items)
