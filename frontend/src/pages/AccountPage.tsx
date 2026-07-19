// Account page: manage connected sign-in providers. Discord is the primary
// account and is always connected; YouTube (Google) and Twitch can be linked or
// disconnected here. Once linked, a provider can be used to sign in.

import { useState } from 'react';
import { Alert, Badge, Button, Card, Group, Loader, Stack, Text, Title } from '@mantine/core';
import { IconBrandDiscord, IconBrandTwitch, IconBrandYoutube } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi } from '@/api/auth';
import { useAuth } from '@/hooks/useAuth';
import type { LinkedAccounts, Provider } from '@/types';

const ROWS: {
  provider: Provider;
  label: string;
  color: string;
  icon: typeof IconBrandDiscord;
  primary?: boolean;
}[] = [
  { provider: 'discord', label: 'Discord', color: 'indigo', icon: IconBrandDiscord, primary: true },
  { provider: 'google', label: 'YouTube', color: 'red', icon: IconBrandYoutube },
  { provider: 'twitch', label: 'Twitch', color: 'grape', icon: IconBrandTwitch },
];

export function AccountPage() {
  const { linkAccount, unlinkAccount } = useAuth();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<Provider | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['auth', 'links'],
    queryFn: authApi.links,
  });

  const disconnect = async (provider: Provider) => {
    setBusy(provider);
    try {
      const updated = await unlinkAccount(provider);
      queryClient.setQueryData<LinkedAccounts>(['auth', 'links'], updated);
      notifications.show({ message: `${provider} disconnected`, color: 'gray' });
    } catch {
      notifications.show({ message: 'Could not disconnect. Try again.', color: 'red' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Stack gap="lg" maw={620}>
      <Title order={2}>Account</Title>
      <Text c="dimmed" size="sm">
        Connect YouTube and Twitch to your account so you can sign in with any of
        them. Your Discord account is the primary login and can't be disconnected.
      </Text>

      {isLoading ? (
        <Loader />
      ) : isError || !data ? (
        <Alert color="red">Failed to load your connected accounts.</Alert>
      ) : (
        <Stack gap="sm">
          {ROWS.map(({ provider, label, color, icon: Icon, primary }) => {
            const link = data[provider];
            return (
              <Card key={provider} withBorder radius="md" p="md">
                <Group justify="space-between" wrap="nowrap">
                  <Group wrap="nowrap" gap="sm">
                    <Icon size={26} color={`var(--mantine-color-${color}-6)`} />
                    <div>
                      <Group gap="xs">
                        <Text fw={600}>{label}</Text>
                        {link.linked ? (
                          <Badge color="green" variant="light">
                            Connected
                          </Badge>
                        ) : (
                          <Badge color="gray" variant="light">
                            Not connected
                          </Badge>
                        )}
                      </Group>
                      {link.handle && (
                        <Text size="xs" c="dimmed">
                          {link.handle}
                        </Text>
                      )}
                    </div>
                  </Group>

                  {primary ? (
                    <Badge color="indigo" variant="outline">
                      Primary
                    </Badge>
                  ) : link.linked ? (
                    <Button
                      variant="light"
                      color="gray"
                      loading={busy === provider}
                      onClick={() => disconnect(provider)}
                    >
                      Disconnect
                    </Button>
                  ) : (
                    <Button color={color} onClick={() => linkAccount(provider)}>
                      Connect
                    </Button>
                  )}
                </Group>
              </Card>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}
