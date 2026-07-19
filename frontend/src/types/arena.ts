// Mirrors of the arena server's JSON contract (arena/server/webapi.py). These
// are reached through the reverse proxy at /api/arena/* (the proxy strips the
// /arena segment back to the arena's native /api/*).

export interface ArenaFighter {
  slot: number;
  name: string;
  class: string;
  is_npc: boolean;
  owner: string | null;
  [key: string]: unknown;
}

export interface ArenaQueueEntry {
  character_id: number;
  name: string;
  priority: boolean;
}

export interface ArenaResponse {
  phase: string;
  round: Record<string, unknown> | null;
  fighters: ArenaFighter[];
  queue: ArenaQueueEntry[];
  is_open: boolean;
}

export type LeaderboardBy = 'damage' | 'wins';
export type LeaderboardScope = 'season' | 'alltime';

export interface LeaderRow {
  name: string;
  value: number;
}

export interface LeaderboardResponse {
  scope: string;
  season_id?: number;
  by: string;
  rows: LeaderRow[];
}

export interface HofRecord {
  record_key: string;
  character_id: number | null;
  character_name: string;
  value: number;
  achieved_at: string | null;
}

export interface HofResponse {
  records: HofRecord[];
}
