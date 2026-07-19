// A small text input for a mantine-datatable column header filter (the popover
// that opens from the column's filter icon). Pass it as a column's `filter` and
// set `filtering` to `value !== ''` so the icon shows the active state.

import { ActionIcon, Select, TextInput } from '@mantine/core';
import { IconSearch, IconX } from '@tabler/icons-react';

interface Props {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function TextColumnFilter({ value, onChange, placeholder = 'Filter…' }: Props) {
  return (
    <TextInput
      autoFocus
      placeholder={placeholder}
      leftSection={<IconSearch size={16} />}
      rightSection={
        value ? (
          <ActionIcon variant="subtle" color="gray" onClick={() => onChange('')}>
            <IconX size={14} />
          </ActionIcon>
        ) : null
      }
      value={value}
      onChange={(e) => onChange(e.currentTarget.value)}
    />
  );
}

// Case-insensitive substring match used to apply the filter to records.
export function matches(field: string | null | undefined, query: string): boolean {
  if (!query) return true;
  return (field ?? '').toLowerCase().includes(query.toLowerCase());
}

// A Yes/No (clearable -> "All") column-header filter for boolean columns. The
// value is 'yes' | 'no' | null; pass it as a column's `filter` and set
// `filtering` to `value !== null`.
interface YesNoProps {
  value: string | null;
  onChange: (value: string | null) => void;
  label?: string;
}

export function YesNoColumnFilter({ value, onChange, label }: YesNoProps) {
  return (
    <Select
      label={label}
      placeholder="All"
      clearable
      data={[
        { value: 'yes', label: 'Yes' },
        { value: 'no', label: 'No' },
      ]}
      value={value}
      onChange={onChange}
      comboboxProps={{ withinPortal: false }}
    />
  );
}

// Applies a Yes/No filter to a boolean field (null filter = keep all).
export function matchesYesNo(field: boolean, filter: string | null): boolean {
  if (filter === null) return true;
  return filter === 'yes' ? field : !field;
}

// A single-select (clearable -> "All") column-header filter populated with the
// given options ("the selections"). Value is the chosen option's value or null.
interface SelectProps {
  value: string | null;
  onChange: (value: string | null) => void;
  data: { value: string; label: string }[];
  label?: string;
}

export function SelectColumnFilter({ value, onChange, data, label }: SelectProps) {
  return (
    <Select
      label={label}
      placeholder="All"
      clearable
      searchable
      data={data}
      value={value}
      onChange={onChange}
      comboboxProps={{ withinPortal: false }}
      nothingFoundMessage="No matches"
    />
  );
}
