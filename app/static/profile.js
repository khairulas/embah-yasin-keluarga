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
  ul.innerHTML = persons.map(p =>
    `<li class="list-group-item"><a href="/profile/${p.id}">${escapeHtml(p.name)}</a></li>`
  ).join("");
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
