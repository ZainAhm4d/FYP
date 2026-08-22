/**
 * Admin portal (CH-18) — user lifecycle management.
 * The redirect below is UX only; every /admin endpoint is enforced server-side.
 */

let _adminUsers = [];
let _deleteTarget = null;

async function initAdminPage() {
    // Guard: must be logged in AND an admin (server still enforces on every call)
    try {
        const me = await API.get('/auth/users/me', true);
        if (!me.is_admin) {
            Notifications.error('Admin privileges required');
            setTimeout(() => { window.location.href = 'dashboard.html'; }, 800);
            return;
        }
    } catch (_) {
        window.location.href = 'index.html?login=1&next=admin.html';
        return;
    }

    _initTabs();
    _initModals();
    document.getElementById('userSearch')?.addEventListener('input', renderUsersTable);

    await Promise.all([loadStats(), loadUsers()]);
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

function _initTabs() {
    document.querySelectorAll('.admin-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.admin-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            ['users', 'deleted', 'audit'].forEach(t => {
                document.getElementById(`tab-${t}`)?.classList.toggle('hidden', t !== btn.dataset.tab);
            });
            if (btn.dataset.tab === 'audit') loadAudit();
            if (btn.dataset.tab === 'deleted') renderDeletedList();
        });
    });
}

// ── Stats ─────────────────────────────────────────────────────────────────────

async function loadStats() {
    try {
        const s = await API.get('/admin/stats', true);
        const fmtBytes = (b) => b > 1e9 ? (b / 1e9).toFixed(1) + ' GB'
            : b > 1e6 ? (b / 1e6).toFixed(1) + ' MB' : Math.round(b / 1e3) + ' KB';
        // icon-circle stat cards (reference style) — each stat keeps a
        // semantically distinct accent color, teal reserved for the
        // "headline" total-users metric to match the rest of the app's brand.
        const card = (label, value, icon, bg, fg) => `
            <div class="admin-stat-card">
                <div class="admin-stat-icon" style="background:${bg};">
                    <i data-lucide="${icon}" style="width:22px;height:22px;color:${fg};"></i>
                </div>
                <div class="admin-stat-value">${value}</div>
                <div class="admin-stat-label">${label}</div>
            </div>`;
        document.getElementById('adminStats').innerHTML =
            card('Total Users', s.total_users, 'users', 'var(--primary-50)', 'var(--primary-600)') +
            card('Active', s.active_users, 'check-circle-2', '#dcfce7', '#22c55e') +
            card('Deleted', s.deleted_users, 'trash-2', '#fef3c7', '#d97706') +
            card('Datasets', s.total_datasets, 'database', '#f3e8ff', '#a855f7') +
            card('Storage Used', fmtBytes(s.uploads_size_bytes), 'hard-drive', '#f1f5f9', '#64748b');
        if (window.lucide) lucide.createIcons();
    } catch (e) {
        Notifications.error('Could not load stats: ' + (e.message || ''));
    }
}

// ── Users table ───────────────────────────────────────────────────────────────

async function loadUsers() {
    try {
        _adminUsers = await API.get('/admin/users', true);
        renderUsersTable();
        renderDeletedList();
    } catch (e) {
        Notifications.error('Could not load users: ' + (e.message || ''));
    }
}

function _fmtDate(d) {
    return d ? new Date(d).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—';
}

function _initials(name, email) {
    const src = (name || '').trim() || (email || '');
    const parts = src.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return src.slice(0, 2).toUpperCase();
}

