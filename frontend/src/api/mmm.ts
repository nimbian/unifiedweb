import { apiClient } from './client';
import type { MmmBadgeTier, MmmDonor, MmmImportResult } from '@/types';

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

  // Admin only: replace donor data from an uploaded CSV.
  importDonors: async (file: File): Promise<MmmImportResult> => {
    const form = new FormData();
    form.append('file', file);
    const { data } = await apiClient.post<MmmImportResult>('/mmm/admin/donors', form);
    return data;
  },
};
