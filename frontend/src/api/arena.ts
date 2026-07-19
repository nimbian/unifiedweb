// Arena (DnD Battle) API — reached through the reverse proxy at /api/arena/*.
//
// The shared apiClient has baseURL /api, so a path of "/arena/<route>" resolves
// to /api/arena/<route>; the proxy strips the /arena segment to the arena's own
// /api/<route>. (So the live-state call is "/arena/arena" → /api/arena/arena →
// arena /api/arena — the doubled word is expected.) The portal access token is
// attached automatically for the authed routes; the read routes below are public.

import axios from 'axios';
import { apiClient } from './client';
import type {
  ArenaCharacter,
  ArenaMe,
  ArenaResponse,
  GearState,
  HofResponse,
  LeaderboardBy,
  LeaderboardResponse,
  LeaderboardScope,
  RetireResult,
  RosterResponse,
  ShopResponse,
} from '@/types/arena';

// The arena server speaks a {"error": {code, message}} envelope (not FastAPI's
// {"detail": ...}). Pull the human message out of an axios failure for the UI.
export function arenaErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const message = err.response?.data?.error?.message;
    if (typeof message === 'string' && message) return message;
  }
  return fallback;
}

// A 401 from an authed arena route means "no arena session": either the caller
// isn't signed in at all, or they're signed in to the portal but haven't linked
// Twitch (the portal token then carries no twitch_uid, so the arena can't map a
// user). Callers pair this with the portal auth state to pick the right prompt.
export function isArenaUnauthorized(err: unknown): boolean {
  return axios.isAxiosError(err) && err.response?.status === 401;
}

export const arenaApi = {
  async liveState(): Promise<ArenaResponse> {
    const { data } = await apiClient.get<ArenaResponse>('/arena/arena');
    return data;
  },
  async leaderboard(by: LeaderboardBy, scope: LeaderboardScope): Promise<LeaderboardResponse> {
    const { data } = await apiClient.get<LeaderboardResponse>('/arena/leaderboard', {
      params: { by, scope },
    });
    return data;
  },
  async hallOfFame(): Promise<HofResponse> {
    const { data } = await apiClient.get<HofResponse>('/arena/hof');
    return data;
  },

  // ── Authed (portal Bearer attached by apiClient) ──────────────────────────
  async me(): Promise<ArenaMe> {
    const { data } = await apiClient.get<ArenaMe>('/arena/me');
    return data;
  },
  async roster(): Promise<RosterResponse> {
    const { data } = await apiClient.get<RosterResponse>('/arena/characters');
    return data;
  },
  async character(id: number): Promise<ArenaCharacter> {
    const { data } = await apiClient.get<ArenaCharacter>(`/arena/characters/${id}`);
    return data;
  },
  async shop(): Promise<ShopResponse> {
    const { data } = await apiClient.get<ShopResponse>('/arena/shop');
    return data;
  },

  async rename(id: number, name: string): Promise<ArenaCharacter> {
    const { data } = await apiClient.post<ArenaCharacter>(
      `/arena/characters/${id}/rename`,
      { name },
    );
    return data;
  },
  async retire(id: number): Promise<RetireResult> {
    const { data } = await apiClient.post<RetireResult>(`/arena/characters/${id}/retire`, {});
    return data;
  },
  async equip(id: number, itemId: string): Promise<GearState> {
    const { data } = await apiClient.post<GearState>(
      `/arena/characters/${id}/equip`,
      { item_id: itemId },
    );
    return data;
  },
  async unequip(id: number, slot: string): Promise<GearState> {
    const { data } = await apiClient.post<GearState>(
      `/arena/characters/${id}/unequip`,
      { slot },
    );
    return data;
  },
  async buy(id: number, itemId: string): Promise<GearState> {
    const { data } = await apiClient.post<GearState>(
      `/arena/characters/${id}/buy`,
      { item_id: itemId },
    );
    return data;
  },
};
