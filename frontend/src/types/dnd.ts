// Mirror of the backend DnD schemas (app/dnd/schemas.py). Discord ids and the
// character `key` are strings (snowflake precision).

export interface CharacterSummary {
  key: string;
  char_name: string | null;
  username: string;
  discord_id: string | null;
  class_id: string;
  class_name: string | null;
  subclass_name: string | null;
  title: string | null;
  level: number;
  xp: number;
  gold: number;
  abyss_best_floor: number;
  duel_wins: number;
  duel_losses: number;
  active: boolean;
}

export interface Ability {
  key: string; // str/dex/con/int/wis/cha
  score: number;
  modifier: number;
}

export interface EquipmentSlot {
  slot: string; // weapon/armor/charm
  name: string | null;
  rarity: string | null;
  affixed: boolean;
  detail: string | null;
  affixes: unknown[];
}

export interface InventoryItem {
  item_id: string;
  name: string | null;
  type: string | null;
  rarity: string | null;
  quantity: number;
  value: number;
}

export interface BestiaryEntry {
  monster_id: string;
  name: string; // "????" when undiscovered
  discovered: boolean;
  kills: number;
  cr: number | null;
  family: string | null;
}

export interface EarnedAchievement {
  id: string;
  name: string;
  description: string | null;
  emoji: string | null;
  category: string | null;
  earned_at: string | null;
}

export interface CharacterDetail {
  key: string;
  char_name: string | null;
  username: string;
  discord_id: string | null;
  class_id: string;
  class_name: string | null;
  subclass_name: string | null;
  title: string | null;
  active: boolean;
  level: number;
  xp: number;
  gold: number;
  hp: number;
  max_hp: number;
  resource: number;
  max_resource: number;
  abilities: Ability[];
  armor_class: number;
  proficiency: number;
  current_zone: string | null;
  bag_used: number;
  bag_capacity: number;
  abyss_best_floor: number;
  abyss_weekly_floor: number;
  duel_wins: number;
  duel_losses: number;
  daily_streak: number;
  affix_bonuses: Record<string, number>;
  equipment: EquipmentSlot[];
  inventory: InventoryItem[];
  bestiary: BestiaryEntry[];
  achievements: EarnedAchievement[];
}

export interface LeaderEntry {
  key: string;
  name: string;
  class_name: string | null;
  level: number;
  value: number;
}

// The set of boards for one character game mode.
export interface ModeLeaderboard {
  by_level: LeaderEntry[];
  by_gold: LeaderEntry[];
  by_abyss: LeaderEntry[];
  by_duels: LeaderEntry[];
  by_speedrun: LeaderEntry[]; // value = seconds from creation to level 20
}

export interface DndLeaderboard {
  normal: ModeLeaderboard; // neither the hardcore nor speedrun flag set
  hardcore: ModeLeaderboard; // permadeath characters
  speedrun: ModeLeaderboard; // characters racing to level 20
}

export interface BossContributor {
  key: string;
  name: string;
  damage: number;
}

export interface ActiveBoss {
  id: number;
  name: string;
  max_hp: number;
  hp: number;
  ac: number;
  spawned_at: string | null;
  contributors: BossContributor[];
}

export interface DefeatedBoss {
  name: string;
  max_hp: number;
  defeated_at: string | null;
}

export interface WorldBossView {
  active: ActiveBoss | null;
  recent: DefeatedBoss[];
}

export interface AchievementInfo {
  id: string;
  name: string;
  description: string | null;
  emoji: string | null;
  category: string | null;
  threshold: number | null;
  earned_count: number;
}

export interface AchievementsView {
  total_players: number;
  achievements: AchievementInfo[];
}
