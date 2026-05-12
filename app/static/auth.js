// auth.js — handles Firebase Google sign-in and exposes authedFetch()
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js";
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signOut,
  onAuthStateChanged
} from "https://www.gstatic.com/firebasejs/10.13.0/firebase-auth.js";

const app = initializeApp(window.FIREBASE_CONFIG);
export const auth = getAuth(app);

export async function signInWithGoogle() {
  const provider = new GoogleAuthProvider();
  return await signInWithPopup(auth, provider);
}

export async function signOutUser() {
  await signOut(auth);
  window.location.href = "/login";
}

/** Wrap fetch to attach the Firebase ID token as a bearer header. */
export async function authedFetch(url, options = {}) {
  const user = auth.currentUser;
  if (!user) {
    window.location.href = "/login";
    throw new Error("not authenticated");
  }
  const token = await user.getIdToken(/* forceRefresh */ false);
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
    "Authorization": `Bearer ${token}`,
  };
  const resp = await fetch(url, { ...options, headers });
  if (resp.status === 401) {
    window.location.href = "/login";
    throw new Error("session expired");
  }
  return resp;
}

/** Render the user nav (top-right) and call back when auth resolves. */
export function onAuthReady(callback) {
  onAuthStateChanged(auth, async (user) => {
    const nav = document.getElementById("user-nav");
    if (user) {
      // Notify backend so /users record is upserted
      try { await authedFetch("/api/me"); } catch (e) { /* ignored */ }

      if (nav) {
        nav.innerHTML = `
          <img src="${user.photoURL || ''}" alt="" width="28" height="28"
               class="rounded-circle me-2" referrerpolicy="no-referrer">
          <span class="me-3">${user.displayName || user.email}</span>
          <button id="signout-btn" class="btn btn-sm btn-outline-light">Log Keluar</button>
        `;
        document.getElementById("signout-btn").addEventListener("click", signOutUser);
      }
    } else {
      if (nav) {
        nav.innerHTML = `<a href="/login" class="btn btn-sm btn-outline-light">Log Masuk</a>`;
      }
    }
    callback(user);
  });
}
