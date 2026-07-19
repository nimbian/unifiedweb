"""Collection business logic (per-user card lists + global search + selling)."""

import random
from decimal import Decimal

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.repositories.collection_repository import CollectionRepository
from app.schemas.buy import BoughtCard, BuyRequest, BuyResult
from app.schemas.card import CardRow, SearchFacets, SearchResults
from app.schemas.sell import SellRequest, SellResult, SoldCard
from app.services.mappers import row_to_card, row_to_search

logger = get_logger(__name__)

# Maps the frontend "category" tab to the legacy ``mons.class`` literal.
CLASS_LITERALS = {
    "monsters": "Monsters",
    "items": "Item",       # note: legacy class literal is singular "Item"
    "locations": "Locations",
}

# Cards sell for 70% of value on a straight sale (the bot's ``s_button`` rate).
SELL_RATE = 0.7

# Haggle sell: a d20 "persuasion check" gamble (the bot's ``h_s_button``). Each
# tier is (inclusive max roll, rate). 1 -> 50%, 2-8 -> 60%, 9-12 -> 70%,
# 13-19 -> 80%, 20 -> 90%. Ported verbatim from buttons.py.
_HAGGLE_SELL_TIERS: list[tuple[int, float]] = [(1, 0.5), (8, 0.6), (12, 0.7), (19, 0.8), (20, 0.9)]

# Buying from the shop costs 150% on a straight buy (the bot's ``buy_button``).
BUY_RATE = 1.5

# Haggle buy (the bot's ``haggle_buy_button``): a better roll is *cheaper*.
# 1 -> 170%, 2-8 -> 160%, 9-12 -> 150%, 13-19 -> 140%, 20 -> 130%. The worst case
# (170%) is what the buyer must be able to afford before rolling.
_HAGGLE_BUY_TIERS: list[tuple[int, float]] = [(1, 1.7), (8, 1.6), (12, 1.5), (19, 1.4), (20, 1.3)]
HAGGLE_BUY_WORST_RATE = 1.7


def _tier_rate(tiers: list[tuple[int, float]], roll: int) -> float:
    for max_roll, rate in tiers:
        if roll <= max_roll:
            return rate
    return tiers[-1][1]


def _at_rate(value: Decimal | None, rate: float) -> Decimal:
    """Per-card value * rate, rounded to 3 dp (the bot's ``round(v * rate, 3)``)."""
    return Decimal(str(round(float(value or 0) * rate, 3)))


