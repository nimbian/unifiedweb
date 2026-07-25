// Mirror of the backend Pydantic schemas. Kept in one place and imported by the
// api clients and pages so column definitions stay type-safe.

export interface UserSummary {
  name: string | null;
  // String, not number: Discord snowflake ids exceed JS Number.MAX_SAFE_INTEGER,
  // so a numeric did would be silently rounded and break /user/:did links.
  did: string;
  card_count: number;
  collection_value: string; // Decimal serialized as string
  gp: string;
  last_active: string | null; // ISO date of most recent card (Active pill)
}

export interface UserProfile {
  did: string;
  name: string | null;
  gp: string; // Decimal serialized as string
  roleid: number | null; // chosen set's rwid (picker value)
  role: string | null; // sets.role text shown below the name
}

// A selectable role — a set the user has completed.
export interface RoleOption {
  rwid: number;
  name: string | null;
  role: string | null;
}

export interface RoleResult {
  roleid: number | null;
  role: string | null;
}

// Progress page: headline stats + per-set completion.
export interface ProgressStats {
  total_value: string; // Decimal serialized as string
  top_value: string; // one of each (most valuable copy per mon)
  total_cards: number;
  unique_cards: number;
}

export type SetCategory = 'baseSets' | 'sets' | 'expansions';

export interface SetProgress {
  name: string;
  slug: string;
  category: SetCategory;
  // Sub-section within Unique Sets (Creatures/Items/Locations); null otherwise.
  group: string | null;
  // The set's role (sets.role); shown when the set is complete. null otherwise.
  role: string | null;
  owned: number;
  total: number;
}

export interface UserProgress {
  stats: ProgressStats;
  sets: SetProgress[];
}

export interface CardRow {
  collection_id: number;
  cr: string | null;
  name: string | null;
  exp: string | null;
  grade: number | null;
  holo: boolean;
  edition: string;
  value: string | null;
  set_name: string | null;
  date: string | null;
  mon_id: number | null;
}

export interface SearchRow {
  user: string | null;
  collection_id: number;
  cr: string | null;
  name: string | null;
  exp: string | null;
  grade: number | null;
  holo: boolean;
  edition: string;
  value: string | null;
  set_name: string | null;
  last_active: string | null; // owner's most recent card date (Active pill)
}

export interface SearchResults {
  items: SearchRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface SearchFacets {
  expansions: string[];
  grades: number[];
  crs: string[];
}

export interface CardLayers {
  color: string[];
  cards: string[];
  holo: string[];
  grade: string[];
}

export interface LeaderboardCard {
  user: string | null;
  collection_id: number;
  cr: string | null;
  name: string | null;
  exp: string | null;
  grade: number | null;
  holo: boolean;
  edition: string;
  value: string | null;
  date: string | null;
}

export interface CollectionRanking {
  user: string | null;
  did: string;
  value: string; // Decimal serialized as string
}

export interface CountRanking {
  user: string | null;
  did: string;
  count: number;
}

export interface Leaderboard {
  today: LeaderboardCard[];
  past_7_days: LeaderboardCard[];
  this_month: LeaderboardCard[];
  perfect_thirty: LeaderboardCard[];
  top_collections: CollectionRanking[];
  best_copy_collections: CollectionRanking[];
  pristine_hunters: CountRanking[];
}

export interface SetOption {
  name: string;
  slug: string;
}

export interface ExpansionOption {
  exp: string;
  name: string;
  slug: string;
}

export interface SetSidebar {
  creature_sets: SetOption[];
  item_sets: SetOption[];
  location_sets: SetOption[];
  expansions: ExpansionOption[];
}

export interface SetCardEntry {
  name: string | null;
  has: boolean;
  count: number;
  cards: CardRow[];
}

export interface DriveImage {
  id: string;
  name: string;
}

export interface AuthenticatedUser {
  did: string;
  name: string | null;
  rwid: number | null;
  is_admin?: boolean;
}

// Sign-in providers. Discord is the primary account; Google (the "YouTube"
// login) and Twitch can be linked to it and used to sign in.
export type Provider = 'discord' | 'google' | 'twitch';

export interface ProviderLink {
  linked: boolean;
  handle: string | null;
}

export interface LinkedAccounts {
  discord: ProviderLink;
  google: ProviderLink;
  twitch: ProviderLink;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export type CardCategory = 'full' | 'monsters' | 'items' | 'locations';

export interface SoldCard {
  collection_id: number;
  name: string | null;
  value: string | null;
  payout: string;
}

export interface SellResult {
  sold: SoldCard[];
  total_payout: string;
  new_gp: string;
  rate: number;
  roll: number | null; // the d20 roll on a haggle sale; null for a straight sale
}

export interface BoughtCard {
  collection_id: number;
  name: string | null;
  value: string | null;
  cost: string;
}

// ── Midweek Monster Mash donor badges ──────────────────────────────────────
export interface MmmBadgeTier {
  key: string;
  title: string;
  points: number; // points awarded per badge of this tier
}

export interface MmmDonor {
  name: string;
  points: number;
  total_badges: number;
  rank: number;
  badges: Record<string, number>; // tier key -> count
}

export interface MmmImportResult {
  inserted: number;
  updated: number;
  total: number;
}

export interface BuyResult {
  bought: BoughtCard[];
  total_cost: string;
  new_gp: string;
  rate: number;
  roll: number | null; // the d20 roll on a haggle buy; null for a straight buy
}
