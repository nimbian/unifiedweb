import { apiClient } from './client';
import type {
  BuyResult,
  CardCategory,
  CardRow,
  SearchFacets,
  SearchResults,
  SellResult,
} from '@/types';

export interface SearchParams {
  q?: string;
  holo?: boolean;
  exp?: string;
  grade?: number;
  cr?: string;
  name?: string;
  active?: boolean;
  sort?: string;
  direction?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

export const collectionsApi = {
  cards: async (did: number | string, category: CardCategory = 'full'): Promise<CardRow[]> => {
    const { data } = await apiClient.get<CardRow[]>(`/users/${did}/cards`, {
      params: { category },
    });
    return data;
  },

  cardsByCr: async (did: number | string, cr: string): Promise<CardRow[]> => {
    const { data } = await apiClient.get<CardRow[]>(`/users/${did}/cards/cr/${cr}`);
    return data;
  },

  // A single page of the global search. The backend filters/orders server-side,
  // so the frontend loads results incrementally rather than all at once.
  search: async (params: SearchParams = {}): Promise<SearchResults> => {
    const { data } = await apiClient.get<SearchResults>('/search', { params });
    return data;
  },

  // Distinct expansions/grades across all collections — the options offered by
  // the search column filters.
  searchFacets: async (): Promise<SearchFacets> => {
    const { data } = await apiClient.get<SearchFacets>('/search/facets');
    return data;
  },

  // Sell the authenticated user's own cards. The server resolves the seller from
  // the JWT, so only your own cards can ever be sold. ``haggle`` opts into the
  // d20 gamble (50%-90%) instead of the flat 70%.
  sell: async (collectionIds: number[], haggle = false): Promise<SellResult> => {
    const { data } = await apiClient.post<SellResult>('/me/sell', {
      collection_ids: collectionIds,
      haggle,
    });
    return data;
  },

  // Buy shop cards (the system user's uid-0 collection) for the signed-in user.
  // ``haggle`` opts into the d20 gamble (130%-170%) instead of the flat 150%.
  buy: async (collectionIds: number[], haggle = false): Promise<BuyResult> => {
    const { data } = await apiClient.post<BuyResult>('/me/buy', {
      collection_ids: collectionIds,
      haggle,
    });
    return data;
  },
};
