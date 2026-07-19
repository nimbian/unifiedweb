-- 0006_training.sql — R6 cross-player co-training (docs/R4_R6_plan.md).
-- A retired character can mentor a bounded number of times; a trained character
-- records its two parents (lineage display, "Trained by X & Y"). generation
-- already exists (0001). Server-only writes (hard rule #2).

ALTER TABLE characters
    ADD COLUMN mentor_uses  INT NOT NULL DEFAULT 0,   -- times this char has mentored
    ADD COLUMN trained_by_a BIGINT REFERENCES characters(id),  -- parent A (nullable)
    ADD COLUMN trained_by_b BIGINT REFERENCES characters(id);  -- parent B (nullable)
