-- 0003_rewards.sql — Twitch EventSub channel-point reward hooks (PLAN.md §6.2).
-- Redemptions grant per-user tokens/slots; support events (subs/bits) grant gold.
-- Idempotency uses the existing processed_events table (0001). Server-only writes.

ALTER TABLE users
    ADD COLUMN bonus_slots     INT NOT NULL DEFAULT 0,   -- extra living-roster slots (rented)
    ADD COLUMN reroll_tokens   INT NOT NULL DEFAULT 0,   -- stat rerolls available (!reroll)
    ADD COLUMN priority_tokens INT NOT NULL DEFAULT 0;   -- queue-priority tokens (!enter jumps)
