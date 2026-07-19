const STAT_ORDER = ["STR", "DEX", "CON", "INT", "WIS", "CHA"];

export default function StatBlock({ stats }: { stats: Record<string, number> }) {
  return (
    <div className="statgrid">
      {STAT_ORDER.map((k) => (
        <div className="stat" key={k}>
          <div className="k">{k}</div>
          <div className="v">{stats[k] ?? "-"}</div>
        </div>
      ))}
    </div>
  );
}
