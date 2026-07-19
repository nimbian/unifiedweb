// Character sheet: stats, battle record, gear. Owner-only controls (rename,
// retire, equip/unequip, buy link) appear when the arena reports is_owner for
// the resolved session. The read itself is public — anyone can view a sheet.

import { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Modal,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useCharacter, useEquip, useRename, useRetire, useUnequip } from '@/hooks/useArena';
import { arenaErrorMessage } from '@/api/arena';
import type { ArenaCharacter, ArenaEquippedItem } from '@/types/arena';
import { equippedGrantsText, itemDisplayName } from './gearText';

const STAT_ORDER = ['STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA'];
const GEAR_SLOTS = ['weapon', 'armor', 'trinket'] as const;

function StatBlock({ stats }: { stats: Record<string, number> }) {
  return (
    <SimpleGrid cols={{ base: 3, sm: 6 }} spacing="xs">
      {STAT_ORDER.map((k) => (
        <Card key={k} withBorder radius="md" padding="xs" ta="center">
          <Text c="dimmed" size="xs" fw={700}>
            {k}
          </Text>
          <Text fw={700} size="lg">
            {stats[k] ?? '-'}
          </Text>
        </Card>
      ))}
    </SimpleGrid>
  );
}

function GearSlot({
  slot,
  item,
  canUnequip,
  onUnequip,
  busy,
}: {
  slot: string;
  item: ArenaEquippedItem | undefined;
  canUnequip: boolean;
  onUnequip: () => void;
  busy: boolean;
}) {
  return (
    <Card withBorder radius="md" padding="md">
      <Text c="dimmed" size="xs" tt="uppercase" fw={700}>
        {slot}
      </Text>
      {item ? (
        <Stack gap={4} mt={4}>
          <Text fw={600}>{itemDisplayName(item)}</Text>
          <Text c="dimmed" size="xs">
            {equippedGrantsText(item)}
          </Text>
          {canUnequip && (
            <Button variant="light" color="gray" size="compact-sm" onClick={onUnequip} disabled={busy}>
              Unequip
            </Button>
          )}
        </Stack>
      ) : (
        <Text c="dimmed" mt={4}>
          empty
        </Text>
      )}
    </Card>
  );
}

