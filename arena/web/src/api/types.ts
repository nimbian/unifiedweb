// Mirrors of the server's /api JSON contract (server/webapi.py).

export interface User {
  id: number;
  login: string;
  display_name: string;
}

export interface Me {
  user: User;
  gold: number;
}

export interface ItemGrants {
  ap_mult: number;
  ac_bonus: number;
  speed_mult: number;
  crit_pp: number;
  loot_pp: number;
}

export interface ShopItem {
  item_id: string;
  slot: string;
  name: string;
  price: number;
  grants: ItemGrants;
}

export interface InventoryItem extends ShopItem {
  equipped: boolean;
}

export interface Lineage {
  generation: number;
  trained_by: { id: number; name: string }[] | null;
}

export type EquippedItem = ShopItem | { item_id: string };

export interface Character {
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
  equipment: Record<string, EquippedItem>;
  lineage: Lineage;
  is_retired: boolean;
  retired_at: string | null;
  owner_login: string | null;
  owner_platform: string | null;
  inventory?: InventoryItem[];
  is_owner?: boolean;
}

export interface RosterResponse {
  living: Character[];
  retired: Character[];
}

export interface ShopResponse {
  enabled: boolean;
  items: ShopItem[];
}

export interface GearState {
  equipment: Record<string, EquippedItem>;
  inventory: InventoryItem[];
  gold?: number;
}

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

export interface ArenaFighter {
  slot: number;
  name: string;
  class: string;
  is_npc: boolean;
  owner: string | null;
  [key: string]: unknown;
}

export interface ArenaResponse {
  phase: string;
  round: Record<string, unknown> | null;
  fighters: ArenaFighter[];
  queue: { character_id: number; name: string; priority: boolean }[];
  is_open: boolean;
}
