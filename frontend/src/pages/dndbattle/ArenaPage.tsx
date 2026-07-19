import { Alert, Badge, Center, Group, Loader, Stack, Table, Text, Title } from '@mantine/core';
import { IconSwords } from '@tabler/icons-react';
import { useArenaState } from '@/hooks/useArena';

const PHASE_LABELS: Record<string, string> = {
  idle: 'Arena closed',
  intermission: 'Intermission — queue is open',
  roster_lock: 'Lineup locked — betting open',
  combat: 'FIGHT!',
  results: 'Results',
  paused: 'Paused',
};

export function ArenaPage() {
  const { data, isLoading, error } = useArenaState();

  if (isLoading) {
    return (
      <Center h="60vh">
        <Loader color="grape" />
      </Center>
    );
  }
  if (error || !data) {
    return (
      <Alert color="red" title="Couldn't load the arena">
        {(error as Error)?.message ?? 'Please try again.'}
      </Alert>
    );
  }

  const { phase, round, fighters, queue, is_open } = data;
  const kind = (round?.kind as string) ?? 'race';

  return (
    <Stack gap="lg">
      <Group gap="sm">
        <Title order={2}>
          <IconSwords size={26} style={{ verticalAlign: 'text-bottom', marginRight: 8 }} />
          Live Arena
        </Title>
        <Badge color={is_open ? 'green' : 'gray'} variant={is_open ? 'filled' : 'light'}>
          {is_open ? 'OPEN' : 'CLOSED'}
        </Badge>
        <Badge color="grape" variant="light">
          {PHASE_LABELS[phase] ?? phase}
        </Badge>
        {round != null && kind === 'monster' && (
          <Badge color="orange" variant="light">
            monster battle
          </Badge>
        )}
      </Group>

      {fighters.length > 0 && (
        <Stack gap="xs">
          <Title order={3}>Current lineup</Title>
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Slot</Table.Th>
                <Table.Th>Fighter</Table.Th>
                <Table.Th>Class</Table.Th>
                <Table.Th>Owner</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {fighters.map((f) => (
                <Table.Tr key={f.slot}>
                  <Table.Td>{f.slot}</Table.Td>
                  <Table.Td>{f.name}</Table.Td>
                  <Table.Td>{f.class}</Table.Td>
                  <Table.Td c="dimmed">{f.is_npc ? 'NPC' : `@${f.owner ?? '?'}`}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Stack>
      )}

      <Stack gap="xs">
        <Title order={3}>Queue ({queue.length})</Title>
        {queue.length === 0 ? (
          <Text c="dimmed" size="sm">
            Nobody queued — type <code>!enter</code> in chat to join the next round.
          </Text>
        ) : (
          <Table striped withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={48}>#</Table.Th>
                <Table.Th>Character</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {queue.map((q, i) => (
                <Table.Tr key={q.character_id}>
                  <Table.Td>{i + 1}</Table.Td>
                  <Table.Td>{q.name}</Table.Td>
                  <Table.Td>
                    {q.priority && (
                      <Badge size="sm" color="yellow" variant="light">
                        priority
                      </Badge>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Stack>

      <Text c="dimmed" size="xs">
        Updates every few seconds. The full spectacle is on stream!
      </Text>
    </Stack>
  );
}
