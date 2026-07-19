import { useState } from 'react';
import { Alert, Center, Group, Loader, SegmentedControl, Stack, Table, Text, Title } from '@mantine/core';
import { IconTrophy } from '@tabler/icons-react';
import { useArenaLeaderboard } from '@/hooks/useArena';
import type { LeaderboardBy, LeaderboardScope } from '@/types/arena';

export function DndBattleLeaderboardPage() {
  const [by, setBy] = useState<LeaderboardBy>('damage');
  const [scope, setScope] = useState<LeaderboardScope>('season');
  const { data, isLoading, error } = useArenaLeaderboard(by, scope);

  return (
    <Stack gap="lg">
      <Title order={2}>
        <IconTrophy size={26} style={{ verticalAlign: 'text-bottom', marginRight: 8 }} />
        Leaderboard
      </Title>

      <Group>
        <SegmentedControl
          value={by}
          onChange={(v) => setBy(v as LeaderboardBy)}
          data={[
            { label: 'Damage', value: 'damage' },
            { label: 'Wins', value: 'wins' },
          ]}
        />
        <SegmentedControl
          value={scope}
          onChange={(v) => setScope(v as LeaderboardScope)}
          data={[
            { label: 'This season', value: 'season' },
            { label: 'All-time', value: 'alltime' },
          ]}
        />
      </Group>

      {isLoading && (
        <Center h="30vh">
          <Loader color="grape" />
        </Center>
      )}
      {error && (
        <Alert color="red" title="Couldn't load the leaderboard">
          {(error as Error).message}
        </Alert>
      )}
      {data &&
        (data.rows.length === 0 ? (
          <Text c="dimmed">Nothing recorded yet — go fight!</Text>
        ) : (
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={48}>#</Table.Th>
                <Table.Th>Character</Table.Th>
                <Table.Th ta="right">{by === 'damage' ? 'Damage' : 'Wins'}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.rows.map((row, i) => (
                <Table.Tr key={`${row.name}-${i}`}>
                  <Table.Td>{i + 1}</Table.Td>
                  <Table.Td>{row.name}</Table.Td>
                  <Table.Td ta="right">{row.value.toLocaleString()}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ))}
    </Stack>
  );
}
