// Auth context — the SPA equivalent of Flask-Login's `current_user`.
//
// On mount it attempts a silent refresh (using the httpOnly refresh cookie) so a
// returning user is restored without re-doing the OAuth dance. Every account is
// anchored on Discord; a user can sign in with — or link — Google (the "YouTube"
// login) and Twitch. The OAuth redirect flow (login *or* link) stashes the
// provider, intent, and CSRF state in sessionStorage; `completeOAuth` (called by
// the callback page) reads them back to finish the right action.

import { createContext, useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { authApi } from '@/api/auth';
import { setAccessToken } from '@/api/client';
import type { AuthenticatedUser, LinkedAccounts, Provider } from '@/types';

type Intent = 'login' | 'link';

export interface OAuthResult {
  intent: Intent;
  provider: Provider;
  did: string | null;
}

export interface AuthContextValue {
  user: AuthenticatedUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  // Start a sign-in with a provider (redirects the browser).
  login: (provider: Provider) => Promise<void>;
  // Start linking a provider to the signed-in account (redirects the browser).
  linkAccount: (provider: Provider) => Promise<void>;
  // Disconnect a linked provider.
  unlinkAccount: (provider: Provider) => Promise<LinkedAccounts>;
  // Link Discord via a one-time code from the bot's /link (no OAuth redirect).
  redeemLinkCode: (code: string) => Promise<LinkedAccounts>;
  // Finish a redirect flow (login or link) using the ?code & ?state from the URL.
  completeOAuth: (code: string, urlState: string | null) => Promise<OAuthResult>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// sessionStorage keys describing the OAuth redirect in flight.
const OAUTH_PROVIDER = 'oauth_provider';
const OAUTH_INTENT = 'oauth_intent';
const OAUTH_STATE = 'oauth_state';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadProfile = useCallback(async () => {
    const me = await authApi.me();
    setUser(me);
    return me;
  }, []);

  // Silent refresh on first load.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const token = await authApi.refresh();
        setAccessToken(token.access_token);
        if (active) await loadProfile();
      } catch {
        setAccessToken(null);
        if (active) setUser(null);
      } finally {
        if (active) setIsLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [loadProfile]);

  // Kick off an OAuth redirect, recording what we intend to do when it returns.
  const startOAuth = useCallback(async (provider: Provider, intent: Intent) => {
    const { url, state } = await authApi.authorizeUrl(provider);
    sessionStorage.setItem(OAUTH_PROVIDER, provider);
    sessionStorage.setItem(OAUTH_INTENT, intent);
    sessionStorage.setItem(OAUTH_STATE, state);
    window.location.href = url;
  }, []);

  const login = useCallback((provider: Provider) => startOAuth(provider, 'login'), [startOAuth]);
  const linkAccount = useCallback(
    (provider: Provider) => startOAuth(provider, 'link'),
    [startOAuth],
  );

  const completeOAuth = useCallback(
    async (code: string, urlState: string | null): Promise<OAuthResult> => {
      const provider = sessionStorage.getItem(OAUTH_PROVIDER) as Provider | null;
      const intent = (sessionStorage.getItem(OAUTH_INTENT) as Intent | null) ?? 'login';
      const expected = sessionStorage.getItem(OAUTH_STATE);
      sessionStorage.removeItem(OAUTH_PROVIDER);
      sessionStorage.removeItem(OAUTH_INTENT);
      sessionStorage.removeItem(OAUTH_STATE);

      if (!provider) throw new Error('No sign-in is in progress.');
      if (expected && urlState && urlState !== expected) {
        throw new Error('OAuth state mismatch');
      }

      if (intent === 'link') {
        // The redirect reloaded the SPA and dropped the in-memory access token;
        // restore it from the refresh cookie before calling the authenticated
        // link endpoint (the axios interceptor won't auto-refresh /auth/* URLs).
        const restored = await authApi.refresh();
        setAccessToken(restored.access_token);
        await authApi.linkProvider(provider, code);
        const me = await loadProfile();
        return { intent, provider, did: me.did };
      }

      const token = await authApi.exchangeCode(provider, code);
      setAccessToken(token.access_token);
      const me = await loadProfile();
      return { intent, provider, did: me.did };
    },
    [loadProfile],
  );

  const unlinkAccount = useCallback((provider: Provider) => authApi.unlinkProvider(provider), []);

  const redeemLinkCode = useCallback(
    async (code: string): Promise<LinkedAccounts> => {
      const links = await authApi.redeemLinkCode(code);
      // The current access token predates the link and carries no did; mint a
      // fresh one so `did` (and Satchemon access) reflects the new Discord link
      // right away instead of only after the next silent refresh.
      const token = await authApi.refresh();
      setAccessToken(token.access_token);
      await loadProfile();
      return links;
    },
    [loadProfile],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: user !== null,
      isLoading,
      login,
      linkAccount,
      unlinkAccount,
      redeemLinkCode,
      completeOAuth,
      logout,
    }),
    [user, isLoading, login, linkAccount, unlinkAccount, redeemLinkCode, completeOAuth, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
