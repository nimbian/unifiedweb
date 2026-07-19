import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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

// ── Authed player data ──────────────────────────────────────────────────────
// retry:false so a 401 (no arena session — the "Link Twitch to play" gate)
// surfaces immediately instead of being retried three times.

export function useArenaMe() {
  return useQuery({
    queryKey: ['arena', 'me'],
    queryFn: arenaApi.me,
    retry: false,
  });
}

export function useRoster() {
  return useQuery({
    queryKey: ['arena', 'roster'],
    queryFn: arenaApi.roster,
    retry: false,
  });
}

export function useCharacter(id: number) {
  return useQuery({
    queryKey: ['arena', 'character', id],
    queryFn: () => arenaApi.character(id),
    enabled: Number.isFinite(id) && id > 0,
    retry: false,
  });
}

export function useShop() {
  return useQuery({
    queryKey: ['arena', 'shop'],
    queryFn: arenaApi.shop,
  });
}

// Every character mutation refreshes the sheet, the roster and the wallet.
function useInvalidateCharacter(id: number) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['arena', 'character', id] });
    void queryClient.invalidateQueries({ queryKey: ['arena', 'roster'] });
    void queryClient.invalidateQueries({ queryKey: ['arena', 'me'] });
  };
}

export function useRename(id: number) {
  const invalidate = useInvalidateCharacter(id);
  return useMutation({
    mutationFn: (name: string) => arenaApi.rename(id, name),
    onSuccess: invalidate,
  });
}

export function useRetire(id: number) {
  const invalidate = useInvalidateCharacter(id);
  return useMutation({
    mutationFn: () => arenaApi.retire(id),
    onSuccess: invalidate,
  });
}

export function useEquip(id: number) {
  const invalidate = useInvalidateCharacter(id);
  return useMutation({
    mutationFn: (itemId: string) => arenaApi.equip(id, itemId),
    onSuccess: invalidate,
  });
}

export function useUnequip(id: number) {
  const invalidate = useInvalidateCharacter(id);
  return useMutation({
    mutationFn: (slot: string) => arenaApi.unequip(id, slot),
    onSuccess: invalidate,
  });
}

export function useBuy(id: number) {
  const invalidate = useInvalidateCharacter(id);
  return useMutation({
    mutationFn: (itemId: string) => arenaApi.buy(id, itemId),
    onSuccess: invalidate,
  });
}
