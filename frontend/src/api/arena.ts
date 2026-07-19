// Arena (DnD Battle) API — reached through the reverse proxy at /api/arena/*.
//
// The shared apiClient has baseURL /api, so a path of "/arena/<route>" resolves
// to /api/arena/<route>; the proxy strips the /arena segment to the arena's own
// /api/<route>. (So the live-state call is "/arena/arena" → /api/arena/arena →
// arena /api/arena — the doubled word is expected.) The portal access token is
// attached automatically for the authed routes; the read routes below are public.

import { apiClient } from './client';
import type {
  ArenaResponse,
  HofResponse,
  LeaderboardBy,
  LeaderboardResponse,
  LeaderboardScope,
} from '@/types/arena';

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
};
