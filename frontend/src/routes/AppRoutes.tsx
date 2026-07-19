import { Route, Routes } from 'react-router-dom';
import { MainLayout } from '@/layouts/MainLayout';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { UsersPage } from '@/pages/UsersPage';
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

// Route map (was Flask's @app.route decorators):
//   /                -> UsersPage        (/satchemon/)
//   /user/:did       -> UserCardsPage    (/satchemon/user/<did>)
//   /me              -> UserCardsPage    (/satchemon/mycards, protected)
//   /search          -> SearchPage       (/satchemon/search)
//   /leaderboard     -> LeaderboardPage  (top pulls + Perfect 30)
//   /shop            -> UserCardsPage    (system user uid 0 — sold-back cards)
//   /slideshow       -> SlideshowPage    (/CS)
//   /login           -> LoginPage
//   /auth/callback   -> AuthCallbackPage  (Discord redirect target)
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />

      <Route element={<MainLayout />}>
        <Route path="/" element={<UsersPage />} />
        <Route path="/user/:did" element={<UserCardsPage />} />
        <Route path="/user/:did/progress" element={<ProgressPage />} />
        <Route
          path="/me"
          element={
            <ProtectedRoute>
              <UserCardsPage self />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account"
          element={
            <ProtectedRoute>
              <AccountPage />
            </ProtectedRoute>
          }
        />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/leaderboard" element={<LeaderboardPage />} />
        <Route path="/shop" element={<UserCardsPage shop />} />

        {/* DnD Adventure section */}
        <Route path="/dnd" element={<AdventurersPage />} />
        <Route
          path="/dnd/mine"
          element={
            <ProtectedRoute>
              <AdventurersPage mineOnly />
            </ProtectedRoute>
          }
        />
        <Route path="/dnd/character/:key" element={<CharacterPage />} />
        <Route path="/dnd/leaderboard" element={<DndLeaderboardPage />} />
        <Route path="/dnd/worldboss" element={<WorldBossPage />} />
        <Route path="/dnd/achievements" element={<DndAchievementsPage />} />

        <Route path="/slideshow" element={<SlideshowPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
