# Google SSO Setup — Bank Portal & Customer Connect

The portal ships with full Google OAuth 2.0 flows (authlib) plus strict bank
domain validation. Password logins (`bank@bank.com/bank123`) always work —
SSO is optional and additive.

## Fast-check your config

Start the portal and open **http://127.0.0.1:5000/ssostatus** — it shows the
fingerprinted client id, whether the secret is set, and the **exact redirect
URI you must register**. Local dev default:
`http://127.0.0.1:5000/auth/callback`.

## Step 1 — Google Cloud Console (you already created client `Nandu`; finish it)

1. `console.cloud.google.com` → project **Credence** → **APIs & Services →
   OAuth consent screen**
   - User type: **External**. App name: anything (e.g. `Nandu`).
   - **Publishing status: Testing** → **Test users** → **Add users** → add
     **your own Google email** (and each demo account). A Testing app ONLY
     lets whitelisted accounts in — until you add yourself, Google shows
     “Access blocked … has not completed verification”.
2. **APIs & Services → Credentials → Clients → `Nandu` (Web application) →
   ✏️ Edit**
   - **Authorized redirect URIs** — add BOTH, exactly as written:
     ```
     http://127.0.0.1:5000/auth/callback
     https://credence-predelinquency.onrender.com/auth/callback
     ```
     (Replace the second with your real deployed host if different. No
     trailing slashes, http vs https matters.)
   - **Authorized JavaScript origins**: `http://127.0.0.1:5000` and
     `https://credence-predelinquency.onrender.com` (optional; not required
     for the server flow but harmless).
   - Save.
3. **Client secret** — if you still have the value/JSON from creation:
   great. If you closed the popup without saving it, it cannot be re-shown —
   create a **new** client (Credentials → Create client → Web application →
   paste the same redirect URIs → Save) and copy the secret this time, then
   delete `Nandu`.

## Step 2 — Wire it up

Local — edit `.env` (already exists in the repo, git-ignored):

```
GOOGLE_CLIENT_ID=989893764352-xxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
OAUTH_REDIRECT_URI=http://127.0.0.1:5000/auth/callback
```

then **restart** the portal (`Ctrl-C`, then `make portal`) — `.env` is read
at startup.

Deployed (Render): service → **Environment** → add
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`OAUTH_REDIRECT_URI=https://credence-predelinquency.onrender.com/auth/callback`
→ redeploy. (`render.yaml` declares these as `sync: false` placeholders.)

## Step 3 — Test

1. `http://127.0.0.1:5000/ssostatus` → `configured: true`.
2. `http://127.0.0.1:5000/login/bank` → pick a bank → Google page → consent.
3. Bank-domain check: an email that does NOT end in the selected bank's
   domain (see `frontend/banks.yaml`) gets the red **Unauthorized** page;
   a matching domain lands in the portal.
4. `/login/customer` → any Google account → `/customer` (C000000).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `redirect_uri_mismatch` | The console URI differs from `OAUTH_REDIRECT_URI` (case, trailing slash, `http` vs `https`). Compare with `/ssostatus`. On Render it must be `https://…onrender.com/auth/callback`. |
| `Access blocked: … has not completed the Google verification process` | Consent screen is Testing and your account isn't a Test user — add it, or Publish the app. |
| `invalid_grant` | Stale authorization — retry from `/login/bank`; clear localhost cookies if it persists. |
| SSO loops back to login | Fixed in code (userinfo is fetched explicitly). Make sure you have the latest `main`. |
| `Google SSO is not configured` page | Env vars missing/empty — `/ssostatus` shows exactly what's loaded. |
