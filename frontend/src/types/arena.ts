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

// ── Authed player data (roster / character sheet / shop) ────────────────────
// Reached with the portal Bearer token attached; the arena upserts the
// twitch_uid claim onto its (platform, platform_user_id) user (PLAN §8).

export interface ArenaUser {
  id: number;
  login: string;
  display_name: string;
}

export interface ArenaMe {
  user: ArenaUser;
  gold: number;
}

export interface ItemGrants {
  ap_mult: number;
  ac_bonus: number;
  speed_mult: number;
  crit_pp: number;
  loot_pp: number;
}

export interface ArenaShopItem {
  item_id: string;
  slot: string;
  name: string;
  price: number;
  grants: ItemGrants;
}

export interface ArenaInventoryItem extends ArenaShopItem {
  equipped: boolean;
}

// Equipped gear is a full catalog item when known, else just its id.
export type ArenaEquippedItem = ArenaShopItem | { item_id: string };

export interface ArenaLineage {
  generation: number;
  trained_by: { id: number; name: string }[] | null;
}

export interface ArenaCharacter {
  id: number;
  name: string;
  class_name: string;
  race: string;
  level: number;
  xp: number;
  stats: Record<string, number>;
  battles_fought: number;
  battles_left: number;
  wins: number;
  losses: number;
  lifetime_damage: number;
  lifetime_hits: number;
  lifetime_crits: number;
  highest_hit: number;
  sprite_set: string;
  personality: string;
  equipment: Record<string, ArenaEquippedItem>;
  lineage: ArenaLineage;
  is_retired: boolean;
  retired_at: string | null;
  owner_login: string | null;
  owner_platform: string | null;
  inventory?: ArenaInventoryItem[];
  is_owner?: boolean;
}

export interface RosterResponse {
  living: ArenaCharacter[];
  retired: ArenaCharacter[];
}

export interface ShopResponse {
  enabled: boolean;
  items: ArenaShopItem[];
}

export interface GearState {
  equipment: Record<string, ArenaEquippedItem>;
  inventory: ArenaInventoryItem[];
  gold?: number;
}

export interface RetireResult {
  ok: boolean;
  retired_at: string | null;
}