class CollectionService:
    def __init__(self, repo: CollectionRepository) -> None:
        self.repo = repo

    def full_collection(self, did: int) -> list[CardRow]:
        return [row_to_card(r) for r in self.repo.get_full_collection(did)]

    def by_category(self, did: int, category: str) -> list[CardRow]:
        klass = CLASS_LITERALS[category]
        return [row_to_card(r) for r in self.repo.get_by_class(did, klass)]

    def by_cr(self, did: int, cr_code: str) -> list[CardRow]:
        """The CR drill-down (was /api/cs/<c>/<did>)."""
        return [row_to_card(r) for r in self.repo.get_cards_for_cr(did, cr_code)]

    def search(
        self,
        q: str | None,
        holo: bool | None,
        exp: str | None,
        grade: int | None,
        cr: str | None,
        name: str | None,
        active: bool | None,
        sort: str | None,
        direction: str,
        limit: int,
        offset: int,
    ) -> SearchResults:
        """A page of the global search grid (was /api/getAll), with an optional
        global text filter, a card-name filter, holo Yes/No, expansion, grade,
        CR and owner-activity filters, server-side sorting, and the total match
        count so the client can load results incrementally.
        """
        total = self.repo.count_all_collections(q, holo, exp, grade, cr, name, active)
        rows = self.repo.get_all_collections(
            q, holo, exp, grade, cr, name, active, sort, direction, limit=limit, offset=offset
        )
        return SearchResults(
            items=[row_to_search(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def search_facets(self) -> SearchFacets:
        """Distinct expansions, grades and CRs for the search column-filter dropdowns."""
        expansions, grades, crs = self.repo.search_facets()
        return SearchFacets(
            expansions=list(expansions), grades=list(grades), crs=list(crs)
        )

    def sell(self, did: int, request: SellRequest) -> SellResult:
        """Sell the caller's own cards (ports the bot's /sell ``s_button`` and the
        ``h_s_button`` haggle gamble).

        A straight sale pays a flat 70%. A haggle sale rolls a d20 "persuasion
        check" for a 50%–90% rate — the roll is taken server-side and the result
        is final (the client cannot influence or retry it).

        Ownership is enforced server-side: only cards actually owned by ``did`` are
        sold; ids the caller does not own are rejected so the client cannot probe
        or affect another user's collection.
        """
        uid = self.repo.resolve_uid(did)
        if uid is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not registered")

        requested = set(request.collection_ids)
        owned = self.repo.get_owned_for_sale(did, list(requested))
        owned_by_id = {r._mapping["collection_id"]: r for r in owned}

        # Reject the whole request if any requested card is not the caller's.
        not_owned = requested - owned_by_id.keys()
        if not_owned:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"These cards are not yours: {sorted(not_owned)}",
            )

        if request.haggle:
            roll: int | None = random.randint(1, 20)
            rate = _tier_rate(_HAGGLE_SELL_TIERS, roll)
        else:
            roll = None
            rate = SELL_RATE

        sold: list[SoldCard] = []
        payouts: list[tuple[int, Decimal]] = []
        total = Decimal("0")
        for cid in requested:
            row = owned_by_id[cid]._mapping
            payout = _at_rate(row["value"], rate)
            total += payout
            payouts.append((cid, payout))
            sold.append(
                SoldCard(collection_id=cid, name=row["name"], value=row["value"], payout=payout)
            )

        new_gp = self.repo.execute_sale(uid, did, payouts, total)
        logger.info(
            "did=%s sold %d card(s) for %s GP (haggle=%s roll=%s rate=%s)",
            did, len(sold), total, request.haggle, roll, rate,
        )
        return SellResult(sold=sold, total_payout=total, new_gp=new_gp, rate=rate, roll=roll)

    def buy(self, did: int, request: BuyRequest) -> BuyResult:
        """Buy cards from the shop (the system user's uid-0 collection); ports the
        bot's ``buy_button`` / ``haggle_buy_button``.

        A straight buy costs 150% of value. A haggle buy rolls a d20 for a
        130%–170% rate (a better roll is cheaper) — but the buyer must be able to
        afford the worst case (170%) before rolling, and the roll is final.

        Only cards currently in the shop can be bought (enforced server-side), and
        the buyer must have enough GP.
        """
        uid = self.repo.resolve_uid(did)
        if uid is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not registered")

        requested = set(request.collection_ids)
        shop = self.repo.get_shop_cards_for_buy(list(requested))
        shop_by_id = {r._mapping["collection_id"]: r for r in shop}

        # Reject if any requested card is not actually in the shop.
        not_shop = requested - shop_by_id.keys()
        if not_shop:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"These cards are not in the shop: {sorted(not_shop)}",
            )

        # Affordability is checked against the worst case the buy could cost (170%
        # when haggling), so a committed haggle can never overdraw the buyer.
        required_rate = HAGGLE_BUY_WORST_RATE if request.haggle else BUY_RATE
        required = sum(
            (_at_rate(shop_by_id[cid]._mapping["value"], required_rate) for cid in requested),
            Decimal("0"),
        )
        gp = self.repo.get_gp(uid) or Decimal("0")
        if gp < required:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Not enough GP: need {required}, have {gp}",
            )

        if request.haggle:
            roll: int | None = random.randint(1, 20)
            rate = _tier_rate(_HAGGLE_BUY_TIERS, roll)
        else:
            roll = None
            rate = BUY_RATE

        bought: list[BoughtCard] = []
        total = Decimal("0")
        for cid in requested:
            row = shop_by_id[cid]._mapping
            cost = _at_rate(row["value"], rate)
            total += cost
            bought.append(
                BoughtCard(collection_id=cid, name=row["name"], value=row["value"], cost=cost)
            )

        new_gp = self.repo.execute_buy(uid, list(requested), total)
        logger.info(
            "did=%s bought %d card(s) for %s GP (haggle=%s roll=%s rate=%s)",
            did, len(bought), total, request.haggle, roll, rate,
        )
        return BuyResult(bought=bought, total_cost=total, new_gp=new_gp, rate=rate, roll=roll)
