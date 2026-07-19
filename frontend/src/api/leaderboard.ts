import { apiClient } from './client';
import type { Leaderboard } from '@/types';

export const leaderboardApi = {
  get: async (): Promise<Leaderboard> => {
    const { data } = await apiClient.get<Leaderboard>('/leaderboard');
    return data;
  },
};
