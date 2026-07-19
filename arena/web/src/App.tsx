import { Outlet } from "react-router-dom";
import NavBar from "./components/NavBar";

export default function App() {
  return (
    <div className="app">
      <NavBar />
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
