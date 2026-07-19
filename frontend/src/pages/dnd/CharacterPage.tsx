// A single character's sheet: vitals, ability scores, equipment, inventory,
// bestiary (masked until discovered), and earned achievements.

import {
  Alert,
  Anchor,
  Badge,
  Card,
  Center,
  Group,
  Loader,
  Progress,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { Link, useParams } from 'react-router-dom';
import { useDndCharacter } from '@/hooks/useDnd';
import { DndNav, rarityColor } from './DndNav';
import type { CharacterDetail } from '@/types/dnd';

const ABILITY_LABEL: Record<string, string> = {
  str: 'STR', dex: 'DEX', con: 'CON', int: 'INT', wis: 'WIS', cha: 'CHA',
};

// D&D challenge ratings below 1 are written as fractions, not decimals.
const CR_FRACTIONS: Record<number, string> = { 0.125: '1/8', 0.25: '1/4', 0.5: '1/2' };

function formatCr(cr: number): string {
  return CR_FRACTIONS[cr] ?? String(cr);
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card withBorder padding="sm" radius="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="lg" fw={700}>
        {value}
      </Text>
    </Card>
  );
}

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <Card withBorder padding="sm" radius="md">
      <Group justify="space-between" mb={4}>
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
          {label}
        </Text>
        <Text size="sm" fw={600}>
          {value} / {max}
        </Text>
      </Group>
      <Progress value={pct} color={color} size="md" radius="xl" />
    </Card>
  );
}