function renderUsersTable() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    const q = (document.getElementById('userSearch')?.value || '').toLowerCase();
    const rows = _adminUsers
        .filter(u => !u.deleted_at)
        .filter(u => !q || u.email.toLowerCase().includes(q)
                       || (u.full_name || '').toLowerCase().includes(q));

    tbody.innerHTML = rows.map(u => `
        <tr>
            <td>
                <div class="flex items-center gap-2.5">
                    <span class="admin-mini-avatar">${_initials(u.full_name, u.email)}</span>
                    <div>
                        <p class="font-semibold text-gray-800 flex items-center gap-1.5">
                            ${u.full_name || '—'}
                            ${u.is_admin ? '<span class="admin-role-badge">ADMIN</span>' : ''}
                        </p>
                        <p class="text-xs text-gray-400">${u.email}</p>
                    </div>
                </div>
            </td>
            <td>
                <span class="admin-status-dot ${u.is_active ? 'active' : 'inactive'}"></span>
                <span class="text-xs font-semibold ${u.is_active ? 'text-gray-700' : 'text-gray-400'}">${u.is_active ? 'Active' : 'Deactivated'}</span>
            </td>
            <td class="text-gray-600">${u.dataset_count}</td>
            <td class="text-gray-600">${u.dashboard_count}</td>
            <td class="text-gray-400 text-xs">${_fmtDate(u.last_login_at)}</td>
            <td class="text-gray-400 text-xs">${_fmtDate(u.created_at)}</td>
            <td class="text-right whitespace-nowrap">
                ${u.is_active
                    ? `<button onclick="adminDeactivate(${u.id})" class="text-xs font-semibold text-amber-700 border border-amber-300 px-3 py-1.5 rounded-lg hover:bg-amber-50 mr-1">Deactivate</button>`
                    : `<button onclick="adminReactivate(${u.id})" class="text-xs font-semibold text-green-700 border border-green-300 px-3 py-1.5 rounded-lg hover:bg-green-50 mr-1">Reactivate</button>`}
                <button onclick="adminOpenDelete(${u.id})" class="text-xs font-semibold text-red-600 border border-red-300 px-3 py-1.5 rounded-lg hover:bg-red-50">Delete</button>
            </td>
        </tr>`).join('')
        || '<tr><td colspan="7" class="px-4 py-8 text-center text-gray-400">No users match.</td></tr>';
}

