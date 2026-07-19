// Shop: the gear catalog (public to browse) plus buying for one of your living
// characters. Buying needs a signed-in arena session (portal token with Twitch
// linked) and the streamer's gear economy switched on; both are surfaced inline
// so the catalog stays visible either way.

import { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { Link } from 'react-router-dom';
import { useArenaMe, useBuy, useRoster, useShop } from '@/hooks/useArena';
import { arenaErrorMessage, isArenaUnauthorized } from '@/api/arena';
import { useAuth } from '@/hooks/useAuth';
import { grantsText } from './gearText';

const SLOTS = ['weapon', 'armor', 'trinket'] as const;

export function ShopPage() {
  const { isAuthenticated } = useAuth();
  const shop = useShop();
  const me = useArenaMe();
  const roster = useRoster();

  const living = roster.data?.living ?? [];
  const [targetId, setTargetId] = useState<number | null>(null);
  const target = targetId ?? living[0]?.id ?? null;
  const buy = useBuy(target ?? 0);

  if (shop.isLoading) {
    return (
      <Center h="60vh">
        <Loader color="grape" />
      </Center>
    );
  }
  if (shop.error || !shop.data) {
    return (
      <Alert color="red" title="Couldn't load the shop">
        {arenaErrorMessage(shop.error, 'Please try again.')}
      </Alert>
    );
  }

  const { enabled, items } = shop.data;
  const signedIn = Boolean(me.data);
  const noArenaSession = me.error && isArenaUnauthorized(me.error);

  const owned = new Set(
    living.find((c) => c.id === target)?.inventory?.map((i) => i.item_id) ?? [],
  );

  const targetOptions = living.map((c) => ({
    value: String(c.id),
    label: `${c.name} (Lv${c.level} ${c.class_name})`,
  }));

  return (
    <Stack gap="lg">
      <Title order={2}>Shop</Title>

      {!enabled && (
        <Alert color="yellow" title="The shop isn't open yet">
          Browse the catalog below — buying unlocks when the streamer enables the gear economy.
        </Alert>
      )}

      {noArenaSession && (
        <Alert color="grape" variant="light">
          {isAuthenticated ? (
            <>
              <Link to="/account">Link Twitch</Link> to your MooreDnD account to buy gear for your
              characters.
            </>
          ) : (
            <>
              <Link to="/login">Sign in</Link> (and link Twitch) to buy gear for your characters.
            </>
          )}
        </Alert>
      )}

      {signedIn && living.length > 0 && (
        <Group gap="sm" align="center">
          <Text c="dimmed" size="sm">
            Buying for:
          </Text>
          <Select
            value={String(target)}
            onChange={(v) => setTargetId(v ? Number(v) : null)}
            data={targetOptions}
            allowDeselect={false}
            w={260}
          />
          <Badge color="yellow" variant="light" size="lg">
            {me.data!.gold.toLocaleString()}g
          </Badge>
        </Group>
      )}

      {buy.error && <Alert color="red">{arenaErrorMessage(buy.error, 'Purchase failed.')}</Alert>}

      {SLOTS.map((slot) => {
        const slotItems = items.filter((i) => i.slot === slot);
        if (slotItems.length === 0) return null;
        return (
          <div key={slot}>
            <Title order={3} tt="capitalize" mb="xs">
              {slot}s
            </Title>
            <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="md">
              {slotItems.map((item) => (
                <Card key={item.item_id} withBorder radius="md" padding="md">
                  <Text fw={600}>{item.name}</Text>
                  <Text c="dimmed" size="xs">
                    {grantsText(item.grants)}
                  </Text>
                  <Group justify="space-between" mt="sm" align="center">
                    <Badge color="yellow" variant="light">
                      {item.price.toLocaleString()}g
                    </Badge>
                    {enabled &&
                      signedIn &&
                      target !== null &&
                      (owned.has(item.item_id) ? (
                        <Badge color="gray" variant="light">
                          owned
                        </Badge>
                      ) : (
                        <Button
                          size="compact-sm"
                          loading={buy.isPending && buy.variables === item.item_id}
                          disabled={buy.isPending}
                          onClick={() => buy.mutate(item.item_id)}
                        >
                          Buy
                        </Button>
                      ))}
                  </Group>
                </Card>
              ))}
            </SimpleGrid>
          </div>
        );
      })}
    </Stack>
  );
}
