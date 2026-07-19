import { apiClient } from './client';
import type { UserProgress } from '@/types';

export const progressApi = {
  get: async (did: number | string): Promise<UserProgress> => {
    const { data } = await apiClient.get<UserProgress>(`/users/${did}/progress`);
    return data;
  },
};
