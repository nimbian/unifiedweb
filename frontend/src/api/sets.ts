import { apiClient } from './client';
import type { SetCardEntry, SetSidebar } from '@/types';

export const setsApi = {
  sidebar: async (): Promise<SetSidebar> => {
    const { data } = await apiClient.get<SetSidebar>('/sets/sidebar');
    return data;
  },

  setView: async (did: number | string, slug: string): Promise<SetCardEntry[]> => {
    const { data } = await apiClient.get<SetCardEntry[]>(`/users/${did}/sets/${slug}`);
    return data;
  },
};
