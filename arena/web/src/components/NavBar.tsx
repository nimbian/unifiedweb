import { NavLink, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useMe, logout } from "../api/hooks";

export default function NavBar() {
  const me = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();

  async function onLogout() {
    await logout();
    qc.clear();
    navigate("/");
  }

  return (
    <nav className="navbar">
      <span className="brand">D&D Arena</span>
      <NavLink to="/arena">Arena</NavLink>
      <NavLink to="/roster">My Characters</NavLink>
      <NavLink to="/shop">Shop</NavLink>
      <NavLink to="/leaderboard">Leaderboard</NavLink>
      <NavLink to="/hof">Hall of Fame</NavLink>
      <span className="spacer" />
      {me.data ? (
        <>
          <span>
            {me.data.user.display_name || me.data.user.login}{" "}
            <span className="gold">{me.data.gold.toLocaleString()}g</span>
          </span>
          <button className="btn small ghost" onClick={() => void onLogout()}>
            Log out
          </button>
        </>
      ) : (
        <a className="btn small twitch" href="/api/auth/login">
          Login with Twitch
        </a>
      )}
    </nav>
  );
}
