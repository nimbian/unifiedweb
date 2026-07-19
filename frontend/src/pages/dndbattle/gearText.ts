// Human-readable summary of an item's stat grants (shared by the sheet + shop).

import type { ArenaEquippedItem, ItemGrants } from '@/types/arena';

export function grantsText(g: ItemGrants): string {
  const parts: string[] = [];
  if (g.ap_mult) parts.push(`+${Math.round(g.ap_mult * 100)}% power`);
  if (g.ac_bonus) parts.push(`+${g.ac_bonus} AC`);
  if (g.speed_mult) parts.push(`+${Math.round(g.speed_mult * 100)}% speed`);
  if (g.crit_pp) parts.push(`+${g.crit_pp}% crit dmg`);
  if (g.loot_pp) parts.push(`+${g.loot_pp}% loot`);
  return parts.join(' · ');
}

// Equipped gear is either a full catalog item (has grants) or just its id.
export function equippedGrantsText(item: ArenaEquippedItem): string {
  return 'grants' in item ? grantsText(item.grants) : '';
}

export function itemDisplayName(item: ArenaEquippedItem): string {
  return 'name' in item ? item.name : item.item_id;
}