export function CharacterSheetPage() {
  const { id } = useParams();
  const charId = Number(id);
  const navigate = useNavigate();

  const character = useCharacter(charId);
  const rename = useRename(charId);
  const retire = useRetire(charId);
  const equip = useEquip(charId);
  const unequip = useUnequip(charId);

  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState('');
  const [confirmRetire, setConfirmRetire] = useState(false);

  if (character.isLoading) {
    return (
      <Center h="60vh">
        <Loader color="grape" />
      </Center>
    );
  }
  if (character.error || !character.data) {
    return (
      <Alert color="red" title="Couldn't load this character">
        {arenaErrorMessage(character.error, 'No such character.')}
      </Alert>
    );
  }

  const ch: ArenaCharacter = character.data;
  const owner = ch.is_owner === true;
  const canManage = owner && !ch.is_retired;
  const busy = rename.isPending || retire.isPending || equip.isPending || unequip.isPending;
  const mutationError =
    rename.error ?? retire.error ?? equip.error ?? unequip.error;
  const bag = (ch.inventory ?? []).filter((i) => !i.equipped);

  return (
    <Stack gap="lg">
      <div>
        <Group gap="sm" align="center" wrap="wrap">
          <Title order={2}>{ch.name}</Title>
          <Badge variant="light" color="grape" size="lg">
            Lv{ch.level}
          </Badge>
          {ch.is_retired && (
            <Badge variant="light" color="gray" size="lg">
              retired
            </Badge>
          )}
          {canManage && (
            <Button
              variant="subtle"
              size="compact-sm"
              onClick={() => {
                setNewName(ch.name);
                setRenaming((r) => !r);
              }}
            >
              Rename
            </Button>
          )}
          {canManage && (
            <Button
              variant="subtle"
              color="red"
              size="compact-sm"
              onClick={() => setConfirmRetire(true)}
            >
              Retire
            </Button>
          )}
        </Group>
        <Text c="dimmed" size="sm">
          {ch.personality && `${ch.personality} `}
          {ch.race} {ch.class_name}
          {ch.owner_login && ` · @${ch.owner_login}`}
          {ch.lineage.trained_by && (
            <>
              {` · gen ${ch.lineage.generation}, trained by `}
              {ch.lineage.trained_by.map((p, i) => (
                <span key={p.id}>
                  {i > 0 && ' & '}
                  <Link to={`/dndbattle/character/${p.id}`}>{p.name}</Link>
                </span>
              ))}
            </>
          )}
        </Text>
      </div>

      {renaming && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            rename.mutate(newName, { onSuccess: () => setRenaming(false) });
          }}
        >
          <Group gap="xs">
            <TextInput
              value={newName}
              onChange={(e) => setNewName(e.currentTarget.value)}
              maxLength={20}
              data-autofocus
              style={{ flex: 1, maxWidth: 260 }}
            />
            <Button type="submit" loading={rename.isPending} disabled={busy && !rename.isPending}>
              Save
            </Button>
          </Group>
        </form>
      )}

      {mutationError && <Alert color="red">{arenaErrorMessage(mutationError, 'That didn’t work.')}</Alert>}

      <StatBlock stats={ch.stats} />

      <Card withBorder radius="md" padding="md">
        <Group gap="xs" wrap="wrap">
          <Text>
            <Text component="span" fw={700}>
              {ch.wins}
            </Text>
            W /{' '}
            <Text component="span" fw={700}>
              {ch.losses}
            </Text>
            L
          </Text>
          <Badge variant="light" color="gray">
            {ch.battles_fought} battles fought
          </Badge>
          {!ch.is_retired && (
            <Badge variant="light" color="gray">
              {ch.battles_left} left
            </Badge>
          )}
          <Badge variant="light" color="gray">
            {ch.lifetime_damage.toLocaleString()} lifetime dmg
          </Badge>
          <Badge variant="light" color="gray">
            {ch.highest_hit.toLocaleString()} biggest hit
          </Badge>
          <Badge variant="light" color="gray">
            {ch.lifetime_crits.toLocaleString()} crits
          </Badge>
        </Group>
      </Card>

      <div>
        <Title order={3} mb="xs">
          Gear
        </Title>
        <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="md">
          {GEAR_SLOTS.map((slot) => (
            <GearSlot
              key={slot}
              slot={slot}
              item={ch.equipment[slot]}
              canUnequip={canManage}
              onUnequip={() => unequip.mutate(slot)}
              busy={busy}
            />
          ))}
        </SimpleGrid>
      </div>

      {owner && bag.length > 0 && (
        <div>
          <Title order={3} mb="xs">
            Bag
          </Title>
          <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="md">
            {bag.map((item) => (
              <Card key={item.item_id} withBorder radius="md" padding="md">
                <Text fw={600}>{item.name}</Text>
                <Text c="dimmed" size="xs">
                  {item.slot}
                </Text>
                {!ch.is_retired && (
                  <Button
                    mt="xs"
                    size="compact-sm"
                    onClick={() => equip.mutate(item.item_id)}
                    disabled={busy}
                  >
                    Equip
                  </Button>
                )}
              </Card>
            ))}
          </SimpleGrid>
        </div>
      )}

      {canManage && (
        <Text c="dimmed" size="sm">
          Need more gear? Visit the <Link to="/dndbattle/shop">shop</Link>.
        </Text>
      )}

      <Modal
        opened={confirmRetire}
        onClose={() => setConfirmRetire(false)}
        title={`Retire ${ch.name}?`}
        centered
      >
        <Stack gap="md">
          <Text size="sm">
            Retirement is permanent — the character stops fighting and keeps its place in your
            retired legends (and can mentor new characters later). Gear is lost; your gold is kept.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirmRetire(false)}>
              Cancel
            </Button>
            <Button
              color="red"
              loading={retire.isPending}
              onClick={() =>
                retire.mutate(undefined, {
                  onSuccess: () => {
                    setConfirmRetire(false);
                    navigate('/dndbattle/roster');
                  },
                  onError: () => setConfirmRetire(false),
                })
              }
            >
              Retire
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
