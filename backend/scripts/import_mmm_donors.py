"""Import / update Midweek Monster Mash donors from a CSV.

The old static site was driven by a hand-maintained ``donors.csv`` with the
header::

    name,initiate,apprentice,knight,master,ascendant,luminary,arbiter

This keeps that workflow: point it at such a CSV and it upserts each row into the
``mmm_donors`` table by name (existing donors are updated, new ones inserted).
Missing/blank tier columns default to 0; unknown columns are ignored; blank
names are skipped.

Usage (from the backend/ directory, with DATABASE_URL set as for the app)::

    .venv/bin/python -m scripts.import_mmm_donors path/to/donors.csv
"""

from __future__ import annotations

import csv
import sys

from app.core.database import SessionLocal
from app.models import MmmDonor
from app.models.mmm_donor import TIER_KEYS


def _count(row: dict[str, str], key: str) -> int:
    try:
        return max(0, int(row.get(key, "0") or 0))
    except ValueError:
        return 0


def import_csv(path: str) -> tuple[int, int]:
    """Upsert donors from ``path``. Returns (inserted, updated)."""
    inserted = updated = 0
    with SessionLocal() as db, open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Normalize headers to lower-case so 'Name'/'NAME' etc. all work.
        reader.fieldnames = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
        for raw in reader:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            name = row.get("name", "").strip()
            if not name:
                continue
            counts = {key: _count(row, key) for key in TIER_KEYS}
            donor = db.query(MmmDonor).filter(MmmDonor.name == name).one_or_none()
            if donor is None:
                db.add(MmmDonor(name=name, **counts))
                inserted += 1
            else:
                for key, value in counts.items():
                    setattr(donor, key, value)
                updated += 1
        db.commit()
    return inserted, updated


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m scripts.import_mmm_donors <donors.csv>")
    inserted, updated = import_csv(sys.argv[1])
    print(f"MMM donors imported: {inserted} inserted, {updated} updated.")


if __name__ == "__main__":
    main()
