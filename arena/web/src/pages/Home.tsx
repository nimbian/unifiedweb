import { Link } from "react-router-dom";
import { useMe } from "../api/hooks";

export default function Home() {
  const me = useMe();

  return (
    <div>
      <h1>D&D Arena</h1>
      <p>
        Create a D&D character in Twitch chat, send it into recurring arena
        battles on stream, and manage it here: rename it, buy and swap gear,
        and browse the leaderboards and Hall of Fame.
      </p>
      {me.data ? (
        <div className="card">
          <h3>Welcome back, {me.data.user.display_name || me.data.user.login}!</h3>
          <p className="sub">
            You have <span className="gold-text">{me.data.gold.toLocaleString()}g</span>.
          </p>
          <div className="row">
            <Link className="btn" to="/roster">
              My characters
            </Link>
            <Link className="btn ghost" to="/arena">
              Live arena
            </Link>
          </div>
        </div>
      ) : (
        <div className="card">
          <h3>Get started</h3>
          <p className="sub">
            Log in with your Twitch account to manage the characters you created
            in chat (<code>!create &lt;class&gt; &lt;race&gt; &lt;name&gt;</code>).
          </p>
          <a className="btn twitch" href="/api/auth/login?next=/roster">
            Login with Twitch
          </a>
        </div>
      )}
      <h2>How it works</h2>
      <ul className="muted">
        <li>Characters are created in Twitch chat and live for 25 battles.</li>
        <li>Type <code>!enter</code> in chat to queue for the next round.</li>
        <li>Earn gold by watching and betting — spend it in the shop.</li>
        <li>Rename, re-gear, and retire your characters right here.</li>
      </ul>
    </div>
  );
}
