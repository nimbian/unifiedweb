// Adventurers — a searchable table of every character in the DnD bot.

import { useEffect, useMemo, useState } from 'react';
import { Alert, Badge, Group, SegmentedControl, TextInput } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useDebouncedValue } from '@mantine/hooks';
import { DataTable, type DataTableSortStatus } from 'mantine-datatable';
import { useNavigate } from 'react-router-dom';
import { useDndCharacters } from '@/hooks/useDnd';
import { useAuth } from '@/hooks/useAuth';
import { matches } from '@/components/TextColumnFilter';
import { DndNav } from './DndNav';
import type { CharacterSummary } from '@/types/dnd';

const PAGE_SIZES = [10, 25, 50, 100];

export function AdventurersPage({ mineOnly = false }: { mineOnly?: boolean }) {
  const { data = [], isLoading, isError } = useDndCharacters();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [debounced] = useDebouncedValue(query, 200);
  const [scope, setScope] = useState('all');
  // In "My DnD Adventure" mode the scope is locked to the logged-in player.
  const effectiveScope = mineOnly ? 'mine' : scope;
  const [sort, setSort] = useState<DataTableSortStatus<CharacterSummary>>({
    columnAccessor: 'level',
    direction: 'desc',
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const filtered = useMemo(() => {
    const dir = sort.direction === 'asc' ? 1 : -1;
    return [...data]
      .filter((c) => effectiveScope === 'all' || c.discord_id === user?.did)
      .filter(
        (c) =>
          matches(c.char_name ?? c.username, debounced) || matches(c.class_name ?? '', debounced),
      )
      .sort((a, b) => {
        const av = a[sort.columnAccessor as keyof CharacterSummary];
        const bv = b[sort.columnAccessor as keyof CharacterSummary];
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
        return String(av ?? '').localeCompare(String(bv ?? ''), undefined, { numeric: true }) * dir;
      });
  }, [data, effectiveScope, user?.did, debounced, sort]);

  useEffect(() => setPage(1), [debounced, effectiveScope, pageSize, sort]);
  const records = filtered.slice((page - 1) * pageSize, page * pageSize);

  if (isError) return <Alert color="red">Failed to load adventurers.</Alert>;

  return (
    <>
      <DndNav />
      <Group justify="space-between" mb="md">
        {user && !mineOnly ? (
          <SegmentedControl
            value={scope}
            onChange={setScope}
            data={[
              { value: 'all', label: 'All' },
              { value: 'mine', label: 'My Adventurers' },
            ]}
          />
        ) : (
          <span />
        )}
        <TextInput
          placeholder="Search name or class…"
          leftSection={<IconSearch size={16} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          w={280}
        />
      </Group>
      <DataTable<CharacterSummary>
        withTableBorder
        borderRadius="md"
        striped
        highlightOnHover
        minHeight={200}
        fetching={isLoading}
        idAccessor="key"
        records={records}
        totalRecords={filtered.length}
        page={page}
        onPageChange={setPage}
        recordsPerPage={pageSize}
        recordsPerPageOptions={PAGE_SIZES}
        onRecordsPerPageChange={setPageSize}
        sortStatus={sort}
        onSortStatusChange={setSort}
        onRowClick={({ record }) => navigate(`/dnd/character/${record.key}`)}
        columns={[
          {
            accessor: 'char_name',
            title: 'Character',
            sortable: true,
            render: (c) => (
              <Group gap={6} wrap="nowrap">
                <span>{c.char_name ?? c.username}</span>
                {c.active && (
                  <Badge size="xs" color="green" variant="light">
                    active
                  </Badge>
                )}
              </Group>
            ),
          },
          {
            accessor: 'class_name',
            title: 'Class',
            sortable: true,
            render: (c) => (c.subclass_name ? `${c.class_name} · ${c.subclass_name}` : c.class_name),
          },
          { accessor: 'level', title: 'Level', textAlign: 'right', sortable: true },
          {
            accessor: 'gold',
            title: 'Gold',
            textAlign: 'right',
            sortable: true,
            render: (c) => c.gold.toLocaleString(),
          },
          {
            accessor: 'abyss_best_floor',
            title: 'Abyss',
            textAlign: 'right',
            sortable: true,
            render: (c) => (c.abyss_best_floor > 0 ? c.abyss_best_floor : '—'),
          },
          {
            accessor: 'duel_wins',
            title: 'Duels (W/L)',
            textAlign: 'right',
            sortable: true,
            render: (c) => `${c.duel_wins}/${c.duel_losses}`,
          },
        ]}
      />
    </>
  );
}
