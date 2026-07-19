// Gate shown when an authed arena route returns 401 (no arena session).
//
// A portal account only maps to an arena character once Twitch is linked (the
// portal JWT then carries a twitch_uid claim the arena resolves onto its
// (platform, platform_user_id) user — PLAN §8). So a 401 has two causes, and we
// use the portal auth state to tell them apart:
//   • not signed in to the portal  → send them to sign in
//   • signed in, no Twitch linked   → send them to /account to link Twitch

import { Button, Card, Center, Stack, Text, Title } from '@mantine/core';
import { IconBrandTwitch } from '@tabler/icons-react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';

export function PlayGate({ what }: { what: string }) {
  const { isAuthenticated } = useAuth();

  return (
    <Center h="60vh">
      <Card withBorder radius="lg" padding="xl" maw={440}>
        <Stack gap="md" align="center" ta="center">
          <IconBrandTwitch size={44} color="var(--mantine-color-grape-5)" />
          {isAuthenticated ? (
            <>
              <Title order={3}>Link Twitch to play</Title>
              <Text c="dimmed" size="sm">
                Your arena characters are tied to your Twitch account. Connect
                Twitch to your MooreDnD account and {what} will show up here.
              </Text>
              <Button
                component={Link}
                to="/account"
                color="grape"
                leftSection={<IconBrandTwitch size={16} />}
              >
                Connect Twitch
              </Button>
            </>
          ) : (
            <>
              <Title order={3}>Sign in to play</Title>
              <Text c="dimmed" size="sm">
                Sign in to your MooreDnD account (then link Twitch) to see {what}.
              </Text>
              <Button component={Link} to="/login" color="grape">
                Sign in
              </Button>
            </>
          )}
        </Stack>
      </Card>
    </Center>
  );
}
