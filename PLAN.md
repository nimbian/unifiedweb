# Unified Website Plan — Satchemon + DnD Battle Portal

**Date:** 2026-07-19
**Rule honored throughout:** no changes land in `bot/`, `dndadventure/`, `dndbattle/`, or
`newweb/`. All new work lives in a new top-level project (proposed: `unifiedweb/`), with
forks/copies of any existing code that must change.

---

## 1. Goal

One website with a homepage that routes users to **Satchemon** (TCG) or **DnD Battle**
(Twitch arena), with a single sign-in that accepts **any** of Discord, Google/YouTube, or
Twitch — account first, linking later. Bots keep working unchanged for their users.

---

## 2. Verified current state

| System | Identity key | DB | Auth today |
|---|---|---|---|
| `bot/mooreDnD-Bot` (Satchemon bot) | `users.did` in every raw-SQL query (`sqlhelper.py`) | satchemon PG | n/a (Discord interactions) |
| `dndadventure` bot | `players.discord_id` / `user_id` | `dndbot` PG (same server) | n/a (Discord interactions) |
| `dndbattle` | `users (platform, platform_user_id)` — Twitch id for twitch | own PG | Own Twitch OAuth + HMAC `dnd_session` cookie (`server/websession.py`, `webapi.py`) |
| `newweb` | JWT **subject = `did`**, `rwid` as extra claim | satchemon PG (+ dndbot read-only) | Multi-provider OAuth (discord/google/twitch) but Google/Twitch **login requires prior link** to a Discord-anchored row (`auth_service.py`) |

**Load-bearing facts discovered:**

1. `users` (satchemon) primary key is **`rwid`** (serial). `did` is `bigint NULL` with a
   `UNIQUE` constraint (`undid`). Nearly all FKs (`collections.uid`, `trades`, etc.)
   reference **`rwid`**, not `did`. → A did-less user row is already legal in the schema.
2. Migration `0003_linked_accounts` already added `google_sub` / `twitch_uid`
   (both `UNIQUE`) + display columns to `users`. → The provider→user resolution
   plumbing exists; only the "no row yet → create one" branch is missing.
3. The newweb JWT already carries `rwid` as a claim (`_issue_tokens`), and
   `AuthenticatedUser` already has an `rwid` field. → Moving the token subject from
   `did` to `rwid` is a small, contained change in the fork.
4. dndbattle's `platform_user_id` for platform `'twitch'` **is the same Twitch user id**
   that newweb stores in `users.twitch_uid`. → Portal↔arena account mapping is a value
   join; **zero schema changes in the dndbattle DB**.
