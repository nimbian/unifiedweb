-- 0007_inventory.sql — real per-character gear inventory (owner-ratified 2026-07-11).
--
-- character_equipment (0005) becomes the "equipped pointer" (one item per slot);
-- character_items is OWNERSHIP. Buying adds to the inventory and equips; replacing
-- a slot returns the old item to the inventory instead of destroying it; unequip
-- clears the pointer and keeps the item. Equipped ⊆ owned, enforced by a
-- composite FK. item_id references the config [shop.items.<id>] catalog (no FK —
-- the catalog is config, not a table).

CREATE TABLE character_items (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    item_id      TEXT   NOT NULL,
    acquired_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (character_id, item_id)   -- one copy of each catalog item per character
);

-- Backfill: everything currently equipped is owned.
INSERT INTO character_items (character_id, item_id, acquired_at)
SELECT character_id, item_id, purchased_at FROM character_equipment
ON CONFLICT DO NOTHING;

-- Integrity: an equipped item must be an owned item.
ALTER TABLE character_equipment
    ADD CONSTRAINT character_equipment_owned_fk
    FOREIGN KEY (character_id, item_id)
    REFERENCES character_items (character_id, item_id) ON DELETE CASCADE;
