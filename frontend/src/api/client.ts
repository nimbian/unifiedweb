// Axios instance with auth interceptors.
//
// - Request interceptor attaches the in-memory access token as a Bearer header.
// - Response interceptor catches 401s, performs a single refresh (via the
//   httpOnly refresh cookie) and replays the original request. Concurrent 401s
//   share one in-flight refresh promise so we never stampede /auth/refresh.

import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios';
import type { TokenResponse } from '@/types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

// Access token lives in memory only (not localStorage) to reduce XSS exposure.
let accessToken: string | null = null;
export const setAccessToken = (token: string | null) => {
  accessToken = token;
};
export const getAccessToken = () => accessToken;

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // send the refresh cookie on /auth/refresh
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.set('Authorization', `Bearer ${accessToken}`);
  }
  return config;
});

// ── Single-flight refresh ──────────────────────────────────────────────────
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  try {
    const { data } = await axios.post<TokenResponse>(
      `${BASE_URL}/auth/refresh`,
      {},
      { withCredentials: true },
    );
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    setAccessToken(null);
    return null;
  }
}

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    const isAuthEndpoint = original?.url?.includes('/auth/');

    if (error.response?.status === 401 && original && !original._retry && !isAuthEndpoint) {
      original._retry = true;
      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
      const newToken = await refreshPromise;
      if (newToken) {
        original.headers.set('Authorization', `Bearer ${newToken}`);
        return apiClient(original);
      }
    }
    return Promise.reject(error);
  },
);
