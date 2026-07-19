// App-wide card viewer. Any table calls useCardViewer().open({ collectionId,
// name }) to pop a modal showing the interactive 3D card. Rendered once at the
// app root so the heavy layered card mounts only on demand.

import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Modal } from '@mantine/core';
import { CardImage } from './CardImage';

interface ViewedCard {
  collectionId: number;
  name?: string | null;
}

interface CardViewerValue {
  open: (card: ViewedCard) => void;
}

const CardViewerContext = createContext<CardViewerValue | null>(null);

export function CardViewerProvider({ children }: { children: ReactNode }) {
  const [card, setCard] = useState<ViewedCard | null>(null);
  const open = useCallback((c: ViewedCard) => setCard(c), []);
  const value = useMemo(() => ({ open }), [open]);

  return (
    <CardViewerContext.Provider value={value}>
      {children}
      <Modal
        opened={card !== null}
        onClose={() => setCard(null)}
        title={card ? `${card.name ?? 'Card'} — #${card.collectionId}` : ''}
        centered
        size="auto"
      >
        {card && <CardImage collectionId={card.collectionId} />}
      </Modal>
    </CardViewerContext.Provider>
  );
}

export function useCardViewer(): CardViewerValue {
  const ctx = useContext(CardViewerContext);
  if (!ctx) throw new Error('useCardViewer must be used within a CardViewerProvider');
  return ctx;
}
