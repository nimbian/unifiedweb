"""Import / update Midweek Monster Mash donors from a CSV (command-line).

The old static site was driven by a hand-maintained ``donors.csv`` with the
header::

    name,initiate,apprentice,knight,master,ascendant,luminary,arbiter

This keeps that workflow from a shell (the same upsert is also available to
admins in the web UI via ``POST /api/mmm/admin/donors``). Existing donors are
matched by name and updated; new ones are inserted. Missing/blank tier columns
default to 0; unknown columns are ignored; blank names are skipped.

Usage (from the backend/ directory, with DATABASE_URL set as for the app)::

    .venv/bin/python -m scripts.import_mmm_donors path/to/donors.csv
"""

from __future__ import annotations

import sys

from app.core.database import SessionLocal
from app.repositories.mmm_repository import MmmRepository
from app.services.mmm_service import MmmService


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m scripts.import_mmm_donors <donors.csv>")
    with open(sys.argv[1], encoding="utf-8-sig") as f:
        text = f.read()
    with SessionLocal() as db:
        result = MmmService(MmmRepository(db)).import_csv_text(text)
        db.commit()
    print(f"MMM donors imported: {result.inserted} inserted, {result.updated} updated.")


if __name__ == "__main__":
    main()
