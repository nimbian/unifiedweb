-- 0004_monsters.sql — R4 tiered monster battles (docs/R4_R6_plan.md).
-- Only new persistence R4 needs: a key/value game-state table for the escalating
-- monster ladder (so the tier survives restarts). The per-round monster/KO/MVP
-- state lives on the in-memory Entry/RoundContext and drives the overlay events;
-- persisting it (for replay/analytics) is a later, optional addition.
-- Server-only writes (hard rule #2).

CREATE TABLE game_state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed the monster ladder at tier 1 (the arena also defaults to 1 when unset).
INSERT INTO game_state (key, value) VALUES ('monster_ladder_tier', '1');