function CharacterSheet({ c }: { c: CharacterDetail }) {
  const affixes = Object.entries(c.affix_bonuses ?? {}).filter(([, v]) => v);

  return (
    <Stack gap="lg">
      {/* Header */}
      <Card withBorder radius="md" padding="lg">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={2}>
              {c.char_name ?? c.username}
              {c.title && (
                <Text component="span" c="grape" fw={500} ml="xs" size="lg">
                  {c.title}
                </Text>
              )}
            </Title>
            <Text c="dimmed">
              Level {c.level} {c.class_name}
              {c.subclass_name ? ` · ${c.subclass_name}` : ''} · played by {c.username}
            </Text>
          </div>
          {c.active && <Badge color="green" variant="light">Active</Badge>}
        </Group>
      </Card>

      {/* Vitals */}
      <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} spacing="md">
        <Bar label="HP" value={c.hp} max={c.max_hp} color="red" />
        <Bar label="Resource" value={c.resource} max={c.max_resource} color="blue" />
        <Stat label="Armor Class" value={c.armor_class} />
        <Stat label="Gold" value={c.gold.toLocaleString()} />
        <Stat label="Proficiency" value={`+${c.proficiency}`} />
        <Stat label="XP" value={c.xp.toLocaleString()} />
        <Stat label="Zone" value={c.current_zone ?? '—'} />
        <Stat label="Bag" value={`${c.bag_used} / ${c.bag_capacity}`} />
        <Stat label="Abyss Best" value={c.abyss_best_floor > 0 ? `Floor ${c.abyss_best_floor}` : '—'} />
        <Stat label="Duels (W/L)" value={`${c.duel_wins} / ${c.duel_losses}`} />
        <Stat label="Daily Streak" value={c.daily_streak} />
      </SimpleGrid>

      {/* Ability scores */}
      <div>
        <Title order={4} mb="sm">Ability Scores</Title>
        <SimpleGrid cols={{ base: 3, sm: 6 }} spacing="sm">
          {c.abilities.map((a) => (
            <Card key={a.key} withBorder padding="sm" radius="md" ta="center">
              <Text size="xs" c="dimmed" fw={700}>{ABILITY_LABEL[a.key] ?? a.key}</Text>
              <Text size="xl" fw={700}>{a.score}</Text>
              <Text size="sm" c="dimmed">{a.modifier >= 0 ? `+${a.modifier}` : a.modifier}</Text>
            </Card>
          ))}
        </SimpleGrid>
      </div>

      {/* Equipment */}
      <div>
        <Title order={4} mb="sm">Equipment</Title>
        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
          {c.equipment.map((e) => (
            <Card key={e.slot} withBorder padding="sm" radius="md">
              <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{e.slot}</Text>
              {e.name ? (
                <>
                  <Group gap={6} mt={2}>
                    <Text fw={600}>{e.name}</Text>
                    {e.rarity && (
                      <Badge size="xs" color={rarityColor(e.rarity)} variant="light">
                        {e.rarity}
                      </Badge>
                    )}
                    {e.affixed && <Badge size="xs" color="yellow" variant="light">affixed</Badge>}
                  </Group>
                  {e.detail && <Text size="xs" c="dimmed" mt={4}>{e.detail}</Text>}
                </>
              ) : (
                <Text c="dimmed" mt={2}>— empty —</Text>
              )}
            </Card>
          ))}
        </SimpleGrid>
        {affixes.length > 0 && (
          <Group gap="xs" mt="sm">
            <Text size="sm" c="dimmed">Equipped bonuses:</Text>
            {affixes.map(([k, v]) => (
              <Badge key={k} variant="light" color="yellow">
                {k} +{v}
              </Badge>
            ))}
          </Group>
        )}
      </div>

      {/* Inventory + Achievements side by side on wide screens */}
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <div>
          <Title order={4} mb="sm">Inventory ({c.bag_used}/{c.bag_capacity})</Title>
          {c.inventory.length === 0 ? (
            <Text c="dimmed">Empty bag.</Text>
          ) : (
            <Table striped withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Item</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th ta="right">Qty</Table.Th>
                  <Table.Th ta="right">Value</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {c.inventory.map((it) => (
                  <Table.Tr key={it.item_id}>
                    <Table.Td>
                      <Group gap={6}>
                        {it.name}
                        {it.rarity && it.rarity !== 'common' && (
                          <Badge size="xs" color={rarityColor(it.rarity)} variant="light">
                            {it.rarity}
                          </Badge>
                        )}
                      </Group>
                    </Table.Td>
                    <Table.Td>{it.type ?? '—'}</Table.Td>
                    <Table.Td ta="right">{it.quantity}</Table.Td>
                    <Table.Td ta="right">{it.value}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </div>

        <div>
          <Title order={4} mb="sm">Achievements ({c.achievements.length})</Title>
          {c.achievements.length === 0 ? (
            <Text c="dimmed">No achievements yet.</Text>
          ) : (
            <Stack gap="xs">
              {c.achievements.map((a) => (
                <Group key={a.id} gap="sm" wrap="nowrap">
                  <Text size="xl">{a.emoji ?? '🏆'}</Text>
                  <div>
                    <Text fw={600}>{a.name}</Text>
                    {a.description && <Text size="xs" c="dimmed">{a.description}</Text>}
                  </div>
                </Group>
              ))}
            </Stack>
          )}
        </div>
      </SimpleGrid>

      {/* Bestiary */}
      <div>
        <Title order={4} mb="sm">
          Bestiary ({c.bestiary.filter((b) => b.discovered).length}/{c.bestiary.length} discovered)
        </Title>
        <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} spacing="xs">
          {c.bestiary.map((b) => (
            <Card
              key={b.monster_id}
              withBorder
              padding="xs"
              radius="md"
              style={{ opacity: b.discovered ? 1 : 0.55 }}
            >
              <Group justify="space-between" wrap="nowrap">
                <Text fw={600} lineClamp={1}>{b.name}</Text>
                {b.discovered && <Badge size="xs" variant="light">×{b.kills}</Badge>}
              </Group>
              <Text size="xs" c="dimmed">
                {b.discovered ? `${b.family ?? ''}${b.cr != null ? ` · CR ${formatCr(b.cr)}` : ''}` : 'undiscovered'}
              </Text>
            </Card>
          ))}
        </SimpleGrid>
      </div>
    </Stack>
  );
}

export function CharacterPage() {
  const { key = '' } = useParams();
  const { data, isLoading, isError } = useDndCharacter(key);

  return (
    <>
      <DndNav />
      <Anchor component={Link} to="/satchemon/progress" size="sm">
        ← All adventurers
      </Anchor>
      {isLoading ? (
        <Center h="40vh">
          <Loader />
        </Center>
      ) : isError || !data ? (
        <Alert color="red" mt="md">Character not found.</Alert>
      ) : (
        <div style={{ marginTop: 12 }}>
          <CharacterSheet c={data} />
        </div>
      )}
    </>
  );
}
