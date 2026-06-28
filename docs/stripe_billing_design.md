# Rook — Stripe Subscription Billing: Design / Scoping Pass

> **Status: design only. No billing code in this PR.** Deliverable is this doc.
> The headline finding: **the entitlement + gating layer already exists and is
> wired for exactly this.** Stripe is the missing *billing* half — checkout, a
> webhook to flip tier, and attaching the existing guards to routes. There is
> almost nothing to invent on the entitlement side; the work is plumbing Stripe
> into a model that was built expecting it.

---

## Decisions needed from Stephen (read this first)

1. **Entitlement source of truth → recommend the Rook DB (`users.tier`).** It is
   *already* the implemented store (`backend/models/user.py`), already loaded on
   every request (`get_current_user`), and the gate code already reads it. Stripe
   is the billing system-of-record and syncs *into* the DB via webhook; Clerk stays
   identity-only. **Need: confirm this** (full tradeoffs in §3).

2. **Stale tier doc conflict.** Two tier definitions exist and disagree:
   - **Canonical (implemented):** `backend/models/user.py` → `TIER_LIMITS` =
     `intro / standard / pro`, no free tier. Matches `CLAUDE.md` → "SaaS Pricing
     (Stages 25-30)".
   - **Stale:** `docs/stages/stage-25-saas-foundation.md:261-263` → `users.tier
     DEFAULT 'free'`, comment `free | starter | pro | league`, `credits DEFAULT 50`.
     This is an early-foundation draft that was superseded by the implementation.
   **Need: confirm `user.py`/CLAUDE.md is canonical, and let me delete/annotate the
   stale stage-25 block in a separate cleanup** (out of scope for this docs PR).

3. **`/season` billing semantics.** Pricing is quoted as e.g. "$5/month **or**
   $15/season" (`CLAUDE.md`). Is `/season` an **annual recurring** subscription, a
   **one-time seasonal pass** (set tier until a fixed expiry, no auto-renew), or
   recurring-annual-that-renews? This is the single biggest Stripe-object-model
   fork (recurring Price vs one-time Price + manual expiry job). See §6.

4. **Cancellation behavior** (`customer.subscription.deleted`). On cancel/expiry,
   downgrade to **`intro`** (keep the account, lose paid features) or a distinct
   `canceled`/none state? Credits "accumulate, never reset" (`user.py:112`) — confirm
   they survive a downgrade.

