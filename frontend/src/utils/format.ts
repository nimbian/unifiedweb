// Challenge-rating ordering — ported from static/scripts/sets.js (`crsort`).
const CR_ORDER = [
  '1/8', '1/4', '1/2', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
  '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22',
  '23', '24', '25', '26', '27', '28', '29', '30',
];

export function compareCr(a: string | null, b: string | null): number {
  const ia = CR_ORDER.indexOf(a ?? '');
  const ib = CR_ORDER.indexOf(b ?? '');
  return ia - ib;
}

export function formatValue(value: string | null, digits = 3): string {
  if (value === null || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : value;
}

// Highlight rule from userCardsJS.j2: grade 10 + holo => gold.
export function isGoldCard(grade: number | null, holo: boolean): boolean {
  return grade === 10 && holo;
}

// A user is "active" if their most recent card is less than a month (~30 days)
// old. ``lastActive`` is the ISO date of that card (null if they have none).
const ACTIVE_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;
export function isActive(lastActive: string | null): boolean {
  if (!lastActive) return false;
  const t = new Date(lastActive).getTime();
  return Number.isFinite(t) && Date.now() - t < ACTIVE_WINDOW_MS;
}
