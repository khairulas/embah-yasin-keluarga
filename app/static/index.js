import { onAuthReady, authedFetch } from "./auth.js";

const householdsList = document.getElementById("households-list");
const searchResults = document.getElementById("search-results");
const searchBox = document.getElementById("search-box");
const loginPrompt = document.getElementById("login-prompt");

onAuthReady(async (user) => {
  if (!user) {
    loginPrompt.style.display = "block";
    return;
  }
  await loadHouseholds();
});

async function loadHouseholds() {
  householdsList.innerHTML = '<div class="col-12 text-muted">Memuatkan...</div>';
  try {
    const resp = await authedFetch("/api/households");
    const { households } = await resp.json();
    if (!households.length) {
      householdsList.innerHTML = '<div class="col-12 text-muted">Tiada keluarga berdaftar.</div>';
      return;
    }
    householdsList.innerHTML = households.map(h => {
      const ketua = (h.members || []).find(m => m.role === "ketua") || h.members?.[0];
      const ketuaName = ketua?.full_name_cached || "(Tiada ketua)";
      const memberCount = (h.members || []).length;
      return `
        <div class="col-md-6 col-lg-4">
          <a href="/household/${h.household_id}" class="text-decoration-none">
            <div class="card person-card h-100">
              <div class="card-body">
                <h5 class="card-title text-dark">${escapeHtml(ketuaName)}</h5>
                <p class="card-text text-muted small mb-0">
                  ${memberCount} ahli keluarga
                </p>
              </div>
            </div>
          </a>
        </div>
      `;
    }).join("");
  } catch (e) {
    householdsList.innerHTML = `<div class="col-12 text-danger">Ralat: ${e.message}</div>`;
  }
}

let searchDebounce;
searchBox.addEventListener("input", (e) => {
  clearTimeout(searchDebounce);
  const q = e.target.value.trim();
  if (!q) {
    searchResults.style.display = "none";
    return;
  }
  searchDebounce = setTimeout(() => doSearch(q), 250);
});

async function doSearch(q) {
  try {
    const resp = await authedFetch(`/api/persons?q=${encodeURIComponent(q)}`);
    const json = await resp.json();
    const persons = json.persons;
    searchResults.style.display = "flex";
    if (!persons || !persons.length) {
      searchResults.innerHTML = '<div class="col-12 text-muted">Tiada hasil carian.</div>';
      return;
    }
    searchResults.innerHTML = `<div class="col-12"><h5>Hasil carian (${persons.length})</h5></div>`
      + persons.map(p => `
        <div class="col-md-6 col-lg-4">
          <a href="/profile/${p.person_id}" class="text-decoration-none">
            <div class="card person-card h-100">
              <div class="card-body">
                <h6 class="card-title text-dark mb-1">${escapeHtml(p.full_name)}</h6>
                <small class="text-muted">
                  ${p.jantina === "L" ? "Lelaki" : p.jantina === "P" ? "Perempuan" : "—"}
                  ${p.tahun_lahir ? "· Lahir " + p.tahun_lahir : ""}
                </small>
              </div>
            </div>
          </a>
        </div>
      `).join("");
  } catch (e) {
    searchResults.style.display = "flex";
    searchResults.innerHTML = `<div class="col-12 text-danger">Ralat carian: ${escapeHtml(e.message)}</div>`;
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}
