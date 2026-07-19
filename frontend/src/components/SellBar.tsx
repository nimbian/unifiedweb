// Page-level sell toolbar for the owner of a collection. Operates on the shared
// selection (across every card table on the page), so you can pick cards from
// the Full Collection, set views, etc. and sell them together. The web
// equivalent of the Discord bot's /sell; the backend independently enforces
// ownership.
//
// Two ways to sell: a straight sale (flat 70%) or "Haggle" — the bot's d20
// gamble that pays a rate between 50% and 90% based on a server-side roll. The
// roll is final.

import { useMemo, useState } from 'react';
import { Alert, Button, Group, Modal, Paper, Stack, Table, Text } from '@mantine/core';
import { IconCoin, IconDice5, IconSquareOff } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { isAxiosError } from 'axios';
import { useSellCards } from '@/hooks/useCollections';
import { formatValue } from '@/utils/format';
import { useSelection } from './SelectionContext';

const SELL_RATE = 0.7;
const round3 = (n: number) => Math.round(n * 1000) / 1000;

type Mode = 'straight' | 'haggle' | null;

export function SellBar({ did }: { did: string }) {
  const selection = useSelection();
  const [mode, setMode] = useState<Mode>(null);
  const sell = useSellCards(did);

  const selected = selection?.selectedCards ?? [];

  const totalValue = useMemo(
    () => selected.reduce((sum, c) => sum + Number(c.value ?? 0), 0),
    [selected],
  );
  // Straight-sale estimate (per-card 70%, matching the server's rounding).
  const estimate = useMemo(
    () => selected.reduce((sum, c) => sum + round3(Number(c.value ?? 0) * SELL_RATE), 0),
    [selected],
  );

  if (!selection) return null;

  const confirm = (haggle: boolean) => {
    const ids = selected.map((c) => c.collection_id);
    sell.mutate(
      { collectionIds: ids, haggle },
      {
        onSuccess: (result) => {
          const base = `Sold ${result.sold.length} card(s) for ${formatValue(result.total_payout)} GP. New balance: ${formatValue(result.new_gp)} GP.`;
          notifications.show({
            title: result.roll != null ? `🎲 Rolled ${result.roll} → ${Math.round(result.rate * 100)}%` : 'Cards sold',
            message: base,
            color: result.roll != null && result.rate < SELL_RATE ? 'yellow' : 'green',
          });
          selection.clear();
          setMode(null);
        },
        onError: (err) => {
          const detail = isAxiosError(err)
            ? ((err.response?.data as { detail?: string } | undefined)?.detail ?? err.message)
            : 'Sale failed';
          notifications.show({ title: 'Sale failed', message: String(detail), color: 'red' });
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
            ? `${selection.count} selected · est. ${estimate.toFixed(3)} GP at 70%`
            : 'Select cards (checkboxes) to sell — flat 70%, or haggle for 50%–90%'}
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
            leftSection={<IconCoin size={16} />}
            color="green"
            disabled={selection.count === 0}
            onClick={() => setMode('straight')}
          >
            Sell selected
          </Button>
        </Group>
      </Group>

      <Modal
        opened={mode !== null}
        onClose={() => setMode(null)}
        title={haggling ? 'Haggle — roll the dice' : 'Confirm sale'}
        centered
      >
        <Stack>
          {haggling ? (
            <Alert color="grape" variant="light">
              You'll roll a d20: <b>1</b> = 50%, <b>2–8</b> = 60%, <b>9–12</b> = 70%, <b>13–19</b> =
              80%, <b>20</b> = 90%. The roll is final and the sale cannot be undone.
            </Alert>
          ) : (
            <Text size="sm">
              Sell {selection.count} card(s) for 70% of their value? This cannot be undone.
            </Text>
          )}
          <Table withTableBorder withColumnBorders striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Card</Table.Th>
                <Table.Th ta="right">Value</Table.Th>
                {!haggling && <Table.Th ta="right">Payout</Table.Th>}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {selected.map((c) => (
                <Table.Tr key={c.collection_id}>
                  <Table.Td>{c.name}</Table.Td>
                  <Table.Td ta="right">{formatValue(c.value)}</Table.Td>
                  {!haggling && (
                    <Table.Td ta="right">{round3(Number(c.value ?? 0) * SELL_RATE).toFixed(3)}</Table.Td>
                  )}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Text fw={600} ta="right">
            {haggling
              ? `Value: ${totalValue.toFixed(3)} GP · payout ${round3(totalValue * 0.5).toFixed(3)}–${round3(totalValue * 0.9).toFixed(3)} GP`
              : `Total: ${estimate.toFixed(3)} GP`}
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setMode(null)}>
              Cancel
            </Button>
            <Button
              color={haggling ? 'grape' : 'green'}
              leftSection={haggling ? <IconDice5 size={16} /> : undefined}
              loading={sell.isPending}
              onClick={() => confirm(haggling)}
            >
              {haggling ? 'Roll & sell' : 'Confirm sale'}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Paper>
  );
}
