// DnD leaderboards, split across the three character game modes (normal /
// hardcore / speedrun). Each mode is its own tab; Normal is the default. Within
// a tab the boards rank that mode's characters by level, gold, deepest Abyss
// floor, and duel wins — the Speedrun tab leads with fastest run to level 20.

import { Alert, Anchor, Badge, Center, Loader, Paper, SimpleGrid, Table, Tabs, Text, Title } from '@mantine/core';
import { Link } from 'react-router-dom';
import { useDndLeaderboard } from '@/hooks/useDnd';
import { DndNav } from './DndNav';
import type { LeaderEntry, ModeLeaderboard } from '@/types/dnd';

const RANK_COLORS = ['yellow', 'gray', 'orange'];

// Seconds → compact "Dd Hh Mm" duration (the two largest non-zero units).
function formatDuration(secs: number): string {
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  const parts = ([
    [d, 'd'],
    [h, 'h'],
    [m, 'm'],
    [s, 's'],
  ] as [number, string][]).filter(([v]) => v > 0);
  if (parts.length === 0) return '0s';
  return parts.slice(0, 2).map(([v, u]) => `${v}${u}`).join(' ');
}

function Board({ title, rows, fmt }: { title: string; rows: LeaderEntry[]; fmt?: (n: number) => string }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Title order={4} mb="sm">{title}</Title>
      {rows.length === 0 ? (
        <Text c="dimmed">No data yet.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={40}>#</Table.Th>
              <Table.Th>Adventurer</Table.Th>
              <Table.Th ta="right">Value</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r, i) => (
              <Table.Tr key={r.key}>
                <Table.Td>
                  <Badge color={RANK_COLORS[i] ?? 'blue'}>{i + 1}</Badge>
                </Table.Td>
                <Table.Td>
                  <Anchor component={Link} to={`/satchemon/progress/character/${r.key}`}>
                    {r.name}
                  </Anchor>
                  <Text component="span" c="dimmed" size="xs" ml={6}>
                    {r.class_name}
                  </Text>
                </Table.Td>
                <Table.Td ta="right">{fmt ? fmt(r.value) : r.value}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Paper>
  );
}

// The grid of boards for one mode. The Speedrun tab leads with the run-time
// board (its defining metric); the others lead with level.
function ModeBoards({ board, speedrun = false }: { board: ModeLeaderboard; speedrun?: boolean }) {
  return (
    <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
      {speedrun ? (
        <Board title="Fastest to Lvl 20" rows={board.by_speedrun} fmt={formatDuration} />
      ) : (
        <Board title="Highest Level" rows={board.by_level} />
      )}
      <Board title="Richest" rows={board.by_gold} fmt={(n) => `${n.toLocaleString()} g`} />
      <Board title="Deepest Abyss" rows={board.by_abyss} fmt={(n) => `Floor ${n}`} />
      <Board title="Most Duel Wins" rows={board.by_duels} />
    </SimpleGrid>
  );
}

export function DndLeaderboardPage() {
  const { data, isLoading, isError } = useDndLeaderboard();

  return (
    <>
      <DndNav />
      {isLoading ? (
        <Center h="40vh"><Loader /></Center>
      ) : isError || !data ? (
        <Alert color="red">Failed to load the leaderboard.</Alert>
      ) : (
        <Tabs defaultValue="normal" keepMounted={false}>
          <Tabs.List mb="lg">
            <Tabs.Tab value="normal">Normal</Tabs.Tab>
            <Tabs.Tab value="hardcore">Hardcore</Tabs.Tab>
            <Tabs.Tab value="speedrun">Speedrun</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="normal">
            <ModeBoards board={data.normal} />
          </Tabs.Panel>
          <Tabs.Panel value="hardcore">
            <ModeBoards board={data.hardcore} />
          </Tabs.Panel>
          <Tabs.Panel value="speedrun">
            <ModeBoards board={data.speedrun} speedrun />
          </Tabs.Panel>
        </Tabs>
      )}
    </>
  );
}
