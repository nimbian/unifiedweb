"""Set / expansion schemas (the tab + drill-down structures)."""

from pydantic import BaseModel

from app.schemas.card import CardRow


class SetOption(BaseModel):
    """A selectable set/expansion tab button (was the ``msets/isets/lsets`` lists)."""

    name: str
    # URL-safe slug using the legacy encoding (space->_, '->8, ?->9) so existing
    # links keep working; the frontend uses this for routing/keys.
    slug: str


class ExpansionOption(BaseModel):
    """An expansion entry (was ``getExpansions`` -> (exp, expansion))."""

    exp: str
    name: str
    slug: str


class SetSidebar(BaseModel):
    """Everything needed to render a user's collection tabs in one payload."""

    creature_sets: list[SetOption]
    item_sets: list[SetOption]
    location_sets: list[SetOption]
    expansions: list[ExpansionOption]


class SetCardEntry(BaseModel):
    """A card slot within a named set, with whether the user owns it.

    Was the dict built in ``api.apiGetCards``:
        {'name', 'has', 'count', 'cs'}
    """

    name: str | None
    has: bool
    count: int
    cards: list[CardRow]
