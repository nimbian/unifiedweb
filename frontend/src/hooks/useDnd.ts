import { useQuery } from '@tanstack/react-query';
import { dndApi } from '@/api/dnd';

export function useDndCharacters() {
  return useQuery({ queryKey: ['dnd', 'characters'], queryFn: dndApi.characters });
}

export function useDndCharacter(key: string) {
  return useQuery({
    queryKey: ['dnd', 'character', key],
    queryFn: () => dndApi.character(key),
    enabled: Boolean(key),
  });
}

export function useDndLeaderboard() {
  return useQuery({ queryKey: ['dnd', 'leaderboard'], queryFn: dndApi.leaderboard });
}

export function useWorldBoss() {
  return useQuery({
    queryKey: ['dnd', 'worldboss'],
    queryFn: dndApi.worldBoss,
    refetchInterval: 30_000, // the boss is live; keep it fresh
  });
}

export function useDndAchievements() {
  return useQuery({ queryKey: ['dnd', 'achievements'], queryFn: dndApi.achievements });
}
