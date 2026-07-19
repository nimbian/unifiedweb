// Leaderboard page — top-value cards *pulled* (by acquisition date) in three
// rolling windows (today / past 7 days / this month), plus the "Perfect 30":
// every card whose value is exactly 10000. Each window shows the single highest
// value, with ties listed together (computed server-side).

import {
  Alert,
  Anchor,
  Badge,
  Center,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { IconTrophy } from '@tabler/icons-react';
import { Link } from 'react-router-dom';
import { DataTable } from 'mantine-datatable';
import { useLeaderboard } from '@/hooks/useLeaderboard';
import { useCardViewer } from '@/components/CardViewer';
import { formatValue } from '@/utils/format';
import type { LeaderboardCard } from '@/types';

// Medal colours for the top-3 standings.
const RANK_COLORS = ['yellow', 'gray', 'orange'];

// A top-N user standing. The metric column is supplied by the caller so the same
// table renders both value-based (Decimal) and count-based standings.
function RankingSection<T extends { user: string | null; did: string }>({
  title,
  subtitle,
  rows,
  metricLabel,
  renderMetric,
  emptyText = 'No data yet.',
}: {
  title: string;
  subtitle?: string;
  rows: T[];
  metricLabel: string;
  renderMetric: (row: T) => React.ReactNode;
  emptyText?: string;
}) {
  return (
    <Paper withBorder radius="md" p="md">
      <Title order={3}>{title}</Title>
      {subtitle && (
        <Text size="sm" c="dimmed" mb="sm">
          {subtitle}
        </Text>
      )}
      {rows.length === 0 ? (
        <Text c="dimmed" mt="sm">
          {emptyText}
        </Text>
      ) : (
        <Table striped highlightOnHover mt="sm" withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={50}>#</Table.Th>
              <Table.Th>Owner</Table.Th>
              <Table.Th ta="right">{metricLabel}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r, i) => (
              <Table.Tr key={r.did}>
                <Table.Td>
                  <Badge color={RANK_COLORS[i] ?? 'blue'}>{i + 1}</Badge>
                </Table.Td>
                <Table.Td>
                  <Anchor component={Link} to={`/satchemon/user/${r.did}/progress`}>
                    {r.user ?? r.did}
                  </Anchor>
                </Table.Td>
                <Table.Td ta="right">{renderMetric(r)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Paper>
  );
}

function formatDate(date: string | null): string {
  if (!date) return '—';
  const d = new Date(date);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString();
}

function Section({
  title,
  subtitle,
  cards,
  showDate = true,
}: {
  title: string;
  subtitle?: string;
  cards: LeaderboardCard[];
  showDate?: boolean;
}) {
  const viewer = useCardViewer();
  return (
    <Paper withBorder radius="md" p="md">
      <Title order={3}>{title}</Title>
      {subtitle && (
        <Text size="sm" c="dimmed" mb="sm">
          {subtitle}
        </Text>
      )}
      {cards.length === 0 ? (
        <Text c="dimmed" mt="sm">
          No cards.
        </Text>
      ) : (
        <DataTable<LeaderboardCard>
          withTableBorder
          borderRadius="sm"
          striped
          mt="sm"
          idAccessor="collection_id"
          records={cards}
          columns={[
            {
              accessor: 'collection_id',
              title: 'Card ID',
              width: 90,
              render: ({ collection_id, name }) => (
                <Anchor onClick={() => viewer.open({ collectionId: collection_id, name })}>
                  {collection_id}
                </Anchor>
              ),
            },
            { accessor: 'user', title: 'Owner', render: ({ user }) => user ?? '—' },
            { accessor: 'cr', title: 'CR', width: 70 },
            { accessor: 'name', title: 'Card' },
            { accessor: 'exp', title: 'Expansion' },
            { accessor: 'grade', title: 'Grade', width: 80 },
            {
              accessor: 'holo',
              title: 'Holo',
              width: 80,
              render: ({ holo }) =>
                holo ? <Badge color="grape">Yes</Badge> : <Badge color="gray">No</Badge>,
            },
            {
              accessor: 'value',
              title: 'Value',
              textAlign: 'right',
              render: ({ value }) => formatValue(value),
            },
            ...(showDate
              ? [
                  {
                    accessor: 'date',
                    title: 'Pulled',
                    render: ({ date }: LeaderboardCard) => formatDate(date),
                  },
                ]
              : []),
          ]}
        />
      )}
    </Paper>
  );
}

export function LeaderboardPage() {
  const { data, isLoading, isError } = useLeaderboard();

  if (isLoading) {
    return (
      <Center h="40vh">
        <Loader />
      </Center>
    );
  }
  if (isError || !data) {
    return <Alert color="red">Failed to load the leaderboard.</Alert>;
  }

  return (
    <Stack gap="lg">
      <Title order={2} mb="xs">
        <IconTrophy size={26} style={{ verticalAlign: 'text-bottom', marginRight: 8 }} />
        Leaderboard
      </Title>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <RankingSection
          title="Top Collections"
          subtitle="Highest total collection value."
          rows={data.top_collections}
          metricLabel="Value"
          renderMetric={(r) => formatValue(r.value)}
          emptyText="No collections yet."
        />
        <RankingSection
          title="Best Copy Collection"
          subtitle="Highest value counting only one of each card (the most valuable copy)."
          rows={data.best_copy_collections}
          metricLabel="Value"
          renderMetric={(r) => formatValue(r.value)}
          emptyText="No collections yet."
        />
      </SimpleGrid>

      <Section title="Top pull — today" cards={data.today} />
      <Section title="Top pull — past 7 days" cards={data.past_7_days} />
      <Section title="Top pull — this month" cards={data.this_month} />

      <Section
        title="The Perfect 30"
        subtitle="Every card with a value of exactly 10000."
        cards={data.perfect_thirty}
      />

      <RankingSection
        title="Pristine Hunter"
        subtitle="Most pristine cards owned (grade 10 and holo)."
        rows={data.pristine_hunters}
        metricLabel="Pristine"
        renderMetric={(r) => r.count}
        emptyText="No pristine cards yet."
      />
    </Stack>
  );
}
