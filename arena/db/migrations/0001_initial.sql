-- 0001_initial.sql — D&D Arena initial schema (PostgreSQL 15+)
-- The server is the ONLY writer. A future companion website reads only.
-- Types/indexes refined from PLAN.md §3; the shape is kept intact. Columns for
-- Phase 2+ features (race, trait, seasons, hall_of_fame, processed_events)
-- exist now and sit unused until those phases.

-- Applied by server/migrate.py, which wraps each migration in a transaction and
-- records the version in schema_migrations (that table is created by the runner).

-- ---------------------------------------------------------------------------
-- Users — keyed on (platform, platform_user_id) (PLAN.md §2 rule 4, §3).
-- The same human on two platforms is two separate rows with separate rosters;
-- cross-platform account linking is explicitly out of scope (PLAN.md §12).
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    platform          TEXT        NOT NULL DEFAULT 'twitch',  -- 'twitch' | 'youtube' | 'tiktok'
    platform_user_id  TEXT        NOT NULL,                   -- Twitch user id, YT channel id, ...
    login             TEXT,                                   -- platform handle where applicable
    display_name      TEXT        NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_banned         BOOLEAN     NOT NULL DEFAULT FALSE,
    CONSTRAINT users_platform_identity_uq UNIQUE (platform, platform_user_id)
);
-- Mods target players by login within their platform (!banplayer, !renamechar).
CREATE INDEX idx_users_platform_login ON users (platform, lower(login));

-- ---------------------------------------------------------------------------
-- Characters
-- ---------------------------------------------------------------------------
CREATE TABLE characters (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT   NOT NULL,   -- profanity-filtered, <= 20 chars (enforced in server)
    class           TEXT   NOT NULL,
    race            TEXT   NOT NULL DEFAULT 'human',  -- Phase 2 races; column exists now
    -- ability scores (INT stored as `intl`; `int` is reserved-ish and clashes with type name)
    str             SMALLINT NOT NULL,
    dex             SMALLINT NOT NULL,
    con             SMALLINT NOT NULL,
    intl            SMALLINT NOT NULL,
    wis             SMALLINT NOT NULL,
    cha             SMALLINT NOT NULL,
    level           SMALLINT NOT NULL DEFAULT 1,
    xp              INT      NOT NULL DEFAULT 0,
    battles_fought  SMALLINT NOT NULL DEFAULT 0,   -- retire at 20
    wins            INT      NOT NULL DEFAULT 0,
    losses          INT      NOT NULL DEFAULT 0,
    lifetime_damage BIGINT   NOT NULL DEFAULT 0,
    lifetime_hits   BIGINT   NOT NULL DEFAULT 0,
    lifetime_crits  INT      NOT NULL DEFAULT 0,
    highest_hit     INT      NOT NULL DEFAULT 0,
    sprite_set      TEXT     NOT NULL,             -- assigned at creation
    trait           TEXT,                          -- Phase 3, nullable
    generation      SMALLINT NOT NULL DEFAULT 1,   -- increments per retired char for that user
    personality     TEXT,                          -- cosmetic flavor line
    is_retired      BOOLEAN  NOT NULL DEFAULT FALSE,
    retired_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT characters_class_chk CHECK (class IN (
        'barbarian','fighter','rogue','monk','paladin','ranger','warlock','wizard',
        -- Phase 2 classes allowed by the constraint so no migration is needed to enable them
        'cleric','bard','artificer','druid','sorcerer'
    )),
    CONSTRAINT characters_level_chk  CHECK (level BETWEEN 1 AND 10),
    CONSTRAINT characters_name_len   CHECK (char_length(name) BETWEEN 1 AND 20),
    CONSTRAINT characters_stats_chk  CHECK (
        str  BETWEEN 1 AND 30 AND dex BETWEEN 1 AND 30 AND con BETWEEN 1 AND 30 AND
        intl BETWEEN 1 AND 30 AND wis BETWEEN 1 AND 30 AND cha BETWEEN 1 AND 30
    )
);
-- Fast lookup of a user's living roster (the 3-per-user limit check).
CREATE INDEX idx_characters_user_alive ON characters(user_id) WHERE NOT is_retired;

