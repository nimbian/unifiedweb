import { apiClient } from './client';
import type { AuthenticatedUser, LinkedAccounts, Provider, TokenResponse } from '@/types';

export const authApi = {
  // Get a provider's authorize URL to redirect the browser to (+ CSRF state).
  authorizeUrl: async (provider: Provider): Promise<{ url: string; state: string }> => {
    const { data } = await apiClient.get<{ url: string; state: string }>(`/auth/${provider}/url`);
    return data;
  },

  // Exchange the OAuth code for our access token (refresh set as httpOnly cookie).
  exchangeCode: async (provider: Provider, code: string): Promise<TokenResponse> => {
    const { data } = await apiClient.post<TokenResponse>(`/auth/${provider}`, { code });
    return data;
  },

  // Link a provider to the signed-in account. Returns the updated link status.
  linkProvider: async (provider: Provider, code: string): Promise<LinkedAccounts> => {
    const { data } = await apiClient.post<LinkedAccounts>(`/auth/${provider}/link`, { code });
    return data;
  },

  // Disconnect a linked provider from the signed-in account.
  unlinkProvider: async (provider: Provider): Promise<LinkedAccounts> => {
    const { data } = await apiClient.delete<LinkedAccounts>(`/auth/${provider}/link`);
    return data;
  },

  // The signed-in user's connected providers.
  links: async (): Promise<LinkedAccounts> => {
    const { data } = await apiClient.get<LinkedAccounts>('/auth/links');
    return data;
  },

  refresh: async (): Promise<TokenResponse> => {
    const { data } = await apiClient.post<TokenResponse>('/auth/refresh', {});
    return data;
  },

  logout: async (): Promise<void> => {
    await apiClient.post('/auth/logout', {});
  },

  me: async (): Promise<AuthenticatedUser> => {
    const { data } = await apiClient.get<AuthenticatedUser>('/auth/me');
    return data;
  },
};
