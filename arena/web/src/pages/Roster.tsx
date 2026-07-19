import { Link } from "react-router-dom";
import { useRoster } from "../api/hooks";
import type { Character } from "../api/types";

function CharCard({ ch }: { ch: Character }) {
  return (
    <Link to={`/characters/${ch.id}`} className="card" style={{ display: "block" }}>
      <h3>
        {ch.name} <span className="muted">Lv{ch.level}</span>
      </h3>
      <div className="sub">
        {ch.personality && `${ch.personality} `}
        {ch.race} {ch.class_name}
      </div>
      <div className="sub" style={{ marginTop: 6 }}>
        {ch.wins}W / {ch.losses}L · {ch.lifetime_damage.toLocaleString()} dmg
        {!ch.is_retired && ` · ${ch.battles_left} battles left`}
      </div>
    </Link>
  );
}

export default function Roster() {
  const roster = useRoster();

  if (roster.error?.status === 401) {
    return (
      <div className="card">
        <h3>Log in first</h3>
        <p className="sub">Your characters are tied to your Twitch account.</p>
        <a className="btn twitch" href="/api/auth/login?next=/roster">
          Login with Twitch
        </a>
      </div>
    );
  }
  if (roster.isLoading) return <p className="muted">Loading…</p>;
  if (roster.error) return <p className="error">{roster.error.message}</p>;

  const { living, retired } = roster.data!;
  return (
    <div>
      <h1>My Characters</h1>
      {living.length === 0 ? (
        <p className="muted">
          No living characters — type{" "}
          <code>!create &lt;class&gt; &lt;race&gt; &lt;name&gt;</code> in chat to make one.
        </p>
      ) : (
        <div className="grid">
          {living.map((ch) => (
            <CharCard ch={ch} key={ch.id} />
          ))}
        </div>
      )}
      {retired.length > 0 && (
        <>
          <h2>Retired legends</h2>
          <div className="grid">
            {retired.map((ch) => (
              <CharCard ch={ch} key={ch.id} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
