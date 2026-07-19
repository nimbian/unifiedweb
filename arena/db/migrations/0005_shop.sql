-- 0005_shop.sql — R5 shop + performance-gold economy (docs/R4_R6_plan.md).
-- Per-character equipment (one item per slot); it dies with the character at
-- retirement. Gold lives on the existing users.gold wallet (persists on the user).
-- item_id references the config shop catalog (no FK — catalog is config, not a table).
-- Server-only writes (hard rule #2).

CREATE TABLE character_equipment (
    character_id BIGINT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    slot         TEXT NOT NULL,              -- 'weapon' | 'armor' | 'trinket'
    item_id      TEXT NOT NULL,              -- config [shop.items.<id>] key
    purchased_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (character_id, slot)         -- one item per slot; buying replaces
);
