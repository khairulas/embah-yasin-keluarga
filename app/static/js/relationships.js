// static/js/relationships.js
(function () {
  const panel = document.querySelector('[data-person-id]');
  if (!panel) return;
  const personId = panel.dataset.personId;
  const personName = panel.dataset.personName || 'orang ini';

  const modal = new bootstrap.Modal(document.getElementById('personPicker'));
  const searchInput = document.getElementById('pickerSearch');
  const resultsEl = document.getElementById('pickerResults');
  const confirmEl = document.getElementById('pickerConfirm');
  const confirmText = document.getElementById('pickerConfirmText');
  const confirmBtn = document.getElementById('pickerConfirmBtn');
  const cancelBtn = document.getElementById('pickerCancelBtn');

  let currentAction = null;  // 'add-parent' | 'add-spouse' | 'add-child'
  let selectedPerson = null;
  let searchTimer = null;

  async function authFetch(url, opts = {}) {
    const token = await firebase.auth().currentUser.getIdToken();
    return fetch(url, {
      ...opts,
      headers: {
        ...(opts.headers || {}),
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });
  }

  function openPicker(action) {
    currentAction = action;
    selectedPerson = null;
    searchInput.value = '';
    resultsEl.innerHTML = '';
    confirmEl.classList.add('d-none');
    modal.show();
    setTimeout(() => searchInput.focus(), 150);
  }

  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    const q = searchInput.value.trim();
    if (q.length < 2) { resultsEl.innerHTML = ''; return; }
    searchTimer = setTimeout(async () => {
      const res = await authFetch(`/api/persons/search?q=${encodeURIComponent(q)}&exclude=${personId}`);
      const { results } = await res.json();
      resultsEl.innerHTML = results.map(p => `
        <button type="button" class="list-group-item list-group-item-action"
                data-id="${p.id}" data-name="${p.full_name}">
          <strong>${p.full_name}</strong>
          <small class="text-muted d-block">${p.household_name || ''} ${p.dob_year ? '· ' + p.dob_year : ''}</small>
        </button>
      `).join('') || '<div class="text-muted">Tiada hasil.</div>';
    }, 250);
  });

  resultsEl.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-id]');
    if (!btn) return;
    selectedPerson = { id: btn.dataset.id, name: btn.dataset.name };
    const verb = { 'add-parent': 'sebagai ibu/bapa kepada',
                   'add-spouse': 'sebagai pasangan',
                   'add-child':  'sebagai anak kepada' }[currentAction];
    confirmText.textContent = `Tambah ${selectedPerson.name} ${verb} ${personName}?`;
    confirmEl.classList.remove('d-none');
  });

  cancelBtn.addEventListener('click', () => confirmEl.classList.add('d-none'));

  confirmBtn.addEventListener('click', async () => {
    if (!selectedPerson) return;
    const body = currentAction === 'add-parent'
      ? { parent_id: selectedPerson.id, child_id: personId }
      : currentAction === 'add-child'
      ? { parent_id: personId, child_id: selectedPerson.id }
      : { a_id: personId, b_id: selectedPerson.id };
    const url = currentAction === 'add-spouse'
      ? '/api/relationships/spouse'
      : '/api/relationships/parent-child';

    const res = await authFetch(url, { method: 'POST', body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) { alert(data.error || 'Ralat'); return; }
    modal.hide();
    location.reload();  // simple; swap for partial re-render later
  });

  panel.addEventListener('click', async (e) => {
    const action = e.target.dataset.action;
    if (!action) return;

    if (action.startsWith('add-')) { openPicker(action); return; }

    if (action.startsWith('remove-')) {
      const reason = prompt('Sebab pembuangan (untuk audit log):');
      if (!reason || !reason.trim()) return;
      const kind = action.replace('remove-', '');
      const body = kind === 'parent'
        ? { parent_id: e.target.dataset.parentId, child_id: personId, reason }
        : kind === 'child'
        ? { parent_id: personId, child_id: e.target.dataset.childId, reason }
        : { a_id: personId, b_id: e.target.dataset.spouseId, reason };
      const url = kind === 'spouse' ? '/api/relationships/spouse' : '/api/relationships/parent-child';
      const res = await authFetch(url, { method: 'DELETE', body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) { alert(data.error || 'Ralat'); return; }
      location.reload();
    }
  });
})();