-- ---------------------------------------------------------------------------
-- Seasons (calendar-month; leaderboards reset, HoF persists) — Phase 2 use
-- ---------------------------------------------------------------------------
CREATE TABLE seasons (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       TEXT        NOT NULL,   -- "Season 3 — March 2026"
    starts_at  TIMESTAMPTZ NOT NULL,
    ends_at    TIMESTAMPTZ NOT NULL,
    CONSTRAINT seasons_range_chk CHECK (ends_at > starts_at)
);

-- ---------------------------------------------------------------------------
-- Rounds
-- ---------------------------------------------------------------------------
CREATE TABLE rounds (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    season_id    INT REFERENCES seasons(id),
    started_at   TIMESTAMPTZ,
    ended_at     TIMESTAMPTZ,
    background   TEXT NOT NULL,
    event        TEXT,                    -- Phase 3 random arena events, nullable
    winner_entry BIGINT,                  -- FK to round_entries, set at end (deferred FK below)
    is_voided    BOOLEAN NOT NULL DEFAULT FALSE  -- crashed/restarted rounds don't consume lifespans
);

-- ---------------------------------------------------------------------------
-- Round entries (one per fighter slot)
-- ---------------------------------------------------------------------------
CREATE TABLE round_entries (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    round_id      BIGINT NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    character_id  BIGINT REFERENCES characters(id),   -- NULL for NPC fill
    slot          SMALLINT NOT NULL,                   -- 0-9 arena position
    is_npc        BOOLEAN  NOT NULL DEFAULT FALSE,
    dummy_sprite  TEXT     NOT NULL,
    total_damage  BIGINT   NOT NULL DEFAULT 0,
    hits          INT      NOT NULL DEFAULT 0,
    crits         INT      NOT NULL DEFAULT 0,
    misses        INT      NOT NULL DEFAULT 0,
    highest_hit   INT      NOT NULL DEFAULT 0,
    placement     SMALLINT,                            -- 1-10, set at round end
    xp_awarded    INT      NOT NULL DEFAULT 0,
    CONSTRAINT round_entries_slot_uq UNIQUE (round_id, slot),
    CONSTRAINT round_entries_slot_chk CHECK (slot BETWEEN 0 AND 9)
);
CREATE INDEX idx_round_entries_character ON round_entries(character_id);
CREATE INDEX idx_round_entries_round     ON round_entries(round_id);

-- Deferred winner FK now that round_entries exists.
ALTER TABLE rounds
    ADD CONSTRAINT rounds_winner_fk
    FOREIGN KEY (winner_entry) REFERENCES round_entries(id);

-- ---------------------------------------------------------------------------
-- Per-swing attack log (~200 rows/round; invaluable for balance analysis).
-- Prune/partition by month if it ever matters (it won't at this scale).
-- ---------------------------------------------------------------------------
CREATE TABLE attacks (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id  BIGINT NOT NULL REFERENCES round_entries(id) ON DELETE CASCADE,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    roll      SMALLINT NOT NULL,   -- raw d20, 1-20
    damage    INT      NOT NULL,   -- 0 on miss
    is_crit   BOOLEAN  NOT NULL DEFAULT FALSE,
    is_miss   BOOLEAN  NOT NULL DEFAULT FALSE,
    CONSTRAINT attacks_roll_chk CHECK (roll BETWEEN 1 AND 20)
);
CREATE INDEX idx_attacks_entry ON attacks(entry_id);

-- ---------------------------------------------------------------------------
-- Idempotency guard for Twitch EventSub redeliveries (Phase 2)
-- ---------------------------------------------------------------------------
CREATE TABLE processed_events (
    event_id     TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Hall of Fame (all-time records; survive season resets) — Phase 2 use
-- ---------------------------------------------------------------------------
CREATE TABLE hall_of_fame (
    record_key   TEXT PRIMARY KEY,   -- 'highest_dps', 'highest_hit', ...
    character_id BIGINT REFERENCES characters(id),
    value        NUMERIC NOT NULL,
    achieved_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

