import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { collectionsApi } from '@/api/collections';
import type { CardCategory } from '@/types';

// Page size for the global search's incremental (infinite-scroll) loading.
export const SEARCH_PAGE_SIZE = 50;

export function useCards(did: number | string, category: CardCategory) {
  return useQuery({
    queryKey: ['cards', String(did), category],
    queryFn: () => collectionsApi.cards(did, category),
    enabled: Boolean(did),
  });
}

export interface SearchFilters {
  holo?: boolean;
  exp?: string;
  grade?: number;
  cr?: string;
  name?: string;
  active?: boolean;
  sort?: string;
  direction?: 'asc' | 'desc';
}

// Global search, loaded incrementally. Each fetch pulls one page; the table
// requests the next page as the user scrolls to the bottom. ``query`` is the
// server-side global text filter (empty string = unfiltered); ``filters`` carries
// the column filters (holo / expansion / grade / cr / name) and the sort, all
// applied server-side.
export function useSearch(query: string, filters: SearchFilters = {}) {
  const { holo, exp, grade, cr, name, active, sort, direction } = filters;
  return useInfiniteQuery({
    queryKey: [
      'search',
      query,
      holo ?? null,
      exp ?? null,
      grade ?? null,
      cr ?? null,
      name ?? null,
      active ?? null,
      sort ?? null,
      direction ?? null,
    ],
    queryFn: ({ pageParam }) =>
      collectionsApi.search({
        q: query || undefined,
        holo,
        exp,
        grade,
        cr,
        name,
        active,
        sort,
        direction,
        limit: SEARCH_PAGE_SIZE,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (last) => {
      const next = last.offset + last.limit;
      return next < last.total ? next : undefined;
    },
  });
}

// The expansion/grade options for the search column filters (rarely change).
export function useSearchFacets() {
  return useQuery({
    queryKey: ['search', 'facets'],
    queryFn: collectionsApi.searchFacets,
    staleTime: 5 * 60 * 1000,
  });
}

// Sell mutation. On success, invalidate everything the sale changes: the user's
// cards (all categories), their set views, the profile/users totals, and search.
export function useSellCards(did: number | string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionIds, haggle }: { collectionIds: number[]; haggle?: boolean }) =>
      collectionsApi.sell(collectionIds, haggle),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cards', String(did)] });
      qc.invalidateQueries({ queryKey: ['set', String(did)] });
      qc.invalidateQueries({ queryKey: ['user', String(did)] });
      qc.invalidateQueries({ queryKey: ['users'] });
      qc.invalidateQueries({ queryKey: ['search'] });
    },
  });
}

// Buy mutation (from the shop). A purchase moves cards out of the shop (uid 0)
// and into the buyer's collection, and changes GP totals — so invalidate cards,
// set views, users/profile totals, search, and the leaderboard broadly.
export function useBuyCards() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionIds, haggle }: { collectionIds: number[]; haggle?: boolean }) =>
      collectionsApi.buy(collectionIds, haggle),
    onSuccess: () => {
      for (const key of ['cards', 'set', 'user', 'users', 'search', 'leaderboard']) {
        qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}
