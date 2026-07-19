// Page-level buy toolbar for the shop (the system user's uid-0 collection),
// shown to any signed-in user. Operates on the shared selection, so you can pick
// cards across the shop's tabs and buy them together. The web equivalent of the
// bot's shop buy/haggle; the backend enforces shop-ownership and affordability.
//
// Straight buy: flat 150% of value. Haggle: a d20 gamble that pays 130%–170%
// (a better roll is cheaper); you must afford the worst case (170%) to haggle.

import { useMemo, useState } from 'react';
import { Alert, Button, Group, Modal, Paper, Stack, Table, Text } from '@mantine/core';
import { IconDice5, IconShoppingCartPlus, IconSquareOff } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { isAxiosError } from 'axios';
import { useBuyCards } from '@/hooks/useCollections';
import { formatValue } from '@/utils/format';
import { useSelection } from './SelectionContext';

const BUY_RATE = 1.5;
const round3 = (n: number) => Math.round(n * 1000) / 1000;

type Mode = 'straight' | 'haggle' | null;

export function BuyBar() {
  const selection = useSelection();
  const [mode, setMode] = useState<Mode>(null);
  const buy = useBuyCards();

  const selected = selection?.selectedCards ?? [];

  const totalValue = useMemo(
    () => selected.reduce((sum, c) => sum + Number(c.value ?? 0), 0),
    [selected],
  );
  // Straight-buy estimate (per-card 150%, matching the server's rounding).
  const estimate = useMemo(
    () => selected.reduce((sum, c) => sum + round3(Number(c.value ?? 0) * BUY_RATE), 0),
    [selected],
  );

  if (!selection) return null;

  const confirm = (haggle: boolean) => {
    const ids = selected.map((c) => c.collection_id);
    buy.mutate(
      { collectionIds: ids, haggle },
      {
        onSuccess: (result) => {
          const base = `Bought ${result.bought.length} card(s) for ${formatValue(result.total_cost)} GP. New balance: ${formatValue(result.new_gp)} GP.`;
          notifications.show({
            title: result.roll != null ? `🎲 Rolled ${result.roll} → ${Math.round(result.rate * 100)}%` : 'Cards purchased',
            message: base,
            color: result.roll != null && result.rate > BUY_RATE ? 'yellow' : 'green',
          });
          selection.clear();
          setMode(null);
        },
        onError: (err) => {
          const detail = isAxiosError(err)
            ? ((err.response?.data as { detail?: string } | undefined)?.detail ?? err.message)
            : 'Purchase failed';
          notifications.show({ title: 'Purchase failed', message: String(detail), color: 'red' });
          setMode(null);
        },
      },
    );
  };

  const haggling = mode === 'haggle';

  return (
    <Paper withBorder p="sm" mb="md" radius="md">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          {selection.count > 0
            ? `${selection.count} selected · est. ${estimate.toFixed(3)} GP at 150%`
            : 'Select shop cards (checkboxes) to buy — flat 150%, or haggle for 130%–170%'}
        </Text>
        <Group gap="xs">
          <Button
            variant="default"
            leftSection={<IconSquareOff size={16} />}
            disabled={selection.count === 0}
            onClick={() => selection.clear()}
          >
            Clear all
          </Button>
          <Button
            variant="light"
            color="grape"
            leftSection={<IconDice5 size={16} />}
            disabled={selection.count === 0}
            onClick={() => setMode('haggle')}
          >
            Haggle
          </Button>
          <Button
            leftSection={<IconShoppingCartPlus size={16} />}
            color="green"
            disabled={selection.count === 0}
            onClick={() => setMode('straight')}
          >
            Buy selected
          </Button>
        </Group>
      </Group>

      <Modal
        opened={mode !== null}
        onClose={() => setMode(null)}
        title={haggling ? 'Haggle — roll the dice' : 'Confirm purchase'}
        centered
      >
        <Stack>
          {haggling ? (
            <Alert color="grape" variant="light">
              You'll roll a d20: <b>1</b> = 170%, <b>2–8</b> = 160%, <b>9–12</b> = 150%, <b>13–19</b>{' '}
              = 140%, <b>20</b> = 130%. You must afford the worst case (170%); the roll is final.
            </Alert>
          ) : (
            <Text size="sm">Buy {selection.count} card(s) for 150% of their value?</Text>
          )}
          <Table withTableBorder withColumnBorders striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Card</Table.Th>
                <Table.Th ta="right">Value</Table.Th>
                {!haggling && <Table.Th ta="right">Cost</Table.Th>}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {selected.map((c) => (
                <Table.Tr key={c.collection_id}>
                  <Table.Td>{c.name}</Table.Td>
                  <Table.Td ta="right">{formatValue(c.value)}</Table.Td>
                  {!haggling && (
                    <Table.Td ta="right">{round3(Number(c.value ?? 0) * BUY_RATE).toFixed(3)}</Table.Td>
                  )}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Text fw={600} ta="right">
            {haggling
              ? `Value: ${totalValue.toFixed(3)} GP · cost ${round3(totalValue * 1.3).toFixed(3)}–${round3(totalValue * 1.7).toFixed(3)} GP`
              : `Total: ${estimate.toFixed(3)} GP`}
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setMode(null)}>
              Cancel
            </Button>
            <Button
              color={haggling ? 'grape' : 'green'}
              leftSection={haggling ? <IconDice5 size={16} /> : undefined}
              loading={buy.isPending}
              onClick={() => confirm(haggling)}
            >
              {haggling ? 'Roll & buy' : 'Confirm purchase'}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Paper>
  );
}
