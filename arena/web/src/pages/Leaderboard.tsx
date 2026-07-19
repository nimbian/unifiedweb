import { useState } from "react";
import { useLeaderboard } from "../api/hooks";

export default function Leaderboard() {
  const [by, setBy] = useState<"damage" | "wins">("damage");
  const [scope, setScope] = useState<"season" | "alltime">("season");
  const board = useLeaderboard(by, scope);

  return (
    <div>
      <h1>Leaderboard</h1>
      <div className="row" style={{ margin: "12px 0" }}>
        <button
          className={`btn small ${by === "damage" ? "" : "ghost"}`}
          onClick={() => setBy("damage")}
        >
          Damage
        </button>
        <button
          className={`btn small ${by === "wins" ? "" : "ghost"}`}
          onClick={() => setBy("wins")}
        >
          Wins
        </button>
        <span className="spacer" style={{ width: 20 }} />
        <button
          className={`btn small ${scope === "season" ? "" : "ghost"}`}
          onClick={() => setScope("season")}
        >
          This season
        </button>
        <button
          className={`btn small ${scope === "alltime" ? "" : "ghost"}`}
          onClick={() => setScope("alltime")}
        >
          All-time
        </button>
      </div>
      {board.isLoading && <p className="muted">Loading…</p>}
      {board.error && <p className="error">{board.error.message}</p>}
      {board.data && (
        board.data.rows.length === 0 ? (
          <p className="muted">Nothing recorded yet — go fight!</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Character</th>
                <th>{by === "damage" ? "Damage" : "Wins"}</th>
              </tr>
            </thead>
            <tbody>
              {board.data.rows.map((row, i) => (
                <tr key={`${row.name}-${i}`}>
                  <td>{i + 1}</td>
                  <td>{row.name}</td>
                  <td>{row.value.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
