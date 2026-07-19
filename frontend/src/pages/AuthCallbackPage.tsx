// OAuth redirect target for every provider. Reads ?code & ?state, then finishes
// whichever flow was in progress: a sign-in (route to the user's collection) or
// an account link (route back to the Account page).

import { useEffect, useRef, useState } from 'react';
import { Button, Center, Loader, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import axios from 'axios';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';

// Pull the backend's human-readable reason out of an error, if there is one.
// The /auth/* endpoints return { detail: "..." }; anything else falls back to a
// generic message.
function messageFor(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (!err.response) return 'Could not reach the server. Please try again.';
  }
  return 'Sign-in failed. Please try again.';
}

export function AuthCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { completeOAuth } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false); // guard against StrictMode double-invoke

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const code = params.get('code');
    const state = params.get('state');
    const oauthError = params.get('error');

    if (oauthError) {
      // The provider itself refused (e.g. the Google app is still in "Testing"
      // and this account isn't a test user, or the user hit "Cancel").
      setError('The provider refused the sign-in. If this is a new user, the app may still be in test mode.');
      return;
    }
    if (!code) {
      setError('Missing authorization code.');
      return;
    }

    completeOAuth(code, state)
      .then(({ intent, did }) => {
        if (intent === 'link') {
          notifications.show({ message: 'Account connected', color: 'green' });
          navigate('/account', { replace: true });
        } else {
          notifications.show({ message: 'Signed in', color: 'green' });
          // Discord-anchored users land on their Satchemon collection; a
          // Twitch/Google-first (did-less) account lands on the portal home.
          navigate(did ? `/satchemon/user/${did}` : '/', { replace: true });
        }
      })
      .catch((err) => setError(messageFor(err)));
  }, [params, completeOAuth, navigate]);

  return (
    <Center h="100vh">
      <Stack align="center" maw={420} px="md">
        {error ? (
          <>
            <Text c="red" ta="center">
              {error}
            </Text>
            <Button variant="light" onClick={() => navigate('/login', { replace: true })}>
              Back to sign in
            </Button>
          </>
        ) : (
          <>
            <Loader />
            <Text c="dimmed">Completing sign-in…</Text>
          </>
        )}
      </Stack>
    </Center>
  );
}
