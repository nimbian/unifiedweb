import { Route, Routes } from 'react-router-dom';
import { MainLayout } from '@/layouts/MainLayout';
import { DndBattleLayout } from '@/layouts/DndBattleLayout';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { HomePage } from '@/pages/HomePage';
import { UsersPage } from '@/pages/UsersPage';
import { ArenaPage } from '@/pages/dndbattle/ArenaPage';
import { DndBattleLeaderboardPage } from '@/pages/dndbattle/DndBattleLeaderboardPage';
import { HallOfFamePage } from '@/pages/dndbattle/HallOfFamePage';
import { RosterPage } from '@/pages/dndbattle/RosterPage';
import { CharacterSheetPage } from '@/pages/dndbattle/CharacterSheetPage';
import { ShopPage } from '@/pages/dndbattle/ShopPage';
import { UserCardsPage } from '@/pages/UserCardsPage';
import { ProgressPage } from '@/pages/ProgressPage';
import { SearchPage } from '@/pages/SearchPage';
import { LeaderboardPage } from '@/pages/LeaderboardPage';
import { AdventurersPage } from '@/pages/dnd/AdventurersPage';
import { CharacterPage } from '@/pages/dnd/CharacterPage';
import { DndLeaderboardPage } from '@/pages/dnd/DndLeaderboardPage';
import { WorldBossPage } from '@/pages/dnd/WorldBossPage';
import { DndAchievementsPage } from '@/pages/dnd/DndAchievementsPage';
import { SlideshowPage } from '@/pages/SlideshowPage';
import { LoginPage } from '@/pages/LoginPage';
import { AuthCallbackPage } from '@/pages/AuthCallbackPage';
import { AccountPage } from '@/pages/AccountPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

// Route map (Phase 2 — unified SPA). Portal-level routes stay at the top; every
// Satchemon page now lives under /satchemon/*, and DnD Adventure (the same
// Discord community) lives under it at /satchemon/progress/* (PLAN §4 decision).
//   /                          -> HomePage         (portal landing)
//   /login                     -> LoginPage
//   /auth/callback             -> AuthCallbackPage (OAuth redirect target)
//   /account                   -> AccountPage      (linked-accounts management)
//   /satchemon                 -> UsersPage        (all users)
//   /satchemon/user/:did       -> UserCardsPage
//   /satchemon/user/:did/progress -> ProgressPage
//   /satchemon/me              -> UserCardsPage    (self, protected)
//   /satchemon/search          -> SearchPage
//   /satchemon/leaderboard     -> LeaderboardPage  (top pulls + Perfect 30)
//   /satchemon/shop            -> UserCardsPage    (system user uid 0)
//   /satchemon/slideshow       -> SlideshowPage    (/CS)
//   /satchemon/progress        -> AdventurersPage  (DnD Adventure)
//   /satchemon/progress/mine|character/:key|leaderboard|worldboss|achievements
//   /dndbattle                 -> ArenaPage        (live arena, public)
//   /dndbattle/leaderboard|hof|shop                (public reads + shop catalog)
//   /dndbattle/roster          -> RosterPage       (authed; Twitch-link gated)
//   /dndbattle/character/:id   -> CharacterSheetPage (public read, owner actions)
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />

      <Route element={<MainLayout />}>
        <Route
          path="/account"
          element={
            <ProtectedRoute>
              <AccountPage />
            </ProtectedRoute>
          }
        />

        {/* Satchemon */}
        <Route path="/satchemon" element={<UsersPage />} />
        <Route path="/satchemon/user/:did" element={<UserCardsPage />} />
        <Route path="/satchemon/user/:did/progress" element={<ProgressPage />} />
        <Route
          path="/satchemon/me"
          element={
            <ProtectedRoute>
              <UserCardsPage self />
            </ProtectedRoute>
          }
        />
        <Route path="/satchemon/search" element={<SearchPage />} />
        <Route path="/satchemon/leaderboard" element={<LeaderboardPage />} />
        <Route path="/satchemon/shop" element={<UserCardsPage shop />} />
        <Route path="/satchemon/slideshow" element={<SlideshowPage />} />

        {/* DnD Adventure — lives under Satchemon */}
        <Route path="/satchemon/progress" element={<AdventurersPage />} />
        <Route
          path="/satchemon/progress/mine"
          element={
            <ProtectedRoute>
              <AdventurersPage mineOnly />
            </ProtectedRoute>
          }
        />
        <Route path="/satchemon/progress/character/:key" element={<CharacterPage />} />
        <Route path="/satchemon/progress/leaderboard" element={<DndLeaderboardPage />} />
        <Route path="/satchemon/progress/worldboss" element={<WorldBossPage />} />
        <Route path="/satchemon/progress/achievements" element={<DndAchievementsPage />} />

        <Route path="*" element={<NotFoundPage />} />
      </Route>

      {/* DnD Battle (arena). Read pages + the shop catalog are public; the
          roster/sheet/buy actions authenticate with the portal Bearer token and
          self-gate on a 401 (see PlayGate) rather than via ProtectedRoute, so a
          signed-in-but-Twitch-unlinked user gets the "link Twitch" prompt. */}
      <Route element={<DndBattleLayout />}>
        <Route path="/dndbattle" element={<ArenaPage />} />
        <Route path="/dndbattle/leaderboard" element={<DndBattleLeaderboardPage />} />
        <Route path="/dndbattle/hof" element={<HallOfFamePage />} />
        <Route path="/dndbattle/shop" element={<ShopPage />} />
        <Route path="/dndbattle/roster" element={<RosterPage />} />
        <Route path="/dndbattle/character/:id" element={<CharacterSheetPage />} />
      </Route>
    </Routes>
  );
}