function renderDeletedList() {
    const box = document.getElementById('deletedList');
    if (!box) return;
    const deleted = _adminUsers.filter(u => u.deleted_at);
    box.innerHTML = deleted.length ? deleted.map(u => `
        <div class="flex flex-wrap items-center gap-3 border border-gray-200 rounded-xl px-4 py-3 text-sm">
            <span class="admin-mini-avatar" style="background:#94a3b8;">${_initials(u.full_name, u.email)}</span>
            <span class="font-mono text-gray-600">${u.email}</span>
            <span class="text-xs text-gray-400">deleted ${_fmtDate(u.deleted_at)}</span>
            <span class="flex-1"></span>
            <input id="restoreEmail${u.id}" type="email" placeholder="restore with email…"
                   class="border border-gray-300 rounded-lg px-3 py-1.5 text-xs w-56">
            <button onclick="adminRestore(${u.id})"
                    class="text-xs font-semibold text-white px-3 py-1.5 rounded-lg" style="background:var(--primary-600);">Restore</button>
        </div>`).join('')
        : '<p class="text-sm text-gray-400">No deleted accounts in the recovery window.</p>';
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function adminDeactivate(id) {
    try {
        await API.put(`/admin/users/${id}/deactivate`, {}, true);
        Notifications.success('Account deactivated — login blocked immediately');
        loadUsers(); loadStats();
    } catch (e) { Notifications.error(e.message || 'Failed'); }
}

async function adminReactivate(id) {
    try {
        await API.put(`/admin/users/${id}/reactivate`, {}, true);
        Notifications.success('Account reactivated');
        loadUsers(); loadStats();
    } catch (e) { Notifications.error(e.message || 'Failed'); }
}

function adminOpenDelete(id) {
    _deleteTarget = _adminUsers.find(u => u.id === id);
    if (!_deleteTarget) return;
    document.getElementById('deleteUserEmail').textContent = _deleteTarget.email;
    const input = document.getElementById('deleteUserConfirmInput');
    input.value = '';
    document.getElementById('confirmDeleteUser').disabled = true;
    const modal = document.getElementById('deleteUserModal');
    modal.classList.remove('hidden'); modal.classList.add('flex');
    input.focus();
}

async function adminRestore(id) {
    const email = document.getElementById(`restoreEmail${id}`)?.value.trim();
    try {
        const qs = email ? `?new_email=${encodeURIComponent(email)}` : '';
        await API.post(`/admin/users/${id}/restore${qs}`, {}, true);
        Notifications.success('Account restored');
        loadUsers(); loadStats();
    } catch (e) { Notifications.error(e.message || 'Restore failed'); }
}

async function loadAudit() {
    const box = document.getElementById('auditList');
    if (!box) return;
    try {
        const rows = await API.get('/admin/audit', true);
        box.innerHTML = rows.length ? rows.map(r => `
            <div class="flex gap-3 border-b border-gray-50 py-1.5">
                <span class="text-gray-400 text-xs w-40 flex-shrink-0">${_fmtDate(r.created_at)}</span>
                <span class="font-semibold w-28 flex-shrink-0" style="color:var(--primary-700);">${r.action}</span>
                <span class="text-gray-600 text-xs">admin #${r.admin_user_id}${r.target_user_id ? ` → user #${r.target_user_id}` : ''} ${r.detail || ''}</span>
            </div>`).join('')
            : '<p class="text-sm text-gray-400 font-sans">No admin actions recorded yet.</p>';
    } catch (e) {
        box.innerHTML = `<p class="text-sm text-red-400 font-sans">${e.message || 'Could not load audit log'}</p>`;
    }
}

// ── Modals ────────────────────────────────────────────────────────────────────

function _initModals() {
    // Add user
    document.getElementById('addUserBtn')?.addEventListener('click', () => {
        const m = document.getElementById('addUserModal');
        m.classList.remove('hidden'); m.classList.add('flex');
    });
    document.getElementById('cancelAddUser')?.addEventListener('click', () => {
        const m = document.getElementById('addUserModal');
        m.classList.add('hidden'); m.classList.remove('flex');
    });
    document.getElementById('confirmAddUser')?.addEventListener('click', async () => {
        const email = document.getElementById('newUserEmail').value.trim();
        const full_name = document.getElementById('newUserName').value.trim();
        const password = document.getElementById('newUserPassword').value;
        const is_admin = document.getElementById('newUserAdmin').checked;
        if (!email || !password) { Notifications.error('Email and password are required'); return; }
        try {
            await API.post('/admin/users', { email, full_name: full_name || null, password, is_admin }, true);
            Notifications.success(`User ${email} created`);
            document.getElementById('addUserModal').classList.add('hidden');
            ['newUserEmail', 'newUserName', 'newUserPassword'].forEach(id => document.getElementById(id).value = '');
            document.getElementById('newUserAdmin').checked = false;
            loadUsers(); loadStats();
        } catch (e) { Notifications.error(e.message || 'Create failed'); }
    });

    // Delete confirm (typed email)
    document.getElementById('deleteUserConfirmInput')?.addEventListener('input', (e) => {
        document.getElementById('confirmDeleteUser').disabled =
            !_deleteTarget || e.target.value.trim() !== _deleteTarget.email;
    });
    document.getElementById('cancelDeleteUser')?.addEventListener('click', () => {
        const m = document.getElementById('deleteUserModal');
        m.classList.add('hidden'); m.classList.remove('flex');
        _deleteTarget = null;
    });
    document.getElementById('confirmDeleteUser')?.addEventListener('click', async () => {
        if (!_deleteTarget) return;
        try {
            const token = Storage.get(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
            const res = await fetch(API.getUrl(`/admin/users/${_deleteTarget.id}`), {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            Notifications.success('Account deleted — recoverable for 30 days');
            document.getElementById('deleteUserModal').classList.add('hidden');
            _deleteTarget = null;
            loadUsers(); loadStats();
        } catch (e) { Notifications.error(e.message || 'Delete failed'); }
    });
}
