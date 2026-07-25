import { apiClient } from './client';
import type { MmmBadgeTier, MmmDonor } from '@/types';

export const mmmApi = {
  // The badge-tier catalog (lowest → highest).
  badges: async (): Promise<MmmBadgeTier[]> => {
    const { data } = await apiClient.get<MmmBadgeTier[]>('/mmm/badges');
    return data;
  },

  // The ranked supporter leaderboard.
  donors: async (): Promise<MmmDonor[]> => {
    const { data } = await apiClient.get<MmmDonor[]>('/mmm/donors');
    return data;
  },

  // One supporter by name (404 if not listed).
  donor: async (name: string): Promise<MmmDonor> => {
    const { data } = await apiClient.get<MmmDonor>(`/mmm/donors/${encodeURIComponent(name)}`);
    return data;
  },
};
