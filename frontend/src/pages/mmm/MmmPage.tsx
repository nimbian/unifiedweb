// MMM donor home: the badge-tier gallery (click a badge to enlarge) over a
// searchable supporter leaderboard. Ports the original static index.html — the
// points/ranks are computed server-side (/api/mmm) instead of in the browser.

import { useMemo, useState } from 'react';
import {
  Alert,
  Anchor,
  Badge,
  Card,
  Center,
  Group,
  Image,
  Loader,
  Modal,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { Link } from 'react-router-dom';
import { useMmmBadges, useMmmDonors } from '@/hooks/useMmm';
import type { MmmBadgeTier } from '@/types';
import { badgeIcon, formatPoints, ordinal, tierColor } from './mmmShared';

const RANK_COLORS = ['yellow', 'gray', 'orange']; // gold/silver/bronze for the top 3

function BadgeGallery({ tiers }: { tiers: MmmBadgeTier[] }) {
  const [active, setActive] = useState<MmmBadgeTier | null>(null);
  return (
    <>
      <SimpleGrid cols={{ base: 2, xs: 3, sm: 4, md: 7 }} spacing="md">
        {tiers.map((tier) => (
          <Card
            key={tier.key}
            withBorder
            radius="md"
            p="sm"
            role="button"
            tabIndex={0}
            onClick={() => setActive(tier)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setActive(tier);
              }
            }}
            style={{ cursor: 'pointer', textAlign: 'center' }}
          >
            <Stack gap={6} align="center">
              <Image src={badgeIcon(tier.key)} alt={tier.title} w="70%" maw={120} loading="lazy" />
              <Text fw={600} size="xs" lh={1.2}>
                {tier.title}
              </Text>
              <Badge color={tierColor(tier.key)} variant="light" size="xs">
                {formatPoints(tier.points)} pts
              </Badge>
            </Stack>
          </Card>
        ))}
      </SimpleGrid>

      <Modal
        opened={active !== null}
        onClose={() => setActive(null)}
        title={active?.title}
        centered
        size="md"
      >
        {active && (
          <Stack align="center" gap="sm">
            <Image src={badgeIcon(active.key)} alt={active.title} maw={340} />
            <Badge color={tierColor(active.key)} size="lg" variant="light">
              Worth {formatPoints(active.points)} points each
            </Badge>
          </Stack>
        )}
      </Modal>
    </>
  );
}

function Leaderboard() {
  const { data: donors, isLoading, isError } = useMmmDonors();
  const [query, setQuery] = useState('');

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return (donors ?? []).filter((d) => d.name.toLowerCase().includes(term));
  }, [donors, query]);

  if (isLoading) {
    return (
      <Center h={120}>
        <Loader />
      </Center>
    );
  }
  if (isError || !donors) {
    return <Alert color="red">The supporter list could not be loaded.</Alert>;
  }
  if (donors.length === 0) {
    return (
      <Text c="dimmed" ta="center" py="lg">
        No supporters have been recognized yet.
      </Text>
    );
  }

  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="wrap">
        <Text c="dimmed" size="sm">
          {donors.length.toLocaleString()} recognized supporter{donors.length === 1 ? '' : 's'}
        </Text>
        <TextInput
          leftSection={<IconSearch size={16} />}
          placeholder="Search supporters"
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          w={{ base: '100%', xs: 260 }}
        />
      </Group>

      <Table.ScrollContainer minWidth={420}>
        <Table striped highlightOnHover withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={70}>Rank</Table.Th>
              <Table.Th>Supporter</Table.Th>
              <Table.Th ta="right">Points</Table.Th>
              <Table.Th ta="right" w={90}>
                Badges
              </Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {visible.map((d) => (
              <Table.Tr key={d.name}>
                <Table.Td>
                  <Badge color={RANK_COLORS[d.rank - 1] ?? 'blue'} variant="light">
                    {ordinal(d.rank)}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Anchor component={Link} to={`/mmm/donor/${encodeURIComponent(d.name)}`}>
                    {d.name}
                  </Anchor>
                </Table.Td>
                <Table.Td ta="right">{formatPoints(d.points)} pts</Table.Td>
                <Table.Td ta="right">{d.total_badges.toLocaleString()}</Table.Td>
              </Table.Tr>
            ))}
            {visible.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={4}>
                  <Text c="dimmed" ta="center" py="sm">
                    No supporters match “{query}”.
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  );
}

export function MmmPage() {
  const { data: tiers, isLoading, isError } = useMmmBadges();

  return (
    <Stack gap="xl">
      <Stack gap={4}>
        <Title order={1}>Midweek Monster Mash — Supporters</Title>
        <Text c="dimmed">
          Every badge is earned by supporting the stream. Climb the tiers to rack up points and
          claim your place on the wall.
        </Text>
      </Stack>

      <Stack gap="sm">
        <Title order={3}>Badge tiers</Title>
        {isLoading ? (
          <Center h={120}>
            <Loader />
          </Center>
        ) : isError || !tiers ? (
          <Alert color="red">The badge catalog could not be loaded.</Alert>
        ) : (
          <BadgeGallery tiers={tiers} />
        )}
      </Stack>

      <Stack gap="sm">
        <Title order={3}>Leaderboard</Title>
        <Leaderboard />
      </Stack>
    </Stack>
  );
}
