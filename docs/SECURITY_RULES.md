# Firestore Security Rules

## Architecture decision: lock down direct client writes

Since our Flask backend uses the **Admin SDK** (which bypasses security rules) to write
all data, we can lock down the Firestore database to **deny all client-side writes**
and only allow reads from authenticated Google users. This means:

- ✅ Frontend (browser) can read data with Firebase JS SDK after Google sign-in
- ✅ Backend (Flask + firebase-admin) can read/write everything
- ❌ Browser cannot write directly — must go through Flask
- ❌ Unauthenticated users see nothing

This is safer than allowing direct client writes because:
1. We can validate every write in Flask (e.g., normalize phone, check tahun_lahir is reasonable)
2. We can write audit logs atomically
3. We can enforce the "any family member can edit any profile" rule with proper logging
4. If a malicious user gets their own auth token, they still can't bypass our validation

## Rules file (`firestore.rules`)

Paste this into Firebase Console → Firestore → Rules.

```
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false;
    }
  }
}

```

## How to deploy these rules

1. Open Firebase Console → your project → Firestore Database → Rules tab
2. Paste the rules above
3. Click "Publish"
4. Test in the Rules Playground simulator before going live

## Why we don't allow direct writes from the JS frontend

It's tempting to let the frontend write directly to Firestore (skip Flask, save server costs).
But for a family tree system with audit requirements:

- The browser can't be trusted to honestly write its own audit log
- We need server-side validation (e.g., phone number format, no orphan persons)
- We want a single source of truth for business logic
- It makes the Flask app the natural place to add features later (PDF export, email
  notifications, family-tree visualization API)

## Backup recommendation

Set up a weekly Firestore export to Google Cloud Storage (free for small data):
Firebase Console → Firestore → Backups. Even on the free Spark plan, you can do
manual exports via gcloud CLI.
