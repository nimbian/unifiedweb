import { apiClient } from './client';
import type { CardLayers } from '@/types';

export const cardsApi = {
  // Which PNGs exist in each layer directory (Color/Cards/Holo/Grade).
  layers: async (): Promise<CardLayers> => {
    const { data } = await apiClient.get<CardLayers>('/card-layers');
    return data;
  },
};
