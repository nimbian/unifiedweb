"""Set / expansion business logic.

Ports ``api.apiGetCards`` and the sidebar builders. The original endpoint
overloaded one URL to return two different JSON shapes; here the concerns are
split:
  * ``sidebar`` -> the tab buttons (SetSidebar)
  * ``set_view`` -> per-slot ownership for a named/base set (list[SetCardEntry])
"""

from collections import defaultdict

from app.repositories.collection_repository import CollectionRepository
from app.repositories.set_repository import SetRepository
from app.schemas.card import CardRow
from app.schemas.set import ExpansionOption, SetCardEntry, SetOption, SetSidebar
from app.services.encoding import name_to_slug, slug_to_name
from app.services.mappers import row_to_card

# Special category slug for the combined base-set view (kept for compatibility).
BASE_SETS_SLUG = "BaseSets"

# Special slugs for the base sets broken out per mon class. The values are the
# legacy ``mons.class`` literals.
BASE_SET_SLUGS = {
    "BaseCreatures": "Monsters",
    "BaseItems": "Item",
    "BaseLocations": "Locations",
}


class SetService:
    def __init__(self, set_repo: SetRepository, collection_repo: CollectionRepository) -> None:
        self.sets = set_repo
        self.collections = collection_repo

    # ── Sidebar (tab buttons) ────────────────────────────────────────────────
    def sidebar(self) -> SetSidebar:
        return SetSidebar(
            creature_sets=[self._opt(n) for n in self.sets.creature_set_names()],
            item_sets=[self._opt(n) for n in self.sets.item_set_names()],
            location_sets=[self._opt(n) for n in self.sets.location_set_names()],
            expansions=[
                ExpansionOption(exp=r._mapping["exp"], name=r._mapping["name"],
                                slug=name_to_slug(r._mapping["name"]))
                for r in self.sets.expansions()
            ],
        )

    @staticmethod
    def _opt(name: str) -> SetOption:
        return SetOption(name=name, slug=name_to_slug(name))

    # ── Per-set ownership view ───────────────────────────────────────────────
    def set_view(self, did: int, slug: str) -> list[SetCardEntry]:
        """Return per-slot ownership for a base or named set.

        ``slug`` is one of: the combined ``BaseSets`` token, a per-class base-set
        token (``BaseCreatures`` / ``BaseItems`` / ``BaseLocations``), or a
        legacy-encoded set/expansion name. The user's owned cards are grouped by
        ``mon_id`` and matched against the set's card slots.
        """
        owned_by_mon = self._owned_cards_by_mon(did)

        if slug == BASE_SETS_SLUG:
            slots = self.sets.base_set_cards()
        elif slug in BASE_SET_SLUGS:
            slots = self.sets.base_set_cards(BASE_SET_SLUGS[slug])
        else:
            name = slug_to_name(slug)
            slots = self.sets.cards_in_set_by_name(name)

        entries: list[SetCardEntry] = []
        for slot in slots:
            mon_id = slot._mapping["monid"]
            owned = owned_by_mon.get(mon_id, [])
            entries.append(
                SetCardEntry(
                    name=slot._mapping["name"],
                    has=bool(owned),
                    count=len(owned),
                    cards=owned,
                )
            )
        return entries

    def _owned_cards_by_mon(self, did: int) -> dict[int, list[CardRow]]:
        grouped: dict[int, list[CardRow]] = defaultdict(list)
        for r in self.collections.get_full_collection(did):
            card = row_to_card(r)
            if card.mon_id is not None:
                grouped[card.mon_id].append(card)
        return grouped