5. **Payment-failed grace** (`invoice.payment_failed`). Immediate downgrade, or a
   `past_due` grace window (Stripe's smart retries, typically ~2-3 wks) before
   dropping tier? Recommend: honor Stripe's retry/`past_due` and only downgrade on
   the terminal `subscription.deleted`.

6. **Monthly credit grant mechanic.** `TIER_LIMITS[*]["credits_monthly"]` (standard
   20, pro 50) should be **added** to the balance on each successful renewal
   (`invoice.payment_succeeded`, `billing_reason=subscription_cycle`). Confirm this
   is the intended renewal mechanic (vs. a cron). The signup bonus
   (`credits_signup_bonus`) is the one-time grant on first purchase.

7. **(Optional) Clerk metadata mirror.** Mirror `tier` into Clerk
   `publicMetadata` so the React app can read it straight off the Clerk session
   without an `/account/me` call? Recommend **no for the security boundary** (the DB
   is), **optionally yes as a UX convenience**. Default: skip it; the SPA already
   fetches `/account/me`.

---

## 1. Tier definition — the source of truth

**Canonical, machine-readable:** `backend/models/user.py:25-77` —
`TIER_LIMITS`, `CREDIT_COSTS`, `CREDIT_PACKS` (the file's own docstring: *"single
source of truth for subscription rules. No other file should define these values."*).
**Prose mirror:** `CLAUDE.md` → "SaaS Pricing (Stages 25-30)".

| Tier | Price | Signup credits | Monthly credits | Leagues | live_draft | trade_analyzer | trade_finder | waiver_wire |
|---|---|---|---|---|---|---|---|---|
| **intro** | $5/mo · $15/season | 25 (one-time) | 0 | 1 | ✗ | ✗ | ✗ | ✗ |
| **standard** | $9/mo · $29/season | 75 | 20 | 2 | ✓ | ✓ | ✗ | ✓ |
| **pro** | $18/mo · $49/season | 200 | 50 | unlimited | ✓ | ✓ | ✓ | ✓ |

`injury_monitoring` + projections / draft board / news / league sync / draft history
are **free on all tiers** (no gate). **No free tier** — `intro` is the floor.
Credit costs (feature unlocked *then* credits charged): `trade_analysis`=10,
`trade_finder`=20, `waiver_wire`=8 (`user.py:64-70`). Credit packs (one-time):
$5→75, $10→175, $25→500 (`user.py:73-77`). **Live draft is a tier entitlement, not a
credit cost.**

---

## 2. Auth + identity wiring (how it works today)

**Request-auth path** (`backend/core/dependencies.py`):
- `_bearer` → `get_current_user_id` (`:175`): production verifies the **Clerk JWT**
  (`_verify_clerk_jwt`, `:99` — RS256, JWKS fetched + cached). Returns
  `{user_id: <Clerk sub>, email}`. Dev fallback: `X-User-Id` header (`:190-195`).
  Clerk's default JWT has no email → fetched from the Clerk Backend API and cached
  (`_fetch_clerk_user_email`, `:141`).
- `get_current_user` (`:212`): maps `user_id` → DB `User` via
  `UserService.get_or_create(external_id=<Clerk sub>, email)` — **creates the row on
  first request**. So every protected route already has the full `User` (incl. `tier`
  + `credits_remaining`) in hand.

**User model** (`backend/models/user.py:84-140`): `external_id` (Clerk id, unique),
`email`, `tier` (default `"intro"`), `credits_remaining` (default 0, *accumulate,
never reset*), `draft_token` (extension), **`stripe_customer_id`**, **`stripe_subscription_id`**
(both already present, nullable, unique), `deleted_at` (soft delete).

**Clerk custom metadata:** **not used for entitlement today.** The JWT is read only
for `sub` (+ email). Clerk also drives the user lifecycle via a webhook
(`backend/routers/webhooks.py` → `/webhooks/clerk`: `user.created` upsert,
`user.deleted` soft-delete; svix signature verification).

**Identity flow:** `Clerk (sub) → users.external_id → users.tier`. Entitlement
already rides along with the per-request user load — **no extra query, no Stripe
call.**

---

## 3. Entitlement source of truth — the load-bearing decision

Three candidates, evaluated against the existing `Clerk → Rook DB` flow:

| Option | Hot-path read (every gated request) | Pros | Cons |
|---|---|---|---|
| **A. Rook DB `users.tier` (RECOMMEND)** | Already loaded by `get_current_user` — **zero extra cost** | Already implemented + read by the gates; transactional with credits; queryable/admin-able; no third-party on the hot path | Must be kept in sync with Stripe (webhook) — but that's true of any option |
| **B. Clerk `publicMetadata.tier`** | In the JWT claims (no DB hit) if put there | Frontend can read tier off the session | Adds a *second* sync target (Stripe→Clerk→read); JWT is cached/short-lived so changes lag until refresh; not transactional with credits; re-plumbs the gate code that already reads the DB |
| **C. Stripe (query subscription live)** | **Stripe API round-trip per request** | Always "true" | Latency + rate limits on the hot path — **disqualifying**; Stripe is the billing record, not a per-request store |

**Recommendation: A.** `users.tier` is authoritative for *entitlement*; **Stripe is
authoritative for *billing state*** and is the upstream that mutates `users.tier`
via webhook. Clerk stays **identity only**.

**Read vs. reconcile split:**
- **Hot path (read):** `users.tier` (+ `credits_remaining`) — already in the
  `User` object every gated request has. The gate calls
  `FeatureService.check_feature_access(user, feature)` which reads `TIER_LIMITS`
  **in memory** (`backend/services/feature_service.py`). **No Stripe API call ever
  on a request.**
- **Reconcile (webhook, async):** Stripe subscription events →
  `UserService.upgrade_tier` / `apply_signup_bonus` (`backend/services/user_service.py:63-104`,
  whose docstrings already say *"Called by Stripe webhook"*) → write `users.tier`,
  `stripe_*`, credits. The DB is reconciled to Stripe out-of-band; reads never wait
  on it.
- **Keeping the others in sync:** Clerk needs nothing (identity only). If we ever
  add option B as a UX mirror, the same webhook would also push `tier` to Clerk
  `publicMetadata` — strictly secondary, never the gate.

---

## 4. Webhook lifecycle surface

New endpoint **`/webhooks/stripe`** — **root-mounted, NOT under `/api`**, mirroring
the Clerk webhook (`backend/main.py:94`; the Stripe URL Stripe calls is
`https://<host>/webhooks/stripe`). Pattern cloned from `_verify_clerk_signature`
(`webhooks.py:26`), swapping svix for `stripe.Webhook.construct_event(body, sig,
STRIPE_WEBHOOK_SECRET)`.

| Stripe event | Drives (in `users` / via `UserService`) |
|---|---|
| `checkout.session.completed` | First purchase: set `stripe_customer_id` + `stripe_subscription_id`; `upgrade_tier(<purchased>)`; one-time `apply_signup_bonus`. (Use this **or** `subscription.created` as the authoritative "started" signal — not both.) |
| `customer.subscription.created` | Subscription exists. Map `price_id → tier`; set tier if not already set by checkout. |
| `customer.subscription.updated` | Tier change (upgrade/downgrade via price swap) → `upgrade_tier(<new>)`; status change (`active`/`past_due`/`canceled@period_end`) → reflect status. |
| `customer.subscription.deleted` | Subscription ended → downgrade per **Decision #4** (recommend → `intro`); clear `stripe_subscription_id`. |
| `invoice.payment_succeeded` (`billing_reason=subscription_cycle`) | Renewal → **add** `TIER_LIMITS[tier]["credits_monthly"]` to balance (Decision #6). First invoice (`subscription_create`) is the signup, not a monthly grant. |
| `invoice.payment_failed` | Mark `past_due`; **do not** downgrade yet (Decision #5) — let Stripe retry; terminal failure arrives as `subscription.deleted`. |

**Requirements (call out explicitly):**
- **Signature verification** — reject unverified payloads (400), same posture as the
  Clerk handler (prod requires the secret; dev may parse unverified).
- **Idempotency** — Stripe retries and may double-deliver. Dedup by `event.id`
  (e.g. a `processed_stripe_events(event_id PK, seen_at)` table, insert-or-skip) **and**
  make each handler idempotent (set-tier is naturally idempotent; **credit grants are
  NOT** — they must be guarded by the event-id dedup so a redelivered
  `invoice.payment_succeeded` can't double-credit).

**Test strategy (no staging backend; prod deploys from `main`):**
- **Local first:** `stripe listen --forward-to localhost:8000/webhooks/stripe` +
  `stripe trigger checkout.session.completed` (etc.) against **test-mode** keys.
  Drives the full state machine without touching prod.
- **Post-release smoke:** after releasing to `main`, point a **test-mode** Stripe
  webhook endpoint at the live URL and replay test events; verify `users.tier`
  transitions. Keep test-mode and live-mode endpoints/secrets separate so test
  traffic can't mutate real entitlements. (There is no separate staging service —
  this two-step is the substitute.)

---

## 5. Gate enforcement points

**Enforcement is backend; the pattern already exists — do not scatter checks.**
`backend/core/dependencies.py:281-331`:
- `require_feature(feature)` → `FeatureService.check_feature_access` → 4xx
  `FeatureNotAvailableError` if `TIER_LIMITS[user.tier][feature]` is false.
- `require_credits(action)` → checks feature access **then** `CreditService.deduct`
  (402 `InsufficientCreditsError`).

**These guards are built but NOT yet attached to routes** — only `NOTE` placeholders
in `draft.py:17,545`. Mapping to attach next pass:

| Surface | Tier rule | Enforcement |
|---|---|---|
| `POST /api/draft/start` (live draft) | standard+ (`live_draft`) | `Depends(require_feature("live_draft"))` — the noted-but-unattached gate |
| Trade analyze (router unbuilt) | standard+, 10 cr | `Depends(require_credits("trade_analysis"))` |
| Trade finder (unbuilt) | **pro only**, 20 cr | `Depends(require_credits("trade_finder"))` |
| Waiver wire (unbuilt) | standard+, 8 cr | `Depends(require_credits("waiver_wire"))` |
| `POST /api/account/leagues` | intro 1 / std 2 / pro ∞ | **already gated** via `FeatureService.can_add_league` (`account.py`) |
| projections / draftboard / news / sync / injury | all tiers | no gate |

**Frontend (UX only, not the security boundary):** `frontend/src/pages/Pricing.jsx`,
`components/landing/PricingTable.jsx`, `pages/Account.jsx` (reads `/account/me` →
`tier` + `tier_limits` + `credits`). Needs: upgrade CTAs wired to checkout,
locked-feature affordances, and 402/feature-error → upgrade-prompt handling. None of
these enforce anything — the backend dependency does.

---

## 6. Stripe object model

**Products/Prices (assuming Decision #3 = recurring):** model **3 Products**
(`Rook Intro`, `Rook Standard`, `Rook Pro`), each with the recurring Price(s) it
sells. Monthly is `recurring{interval:month}`. `/season` is either
`recurring{interval:year}` (auto-renews) **or** a one-time Price + an expiry job
(no renewal) — **blocked on Decision #3**. So tentatively **3 tiers × {monthly,
season}** Prices. **Credit packs** are **one-time** Prices (`small/medium/large`),
sold via a separate one-time Checkout (mode=`payment`), not subscriptions.

- **`price_id → tier` mapping lives in code/config**, not hardcoded in handlers, so
  the webhook resolves a subscription's price to a tier.
- **Test vs live mode:** fully separate object graphs and keys — `sk_test_*` /
  `whsec_*`(test) vs `sk_live_*` / `whsec_*`(live), and **different `price_id`s per
  mode**. Selected by environment (the `STRIPE_*` env vars differ per Railway
  environment); no mode branching in code beyond reading the env.

**Secrets / key handling** — same pattern as Clerk (`backend/config.py`:
`pydantic-settings` `BaseSettings` from env; `.env.example` documents names; real
values are **Railway env vars**, never in the repo). Add:
- `STRIPE_SECRET_KEY` (server SDK)
- `STRIPE_WEBHOOK_SECRET` (signature verification)
- `STRIPE_PRICE_*` (the per-tier/per-period + per-pack price ids)
- `VITE_STRIPE_PUBLISHABLE_KEY` (frontend, if using Stripe.js; with Checkout
  redirect this may be unnecessary)

The `stripe` Python SDK is **not yet a dependency** — adding it is part of the next
pass, not this doc.

---

## 7. Proposed implementation sequence (next pass — not now)

1. **Config + SDK:** add `stripe` dep; `STRIPE_*` settings in `config.py` +
   `.env.example`; create test-mode Products/Prices; record price ids.
2. **Billing router** (`/api/billing`): `POST /checkout` (create a Checkout Session
   for a tier price; ensure/attach `stripe_customer_id`), `POST /portal` (Customer
   Portal session for manage/cancel/payment-method).
3. **Stripe webhook** (`/webhooks/stripe`, root-mounted): signature-verified,
   idempotent (event-id dedup table), driving the §4 transitions through the
   **existing** `UserService.upgrade_tier` / `apply_signup_bonus` + a monthly-credit
   grant.
4. **Attach the gates:** `require_feature("live_draft")` on `/draft/start`;
   `require_credits(...)` on trade/waiver routes as they're built.
5. **Frontend:** Pricing CTAs → `/billing/checkout`; Account → `/billing/portal`;
   global 402/feature-error → upgrade prompt; locked-feature affordances.
6. **Tests:** webhook signature + idempotency + each state transition (mocked
   Stripe events); gate dependencies (allow/deny per tier); checkout/portal session
   creation (mocked SDK). Plus the §4 local Stripe-CLI flow.
7. **Cleanup (separate):** resolve the stale stage-25 tier block (Decision #2).

---

## Appendix — files cited

- Tiers/credits (source of truth): `backend/models/user.py`
- Tier logic / gates: `backend/services/feature_service.py`,
  `backend/services/user_service.py`, `backend/services/credit_service.py`
- Gate dependencies: `backend/core/dependencies.py:281-331`; auth path `:99-232`
- Webhook template + mount: `backend/routers/webhooks.py`, `backend/main.py:89-94`
- Account/entitlement read API: `backend/routers/account.py`
- Config / secrets: `backend/config.py`, `.env.example`
- Frontend surfaces: `frontend/src/pages/Pricing.jsx`,
  `frontend/src/pages/Account.jsx`, `frontend/src/components/landing/PricingTable.jsx`
- Stale tier doc: `docs/stages/stage-25-saas-foundation.md:251-322`
- Prose pricing: `CLAUDE.md` → "SaaS Pricing (Stages 25-30)"
