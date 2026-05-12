import { onAuthReady, authedFetch } from "./auth.js";

const householdId = window.HOUSEHOLD_ID;

onAuthReady(async (user) => {
  if (!user) { window.location.href = "/login"; return; }
  await load();
});

async function load() {
  try {
    const resp = await authedFetch(`/api/households/${householdId}`);
    const { household } = await resp.json();
    if (!household) {
      document.getElementById("loading").innerHTML =
        '<div class="alert alert-warning">Tidak dijumpai.</div>';
      return;
    }

    const ketua = (household.members || []).find(m => m.role === "ketua");
    document.getElementById("household-title").textContent =
      "Keluarga " + (ketua?.full_name_cached || household.household_id);
    document.getElementById("registered-by").textContent =
      household.registered_by_email || "—";
    const reg = household.registered_at?._seconds
      ? new Date(household.registered_at._seconds * 1000).toLocaleString("ms-MY")
      : "—";
    document.getElementById("registered-at").textContent = reg;

    const list = document.getElementById("members-list");
    list.innerHTML = (household.members || []).map(m => `
      <a href="/profile/${m.person_id}" class="list-group-item list-group-item-action">
        <div class="d-flex justify-content-between">
          <div>${escapeHtml(m.full_name_cached)}</div>
          <span class="badge bg-secondary role-badge">${m.role}</span>
        </div>
      </a>
    `).join("") || '<p class="text-muted">Tiada ahli.</p>';

    document.getElementById("loading").style.display = "none";
    document.getElementById("household-content").style.display = "block";
  } catch (e) {
    document.getElementById("loading").innerHTML =
      `<div class="alert alert-danger">Ralat: ${e.message}</div>`;
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}
