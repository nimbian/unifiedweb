import { useQuery } from '@tanstack/react-query';
import { leaderboardApi } from '@/api/leaderboard';

export function useLeaderboard() {
  return useQuery({
    queryKey: ['leaderboard'],
    queryFn: leaderboardApi.get,
    staleTime: 60 * 1000, // refreshes on its own cadence; pulls don't change by the second
  });
}
