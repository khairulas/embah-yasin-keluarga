# Deployment Guide — PythonAnywhere Free Tier

This guide walks through deploying the system to PythonAnywhere's free tier.

## ⚠️ Important free-tier constraint

PythonAnywhere's free tier restricts outbound internet to a whitelist of approved
domains. Google's `*.googleapis.com` IS on the whitelist, so `firebase-admin` works,
but any other external API call (e.g., to a non-Google geocoding service) will fail.

If you later need broader internet access, upgrade to the **Developer plan**
($10/month from Jan 2026).

## Step 1 — Create a Firebase project

1. Go to https://console.firebase.google.com
2. Add project → name it "embah-yasin-keluarga" (or similar)
3. Disable Google Analytics (optional, easier setup)
4. Once created:
   - **Build → Firestore Database** → Create database → Native mode →
     **Region: asia-southeast1 (Singapore)** → Production mode
   - **Build → Authentication** → Get started →
     **Sign-in method → Google** → Enable → Save
5. Add your project's authorized domain:
   - **Authentication → Settings → Authorized domains** →
     Add `<yourname>.pythonanywhere.com`

## Step 2 — Get Firebase credentials

### Service account key (for backend Admin SDK)
1. **Project settings (gear icon) → Service accounts → Generate new private key**
2. Save the downloaded JSON as `serviceAccountKey.json`
3. Keep this file secret — it has full database access

### Web client config (for frontend Google sign-in)
1. **Project settings → General → Your apps → Add app → Web (</> icon)**
2. Register app, copy the `firebaseConfig` object — you need:
   - `apiKey`
   - `authDomain`
   - `projectId`

## Step 3 — Deploy Firestore security rules

1. Open **Firestore Database → Rules** tab
2. Paste the content of `docs/SECURITY_RULES.md`
3. Click **Publish**

## Step 4 — Set up PythonAnywhere

1. Sign up at https://www.pythonanywhere.com (free tier)
2. Open a **Bash console** and clone your repo (or upload files):
   ```bash
   cd ~
   git clone https://github.com/yourname/embah_yasin.git
   cd embah_yasin
   ```
3. Create a virtual environment:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. Upload `serviceAccountKey.json` via the **Files** tab to `~/embah_yasin/`
5. Create `.env` from the template:
   ```bash
   cp .env.example .env
   nano .env   # fill in real values
   ```

## Step 5 — Run the data import

```bash
cd ~/embah_yasin
source venv/bin/activate
python migrations/import_excel.py path/to/Ahli_Keluarga_Embah_Yasin_Cleaned.xlsx --dry-run
# review output, then run for real:
python migrations/import_excel.py path/to/Ahli_Keluarga_Embah_Yasin_Cleaned.xlsx
```

## Step 6 — Configure the web app

1. Go to PythonAnywhere **Web** tab → **Add a new web app**
2. Choose **Manual configuration** → Python 3.11
3. Once created, edit these settings:

   **Source code**: `/home/<yourname>/embah_yasin`

   **Working directory**: `/home/<yourname>/embah_yasin`

   **WSGI configuration file**: edit it and replace the entire contents with:
   ```python
   import os, sys
   from dotenv import load_dotenv

   project_root = "/home/<yourname>/embah_yasin"
   if project_root not in sys.path:
       sys.path.insert(0, project_root)
   load_dotenv(os.path.join(project_root, ".env"))

   from app import app as application
   ```

   **Virtualenv**: `/home/<yourname>/embah_yasin/venv`

   **Static files**: URL `/static/` → Path `/home/<yourname>/embah_yasin/app/static`

4. Click the **Reload** button (green button at top)

## Step 7 — Test

- Visit `https://<yourname>.pythonanywhere.com/login`
- Sign in with a Google account
- That account is now in `/users/{uid}` with role `member`
- To make yourself admin, open Firebase Console → Firestore → `users` →
  find your uid → set `role: "admin"`

## Step 8 — Make yourself the first admin

After your first sign-in, manually promote your account:

1. Firebase Console → Firestore → `users` collection
2. Find document with your email
3. Edit field `role` from `member` to `admin`

Now you can claim profiles, edit anything, and view full audit logs.

## Free tier limits to watch

- **CPU**: 100 CPU-seconds/day. The web app itself doesn't count, but background
  scripts (like the import) do. The Excel import takes ~30s, so it's fine.
- **Storage**: 512 MB. Project + venv ≈ 200 MB. Plenty of room.
- **Web app**: 1 worker, sufficient for a family of <500 people.
- **Outbound**: only `*.googleapis.com` and a few others. Firebase works.
- **Always-on tasks**: not available on free tier — but we don't need them.

## Routine maintenance

- **Renew the web app every 3 months**: PythonAnywhere asks you to click a button
  to keep the free web app alive. Set a calendar reminder.
- **Backup Firestore weekly**: Firebase Console → Firestore → Backups (or use
  `gcloud firestore export`).
- **Monitor usage**: Firebase Console → Usage. You should see ~0% of free quota.

## Troubleshooting

**"Unauthorized" on every API call**
- Token isn't being sent. Check browser devtools → Network → Request headers should
  include `Authorization: Bearer ey...`
- Sign out and sign back in to refresh the token.

**"Firestore initialization failed"**
- `serviceAccountKey.json` path wrong. Check `.env` and that the file exists.
- Service account doesn't have Firestore permission. In Google Cloud Console →
  IAM, ensure the service account has role "Cloud Datastore User" or higher.

**Google sign-in popup blocked**
- Some browsers block popups. The user must allow popups for your site, OR you
  can switch from `signInWithPopup` to `signInWithRedirect` in `auth.js`.

**"This domain is not authorized"**
- Firebase Console → Authentication → Settings → Authorized domains —
  add `<yourname>.pythonanywhere.com`.
