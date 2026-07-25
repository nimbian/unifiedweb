// Shared helpers for the Midweek Monster Mash donor pages.
//
// Badge emblem art lives in the frontend's public/ dir (one WebP per tier), so a
// tier key maps straight to its image URL. The point values, titles and order
// are authoritative on the backend (they drive ranking) and arrive via
// /api/mmm/badges; here we only own the presentation (art + accent colour).

// Emblem for a tier — served from public/mmm-badges/<key>.webp.
export const badgeIcon = (key: string): string => `/mmm-badges/${key}.webp`;

// A Mantine accent colour per tier, roughly matching each emblem's palette.
export const TIER_COLOR: Record<string, string> = {
  initiate: 'orange', // bronze
  apprentice: 'grape', // arcane purple
  knight: 'blue', // steel blue
  master: 'yellow', // gold
  ascendant: 'gray', // platinum
  luminary: 'pink', // prismatic
  arbiter: 'indigo', // cosmic
};

export const tierColor = (key: string): string => TIER_COLOR[key] ?? 'blue';

// 1 -> "1st", 2 -> "2nd", … (ported from the original app.js).
export function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  const suffix = ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${suffix}`;
}

// Points are whole numbers or half-points; show at most one decimal.
export function formatPoints(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
