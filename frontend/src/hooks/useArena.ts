import { useQuery } from '@tanstack/react-query';
import { arenaApi } from '@/api/arena';
import type { LeaderboardBy, LeaderboardScope } from '@/types/arena';

// Live arena state polls every few seconds (matches the standalone arena site).
export function useArenaState() {
  return useQuery({
    queryKey: ['arena', 'live'],
    queryFn: arenaApi.liveState,
    refetchInterval: 4000,
  });
}

export function useArenaLeaderboard(by: LeaderboardBy, scope: LeaderboardScope) {
  return useQuery({
    queryKey: ['arena', 'leaderboard', by, scope],
    queryFn: () => arenaApi.leaderboard(by, scope),
  });
}

export function useHallOfFame() {
  return useQuery({
    queryKey: ['arena', 'hof'],
    queryFn: arenaApi.hallOfFame,
  });
}
