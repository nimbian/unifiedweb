"""Card-image layer manifest.

Lists the PNGs available in each layer directory (Color / Cards / Holo / Grade)
so the frontend can composite — and, for now, randomize — card images without
hardcoding filenames. The bytes themselves are served by the StaticFiles mount
at ``{api_prefix}/cards``; this route lives at a distinct path so it isn't
shadowed by that mount.
"""

import os

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.card import CardLayers

router = APIRouter(tags=["cards"])


def _pngs(subdir: str) -> list[str]:
    path = os.path.join(settings.cards_dir, subdir)
    if not os.path.isdir(path):
        return []
    return sorted(f for f in os.listdir(path) if f.lower().endswith(".png"))


@router.get("/card-layers", response_model=CardLayers, summary="Available card layer images")
def card_layers() -> CardLayers:
    return CardLayers(
        color=_pngs("Color"),
        cards=_pngs("Cards"),
        holo=_pngs("Holo"),
        grade=_pngs("Grade"),
    )
