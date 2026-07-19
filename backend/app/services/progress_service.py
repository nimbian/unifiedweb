"""Progress page business logic.

Assembles a user's headline collection stats and per-set completion counts. Set
completion is "distinct mons owned / card slots in the set" — the same slot
semantics the set drill-down (``SetService.set_view``) uses, but aggregated.

Set categories mirror the collection page's tabs/pickers so each block can
deep-link to the right set:
  * base sets (rwid <= 0) -> three per-class blocks (``baseSets`` tab)
  * named sets in the expansions table -> ``expansions`` tab
  * other named sets (rwid > 0) -> ``sets`` (Unique Sets) tab
"""

from fastapi import HTTPException, status

from app.repositories.collection_repository import CollectionRepository
from app.repositories.set_repository import (
    ITEM_MAX,
    ITEM_MIN,
    LOCATION_MAX,
    LOCATION_MIN,
    SetRepository,
)
from app.schemas.progress import ProgressStats, SetProgress, UserProgress
from app.services.encoding import name_to_slug

# (mons.class literal, display label, base-set picker slug, set rwid) for the base
# blocks. Each base set is a real ``sets`` row with its own role: Creatures=0,
# Items=-1, Locations=-2 — so completing one can grant a role like any other set.
_BASE_CLASS_BLOCKS = [
    ("Monsters", "Creatures", "BaseCreatures", 0),
    ("Item", "Items", "BaseItems", -1),
    ("Locations", "Locations", "BaseLocations", -2),
]


def _unique_group(rwid: int) -> str:
    """Sub-group label for a Unique Set, by the same rwid ranges the sidebar uses."""
    if rwid < ITEM_MIN:
        return "Creatures"
    if rwid < ITEM_MAX:
        return "Items"
    if LOCATION_MIN <= rwid < LOCATION_MAX:
        return "Locations"
    return "Other"


class ProgressService:
    def __init__(self, set_repo: SetRepository, collection_repo: CollectionRepository) -> None:
        self.sets = set_repo
        self.collections = collection_repo

    def build(self, did: int) -> UserProgress:
        if self.collections.resolve_uid(did) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

        total_value, top_value, total_cards, unique_cards = self.collections.progress_stats(did)
        stats = ProgressStats(
            total_value=total_value,
            top_value=top_value,
            total_cards=total_cards,
            unique_cards=unique_cards,
        )

        sets = self._base_blocks(did) + self._named_blocks(did)
        return UserProgress(stats=stats, sets=sets)

    def _base_blocks(self, did: int) -> list[SetProgress]:
        totals = {r._mapping["klass"]: r._mapping["total"] for r in self.sets.base_set_totals()}
        owned = {r._mapping["klass"]: r._mapping["owned"] for r in self.sets.base_set_owned(did)}
        blocks: list[SetProgress] = []
        for klass, label, slug, rwid in _BASE_CLASS_BLOCKS:
            total = totals.get(klass, 0)
            if total == 0:
                continue
            blocks.append(
                SetProgress(
                    name=label,
                    slug=slug,
                    category="baseSets",
                    role=self.sets.role_string(rwid),
                    owned=owned.get(klass, 0),
                    total=total,
                )
            )
        return blocks

    def _named_blocks(self, did: int) -> list[SetProgress]:
        expansion_names = {r._mapping["name"] for r in self.sets.expansions()}
        owned = {r._mapping["name"]: r._mapping["owned"] for r in self.sets.named_set_owned(did)}
        blocks: list[SetProgress] = []
        for r in self.sets.named_set_totals():
            name = r._mapping["name"]
            if name is None:
                continue
            if name in expansion_names:
                category, group = "expansions", None
            else:
                category, group = "sets", _unique_group(r._mapping["rwid"])
            blocks.append(
                SetProgress(
                    name=name,
                    slug=name_to_slug(name),
                    category=category,
                    group=group,
                    role=r._mapping["role"],
                    owned=owned.get(name, 0),
                    total=r._mapping["total"],
                )
            )
        blocks.sort(key=lambda b: (b.category, b.group or "", b.name.lower()))
        return blocks
