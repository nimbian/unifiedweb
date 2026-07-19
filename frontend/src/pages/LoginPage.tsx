import { Button, Card, Center, Stack, Text, Title } from '@mantine/core';
import { IconBrandDiscord, IconBrandTwitch, IconBrandYoutube } from '@tabler/icons-react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import type { Provider } from '@/types';

// The three sign-in options. "YouTube" authenticates through Google (YouTube has
// no OAuth of its own); every account is anchored on the user's Discord id.
const PROVIDERS: { provider: Provider; label: string; color: string; icon: typeof IconBrandDiscord }[] = [
  { provider: 'discord', label: 'Continue with Discord', color: 'indigo', icon: IconBrandDiscord },
  { provider: 'google', label: 'Continue with YouTube', color: 'red', icon: IconBrandYoutube },
  { provider: 'twitch', label: 'Continue with Twitch', color: 'grape', icon: IconBrandTwitch },
];

export function LoginPage() {
  const { isAuthenticated, isLoading, login } = useAuth();

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return (
    <Center h="100vh">
      <Card withBorder shadow="md" radius="lg" p="xl" w={380}>
        <Stack align="center" gap="lg">
          <Title order={2} c="red.5">
            SATCHEMON
          </Title>
          <Text c="dimmed" ta="center" size="sm">
            Sign in to view and manage your card collection. Use whichever account
            you've connected.
          </Text>
          <Stack gap="sm" w="100%">
            {PROVIDERS.map(({ provider, label, color, icon: Icon }) => (
              <Button
                key={provider}
                fullWidth
                size="md"
                color={color}
                leftSection={<Icon size={20} />}
                loading={isLoading}
                onClick={() => login(provider)}
              >
                {label}
              </Button>
            ))}
          </Stack>
          <Text c="dimmed" ta="center" size="xs">
            New here? Sign in with Discord first — you can connect YouTube and
            Twitch from the Account page afterward.
          </Text>
        </Stack>
      </Card>
    </Center>
  );
}
