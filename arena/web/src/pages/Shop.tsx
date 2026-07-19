import { useState } from "react";
import { useBuy, useMe, useRoster, useShop } from "../api/hooks";
import type { ShopItem } from "../api/types";

function grantsText(item: ShopItem): string {
  const g = item.grants;
  const parts: string[] = [];
  if (g.ap_mult) parts.push(`+${Math.round(g.ap_mult * 100)}% power`);
  if (g.ac_bonus) parts.push(`+${g.ac_bonus} AC`);
  if (g.speed_mult) parts.push(`+${Math.round(g.speed_mult * 100)}% speed`);
  if (g.crit_pp) parts.push(`+${g.crit_pp}% crit dmg`);
  if (g.loot_pp) parts.push(`+${g.loot_pp}% loot`);
  return parts.join(" · ");
}

export default function Shop() {
  const shop = useShop();
  const me = useMe();
  const roster = useRoster();
  const living = roster.data?.living ?? [];
  const [targetId, setTargetId] = useState<number | null>(null);
  const target = targetId ?? living[0]?.id ?? null;
  const buy = useBuy(target ?? 0);

  if (shop.isLoading) return <p className="muted">Loading…</p>;
  if (shop.error) return <p className="error">{shop.error.message}</p>;
  const { enabled, items } = shop.data!;

  const owned = new Set(
    living
      .find((c) => c.id === target)
      ?.inventory?.map((i) => i.item_id) ?? [],
  );

  return (
    <div>
      <h1>Shop</h1>
      {!enabled && (
        <div className="card">
          <h3>The shop isn't open yet</h3>
          <p className="sub">
            Browse the catalog below — buying unlocks when the streamer enables
            the gear economy.
          </p>
        </div>
      )}
      {me.data && living.length > 0 && (
        <div className="row" style={{ margin: "12px 0" }}>
          <span className="muted">Buying for:</span>
          <select
            value={target ?? undefined}
            onChange={(e) => setTargetId(Number(e.target.value))}
            className="inline-form"
            style={{ padding: "6px 10px" }}
          >
            {living.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name} (Lv{c.level} {c.class_name})
              </option>
            ))}
          </select>
          <span className="gold-text">{me.data.gold.toLocaleString()}g</span>
        </div>
      )}
      {buy.error && <p className="error">{buy.error.message}</p>}
      {(["weapon", "armor", "trinket"] as const).map((slot) => (
        <div key={slot}>
          <h2>{slot}s</h2>
          <div className="grid">
            {items
              .filter((i) => i.slot === slot)
              .map((item) => (
                <div className="card" key={item.item_id}>
                  <h3>{item.name}</h3>
                  <div className="sub">{grantsText(item)}</div>
                  <div className="row" style={{ marginTop: 10 }}>
                    <span className="gold-text">{item.price.toLocaleString()}g</span>
                    {enabled && me.data && target !== null && (
                      owned.has(item.item_id) ? (
                        <span className="pill">owned</span>
                      ) : (
                        <button
                          className="btn small"
                          disabled={buy.isPending}
                          onClick={() => buy.mutate({ item_id: item.item_id })}
                        >
                          Buy
                        </button>
                      )
                    )}
                  </div>
                </div>
              ))}
          </div>
        </div>
      ))}
      {!me.data && (
        <p className="muted">
          <a href="/api/auth/login?next=/shop">Log in</a> to buy gear for your
          characters.
        </p>
      )}
    </div>
  );
}
