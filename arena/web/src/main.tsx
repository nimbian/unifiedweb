import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import Home from "./pages/Home";
import Roster from "./pages/Roster";
import CharacterSheet from "./pages/CharacterSheet";
import Shop from "./pages/Shop";
import Leaderboard from "./pages/Leaderboard";
import HallOfFame from "./pages/HallOfFame";
import Arena from "./pages/Arena";
import "./styles.css";

const queryClient = new QueryClient();

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Home /> },
      { path: "roster", element: <Roster /> },
      { path: "characters/:id", element: <CharacterSheet /> },
      { path: "shop", element: <Shop /> },
      { path: "leaderboard", element: <Leaderboard /> },
      { path: "hof", element: <HallOfFame /> },
      { path: "arena", element: <Arena /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
);
