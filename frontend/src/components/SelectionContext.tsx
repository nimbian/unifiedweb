// Page-wide card selection for the "sell" flow. Selection is keyed by
// collection_id so a card selected in one table (e.g. Full Collection) shows as
// selected everywhere it appears (e.g. inside a set view), and a single
// "Clear all" empties every checkbox at once.

import { createContext, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { CardRow } from '@/types';

interface SelectionContextValue {
  count: number;
  selectedCards: CardRow[];
  // The currently-selected subset of a given table's records.
  selectedFor: (records: CardRow[]) => CardRow[];
  // Replace the selection for a given table's record set with `next`.
  setSelectedFor: (records: CardRow[], next: CardRow[]) => void;
  clear: () => void;
}

const SelectionContext = createContext<SelectionContextValue | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [selected, setSelected] = useState<Map<number, CardRow>>(new Map());

  const value = useMemo<SelectionContextValue>(
    () => ({
      count: selected.size,
      selectedCards: [...selected.values()],
      selectedFor: (records) => records.filter((r) => selected.has(r.collection_id)),
      setSelectedFor: (records, next) =>
        setSelected((prev) => {
          const m = new Map(prev);
          for (const r of records) m.delete(r.collection_id); // drop this table's old picks
          for (const r of next) m.set(r.collection_id, r); // add the new ones
          return m;
        }),
      clear: () => setSelected(new Map()),
    }),
    [selected],
  );

  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

// Returns the selection context, or null when used outside a provider (so
// non-selectable tables can call it unconditionally without crashing).
export function useSelection(): SelectionContextValue | null {
  return useContext(SelectionContext);
}
