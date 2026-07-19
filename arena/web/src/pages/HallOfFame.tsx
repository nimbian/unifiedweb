import { useHof } from "../api/hooks";

const RECORD_LABELS: Record<string, string> = {
  highest_hit: "Biggest Hit",
  highest_round: "Biggest Round",
  most_wins: "Most Wins",
  most_damage: "Most Lifetime Damage",
};

export default function HallOfFame() {
  const hof = useHof();

  if (hof.isLoading) return <p className="muted">Loading…</p>;
  if (hof.error) return <p className="error">{hof.error.message}</p>;
  const records = hof.data!.records;

  return (
    <div>
      <h1>Hall of Fame</h1>
      <p className="muted">All-time records — these survive season resets.</p>
      {records.length === 0 ? (
        <p className="muted">No records yet. Go make history!</p>
      ) : (
        <div className="grid">
          {records.map((r) => (
            <div className="card" key={r.record_key}>
              <div className="sub">{RECORD_LABELS[r.record_key] ?? r.record_key}</div>
              <h3>{r.character_name}</h3>
              <div className="gold-text" style={{ fontSize: "1.3rem" }}>
                {Math.round(r.value).toLocaleString()}
              </div>
              {r.achieved_at && (
                <div className="sub">{new Date(r.achieved_at).toLocaleDateString()}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