5. dndbattle CLAUDE.md hard rule #4: "Users are keyed on (platform, platform_user_id).
   No account linking." Portal-level mapping does **not** merge arena users — it only
   resolves which arena user a portal session may act as. Still: get this **ratified by
   the design owner** before Phase 2 (it supersedes the spirit of rule #4 the same way
   the player website superseded §8's read-only deferral).
6. Bot leaderboard-style scans (`sqlhelper.py`: `where did > 0`, `group by did`) naturally
   exclude `did IS NULL` rows (NULL comparisons are false in PG). → Web-only users are
   invisible to the bot until they link Discord; nothing crashes.
7. The one FK on `did` (`fk_did ... ON DELETE SET NULL`) is unaffected — we never delete
   or rewrite existing `did` values.

---

## 3. Core identity decision

**Promote `users.rwid` to the canonical account id** (Option B below). Do **not** build a
separate identity service.

- **Option A — new identity DB/service** (`accounts` + `account_identities` +
  `account_links` tables): cleanest on paper, but it's a third store to operate, cross-DB
  FKs are impossible anyway, and every existing satchemon FK already points at `rwid`.
- **Option B — `rwid` is the account (chosen):** the satchemon `users` row *is* the
  account. Providers hang off it (`did`, `google_sub`, `twitch_uid` — all already
  present and unique). Login with any provider resolves or creates a row; JWT subject
  becomes `rwid`. dndbattle and dndadventure are reached by value-joins
  (`twitch_uid` → arena `(twitch, platform_user_id)`; `did` → `players.discord_id`).

Consequence: "sign in with Twitch, never touched Discord" = a `users` row with
`did = NULL`, `twitch_uid` set. Satchemon gameplay data for that row is empty until they
link Discord — which is correct, since Satchemon is played through the Discord bot.

---

## 4. Target architecture

```
                        ┌────────────────────────────────────────┐
 browser ── one origin ─┤  reverse proxy (Apache/nginx)          │
                        │   /            → unified SPA (static)  │
                        │   /api/…       → portal backend        │
                        │   /api/arena/… → dndbattle server      │
                        └────────────────────────────────────────┘
        portal backend (fork of newweb/backend)          dndbattle server (fork)
        - /auth: 3-provider login+create+link            - accepts portal JWT
        - satchemon + dnd progress APIs (as today)         (twitch_uid → arena user)
        - JWT subject = rwid                             - own DB, Store-only writes
        - satchemon PG + dndbot PG (ro)                    (hard rules intact)
```

- **One origin** → one JWT, one refresh cookie; no cross-domain SSO gymnastics.
- dndbattle server remains authoritative and in-process for arena writes (its rule #2);
  the portal never touches the arena DB. The proxy path-routes to it.
- Shared JWT verification: either share the HMAC secret between the two backends, or
  (better) switch the portal to an asymmetric alg (RS256/EdDSA) so the arena server only
  ever holds the public key. Arena keeps its own cookie auth as a fallback during
  transition.

### Frontend (new SPA, reusing newweb's stack: React + Vite + TS + Mantine)

```
/                    homepage — two big tiles: Satchemon | DnD Battle
/login               one login page, three provider buttons
/account             linked-accounts management (extend newweb's AccountPage)
/satchemon/*         ported newweb pages (users, cards, search, slideshow, me)
/satchemon/progress  ported dnd-adventure progress pages (already in newweb)
/dndbattle/*         ported dndbattle web pages (arena, roster, sheet, shop, HoF, boards)
```

Open decision (owner call, low stakes): does DnD Adventure get its own homepage tile or
live under Satchemon (both are the same Discord community)? Plan assumes under
Satchemon; promoting it to a third tile is a routing tweak.

---

## 5. Auth flows (portal backend fork)

### Login — any provider, account auto-created
```
exchange code → ProviderIdentity(provider, account_id, display)
→ resolve: did / google_sub / twitch_uid lookup (exists today)
→ if found:      mint JWT  sub=rwid, claims {did?, name, providers}
→ if not found:  INSERT users(name=display, did=NULL|discord id,
                              google_sub/twitch_uid as appropriate,
                              gp=0, pulls=0 …)   ← the new branch
                 mint JWT as above
```
Change from today: remove the "Discord always works even unregistered / others must be
pre-linked" asymmetry in `login_with_provider`; all three providers get the same
resolve-or-create treatment. Discord login for an existing bot user resolves the
existing row exactly as now.

### Linking — now includes Discord
Today `link_provider` refuses Discord ("primary account"). In the fork, Discord becomes
linkable like the others: set `did` on the current row. Unlinking rules: a row must
always keep ≥ 1 provider; unlink of the last one is refused.

### The conflict case (see §7)
Linking provider X fails with 409 when X already belongs to another row — the fork keeps
this behavior, with a much better error message and, later, a merge tool.

### Token compatibility
- New tokens: `sub = rwid` (string), `did` as optional claim, `ver: 2`.
- During rollout, the auth dependency accepts v1 tokens (`sub = did`) until the 7-day
  refresh window drains, resolving rwid on the fly. Then v1 support is removed.
- Ownership checks (`require_self`) move from did-comparison to rwid-comparison;
  public routes keyed on `{did}` (e.g. `/users/{did}`) keep working — did remains a
  stable public handle for bot-registered users.

---

## 6. The `did` problem & bot updates (forked copies, not in-place)

The satchemon bot **always has a did in hand** (it's driven by Discord interactions), so
did-less rows never break a bot command. Only two real hazards exist:

1. **Duplicate-human rows.** Web-first user (row A: `did NULL`, twitch linked) later
   plays the bot → bot's `createUser` inserts row B with their did. The human now has
   two rwids, and linking Discord to row A will 409 against row B.
   **Bot change (fork of `mooreDnD-Bot`):** `createUser` becomes an upsert —
   `INSERT … ON CONFLICT (did) DO NOTHING` (the `undid` unique constraint makes this
   safe) — plus a pre-check so the bot never assumes the insert created the row. This
   doesn't prevent the two-row case (the bot can't know row A exists), but it prevents
   crashes and double-inserts. The two-row case is handled by policy (§7), not the bot.
2. **Aggregate queries.** Already safe (§2.6): NULL-did rows drop out of `did`-keyed
   leaderboards. Optional cleanup in the fork: key leaderboards on `rwid` and only
   display did-linked users, making the behavior explicit instead of incidental.

**dndadventure bot: no changes.** It's keyed on `discord_id`, only ever driven from
Discord, and the portal reads its DB read-only exactly as newweb does today.

**Optional (Phase 4) `/link` command** for the satchemon bot: generates a one-time
short code; the user enters it on `/account` to link their Discord without OAuth. Nice
UX for bot-first users, not required for launch.

---

## 7. Account-merge policy (the genuinely hard part)

Conflict: human has row A (web-created, twitch/google) and row B (bot-created, did).

- **v1 (launch): refuse + guide.** Linking a provider that belongs to another row →
  409 with: "That Discord account already has a Satchemon profile. Sign in with
  Discord instead, then link Twitch/Google from there." The reverse link (sign in as B,
  link A's twitch) hits the same 409 only if A actually exists — and in that direction A
  is usually empty, so also offer: "…or contact an admin to merge."
  **Prevention beats cure:** the non-Discord signup screen states plainly — *"Play our
  Discord bot? Sign in with Discord first and link the rest afterwards."*
- **v2: admin merge tool** (portal backend endpoint + small admin page): in one
  transaction, re-point `collections.uid`, trades tables, sum `gp`/`pulls` from the
  loser row into the survivor, move provider columns, delete the loser. Satchemon DB
  only — arena needs no merge (its users were never duplicated; the twitch id is the
  key). Build only when a real duplicate exists; log 409s to measure need.

---

## 8. dndbattle integration detail

- **Read pages** (arena live view, leaderboards, HoF): already public JSON — the unified
  SPA calls them through the proxy from day one. No auth work at all.
- **Authed actions** (roster, rename, shop, retire): arena server fork
  (`unifiedweb/arena/`) gains one auth path: accept portal JWT → extract `twitch_uid`
  claim → resolve `users(platform='twitch', platform_user_id=twitch_uid)` → same
  session principal its cookie flow produces. Mutations still go through `Store`
  (rule #2 intact). Its own Twitch-OAuth cookie flow stays as fallback until cutover.
- **Portal users without linked Twitch** who open `/dndbattle/*`: read-only view + a
  "Link Twitch to play" prompt. Correct, because the game itself is played via Twitch.
- **Future YouTube arena platform caveat:** Google OAuth `sub` ≠ YouTube channel id. If
  the arena ever adds the youtube platform, the portal must additionally capture the
  YT channel id (extra scope) — flagged now so nobody assumes `google_sub` will join.
- **Design ratification needed** (owner): portal-JWT acceptance + the rule #4 note
  (§2.5) before this phase starts.

---

## 9. New project layout (nothing touches existing folders)

```
unifiedweb/
├── PLAN.md               ← this file (move it in when scaffolding)
├── frontend/             new SPA (start from a copy of newweb/frontend; add homepage,
│                         /satchemon + /dndbattle route trees, 3-provider login)
├── backend/              fork of newweb/backend (auth rework §5, rwid subject,
│                         alembic continues from 0003 — likely needs only a
│                         0004 adding users.created_at/created_via, optional)
├── arena/                fork of dndbattle (only server/webapi.py + websession grow
│                         the portal-JWT path; client/, engine untouched)
├── satchemon-bot/        fork of bot/mooreDnD-Bot (createUser upsert; later /link)
└── deploy/               proxy config (path routing per §4), systemd units, runbook
```

Forks are working copies for this effort; when a phase ships and is validated in prod,
its fork becomes the deployed version and the old folder is retired (archive, don't
delete, until Phase 5).

---

## 10. Phased rollout

| Phase | Deliverable | Risk |
|---|---|---|
| **0 — Shell** | Scaffold `unifiedweb/`; homepage SPA with two tiles linking to the *existing* sites; proxy config. Nothing behind it changes. | none |
| **1 — Identity** | Backend fork: resolve-or-create login for all 3 providers, Discord linkable, JWT sub=rwid with v1-token grace, better 409 messaging. Deploy behind the same origin; newweb frontend keeps working against it (API shape unchanged). | low — one new INSERT branch against prod `users`; test on a DB copy first (same caution as the sell feature) |
| **2 — Unified SPA** | Port newweb pages + dndbattle pages into `frontend/`; arena fork accepts portal JWT; single login everywhere. Old sites still up. | medium — needs arena owner ratification (§8) |
| **3 — Bot hardening** | `satchemon-bot` fork: createUser upsert + existence pre-check; deploy. | low |
| **4 — Polish** | `/link` bot command; admin merge tool if 409 logs justify it; leaderboards re-keyed on rwid. | low |
| **5 — Decommission** | Redirects from old URLs; retire newweb frontend + dndbattle standalone web; archive old folders. | low |

Each phase is independently shippable and reversible; Phase 1 is the only one that
mutates production data paths, and it's additive (new rows only, never rewriting
existing `did` values).

---

## 11. Open decisions for you

1. **DnD Adventure placement** — under Satchemon or third homepage tile? (Plan assumes
   under Satchemon.)
2. **JWT alg** — share HMAC secret between portal and arena (simplest) or move to
   asymmetric keys (arena holds public key only)? Plan recommends asymmetric.
3. **Arena owner ratification** — portal JWT acceptance & rule #4 clarification (§8).
4. **Merge tool timing** — v1 refuses conflicting links; is that acceptable at launch?
5. **Domain/origin** — plan assumes one hostname serving everything; confirm the prod
   hostname so cookie `path`/`secure` settings and OAuth redirect URIs can be registered
   per provider (each of the 3 OAuth apps needs the new redirect URI added).
