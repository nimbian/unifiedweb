// "All users" page — replaces users.j2 / the `#us` DataTable.

import { useEffect, useMemo, useState } from 'react';
import { Alert, Anchor, Group, TextInput, Title } from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { useDebouncedValue } from '@mantine/hooks';
import { DataTable, type DataTableSortStatus } from 'mantine-datatable';
import { useNavigate } from 'react-router-dom';
import { useUsers } from '@/hooks/useUsers';
import { formatValue, isActive } from '@/utils/format';
import { matches, SelectColumnFilter } from '@/components/TextColumnFilter';
import { ActivePill } from '@/components/ActivePill';
import type { UserSummary } from '@/types';

const PAGE_SIZES = [10, 25, 50, 100];

export function UsersPage() {
  const { data = [], isLoading, isError } = useUsers();
  const navigate = useNavigate();
  const [sort, setSort] = useState<DataTableSortStatus<UserSummary>>({
    columnAccessor: 'name',
    direction: 'asc',
  });
  const [query, setQuery] = useState('');
  const [debounced] = useDebouncedValue(query, 200);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const filtered = useMemo(() => {
    const dir = sort.direction === 'asc' ? 1 : -1;
    return [...data]
      // Search matches the user's name or their Discord id.
      .filter((u) => matches(u.name ?? '', debounced) || matches(String(u.did), debounced))
      .filter((u) => activeFilter === null || (activeFilter === 'active') === isActive(u.last_active))
      .sort((a, b) => {
        const av = a[sort.columnAccessor as keyof UserSummary];
        const bv = b[sort.columnAccessor as keyof UserSummary];
        return String(av ?? '').localeCompare(String(bv ?? ''), undefined, { numeric: true }) * dir;
      });
  }, [data, sort, debounced, activeFilter]);

  // Keep the current page valid as filtering/sorting/page-size change the data.
  useEffect(() => setPage(1), [debounced, activeFilter, pageSize, sort]);

  const records = filtered.slice((page - 1) * pageSize, page * pageSize);

  if (isError) {
    return <Alert color="red">Failed to load users.</Alert>;
  }

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>All Users</Title>
        <TextInput
          placeholder="Search users…"
          leftSection={<IconSearch size={16} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          w={280}
        />
      </Group>
      <DataTable<UserSummary>
        withTableBorder
        borderRadius="md"
        striped
        highlightOnHover
        minHeight={200}
        fetching={isLoading}
        idAccessor="did"
        records={records}
        totalRecords={filtered.length}
        page={page}
        onPageChange={setPage}
        recordsPerPage={pageSize}
        recordsPerPageOptions={PAGE_SIZES}
        onRecordsPerPageChange={setPageSize}
        sortStatus={sort}
        onSortStatusChange={setSort}
        onRowClick={({ record }) => navigate(`/satchemon/user/${record.did}`)}
        columns={[
          {
            accessor: 'name',
            title: 'User',
            sortable: true,
            render: ({ name, did }) => (
              <Anchor onClick={() => navigate(`/satchemon/user/${did}`)}>{name ?? did}</Anchor>
            ),
          },
          { accessor: 'card_count', title: 'Cards', sortable: true, textAlign: 'right' },
          {
            accessor: 'collection_value',
            title: 'Collection Value',
            sortable: true,
            textAlign: 'right',
            render: ({ collection_value }) => formatValue(collection_value),
          },
          {
            accessor: 'gp',
            title: 'GP',
            sortable: true,
            textAlign: 'right',
            render: ({ gp }) => formatValue(gp),
          },
          {
            accessor: 'last_active',
            title: 'Active',
            textAlign: 'center',
            sortable: true,
            filter: (
              <SelectColumnFilter
                label="Active"
                value={activeFilter}
                onChange={setActiveFilter}
                data={[
                  { value: 'active', label: 'Active' },
                  { value: 'inactive', label: 'Inactive' },
                ]}
              />
            ),
            filtering: activeFilter !== null,
            render: ({ last_active }) => <ActivePill lastActive={last_active} />,
          },
        ]}
      />
    </>
  );
}
