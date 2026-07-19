import { apiClient } from './client';
import type {
  AchievementsView,
  CharacterDetail,
  CharacterSummary,
  DndLeaderboard,
  WorldBossView,
} from '@/types/dnd';

export const dndApi = {
  characters: async (): Promise<CharacterSummary[]> => {
    const { data } = await apiClient.get<CharacterSummary[]>('/dnd/characters');
    return data;
  },
  character: async (key: string): Promise<CharacterDetail> => {
    const { data } = await apiClient.get<CharacterDetail>(`/dnd/characters/${key}`);
    return data;
  },
  leaderboard: async (): Promise<DndLeaderboard> => {
    const { data } = await apiClient.get<DndLeaderboard>('/dnd/leaderboard');
    return data;
  },
  worldBoss: async (): Promise<WorldBossView> => {
    const { data } = await apiClient.get<WorldBossView>('/dnd/worldboss');
    return data;
  },
  achievements: async (): Promise<AchievementsView> => {
    const { data } = await apiClient.get<AchievementsView>('/dnd/achievements');
    return data;
  },
};
