import { onAuthReady, authedFetch } from "./auth.js";

const personId = window.PERSON_ID;
const loading = document.getElementById("loading");
const content = document.getElementById("profile-content");
const form = document.getElementById("profile-form");
const editBtn = document.getElementById("edit-btn");
const cancelBtn = document.getElementById("cancel-btn");
const claimBtn = document.getElementById("claim-btn");
const formButtons = document.getElementById("form-buttons");
const saveMsg = document.getElementById("save-msg");

let currentPerson = null;
let currentUser = null;

onAuthReady(async (user) => {
  if (!user) { window.location.href = "/login"; return; }
  await loadAll();
});

async function loadAll() {
  try {
    // Load current user record + person + audit
    const [meR, pR, aR] = await Promise.all([
      authedFetch("/api/me"),
      authedFetch(`/api/persons/${personId}`),
      authedFetch(`/api/persons/${personId}/audit`),
    ]);
    currentUser = (await meR.json()).user;
    currentPerson = (await pR.json()).person;
    const audit = (await aR.json()).audit;

    renderHeader();
    renderForm(currentPerson, /* readOnly */ true);
    renderFamily(currentPerson);
    renderAudit(audit);

    loading.style.display = "none";
    content.style.display = "block";
  } catch (e) {
    loading.innerHTML = `<div class="alert alert-danger">Ralat memuatkan profil: ${e.message}</div>`;
  }
}

function renderHeader() {
  document.getElementById("profile-name").textContent = currentPerson.full_name || "(Tiada nama)";
  document.getElementById("profile-jantina-display").textContent =
    currentPerson.jantina === "L" ? "Lelaki" : currentPerson.jantina === "P" ? "Perempuan" : "—";
  document.getElementById("profile-tahun-lahir").textContent = currentPerson.tahun_lahir ?? "—";

  if (currentPerson.claimed_by_uid) {
    document.getElementById("profile-claimed").style.display = "inline";
  }
  // Show claim button if not claimed AND user hasn't claimed another profile
  if (!currentPerson.claimed_by_uid && !currentUser.linked_person_id) {
    claimBtn.style.display = "inline-block";
  }
}

function renderForm(p, readOnly) {
  setVal("full_name", p.full_name);
  setVal("jantina", p.jantina);
  setVal("tahun_lahir", p.tahun_lahir);
  setVal("tarikh_lahir", p.tarikh_lahir);
  setVal("status", p.status || "alive");
  setVal("tarikh_meninggal", p.tarikh_meninggal);
  setVal("email", p.email);
  setVal("phone", p.phone);
  setVal("alt_phone", p.alt_phone);
  const a = p.address || {};
  setVal("address.line1", a.line1);
  setVal("address.line2", a.line2);
  setVal("address.poskod", a.poskod);
  setVal("address.bandar", a.bandar);
  setVal("address.negeri", a.negeri);
  setVal("address.negara", a.negara || "Malaysia");
  setVal("notes", p.notes);

  Array.from(form.elements).forEach(el => { el.disabled = readOnly; });
  formButtons.style.display = readOnly ? "none" : "flex";
  editBtn.style.display = readOnly ? "inline-block" : "none";
}

function setVal(name, value) {
  const el = form.elements[name];
  if (el) el.value = value ?? "";
}

