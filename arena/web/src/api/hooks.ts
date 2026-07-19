import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post, ApiError } from "./client";
import type {
  ArenaResponse,
  Character,
  GearState,
  HofRecord,
  LeaderboardResponse,
  Me,
  RosterResponse,
  ShopResponse,
} from "./types";

export function useMe() {
  return useQuery<Me, ApiError>({
    queryKey: ["me"],
    queryFn: () => api<Me>("/api/me"),
    retry: false,
  });
}

export function useRoster() {
  return useQuery<RosterResponse, ApiError>({
    queryKey: ["roster"],
    queryFn: () => api<RosterResponse>("/api/characters"),
    retry: false,
  });
}

export function useCharacter(id: number) {
  return useQuery<Character, ApiError>({
    queryKey: ["character", id],
    queryFn: () => api<Character>(`/api/characters/${id}`),
  });
}

export function useShop() {
  return useQuery<ShopResponse, ApiError>({
    queryKey: ["shop"],
    queryFn: () => api<ShopResponse>("/api/shop"),
  });
}

export function useLeaderboard(by: "damage" | "wins", scope: "season" | "alltime") {
  return useQuery<LeaderboardResponse, ApiError>({
    queryKey: ["leaderboard", by, scope],
    queryFn: () => api<LeaderboardResponse>(`/api/leaderboard?by=${by}&scope=${scope}`),
  });
}

export function useHof() {
  return useQuery<{ records: HofRecord[] }, ApiError>({
    queryKey: ["hof"],
    queryFn: () => api<{ records: HofRecord[] }>("/api/hof"),
  });
}

export function useArena() {
  return useQuery<ArenaResponse, ApiError>({
    queryKey: ["arena"],
    queryFn: () => api<ArenaResponse>("/api/arena"),
    refetchInterval: 4000,
  });
}

function useCharacterMutation<TResp>(id: number, path: string) {
  const qc = useQueryClient();
  return useMutation<TResp, ApiError, Record<string, unknown>>({
    mutationFn: (body) => post<TResp>(`/api/characters/${id}/${path}`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["character", id] });
      void qc.invalidateQueries({ queryKey: ["roster"] });
      void qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

export const useRename = (id: number) => useCharacterMutation<Character>(id, "rename");
export const useRetire = (id: number) =>
  useCharacterMutation<{ ok: boolean; retired_at: string | null }>(id, "retire");
export const useEquip = (id: number) => useCharacterMutation<GearState>(id, "equip");
export const useUnequip = (id: number) => useCharacterMutation<GearState>(id, "unequip");
export const useBuy = (id: number) => useCharacterMutation<GearState>(id, "buy");

export function logout(): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>("/api/auth/logout");
}
