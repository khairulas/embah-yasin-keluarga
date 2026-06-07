import { onAuthReady, authedFetch } from "./auth.js";

const householdsList = document.getElementById("households-list");
const searchResults = document.getElementById("search-results");
const searchBox = document.getElementById("search-box");
const loginPrompt = document.getElementById("login-prompt");
const homeContent = document.getElementById("home-content");
const founderSection = document.getElementById("founder-section");
const toggleBtn = document.getElementById("toggle-households");

let householdsLoaded = false;

onAuthReady(async (user) => {
  if (!user) {
    loginPrompt.style.display = "block";
    homeContent.style.display = "none";
    return;
  }
  await loadHome();
});

// ---- Home: founder + immediate family (single /api/home read) ----
async function loadHome() {
  founderSection.innerHTML = '<div class="text-muted">Memuatkan...</div>';
  try {
    const resp = await authedFetch("/api/home");
    const data = await resp.json();
    if (!data.founder) {
      // Graceful fallback: no founder configured/found — just show the grid open.
      founderSection.innerHTML = "";
      await loadHouseholds();
      householdsList.style.display = "flex";
      toggleBtn.style.display = "none";
      return;
    }
    renderFounder(data);
  } catch (e) {
    founderSection.innerHTML = `<div class="text-danger">Ralat: ${escapeHtml(e.message)}</div>`;
  }
}

function personCard(p, { focus = false, spouse = false } = {}) {
  const cls = ["card", "person-card", "h-100"];
  const style = [];
  if (spouse) style.push("background:#fff8e7;");
  if (focus) style.push("border-color:#0d6efd; border-width:2px;");
  const jantina = p.gender === "L" ? "Lelaki" : p.gender === "P" ? "Perempuan" : "";
  const meta = [jantina, p.birth_year ? "Lahir " + p.birth_year : "",
                p.is_deceased ? "Allahyarham/ah" : ""].filter(Boolean).join(" · ");
  return `
    <a href="/profile/${p.id}" class="text-decoration-none">
      <div class="${cls.join(" ")}" style="${style.join("")}">
        <div class="card-body">
          <h6 class="card-title text-dark mb-1">${escapeHtml(p.name)}</h6>
          <small class="text-muted">${escapeHtml(meta) || "&nbsp;"}</small>
        </div>
      </div>
    </a>`;
}

function renderFounder(data) {
  const { founder, spouses = [], children = [] } = data;
  let html = '<div class="card mb-3"><div class="card-body">';
  html += '<h4 class="mb-3">Pengasas Keluarga</h4>';

  // Founder + spouses row
  html += '<div class="row g-3 mb-3">';
  html += `<div class="col-md-4 col-lg-3">${personCard(founder, { focus: true })}</div>`;
  spouses.forEach(s => {
    html += `<div class="col-md-4 col-lg-3">${personCard(s, { spouse: true })}</div>`;
  });
  html += "</div>";

  // Children
  if (children.length) {
    html += `<h6 class="text-muted mb-2">Anak-anak (${children.length})</h6>`;
    html += '<div class="row g-2">';
    children.forEach(c => {
      html += `<div class="col-md-3 col-lg-2">${personCard(c)}</div>`;
    });
    html += "</div>";
  } else {
    html += '<p class="text-muted mb-0">Belum ada anak dihubungkan. Tambah melalui profil beliau.</p>';
  }

  html += "</div></div>";
  html += `<a href="/tree/${founder.id}" class="btn btn-outline-primary btn-sm">Lihat Pohon Keluarga penuh →</a>`;
  founderSection.innerHTML = html;
}

// ---- Households: lazy-loaded only when toggled ----
toggleBtn.addEventListener("click", async () => {
  if (householdsList.style.display === "none") {
    if (!householdsLoaded) {
      await loadHouseholds();
      householdsLoaded = true;
    }
    householdsList.style.display = "flex";
    toggleBtn.textContent = "Sembunyikan senarai";
  } else {
    householdsList.style.display = "none";
    toggleBtn.textContent = "Lihat semua keluarga";
  }
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
                <p class="card-text text-muted small mb-0">${memberCount} ahli keluarga</p>
              </div>
            </div>
          </a>
        </div>`;
    }).join("");
  } catch (e) {
    householdsList.innerHTML = `<div class="col-12 text-danger">Ralat: ${escapeHtml(e.message)}</div>`;
  }
}

// ---- Search (unchanged behaviour; hides home-content while active) ----
let searchDebounce;
searchBox.addEventListener("input", (e) => {
  clearTimeout(searchDebounce);
  const q = e.target.value.trim();
  if (!q) {
    searchResults.style.display = "none";
    homeContent.style.display = "block";
    return;
  }
  homeContent.style.display = "none";
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
        </div>`).join("");
  } catch (e) {
    searchResults.style.display = "flex";
    searchResults.innerHTML = `<div class="col-12 text-danger">Ralat carian: ${escapeHtml(e.message)}</div>`;
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}