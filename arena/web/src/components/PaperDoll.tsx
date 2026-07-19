import type { EquippedItem, ShopItem } from "../api/types";

const SLOTS = ["weapon", "armor", "trinket"] as const;

function grantsText(item: EquippedItem): string {
  if (!("grants" in item)) return "";
  const g = (item as ShopItem).grants;
  const parts: string[] = [];
  if (g.ap_mult) parts.push(`+${Math.round(g.ap_mult * 100)}% power`);
  if (g.ac_bonus) parts.push(`+${g.ac_bonus} AC`);
  if (g.speed_mult) parts.push(`+${Math.round(g.speed_mult * 100)}% speed`);
  if (g.crit_pp) parts.push(`+${g.crit_pp}% crit dmg`);
  if (g.loot_pp) parts.push(`+${g.loot_pp}% loot`);
  return parts.join(" · ");
}

interface Props {
  equipment: Record<string, EquippedItem>;
  onUnequip?: (slot: string) => void;
  busy?: boolean;
}

export default function PaperDoll({ equipment, onUnequip, busy }: Props) {
  return (
    <div className="doll">
      {SLOTS.map((slot) => {
        const item = equipment[slot];
        return (
          <div className="slot" key={slot}>
            <div className="slot-name">{slot}</div>
            {item ? (
              <>
                {/* Optional icon: public/gear/<item_id>.png, fail-soft */}
                <img
                  src={`/gear/${item.item_id}.png`}
                  alt=""
                  onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                />
                <div className="item-name">
                  {"name" in item ? item.name : item.item_id}
                </div>
                <div className="grants">{grantsText(item)}</div>
                {onUnequip && (
                  <button
                    className="btn small ghost"
                    onClick={() => onUnequip(slot)}
                    disabled={busy}
                  >
                    Unequip
                  </button>
                )}
              </>
            ) : (
              <div className="muted" style={{ marginTop: 14 }}>
                empty
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
