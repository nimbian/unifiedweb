-- 0002_betting.sql — chat betting economy (PLAN.md §6.6).
-- Free virtual "gold" wallet on each user + one bet per user per round.
-- The server is the ONLY writer; gold is fake currency (never channel points).

-- Gold wallet. Defaults to 0; the server credits the configured starting_gold
-- when it first registers a user (so the amount stays a config value, not a
-- schema constant).
ALTER TABLE users ADD COLUMN gold BIGINT NOT NULL DEFAULT 0;

-- One bet per user per round, placed during ROSTER_LOCK, settled at round end.
CREATE TABLE bets (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    round_id     BIGINT NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    slot         SMALLINT NOT NULL,            -- the fighter slot bet on (0-9)
    amount       BIGINT   NOT NULL,            -- gold staked (already deducted)
    payout       BIGINT,                       -- gold returned at settlement (NULL until settled)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT bets_one_per_round UNIQUE (round_id, user_id),
    CONSTRAINT bets_slot_chk  CHECK (slot BETWEEN 0 AND 9),
    CONSTRAINT bets_amount_chk CHECK (amount > 0)
);
CREATE INDEX idx_bets_round ON bets(round_id);
