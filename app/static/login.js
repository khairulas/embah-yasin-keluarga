import { signInWithGoogle, onAuthReady } from "./auth.js";

onAuthReady((user) => {
  if (user) {
    // already logged in — go home
    window.location.href = "/";
  }
});

document.getElementById("google-signin-btn").addEventListener("click", async () => {
  const errBox = document.getElementById("login-error");
  errBox.style.display = "none";
  try {
    await signInWithGoogle();
    window.location.href = "/";
  } catch (e) {
    errBox.textContent = "Log masuk gagal: " + (e.message || e);
    errBox.style.display = "block";
  }
});
