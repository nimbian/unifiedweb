import { useArena } from "../api/hooks";

const PHASE_LABELS: Record<string, string> = {
  idle: "Arena closed",
  intermission: "Intermission — queue is open",
  roster_lock: "Lineup locked — betting open",
  combat: "FIGHT!",
  results: "Results",
  paused: "Paused",
};

export default function Arena() {
  const arena = useArena();

  if (arena.isLoading) return <p className="muted">Loading…</p>;
  if (arena.error) return <p className="error">{arena.error.message}</p>;
  const { phase, round, fighters, queue, is_open } = arena.data!;
  const kind = (round?.kind as string) ?? "race";

  return (
    <div>
      <h1>Live Arena</h1>
      <div className="row" style={{ margin: "10px 0" }}>
        <span className={`pill ${is_open ? "live" : ""}`}>
          {is_open ? "OPEN" : "CLOSED"}
        </span>
        <span className="pill">{PHASE_LABELS[phase] ?? phase}</span>
        {round != null && kind === "monster" && (
          <span className="pill">monster battle</span>
        )}
      </div>

      {fighters.length > 0 && (
        <>
          <h2>Current lineup</h2>
          <table>
            <thead>
              <tr>
                <th>Slot</th>
                <th>Fighter</th>
                <th>Class</th>
                <th>Owner</th>
              </tr>
            </thead>
            <tbody>
              {fighters.map((f) => (
                <tr key={f.slot}>
                  <td>{f.slot}</td>
                  <td>{f.name}</td>
                  <td>{f.class}</td>
                  <td className="muted">{f.is_npc ? "NPC" : `@${f.owner ?? "?"}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h2>Queue ({queue.length})</h2>
      {queue.length === 0 ? (
        <p className="muted">
          Nobody queued — type <code>!enter</code> in chat to join the next round.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Character</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {queue.map((q, i) => (
              <tr key={q.character_id}>
                <td>{i + 1}</td>
                <td>{q.name}</td>
                <td>{q.priority && <span className="pill">priority</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted" style={{ marginTop: 24 }}>
        Updates every few seconds. The full spectacle is on stream!
      </p>
    </div>
  );
}