editBtn.addEventListener("click", () => renderForm(currentPerson, false));
cancelBtn.addEventListener("click", () => renderForm(currentPerson, true));

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = collectForm();
  saveMsg.innerHTML = '<span class="text-muted">Menyimpan...</span>';
  try {
    const resp = await authedFetch(`/api/persons/${personId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.error || "save failed");
    currentPerson = json.person;
    renderForm(currentPerson, true);
    renderHeader();
    saveMsg.innerHTML = '<div class="alert alert-success">Berjaya disimpan.</div>';
    // Reload audit log to show the new entry
    const aR = await authedFetch(`/api/persons/${personId}/audit`);
    renderAudit((await aR.json()).audit);
  } catch (err) {
    saveMsg.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
  }
});

function collectForm() {
  const fd = new FormData(form);
  const out = {};
  const addr = {};
  for (const [k, v] of fd.entries()) {
    if (k.startsWith("address.")) {
      addr[k.slice(8)] = v;
    } else {
      out[k] = v;
    }
  }
  out.address = addr;
  return out;
}

claimBtn.addEventListener("click", async () => {
  if (!confirm("Tuntut profil ini sebagai milik anda? Tindakan ini tidak boleh dibatalkan.")) return;
  try {
    const resp = await authedFetch(`/api/persons/${personId}/claim`, { method: "POST" });
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.error);
    alert("Profil berjaya dituntut.");
    location.reload();
  } catch (e) {
    alert("Gagal: " + e.message);
  }
});

function renderFamily(p) {
  fillFamilyList("parents-list", p.parent_ids || []);
  fillFamilyList("spouses-list", p.spouse_ids || []);
  fillFamilyList("children-list", p.child_ids || []);
}


function renderAudit(entries) {
  const list = document.getElementById("audit-list");
  if (!entries || !entries.length) {
    list.innerHTML = '<p class="text-muted">Tiada sejarah perubahan.</p>';
    return;
  }
  list.innerHTML = entries.map(e => {
    const when = e.changed_at?._seconds
      ? new Date(e.changed_at._seconds * 1000).toLocaleString("ms-MY")
      : "—";
    const who = e.changed_by_name || e.changed_by_email || "(tidak dikenali)";
    const fields = (e.fields_changed || []).join(", ");
    return `
      <div class="border-bottom py-2">
        <div><strong>${escapeHtml(who)}</strong>
          <span class="badge bg-secondary role-badge">${e.action}</span></div>
        <div class="audit-entry">${when} — Medan: ${escapeHtml(fields) || "—"}</div>
      </div>
    `;
  }).join("");
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

// ---------------------------- Relationship editing ----------------------------

// Removal + edit-anyone power: admin/editor only.
function canEditRelationships() {
  return currentUser && (currentUser.role === "admin" || currentUser.role === "editor");
}

// Add power: admin/editor (anyone) OR a claimed member viewing their OWN profile.
function canAddRelationships() {
  if (canEditRelationships()) return true;
  const mine = currentUser && currentUser.linked_person_id;
  return Boolean(mine) && mine === (currentPerson && currentPerson.person_id);
}

function applyRelEditingVisibility() {
  const canAdd = canAddRelationships();
  document.querySelectorAll(".rel-add-btn").forEach(btn => {
    btn.style.display = canAdd ? "inline-block" : "none";
  });
  const note = document.getElementById("rel-permission-note");
  if (note) {
    if (canEditRelationships()) {
      note.style.display = "none";
    } else if (canAdd) {
      // Member on their own profile: explain the limited scope.
      note.textContent = "Anda boleh menambah ibu bapa, pasangan, dan anak untuk diri sendiri. Hubungi admin untuk membuang hubungan.";
      note.style.display = "block";
    } else {
      note.textContent = "Hanya admin/editor boleh mengubah hubungan keluarga.";
      note.style.display = "block";
    }
  }
}

async function fillFamilyList(elementId, ids) {
  const ul = document.getElementById(elementId);
  if (!ids.length) {
    ul.innerHTML = '<li class="list-group-item text-muted small">Tiada rekod.</li>';
    return;
  }
  const persons = await Promise.all(ids.map(async id => {
    try {
      const r = await authedFetch(`/api/persons/${id}`);
      const j = await r.json();
      return j.person ? { id, name: j.person.full_name } : { id, name: "(tidak dijumpai)" };
    } catch { return { id, name: "(ralat)" }; }
  }));
  const kind = elementId.replace("-list", "");  // "parents" | "spouses" | "children"
  const canEdit = canEditRelationships();
  ul.innerHTML = persons.map(p => `
    <li class="list-group-item d-flex justify-content-between align-items-center">
      <a href="/profile/${p.id}">${escapeHtml(p.name)}</a>
      ${canEdit ? `<button class="btn btn-sm btn-link text-danger rel-remove-btn p-0"
                           data-kind="${kind}" data-other-id="${p.id}"
                           title="Buang hubungan">×</button>` : ''}
    </li>
  `).join("");
}

// Bootstrap modal instance — created lazily on first open
let pickerModal = null;
let pickerState = { kind: null, selectedId: null, selectedName: null, searchTimer: null };

function ensureModal() {
  if (pickerModal) return pickerModal;
  pickerModal = new bootstrap.Modal(document.getElementById("personPickerModal"));
  wirePickerEvents();
  return pickerModal;
}

function wirePickerEvents() {
  const searchInput = document.getElementById("pickerSearch");
  const resultsEl = document.getElementById("pickerResults");
  const statusEl = document.getElementById("pickerStatus");
  const confirmEl = document.getElementById("pickerConfirm");
  const confirmTextEl = document.getElementById("pickerConfirmText");
  const confirmBtn = document.getElementById("pickerConfirmBtn");
  const cancelBtn = document.getElementById("pickerCancelBtn");

  searchInput.addEventListener("input", () => {
    clearTimeout(pickerState.searchTimer);
    const q = searchInput.value.trim();
    confirmEl.classList.add("d-none");
    pickerState.selectedId = null;
    if (q.length < 2) {
      resultsEl.innerHTML = "";
      statusEl.textContent = "";
      return;
    }
    statusEl.textContent = "Mencari...";
    pickerState.searchTimer = setTimeout(async () => {
      try {
        const r = await authedFetch(
          `/api/persons/search?q=${encodeURIComponent(q)}&exclude=${encodeURIComponent(personId)}`);
        const j = await r.json();
        const results = j.results || [];
        if (!results.length) {
          statusEl.textContent = "Tiada hasil.";
          resultsEl.innerHTML = newPersonButtonHtml(searchInput.value.trim());
          return;
        }
        statusEl.textContent = `${results.length} hasil ditemui.`;
        resultsEl.innerHTML = results.map(p => `
          <button type="button" class="list-group-item list-group-item-action picker-result-btn"
                  data-id="${escapeHtml(p.id)}" data-name="${escapeHtml(p.full_name)}">
            <strong>${escapeHtml(p.full_name)}</strong>
            <small class="text-muted d-block">
              ${p.gender === 'L' ? 'Lelaki' : p.gender === 'P' ? 'Perempuan' : ''}
              ${p.birth_year ? ' · b. ' + p.birth_year : ''}
            </small>
          </button>
        `).join("") + newPersonButtonHtml(searchInput.value.trim());
      } catch (e) {
        statusEl.textContent = "Ralat: " + e.message;
      }
    }, 250);
  });

  resultsEl.addEventListener("click", (e) => {
    const newBtn = e.target.closest(".picker-newperson-btn");
    if (newBtn) {
      showNewPersonForm(newBtn.dataset.prefill || "");
      return;
    }
    const btn = e.target.closest(".picker-result-btn");
    if (!btn) return;
    pickerState.selectedId = btn.dataset.id;
    pickerState.selectedName = btn.dataset.name;
    const verb = { parent: "sebagai ibu/bapa kepada",
                   spouse: "sebagai pasangan kepada",
                   child:  "sebagai anak kepada" }[pickerState.kind];
    const meName = currentPerson.full_name || "orang ini";
    confirmTextEl.innerHTML =
      `Tambah <strong>${escapeHtml(pickerState.selectedName)}</strong> ${verb} <strong>${escapeHtml(meName)}</strong>?`;
    confirmEl.classList.remove("d-none");
  });

  cancelBtn.addEventListener("click", () => {
    confirmEl.classList.add("d-none");
    pickerState.selectedId = null;
  });

  confirmBtn.addEventListener("click", async () => {
    if (!pickerState.selectedId) return;
    confirmBtn.disabled = true;
    const statusEl = document.getElementById("pickerStatus");
    try {
      // Check if relationship already exists, to give better feedback
      const existingList = pickerState.kind === "parent" ? currentPerson.parent_ids :
                           pickerState.kind === "spouse" ? currentPerson.spouse_ids :
                                                            currentPerson.child_ids;
      if ((existingList || []).includes(pickerState.selectedId)) {
        statusEl.innerHTML = '<span class="text-warning">Hubungan ini sudah wujud.</span>';
        return;
      }
      await submitAdd(pickerState.kind, pickerState.selectedId);
      pickerModal.hide();
      await reloadPersonAndFamily();
    } catch (e) {
      // Show error inside the modal instead of an alert — easier to read
      statusEl.innerHTML = `<span class="text-danger">Gagal: ${escapeHtml(e.message)}</span>`;
    } finally {
      confirmBtn.disabled = false;
    }
  });
}

// --- Create-and-link (members + admin/editor): anak & spouse only, not parents ---

function createKindAllowed() {
  // pickerState.kind is "parent" | "spouse" | "child"
  // All three allow create-and-link: anak (new baby), spouse (new in-law),
  // parent (deceased/absent ancestor who cannot enter themselves).
  return pickerState.kind === "child" || pickerState.kind === "spouse" || pickerState.kind === "parent";
}

function newPersonButtonHtml(prefill) {
  if (!createKindAllowed()) return "";
  const label = pickerState.kind === "child" ? "anak baharu" :
                pickerState.kind === "spouse" ? "pasangan baharu" :
                "ibu/bapa baharu";
  const safe = escapeHtml(prefill || "");
  return `
    <button type="button" class="list-group-item list-group-item-action picker-newperson-btn text-primary"
            data-prefill="${safe}">
      + Daftar ${label} (orang yang belum ada dalam sistem)
    </button>`;
}

function showNewPersonForm(prefillName) {
  const resultsEl = document.getElementById("pickerResults");
  const statusEl = document.getElementById("pickerStatus");
  const confirmEl = document.getElementById("pickerConfirm");
  confirmEl.classList.add("d-none");
  statusEl.textContent = "";
  const kindLabel = pickerState.kind === "child" ? "anak" :
                    pickerState.kind === "parent" ? "ibu/bapa" :
                    "pasangan";
  resultsEl.innerHTML = `
    <div class="p-2 border rounded">
      <h6 class="mb-2">Daftar ${kindLabel} baharu</h6>
      <input type="text" id="np-name" class="form-control mb-2" placeholder="Nama penuh"
             value="${escapeHtml(prefillName || "")}">
      <select id="np-jantina" class="form-select mb-2">
        <option value="">Jantina (pilihan)</option>
        <option value="L">Lelaki</option>
        <option value="P">Perempuan</option>
      </select>
      <input type="number" id="np-tahun" class="form-control mb-2"
             placeholder="Tahun lahir (pilihan)" min="1850" max="2026">
      <div class="d-flex gap-2">
        <button type="button" class="btn btn-primary btn-sm" id="np-save">Daftar & tambah</button>
        <button type="button" class="btn btn-secondary btn-sm" id="np-cancel">Batal</button>
      </div>
      <div id="np-msg" class="small mt-2"></div>
    </div>`;
  document.getElementById("np-name").focus();
  document.getElementById("np-cancel").addEventListener("click", () => {
    resultsEl.innerHTML = "";
    document.getElementById("pickerSearch").focus();
  });
  document.getElementById("np-save").addEventListener("click", submitNewPerson);
}

async function submitNewPerson() {
  const msg = document.getElementById("np-msg");
  const saveBtn = document.getElementById("np-save");
  const name = document.getElementById("np-name").value.trim();
  const jantina = document.getElementById("np-jantina").value;
  const tahun = document.getElementById("np-tahun").value;
  if (!name) { msg.innerHTML = '<span class="text-danger">Nama penuh diperlukan.</span>'; return; }
  if (!createKindAllowed()) {  // defensive — should not be reachable
    msg.innerHTML = '<span class="text-danger">Jenis hubungan tidak sah untuk pendaftaran orang baharu.</span>';
    return;
  }
  saveBtn.disabled = true;
  msg.innerHTML = '<span class="text-muted">Mendaftar...</span>';
  const person = { full_name: name };
  if (jantina) person.jantina = jantina;
  if (tahun) person.tahun_lahir = parseInt(tahun, 10);
  const kind = pickerState.kind === "child" ? "anak" :
               pickerState.kind === "parent" ? "ibu_bapa" :
               "spouse";
  try {
    const r = await authedFetch("/api/relationships/new-person", {
      method: "POST",
      body: JSON.stringify({ kind, anchor_id: personId, person }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "permintaan gagal");
    pickerModal.hide();
    await reloadPersonAndFamily();
  } catch (e) {
    msg.innerHTML = `<span class="text-danger">Gagal: ${escapeHtml(e.message)}</span>`;
  } finally {
    saveBtn.disabled = false;
  }
}

async function submitAdd(kind, otherId) {
  let url, body;
  if (kind === "parent") {
    url = "/api/relationships/parent-child";
    body = { parent_id: otherId, child_id: personId };
  } else if (kind === "child") {
    url = "/api/relationships/parent-child";
    body = { parent_id: personId, child_id: otherId };
  } else if (kind === "spouse") {
    url = "/api/relationships/spouse";
    body = { a_id: personId, b_id: otherId };
  } else {
    throw new Error("kind tidak sah: " + kind);
  }
  const r = await authedFetch(url, { method: "POST", body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || "permintaan gagal");
}

async function submitRemove(kind, otherId, reason) {
  let url, body;
  if (kind === "parents") {
    url = "/api/relationships/parent-child";
    body = { parent_id: otherId, child_id: personId, reason };
  } else if (kind === "children") {
    url = "/api/relationships/parent-child";
    body = { parent_id: personId, child_id: otherId, reason };
  } else if (kind === "spouses") {
    url = "/api/relationships/spouse";
    body = { a_id: personId, b_id: otherId, reason };
  } else {
    throw new Error("kind tidak sah: " + kind);
  }
  const r = await authedFetch(url, { method: "DELETE", body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || "permintaan gagal");
}

async function reloadPersonAndFamily() {
  const pR = await authedFetch(`/api/persons/${personId}`);
  currentPerson = (await pR.json()).person;
  renderFamily(currentPerson);
  // Refresh audit too, since we just wrote an entry
  const aR = await authedFetch(`/api/persons/${personId}/audit`);
  renderAudit((await aR.json()).audit);
}

// Open the picker — wire up the Add buttons
document.addEventListener("click", (e) => {
  const addBtn = e.target.closest(".rel-add-btn");
  if (addBtn) {
    const kind = addBtn.dataset.rel;
    pickerState.kind = kind;
    pickerState.selectedId = null;
    document.getElementById("pickerSearch").value = "";
    document.getElementById("pickerResults").innerHTML = "";
    document.getElementById("pickerStatus").textContent = "";
    document.getElementById("pickerConfirm").classList.add("d-none");
    document.getElementById("pickerTitle").textContent =
      kind === "parent" ? "Tambah Ibu Bapa" :
      kind === "spouse" ? "Tambah Pasangan" :
      "Tambah Anak";
    ensureModal().show();
    setTimeout(() => document.getElementById("pickerSearch").focus(), 200);
    return;
  }

  const rmBtn = e.target.closest(".rel-remove-btn");
  if (rmBtn) {
    const kind = rmBtn.dataset.kind;       // "parents" | "spouses" | "children"
    const otherId = rmBtn.dataset.otherId;
    const reason = prompt("Sebab pembuangan hubungan ini (untuk audit log):");
    if (!reason || !reason.trim()) return;
    (async () => {
      try {
        await submitRemove(kind, otherId, reason.trim());
        await reloadPersonAndFamily();
      } catch (e) {
        alert("Gagal: " + e.message);
      }
    })();
  }
});

// Apply visibility after each render
const _origRenderHeader = renderHeader;
renderHeader = function () {
  _origRenderHeader();
  applyRelEditingVisibility();
};