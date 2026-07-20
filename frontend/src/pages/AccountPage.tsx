// Account page: manage connected sign-in providers. Any of Discord, YouTube
// (Google) and Twitch can be linked or disconnected, and any linked provider can
// be used to sign in. A row must keep at least one connected provider (the
// backend refuses removing the last one; the UI disables it too).

import { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Stack,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import { IconBrandDiscord, IconBrandTwitch, IconBrandYoutube } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { authApi } from '@/api/auth';
import { useAuth } from '@/hooks/useAuth';
import type { LinkedAccounts, Provider } from '@/types';

const ROWS: {
  provider: Provider;
  label: string;
  color: string;
  icon: typeof IconBrandDiscord;
}[] = [
  { provider: 'discord', label: 'Discord', color: 'indigo', icon: IconBrandDiscord },
  { provider: 'google', label: 'YouTube', color: 'red', icon: IconBrandYoutube },
  { provider: 'twitch', label: 'Twitch', color: 'grape', icon: IconBrandTwitch },
];

function messageFor(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
  }
  return fallback;
}

export function AccountPage() {
  const { linkAccount, unlinkAccount, redeemLinkCode } = useAuth();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<Provider | null>(null);
  const [code, setCode] = useState('');
  const [redeeming, setRedeeming] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['auth', 'links'],
    queryFn: authApi.links,
  });

  const connectedCount = data
    ? ROWS.filter(({ provider }) => data[provider].linked).length
    : 0;

  const disconnect = async (provider: Provider) => {
    setBusy(provider);
    try {
      const updated = await unlinkAccount(provider);
      queryClient.setQueryData<LinkedAccounts>(['auth', 'links'], updated);
      notifications.show({ message: `${provider} disconnected`, color: 'gray' });
    } catch (err) {
      notifications.show({
        message: messageFor(err, 'Could not disconnect. Try again.'),
        color: 'red',
      });
    } finally {
      setBusy(null);
    }
  };

  const redeem = async () => {
    const trimmed = code.trim();
    if (!trimmed) return;
    setRedeeming(true);
    try {
      const updated = await redeemLinkCode(trimmed);
      queryClient.setQueryData<LinkedAccounts>(['auth', 'links'], updated);
      setCode('');
      notifications.show({ message: 'Discord linked', color: 'green' });
    } catch (err) {
      notifications.show({
        message: messageFor(err, 'Could not redeem that code. Try again.'),
        color: 'red',
      });
    } finally {
      setRedeeming(false);
    }
  };

  return (
    <Stack gap="lg" maw={620}>
      <Title order={2}>Account</Title>
      <Text c="dimmed" size="sm">
        Connect Discord, YouTube and Twitch so you can sign in with any of them.
        Play the Discord bot? Connect Discord to link your Satchemon profile. You
        must keep at least one sign-in method connected.
      </Text>

      {isLoading ? (
        <Loader />
      ) : isError || !data ? (
        <Alert color="red">Failed to load your connected accounts.</Alert>
      ) : (
        <Stack gap="sm">
          {ROWS.map(({ provider, label, color, icon: Icon }) => {
            const link = data[provider];
            const isLastConnected = link.linked && connectedCount <= 1;
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

                  {link.linked ? (
                    <Tooltip
                      label="Keep at least one sign-in method connected"
                      disabled={!isLastConnected}
                    >
                      <Button
                        variant="light"
                        color="gray"
                        loading={busy === provider}
                        disabled={isLastConnected}
                        onClick={() => disconnect(provider)}
                      >
                        Disconnect
                      </Button>
                    </Tooltip>
                  ) : (
                    <Button color={color} onClick={() => linkAccount(provider)}>
                      Connect
                    </Button>
                  )}
                </Group>
              </Card>
            );
          })}

          {!data.discord.linked && (
            <Card withBorder radius="md" p="md">
              <Stack gap="xs">
                <Text fw={600}>Have a code from the bot?</Text>
                <Text size="xs" c="dimmed">
                  Run <Text span fw={600}>/link</Text> in the Discord server to get a
                  one-time code, then enter it here to connect Discord without signing
                  in again.
                </Text>
                <Group wrap="nowrap" align="flex-end" gap="sm">
                  <TextInput
                    aria-label="Discord link code"
                    placeholder="e.g. AB12CD34"
                    value={code}
                    onChange={(e) => setCode(e.currentTarget.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') redeem();
                    }}
                    disabled={redeeming}
                    style={{ flex: 1 }}
                  />
                  <Button
                    color="indigo"
                    onClick={redeem}
                    loading={redeeming}
                    disabled={!code.trim()}
                  >
                    Link
                  </Button>
                </Group>
              </Stack>
            </Card>
          )}
        </Stack>
      )}
    </Stack>
  );
}
