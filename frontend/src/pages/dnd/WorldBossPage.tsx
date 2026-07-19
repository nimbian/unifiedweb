// World Boss: the live shared boss (HP, AC, top damage dealers) and recently
// defeated bosses.

import {
  Alert,
  Anchor,
  Badge,
  Card,
  Center,
  Group,
  Loader,
  Paper,
  Progress,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { IconSkull } from '@tabler/icons-react';
import { Link } from 'react-router-dom';
import { useWorldBoss } from '@/hooks/useDnd';
import { DndNav } from './DndNav';

function formatDate(d: string | null): string {
  if (!d) return '—';
  const dt = new Date(d);
  return Number.isNaN(dt.getTime()) ? '—' : dt.toLocaleString();
}

export function WorldBossPage() {
  const { data, isLoading, isError } = useWorldBoss();

  if (isLoading) return <><DndNav /><Center h="40vh"><Loader /></Center></>;
  if (isError || !data) return <><DndNav /><Alert color="red">Failed to load the world boss.</Alert></>;

  const boss = data.active;
  const hpPct = boss && boss.max_hp > 0 ? (boss.hp / boss.max_hp) * 100 : 0;

  return (
    <>
      <DndNav />
      <Stack gap="lg">
        {boss ? (
          <Card withBorder radius="md" padding="lg">
            <Group justify="space-between" mb="xs">
              <Title order={3}>
                <IconSkull size={24} style={{ verticalAlign: 'text-bottom', marginRight: 8 }} />
                {boss.name}
              </Title>
              <Group gap="xs">
                <Badge color="grape" variant="light">AC {boss.ac}</Badge>
                <Text size="sm" c="dimmed">spawned {formatDate(boss.spawned_at)}</Text>
              </Group>
            </Group>
            <Group justify="space-between" mb={4}>
              <Text size="sm" c="dimmed" fw={600}>HP</Text>
              <Text size="sm" fw={600}>
                {boss.hp.toLocaleString()} / {boss.max_hp.toLocaleString()}
              </Text>
            </Group>
            <Progress value={hpPct} color="red" size="xl" radius="xl" />

            <Title order={5} mt="lg" mb="sm">Top Damage</Title>
            {boss.contributors.length === 0 ? (
              <Text c="dimmed">No one has struck the boss yet.</Text>
            ) : (
              <Table striped>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={40}>#</Table.Th>
                    <Table.Th>Adventurer</Table.Th>
                    <Table.Th ta="right">Damage</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {boss.contributors.map((ct, i) => (
                    <Table.Tr key={ct.key}>
                      <Table.Td>{i + 1}</Table.Td>
                      <Table.Td>
                        <Anchor component={Link} to={`/satchemon/progress/character/${ct.key}`}>
                          {ct.name}
                        </Anchor>
                      </Table.Td>
                      <Table.Td ta="right">{ct.damage.toLocaleString()}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Card>
        ) : (
          <Paper withBorder radius="md" p="xl" ta="center">
            <IconSkull size={36} opacity={0.5} />
            <Title order={4} mt="sm">No boss is stalking the realm right now.</Title>
            <Text c="dimmed">Check back when one spawns.</Text>
          </Paper>
        )}

        <div>
          <Title order={4} mb="sm">Recently Defeated</Title>
          {data.recent.length === 0 ? (
            <Text c="dimmed">No bosses defeated yet.</Text>
          ) : (
            <Table striped withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Boss</Table.Th>
                  <Table.Th ta="right">Max HP</Table.Th>
                  <Table.Th>Defeated</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.recent.map((b, i) => (
                  <Table.Tr key={`${b.name}-${i}`}>
                    <Table.Td>{b.name}</Table.Td>
                    <Table.Td ta="right">{b.max_hp.toLocaleString()}</Table.Td>
                    <Table.Td>{formatDate(b.defeated_at)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </div>
      </Stack>
    </>
  );
}
