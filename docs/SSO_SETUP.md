# Google SSO Setup — Bank Portal & Customer Connect

The portal ships with full Google OAuth 2.0 flows (authlib) plus strict bank
domain validation. The code is ready; you must create the credentials in
Google Cloud Console — no code changes needed.

## Flow recap

| Route | Who | What happens |
|---|---|---|
| `/login/bank` | Bank employee | picks institution → Google login → email must match `<bank>.domain` in `frontend/banks.yaml` |
| `/login/customer` | Customer | picks bank (any metadata) → Google login (any email) → lands on `/customer` |
| `/auth/callback` | both | validates state/domain, opens the session |

## Step 1 — Create the OAuth client (5 min)

1. Open <https://console.cloud.google.com> → create a **new project**
   (e.g. `Credence-Portal`) — or reuse one.
2. **APIs & Services → OAuth consent screen**
   - User type: **External**.
   - App name: `Credence Pre-Delinquency Portal`, email, logo optional.
   - **Publishing status = Testing** → under **Test users** add the Google
     accounts that will log in (yours + demo users). A "Testing" app only
     lets whitelisted accounts in — perfect for the hackathon demo. To allow
     any Google account, click **Publish** (unverified banner warning is fine
     for <100 users).
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Web application**.
   - *Authorized JavaScript origins*: `http://127.0.0.1:5000` and your
     deployed origin (`https://credence-predelinquency.onrender.com`).
   - **Authorized redirect URIs** (must be exact, one per line):
     ```
     http://127.0.0.1:5000/auth/callback
     https://credence-predelinquency.onrender.com/auth/callback
     ```
4. Copy the **Client ID** and **Client secret**.

## Step 2 — Wire it up

Local dev — create `.env` from `.env.example`:

```bash
cp .env.example .env   # fill in the values from Step 1
python frontend/app.py
```

Deployed (Render): Service → Environment → add
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_REDIRECT_URI` (use the
https URI), then redeploy. `render.yaml` declares them as `sync: false`
placeholders. (Railway: same variables in the service settings.)

## Step 3 — Test

1. `http://127.0.0.1:5000/login/bank` → pick a bank → Google page → consent.
2. Bank-domain check: log in with an email that does NOT end in the selected
   bank's domain (e.g. any `@gmail.com` for HDFC) → you must see the
   "Unauthorized" red page; a matching domain succeeds.
3. `/login/customer` → any Google account → `/customer` (demo customer
   C000000).
4. Deployed: repeat on the https URL.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `redirect_uri_mismatch` | The URI in the console differs from `OAUTH_REDIRECT_URI` (lowercase, trailing slash, `http` vs `https`). Make them byte-identical; behind Render/`ProxyFix` must be `https`. |
| `Access blocked: ... has not completed the Google verification process` | Consent screen is Testing and the account isn't a Test user — add it, or Publish the app. |
| `invalid_grant` | Stale state — restart the flow from `/login/bank`; sometimes clear browser cookies for localhost. |
| Loops back to login forever | Old bug (fixed): Google returns no `userinfo` in the token; the app now fetches it explicitly. `git pull` / redeploy. |
| `GOOGLE_CLIENT_ID not set` page | Env vars missing — see Step 2. Password logins (`bank@bank.com/bank123`) keep working without SSO. |

## Security notes

- Bank emails are validated against their corporate domain from
  `frontend/banks.yaml` — add your bank's real domain there.
- Sessions are cookie-signed with `PREDELINQ_SECRET` — set a long random value.
- No tokens are persisted; the access token lives only inside the callback.
