/**
 * Datasets Page Logic
 * Displays and manages user's uploaded datasets
 */

let datasets = [];
let filteredDatasets = [];
let datasetToDelete = null;

document.addEventListener('DOMContentLoaded', () => {
    // Load datasets
    loadDatasets();

    // Setup search
    const searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('input', handleSearch);

    // Setup sort
    const sortSelect = document.getElementById('sortSelect');
    sortSelect.addEventListener('change', handleSort);

    // Setup modals
    setupModals();

    // Data model (relationships) panel
    initDataModelPanel();

    // Deep link from upload: datasets.html?review=<id> opens the review directly
    const reviewId = parseInt(new URLSearchParams(window.location.search).get('review'));
    if (reviewId) {
        _fullViewDatasetId = reviewId;
        openCleaningReview(reviewId);
    }

    // CH-10: deep link from a Live Sheets import — open the push-setup modal
    const liveSetupId = parseInt(new URLSearchParams(window.location.search).get('livesetup'));
    if (liveSetupId) {
        // datasets list loads async; retry briefly until it's available
        let tries = 0;
        const t = setInterval(() => {
            if (datasets.some(d => d.id === liveSetupId)) {
                clearInterval(t);
                openLiveModal(liveSetupId);
            } else if (++tries > 20) clearInterval(t);
        }, 300);
    }
});

// ── Data Model: dataset relationships ────────────────────────────────────────

function initDataModelPanel() {
    const leftSel  = document.getElementById('relLeftDataset');
    const rightSel = document.getElementById('relRightDataset');
    if (!leftSel || !rightSel) return;

    leftSel.addEventListener('change',  () => { _loadRelColumns('left');  _maybeSuggestPair(); });
    rightSel.addEventListener('change', () => { _loadRelColumns('right'); _maybeSuggestPair(); });
    document.getElementById('createRelBtn')?.addEventListener('click', createRelationship);
    document.getElementById('suggestRelBtn')?.addEventListener('click', () => suggestRelationships());

    _populateRelDatasetSelects();
    loadRelationships();
    _maybeOfferRelationshipCheck();
}

// ── CH-09: relationship suggestions ──────────────────────────────────────────

const _CARD_LABEL = {
    one_to_one: '1 : 1', one_to_many: '1 : N', many_to_one: 'N : 1', many_to_many: 'N : M',
};

async function suggestRelationships(pairIds) {
    const box = document.getElementById('relSuggestions');
    const btn = document.getElementById('suggestRelBtn');
    if (!box) return;
    box.innerHTML = '<p class="text-sm text-gray-400">Scanning your datasets for shared keys…</p>';
    if (btn) btn.disabled = true;
    try {
        const qs = pairIds && pairIds.length ? `?dataset_ids=${pairIds.join(',')}` : '';
        const resp = await API.get(`/relationships/suggest${qs}`, true);
        const cands = resp.candidates || [];
        if (!cands.length) {
            box.innerHTML = `<p class="text-sm text-gray-500">${resp.message || 'No strong relationships found.'}</p>`;
            return;
        }
        box.innerHTML = cands.slice(0, 8).map((c, i) => {
            const nm = c.cardinality === 'many_to_many';
            return `
            <div class="flex flex-wrap items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 text-sm" id="relSug${i}">
                <span class="font-semibold text-gray-800">${c.left_dataset_name}</span>
                <span class="font-mono text-xs text-emerald-700">${c.left_column}</span>
                <span class="text-emerald-500">↔</span>
                <span class="font-mono text-xs text-emerald-700">${c.right_column}</span>
                <span class="font-semibold text-gray-800">${c.right_dataset_name}</span>
                <span class="text-xs ${nm ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'} px-2 py-0.5 rounded-full font-semibold"
                      title="${nm ? 'Many-to-many: joining can multiply rows' : 'Inferred key relationship'}">
                    ${_CARD_LABEL[c.cardinality] || c.cardinality}${nm ? ' ⚠' : ''}</span>
                <span class="text-xs text-gray-500">${Math.round(c.containment * 100)}% of keys match
                    · e.g. ${(c.matched_examples || []).slice(0, 3).join(', ')}</span>
                <span class="flex-1"></span>
                <button onclick='createSuggestedRelationship(${JSON.stringify(c).replace(/'/g, "&#39;")}, this)'
                        class="text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-lg transition-colors">
                    Create link</button>
                <button onclick="document.getElementById('relSug${i}').remove()"
                        class="text-gray-400 hover:text-gray-600 text-xs font-semibold px-2">Dismiss</button>
            </div>`;
        }).join('');
    } catch (e) {
        box.innerHTML = `<p class="text-sm text-red-400">Could not scan: ${e.message || 'error'}</p>`;
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function createSuggestedRelationship(c, btn) {
    btn.disabled = true; btn.textContent = 'Linking…';
    try {
        await API.post('/relationships', {
            left_dataset_id:  c.left_dataset_id,  left_column:  c.left_column,
            right_dataset_id: c.right_dataset_id, right_column: c.right_column,
            join_type: 'inner', cardinality: c.cardinality,
        }, true);
        Notifications.success('Relationship created');
        btn.closest('div')?.remove();
        loadRelationships();
    } catch (e) {
        Notifications.error(e.message || 'Failed to create relationship');
        btn.disabled = false; btn.textContent = 'Create link';
    }
}

/** When both dataset dropdowns are chosen, run a scoped scan and pre-fill the
 *  column selects with the top candidate for that pair. */
async function _maybeSuggestPair() {
    const l = parseInt(document.getElementById('relLeftDataset')?.value);
    const r = parseInt(document.getElementById('relRightDataset')?.value);
    if (!l || !r || l === r) return;
    try {
        const resp = await API.get(`/relationships/suggest?dataset_ids=${l},${r}`, true);
        const best = (resp.candidates || [])[0];
        if (!best) return;
        // Column selects load async — wait briefly for the options to exist
        const trySet = (sel, val) => {
            const el = document.getElementById(sel);
            if (el && [...el.options].some(o => o.value === val) && !el.value) {
                el.value = val;
                return true;
            }
            return false;
        };
        let tries = 0;
        const timer = setInterval(() => {
            const lcol = best.left_dataset_id === l ? best.left_column : best.right_column;
            const rcol = best.left_dataset_id === l ? best.right_column : best.left_column;
            const done = trySet('relLeftColumn', lcol) | trySet('relRightColumn', rcol);
            if (done || ++tries > 10) clearInterval(timer);
        }, 400);
        Notifications.success(`Suggested key: ${best.left_column} ↔ ${best.right_column} (${_CARD_LABEL[best.cardinality] || ''})`);
    } catch (_) { /* suggestions are best-effort */ }
}

/** Post-upload nudge: offer an automatic relationship check once per dataset. */
function _maybeOfferRelationshipCheck() {
    try {
        const ready = (datasets || []).filter(d => d.processing_status !== 'processing');
        if (ready.length < 2) return;
        const newest = ready.reduce((a, b) => (a.id > b.id ? a : b));
        const seenKey = 'rel_check_offered';
        const seen = JSON.parse(localStorage.getItem(seenKey) || '[]');
        if (seen.includes(newest.id)) return;
        seen.push(newest.id);
        localStorage.setItem(seenKey, JSON.stringify(seen.slice(-50)));

        const bar = document.createElement('div');
        bar.className = 'flex flex-wrap items-center gap-3 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3 text-sm text-indigo-900 mb-4';
        bar.innerHTML = `
            <span>Does <strong>${newest.original_filename || newest.filename}</strong> relate to your other data?</span>
            <button class="text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-lg" id="relCheckYes">Check for me</button>
            <button class="text-xs font-semibold text-indigo-500 hover:text-indigo-700 px-2" id="relCheckNo">No</button>`;
        const panel = document.getElementById('relationshipsList')?.closest('.bg-white');
        panel?.parentElement?.insertBefore(bar, panel);
        bar.querySelector('#relCheckYes').addEventListener('click', () => {
            bar.remove();
            panel?.scrollIntoView({ behavior: 'smooth' });
            suggestRelationships();
        });
        bar.querySelector('#relCheckNo').addEventListener('click', () => bar.remove());
    } catch (_) { /* nudge is optional */ }
}

async function _populateRelDatasetSelects() {
    // Reuse the already-fetched dataset list once loadDatasets() has run
    try {
        const list = datasets.length ? datasets : await API.get('/datasets', true);
        ['relLeftDataset', 'relRightDataset'].forEach(id => {
            const sel = document.getElementById(id);
            sel.innerHTML = '<option value="">— choose —</option>';
            (list || []).forEach(d => {
                const o = document.createElement('option');
                o.value = d.id;
                o.textContent = d.original_filename || d.filename;
                sel.appendChild(o);
            });
        });
    } catch (_) { /* datasets page already shows load errors */ }
}

async function _loadRelColumns(side) {
    const dsSel  = document.getElementById(side === 'left' ? 'relLeftDataset' : 'relRightDataset');
    const colSel = document.getElementById(side === 'left' ? 'relLeftColumn'  : 'relRightColumn');
    colSel.innerHTML = '<option value="">Loading…</option>';
    colSel.disabled = true;
    if (!dsSel.value) { colSel.innerHTML = '<option value="">— pick dataset —</option>'; return; }
    try {
        const resp = await API.get(`/queries/datasets/${dsSel.value}/columns`, true);
        colSel.innerHTML = '<option value="">— choose column —</option>';
        (resp.columns || []).forEach(c => {
            const o = document.createElement('option');
            o.value = c.name;
            o.textContent = `${c.name} (${c.category})`;
            colSel.appendChild(o);
        });
        colSel.disabled = false;
    } catch (e) {
        colSel.innerHTML = '<option value="">Could not load columns</option>';
    }
}

async function createRelationship() {
    const body = {
        left_dataset_id:  parseInt(document.getElementById('relLeftDataset').value),
        left_column:      document.getElementById('relLeftColumn').value,
        right_dataset_id: parseInt(document.getElementById('relRightDataset').value),
        right_column:     document.getElementById('relRightColumn').value,
        join_type:        document.getElementById('relJoinType').value,
    };
    if (!body.left_dataset_id || !body.left_column || !body.right_dataset_id || !body.right_column) {
        Notifications.error('Pick both datasets and their key columns first.');
        return;
    }
    const btn = document.getElementById('createRelBtn');
    btn.disabled = true; btn.textContent = 'Linking…';
    try {
        await API.post('/relationships', body, true);
        Notifications.success('Relationship created');
        loadRelationships();
    } catch (e) {
        Notifications.error(e.message || 'Failed to create relationship');
    } finally {
        btn.disabled = false; btn.textContent = 'Link';
    }
}

async function loadRelationships() {
    const list = document.getElementById('relationshipsList');
    if (!list) return;
    try {
        const rels = await API.get('/relationships', true);
        if (!rels || rels.length === 0) {
            list.innerHTML = '<p class="text-sm text-gray-400">No relationships defined yet. Link two datasets above to build your data model.</p>';
            return;
        }
        list.innerHTML = rels.map(r => `
            <div class="flex flex-wrap items-center gap-3 bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3 text-sm">
                <span class="font-semibold text-gray-800">${r.left_dataset_name}</span>
                <span class="text-indigo-500 font-mono text-xs">${r.left_column}</span>
                <svg class="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/>
                </svg>
                <span class="text-indigo-500 font-mono text-xs">${r.right_column}</span>
                <span class="font-semibold text-gray-800">${r.right_dataset_name}</span>
                <span class="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full">${r.join_type} join</span>
                ${r.cardinality ? `<span class="text-xs ${r.cardinality === 'many_to_many' ? 'bg-amber-100 text-amber-800' : 'bg-indigo-100 text-indigo-700'} px-2 py-0.5 rounded-full font-semibold"
                    title="${r.cardinality === 'many_to_many' ? 'Many-to-many: joining can multiply rows and double-count sums' : 'Inferred key relationship'}">
                    ${_CARD_LABEL[r.cardinality] || r.cardinality}${r.cardinality === 'many_to_many' ? ' ⚠' : ''}</span>` : ''}
                <span class="flex-1"></span>
                <button onclick="materializeRelationship(${r.id}, this)"
                        class="text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-lg transition-colors">
                    Create Joined Dataset
                </button>
                <button onclick="deleteRelationship(${r.id})"
                        class="text-gray-400 hover:text-red-500 transition-colors" title="Delete relationship">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>`).join('');
    } catch (e) {
        list.innerHTML = '<p class="text-sm text-red-400">Could not load relationships.</p>';
    }
}

async function materializeRelationship(relId, btn, confirmFanout = false) {
    btn.disabled = true; btn.textContent = 'Joining…';
    try {
        const resp = await API.post(`/relationships/${relId}/materialize`,
                                    { confirm_fanout: confirmFanout }, true);
        Notifications.success(resp.message || 'Joined dataset created');
        await loadDatasets();
        _populateRelDatasetSelects();
    } catch (e) {
        // CH-09.4: the N:M fan-out guard responds 409 with the projected row
        // count — let the user decide with the numbers in front of them.
        const msg = e.message || 'Join failed';
        if (msg.includes('confirm_fanout') || msg.includes('double-count')) {
            if (window.confirm(msg.replace(/Send \{.*$/, '') + '\n\nCreate the joined dataset anyway?')) {
                return materializeRelationship(relId, btn, true);
            }
        } else {
            Notifications.error(msg);
        }
    } finally {
        btn.disabled = false; btn.textContent = 'Create Joined Dataset';
    }
}

async function deleteRelationship(relId) {
    try {
        const token = Storage.get(CONFIG.STORAGE_KEYS.ACCESS_TOKEN);
        const res = await fetch(API.getUrl(`/relationships/${relId}`), {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
        Notifications.success('Relationship removed');
        loadRelationships();
    } catch (e) {
        Notifications.error('Failed to delete relationship');
    }
}

/**
 * Load datasets from API
 */
// Poll quietly while any dataset is still being cleaned in the background,
// so the "Processing…" badge flips to "Cleaned ✓" without a manual refresh.
let _processingPollTimer = null;

function _scheduleProcessingPoll() {
    clearTimeout(_processingPollTimer);
    if (!datasets.some(d => d.processing_status === 'processing')) return;
    _processingPollTimer = setTimeout(async () => {
        try {
            const fresh = await API.get('/datasets', true);
            datasets = fresh || [];
            filteredDatasets = [...datasets];
            renderDatasets();
            updateStats();
        } catch (_) { /* transient — next poll retries */ }
        _scheduleProcessingPoll();
    }, 3000);
}

async function loadDatasets() {
    const tableContainer = document.getElementById('datasetsTableContainer');
    
    // Show loading skeleton
    SkeletonLoader.show(tableContainer, 'dataTable', { rows: 5, cols: 6 });
    
    try {
        // Fetch datasets from API
        const response = await API.get('/datasets', true);
        datasets = response || [];
        
        filteredDatasets = [...datasets];
        renderDatasets();
        updateStats();
        _scheduleProcessingPoll();

    } catch (error) {
        console.error('Error loading datasets:', error);
        Notifications.error('Failed to load datasets');
        
        // Show empty state
        EmptyStates.show(tableContainer, 'noDatasets');
    }
}

/**
 * Render datasets table
 */
function renderDatasets() {
    const tableContainer = document.getElementById('datasetsTableContainer');
    
    if (filteredDatasets.length === 0) {
        EmptyStates.show(tableContainer, 'noDatasets');
        return;
    }
    
    const tableHTML = `
        <div class="table-container">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Uploaded</th>
                        <th>Rows</th>
                        <th>Columns</th>
                        <th>Size</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${filteredDatasets.map(dataset => `
                        <tr>
                            <td>
                                <div class="flex items-center">
                                    <span class="mr-3"><i data-lucide="table-2" style="width:22px;height:22px;color:#0d9488;"></i></span>
                                    <div>
                                        <p class="font-semibold text-gray-800">${dataset.original_filename || dataset.filename}</p>
                                        <p class="text-xs text-gray-500">ID: ${dataset.id}</p>
                                    </div>
                                </div>
                            </td>
                            <td>${formatDate(dataset.upload_date)}</td>
                            <td>${formatNumber(dataset.row_count)}</td>
                            <td>${dataset.column_count}</td>
                            <td>${dataset.file_size || 'N/A'}</td>
                            <td>
                                ${dataset.processing_status === 'processing'
                                    ? `<span class="px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 inline-flex items-center gap-1.5">
                                        <span class="inline-block w-2.5 h-2.5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></span>
                                        Analyzing…
                                       </span>`
                                    : dataset.processing_status === 'review'
                                    ? `<button onclick="_fullViewDatasetId=${dataset.id};openCleaningReview(${dataset.id})"
                                          class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300 hover:bg-amber-200 transition-colors"
                                          title="Issues were found — review the proposed fixes and approve them">
                                        <i data-lucide="alert-triangle" style="width:12px;height:12px;display:inline-block;vertical-align:-2px;"></i> Review &amp; Clean
                                       </button>`
                                    : dataset.processing_status === 'failed'
                                    ? `<span class="px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800" title="Analysis failed — data is usable raw; use Review Cleaning to retry">Analysis failed</span>`
                                    : `<span class="px-3 py-1 rounded-full text-xs font-semibold ${dataset.cleaned_status ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}">
                                        ${dataset.cleaned_status ? 'Cleaned ✓' : 'Raw'}
                                       </span>`}
                                ${dataset.source_type === 'google_sheets' ? `
                                    <button onclick="openLiveModal(${dataset.id})"
                                            class="ml-1 px-2 py-1 rounded-full text-xs font-bold ${dataset.last_push_at ? 'bg-emerald-100 text-emerald-800 border-emerald-300 hover:bg-emerald-200' : 'bg-teal-100 text-teal-800 border-teal-300 hover:bg-teal-200'} border transition-colors inline-flex items-center gap-1"
                                            title="${dataset.last_push_at ? `Live push configured — sheet edits arrive within seconds (last push: ${new Date(dataset.last_push_at).toLocaleString()})` : `Live Google Sheet${dataset.refresh_interval_minutes ? ` · checks every ${dataset.refresh_interval_minutes} min` : ' · manual refresh only'} — set up instant push via this button`}${dataset.last_refreshed ? ` · last data: ${new Date(dataset.last_refreshed).toLocaleString()}` : ''}">
                                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"
                                                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                                        </svg>
                                        ${dataset.last_push_at ? '⚡ LIVE' : 'LIVE'}
                                    </button>` : ''}
                            </td>
                            <td>
                                <div class="flex gap-2">
                                    <a href="dataset-report.html?id=${dataset.id}" class="text-indigo-600 hover:text-indigo-800" title="Cleaning Report">
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                                        </svg>
                                    </a>
                                    <button onclick="previewDataset(${dataset.id})" class="text-blue-600 hover:text-blue-800" title="Preview">
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                                        </svg>
                                    </button>
                                    <button onclick="useDataset(${dataset.id})" class="text-green-600 hover:text-green-800" title="Use in Query">
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path>
                                        </svg>
                                    </button>
                                    <button onclick="renameDataset(${dataset.id})" class="text-gray-500 hover:text-gray-700" title="Rename">
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                        </svg>
                                    </button>
                                    <button onclick="confirmDelete(${dataset.id})" class="text-red-600 hover:text-red-800" title="Delete">
                                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                        </svg>
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
    
    tableContainer.innerHTML = tableHTML;
}

/**
 * Update statistics cards
 */
function updateStats() {
    const totalDatasets = datasets.length;
    const totalRows = datasets.reduce((sum, d) => sum + (d.row_count || 0), 0);
    const totalColumns = datasets.reduce((sum, d) => sum + (d.column_count || 0), 0);
    
    // Calculate storage from file_size strings (e.g., "1.5 MB")
    let totalBytes = 0;
    datasets.forEach(d => {
        if (d.file_size && typeof d.file_size === 'string') {
            const parts = d.file_size.split(' ');
            if (parts.length === 2) {
                const value = parseFloat(parts[0]);
                const unit = parts[1];
                if (unit === 'MB') totalBytes += value * 1024 * 1024;
                else if (unit === 'KB') totalBytes += value * 1024;
                else if (unit === 'GB') totalBytes += value * 1024 * 1024 * 1024;
                else totalBytes += value;
            }
        }
    });
    
    document.getElementById('totalDatasets').textContent = totalDatasets;
    document.getElementById('totalRows').textContent = formatNumber(totalRows);
    document.getElementById('totalColumns').textContent = totalColumns;
    document.getElementById('storageUsed').textContent = formatFileSize(totalBytes);
}

/**
 * Handle search
 */
function handleSearch(e) {
    const query = e.target.value.toLowerCase();
    
    filteredDatasets = datasets.filter(dataset => 
        (dataset.original_filename || dataset.filename || '').toLowerCase().includes(query)
    );
    
    renderDatasets();
}

/**
 * Handle sort
 */
function handleSort(e) {
    const sortBy = e.target.value;
    
    switch (sortBy) {
        case 'date_desc':
            filteredDatasets.sort((a, b) => new Date(b.upload_date) - new Date(a.upload_date));
            break;
        case 'date_asc':
            filteredDatasets.sort((a, b) => new Date(a.upload_date) - new Date(b.upload_date));
            break;
        case 'name_asc':
            filteredDatasets.sort((a, b) => (a.original_filename || a.filename).localeCompare(b.original_filename || b.filename));
            break;
        case 'name_desc':
            filteredDatasets.sort((a, b) => (b.original_filename || b.filename).localeCompare(a.original_filename || a.filename));
            break;
    }
    
    renderDatasets();
}

/**
 * Preview dataset
 */
// ── Full-data browser (server-side pagination — handles any dataset size) ────

let _fullViewDatasetId = null;
let _fullViewPage = 1;
let _fullViewTotalPages = 1;
let _fullViewTotalRows = 0;
let _fullViewLoadedRows = 0;
let _fullViewCols = [];
let _fullViewLoading = false;
let _fullViewIssuesMode = false;
let _fullViewIssueCount = 0;
let _fullViewEditable = false;
let _fullViewSource = 'raw'; // 'raw' | 'cleaned' — which file edits/deletes land in
let _pendingCellEdits = new Map(); // "row|column" -> new value
let _pendingRowDeletes = new Set();   // row indices staged for deletion (cleaned source only)
let _pendingColDeletes = new Set();   // column names staged for deletion (cleaned source only)
const _FULL_VIEW_PAGE_SIZE = 500; // backend caps page_size at 500

/**
 * Excel/CSV-style infinite scroll: loads rows in batches and appends them as
 * the user scrolls down, instead of paginated Prev/Next buttons.
 */
async function openFullDataView(datasetId) {
    await _openFullDataViewImpl(datasetId, false, 'raw');
}

/**
 * Same infinite-scroll browser, but against the ORIGINAL (pre-cleaning) data
 * with problem cells (missing values, inconsistent text, unparseable
 * numbers/dates — whatever the cleaning plan would fix) highlighted amber.
 */
async function openFullDataViewWithIssues(datasetId) {
    await _openFullDataViewImpl(datasetId, true, 'raw');
}

/**
 * "Review Manually" — same viewer, but against the CLEANED/processed data,
 * highlighting whatever the pipeline couldn't or didn't fix (negative
 * values, outliers, etc). Edits/deletes here change the cleaned copy only —
 * the original file is never touched.
 */
async function openCleanedDataReview(datasetId) {
    await _openFullDataViewImpl(datasetId, true, 'cleaned');
}

async function _openFullDataViewImpl(datasetId, issuesMode, source = 'raw') {
    _fullViewDatasetId = datasetId;
    _fullViewPage = 1;
    _fullViewTotalPages = 1;
    _fullViewTotalRows = 0;
    _fullViewLoadedRows = 0;
    _fullViewCols = [];
    _fullViewLoading = false;
    _fullViewIssuesMode = issuesMode;
    _fullViewIssueCount = 0;
    _fullViewEditable = false;
    _fullViewSource = source;
    _pendingCellEdits = new Map();
    _pendingRowDeletes = new Set();
    _pendingColDeletes = new Set();

    const isCleaned = source === 'cleaned';
    const modal = document.getElementById('previewModal');
    const content = document.getElementById('previewContent');
    modal.classList.remove('hidden');
    content.innerHTML = `
        ${isCleaned ? `<div class="mb-3 flex items-center gap-2 bg-purple-50 border border-purple-200 rounded-lg px-4 py-2.5">
            <svg class="w-5 h-5 text-purple-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <p class="text-sm text-purple-800"><strong>Reviewing the cleaned data.</strong> Edits, and any rows/columns you delete here, change the cleaned copy only — the original file is never touched.</p>
        </div>` : ''}
        <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
            <p class="text-sm text-gray-600" id="fullViewRowCount">Loading rows…</p>
            ${issuesMode ? `<span class="inline-flex items-center gap-3 text-xs font-medium flex-wrap">
                <span class="inline-flex items-center gap-1.5 text-amber-700"><span class="w-3 h-3 rounded-sm" style="background:#fef3c7;border:1px solid #f59e0b;"></span>Cleaning will fix this</span>
                <span class="inline-flex items-center gap-1.5 text-purple-700"><span class="w-3 h-3 rounded-sm" style="background:#f3e8ff;border:1px solid #a855f7;"></span>Flagged — review, not auto-fixed</span>
                <span class="inline-flex items-center gap-1.5 text-red-700"><span class="w-3 h-3 rounded-sm" style="background:#fee2e2;border:1px solid #ef4444;"></span>Problem row</span>
            </span>` : ''}
        </div>
        <div id="fullViewNotices" class="mb-3 space-y-1.5"></div>
        <p class="text-xs text-gray-400 mb-2">Right-click any cell or column header to ask the assistant about it, change its value${isCleaned ? ', or delete the row/column' : ''}.</p>
        <div id="fullViewScroller" class="overflow-auto border border-gray-200 rounded-lg" style="max-height:70vh;">
            <table class="w-full text-sm">
                <thead class="bg-gray-100 sticky top-0" id="fullViewHead"></thead>
                <tbody id="fullViewBody"></tbody>
            </table>
            <p id="fullViewLoadingMore" class="hidden text-center text-xs text-gray-400 py-3">Loading more rows…</p>
        </div>
        <div id="fullViewSaveBar" class="hidden mt-3 flex items-center justify-between gap-3 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2.5">
            <span class="text-sm text-emerald-800"><strong id="fullViewEditCount">0</strong> unsaved change(s)</span>
            <div class="flex gap-2">
                <button type="button" onclick="_discardCellEdits()" class="px-3 py-1.5 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Discard</button>
                <button type="button" onclick="_saveCellEdits()" id="fullViewSaveBtn" class="px-4 py-1.5 text-sm rounded-lg text-white font-semibold" style="background:#0d9488;">Save Changes</button>
            </div>
        </div>`;

    const scroller = document.getElementById('fullViewScroller');
    scroller.addEventListener('scroll', _onFullViewScroll);
    scroller.addEventListener('contextmenu', _onFullViewCellRightClick);
    scroller.addEventListener('contextmenu', _onFullViewHeaderRightClick);

    await _loadNextFullViewPage();
}

function _onFullViewScroll(e) {
    const el = e.target;
    // Fetch the next batch once the user scrolls within ~300px of the bottom.
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 300) {
        _loadNextFullViewPage();
    }
}

async function _loadNextFullViewPage() {
    if (_fullViewLoading) return;
    if (_fullViewPage > 1 && _fullViewPage > _fullViewTotalPages) return; // all rows loaded
    _fullViewLoading = true;

    const rowCountEl = document.getElementById('fullViewRowCount');
    const loadingMoreEl = document.getElementById('fullViewLoadingMore');
    if (_fullViewLoadedRows > 0 && loadingMoreEl) loadingMoreEl.classList.remove('hidden');

    try {
        const endpoint = _fullViewSource === 'cleaned' ? 'cleaned-data-quality' : (_fullViewIssuesMode ? 'data-quality' : 'data');
        const resp = await API.get(
            `/datasets/${_fullViewDatasetId}/${endpoint}?page=${_fullViewPage}&page_size=${_FULL_VIEW_PAGE_SIZE}`, true
        );
        _fullViewTotalPages = resp.total_pages || 1;
        _fullViewTotalRows = resp.total_rows || 0;
        _fullViewEditable = !!resp.editable;
        const rows = resp.rows || [];
        const rowIndices = resp.row_indices || [];

        // Map "rowIndex|column" -> reason, for O(1) highlight lookups per cell.
        const issueMap = new Map();
        (resp.issues || []).forEach(iss => issueMap.set(`${iss.row}|${iss.column}`, iss));
        _fullViewIssueCount += (resp.issues || []).length;

        // Whole-row structural problems (duplicate/empty/header/summary rows).
        const rowIssueMap = new Map();
        (resp.row_issues || []).forEach(ri => rowIssueMap.set(ri.row, ri.reason));
        _fullViewIssueCount += (resp.row_issues || []).length;

        if (_fullViewPage === 1) {
            _fullViewCols = resp.columns || [];
            document.getElementById('fullViewHead').innerHTML =
                `<tr>${_fullViewCols.map(c => `<th class="px-3 py-2 text-left font-semibold border-b whitespace-nowrap" data-col="${_escH(c)}" style="cursor:context-menu;" title="Right-click to apply a change to the whole column">${c}</th>`).join('')}</tr>`;

            const notices = resp.column_notices || [];
            const noticesEl = document.getElementById('fullViewNotices');
            if (noticesEl) {
                noticesEl.innerHTML = notices.map(n => `
                    <div class="text-xs text-indigo-800 bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2">
                        <strong>${_escH(n.column)}:</strong> ${_escH(n.title)} — ${_escH(n.description)}
                    </div>`).join('');
            }
        }

        const body = document.getElementById('fullViewBody');
        const startIdx = _fullViewLoadedRows;
        body.insertAdjacentHTML('beforeend', rows.map((r, i) => {
            const rowIdx = rowIndices[i];
            const rowReason = rowIssueMap.get(rowIdx);
            const markedForDelete = _pendingRowDeletes.has(rowIdx);
            const rowStyle = markedForDelete
                ? ' style="background:#fee2e2;opacity:.5;text-decoration:line-through;"'
                : (rowReason ? ' style="background:#fee2e2;"' : '');
            const rowTitle = markedForDelete
                ? ' title="Marked for deletion — right-click a cell to undo"'
                : (rowReason ? ` title="${rowReason.replace(/"/g, '&quot;')}"` : '');
            return `
            <tr data-row="${rowIdx}" class="${(rowReason || markedForDelete) ? '' : (startIdx + i) % 2 ? 'bg-gray-50' : 'bg-white'}"${rowStyle}${rowTitle}>
                ${_fullViewCols.map(c => {
                    const iss = issueMap.get(`${rowIdx}|${c}`);
                    const reason = iss?.reason;
                    const val = r[c] != null ? r[c] : '<span class="text-gray-300">—</span>';
                    const colMarked = _pendingColDeletes.has(c);
                    const bg = colMarked ? 'background:#fee2e2;opacity:.5;text-decoration:line-through;'
                        : iss ? (iss.tier === 'review' ? 'background:#f3e8ff;' : 'background:#fef3c7;') : '';
                    const attrs = _fullViewEditable
                        ? ` data-row="${rowIdx}" data-col="${_escH(c)}" style="cursor:context-menu;${bg}"`
                        : (bg ? ` style="${bg}"` : '');
                    const titleAttr = reason ? ` title="${reason.replace(/"/g, '&quot;')}"` : '';
                    return `<td class="px-3 py-1.5 border-b border-gray-100 whitespace-nowrap"${attrs}${titleAttr}>${val}</td>`;
                }).join('')}
            </tr>`;
        }).join(''));

        _fullViewLoadedRows += rows.length;
        _fullViewPage += 1;

        if (rowCountEl) {
            rowCountEl.innerHTML = `Showing <strong>${_fullViewLoadedRows.toLocaleString()}</strong> of ` +
                `<strong>${_fullViewTotalRows.toLocaleString()}</strong> rows` +
                (_fullViewIssuesMode ? ` — <strong>${_fullViewIssueCount.toLocaleString()}</strong> issue(s) found so far` : '') +
                (_fullViewLoadedRows < _fullViewTotalRows ? ' — scroll down for more' : '');
        }
    } catch (e) {
        if (rowCountEl) rowCountEl.textContent = `Failed to load data: ${e.message || 'unknown error'}`;
    } finally {
        _fullViewLoading = false;
        if (loadingMoreEl) loadingMoreEl.classList.add('hidden');
    }
}

// ── Per-cell chat editor (right-click any cell) ──────────────────────────────

let _cellChatRow = null;
let _cellChatCol = null;
let _cellChatHistory = []; // [{role, content}]
let _cellChatSuggested = null;

function _onFullViewCellRightClick(e) {
    const td = e.target.closest('td[data-row]');
    if (!td) return; // not an editable cell (e.g. non-editable "cleaned" view)
    e.preventDefault();
    _openCellChatPopover(td);
}

function _closeCellChatPopover() {
    document.getElementById('cellChatPopover')?.remove();
}

function _openCellChatPopover(td) {
    _closeCellChatPopover();

    const row = parseInt(td.dataset.row, 10);
    const col = td.dataset.col;
    _cellChatRow = row;
    _cellChatCol = col;
    _cellChatHistory = [];
    _cellChatSuggested = null;

    const editKey = `${row}|${col}`;
    const currentText = _pendingCellEdits.has(editKey)
        ? _pendingCellEdits.get(editKey)
        : td.textContent.trim();

    const isCleaned = _fullViewSource === 'cleaned';
    const rowMarked = _pendingRowDeletes.has(row);

    const popover = document.createElement('div');
    popover.id = 'cellChatPopover';
    popover.className = 'bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col';
    popover.style.cssText = 'position:fixed; width:320px; max-height:460px; z-index:2000;';
    popover.innerHTML = `
        <div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <div class="min-w-0">
                <p class="text-xs text-gray-400 truncate">${_escH(col)}</p>
                <p class="text-sm font-semibold text-gray-800 truncate" id="cellChatCurrentValue">${_escH(currentText || '(empty)')}</p>
            </div>
            <button type="button" onclick="_closeCellChatPopover()" class="text-gray-400 hover:text-gray-600 flex-shrink-0 ml-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
        <div id="cellChatMessages" class="flex-1 overflow-y-auto px-4 py-3 space-y-2" style="min-height:80px; max-height:220px;">
            <p class="text-xs text-gray-400">Ask what to put here, or just tell me the value — e.g. "set it to North" or "what's wrong with this?"</p>
        </div>
        <div class="px-3 py-2.5 border-t border-gray-100 flex gap-2">
            <input type="text" id="cellChatInput" placeholder="Type a message…"
                   class="flex-1 text-sm border border-gray-300 rounded-lg px-3 py-1.5 outline-none focus:ring-2" style="--tw-ring-color:#5eead4;">
            <button type="button" id="cellChatSendBtn" onclick="_sendCellChatMessage()"
                    class="px-3 py-1.5 text-sm rounded-lg text-white font-semibold" style="background:#0d9488;">Send</button>
        </div>
        ${isCleaned ? `<div class="px-3 pb-2.5 pt-1 border-t border-gray-100">
            <button type="button" onclick="_toggleRowDelete()" class="w-full text-xs font-semibold px-3 py-1.5 rounded-lg border ${rowMarked ? 'border-emerald-300 text-emerald-700 bg-emerald-50' : 'border-red-300 text-red-700 bg-red-50 hover:bg-red-100'}">
                ${rowMarked ? 'Undo — keep this row' : 'Delete this row'}
            </button>
        </div>` : ''}`;
    document.body.appendChild(popover);

    // Position near the cell, clamped inside the viewport.
    const rect = td.getBoundingClientRect();
    const maxLeft = window.innerWidth - 336;
    const maxTop = window.innerHeight - 436;
    popover.style.left = `${Math.max(8, Math.min(rect.left, maxLeft))}px`;
    popover.style.top = `${Math.max(8, Math.min(rect.bottom + 6, maxTop))}px`;

    document.getElementById('cellChatInput').addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') _sendCellChatMessage();
    });
    setTimeout(() => document.getElementById('cellChatInput')?.focus(), 50);

    // Close on outside click (but not on the right-click that opened it).
    setTimeout(() => document.addEventListener('click', _onCellChatOutsideClick), 0);
}

function _onCellChatOutsideClick(e) {
    const popover = document.getElementById('cellChatPopover');
    if (popover && !popover.contains(e.target)) {
        popover.remove();
        document.removeEventListener('click', _onCellChatOutsideClick);
    }
}

async function _sendCellChatMessage() {
    const input = document.getElementById('cellChatInput');
    const sendBtn = document.getElementById('cellChatSendBtn');
    const messages = document.getElementById('cellChatMessages');
    const text = (input?.value || '').trim();
    if (!text || !messages) return;

    messages.insertAdjacentHTML('beforeend',
        `<div class="text-sm bg-gray-100 rounded-lg px-3 py-1.5 ml-6">${_escH(text)}</div>`);
    _cellChatHistory.push({ role: 'user', content: text });
    input.value = '';
    input.disabled = true;
    if (sendBtn) sendBtn.disabled = true;
    messages.insertAdjacentHTML('beforeend',
        `<div id="cellChatThinking" class="text-xs text-gray-400">Thinking…</div>`);
    messages.scrollTop = messages.scrollHeight;

    try {
        const resp = await API.post(`/datasets/${_fullViewDatasetId}/cell-chat`, {
            row: _cellChatRow,
            column: _cellChatCol,
            message: text,
            history: _cellChatHistory,
            source: _fullViewSource,
        }, true);

        document.getElementById('cellChatThinking')?.remove();
        _cellChatHistory.push({ role: 'assistant', content: resp.reply });

        let bubble = `<div class="text-sm bg-teal-50 border border-teal-100 rounded-lg px-3 py-1.5 mr-6">${_escH(resp.reply)}</div>`;
        if (resp.suggested_value !== null && resp.suggested_value !== undefined) {
            _cellChatSuggested = resp.suggested_value;
            bubble += `
                <div class="flex items-center gap-2 mr-6">
                    <span class="text-xs text-gray-500">Suggested: <strong>${_escH(resp.suggested_value)}</strong></span>
                    <button type="button" onclick="_applyCellChatSuggestion()" class="text-xs font-semibold px-2.5 py-1 rounded-md text-white" style="background:#0d9488;">Apply</button>
                </div>`;
        }
        messages.insertAdjacentHTML('beforeend', bubble);
        messages.scrollTop = messages.scrollHeight;
    } catch (e) {
        document.getElementById('cellChatThinking')?.remove();
        messages.insertAdjacentHTML('beforeend',
            `<div class="text-sm bg-red-50 border border-red-100 text-red-700 rounded-lg px-3 py-1.5 mr-6">${_escH(e.message || 'The assistant is unavailable right now.')}</div>`);
        messages.scrollTop = messages.scrollHeight;
    } finally {
        input.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        input.focus();
    }
}

function _applyCellChatSuggestion() {
    if (_cellChatSuggested === null) return;
    _applyCellEdit(_cellChatRow, _cellChatCol, _cellChatSuggested);
    const currentValueEl = document.getElementById('cellChatCurrentValue');
    if (currentValueEl) currentValueEl.textContent = _cellChatSuggested || '(empty)';
}

/** Applies a new value to the cell in the DOM + the pending-edits queue (not saved yet). */
function _applyCellEdit(row, col, value) {
    const key = `${row}|${col}`;
    _pendingCellEdits.set(key, value);

    const candidates = document.querySelectorAll(`#fullViewBody td[data-row="${row}"]`);
    const td = Array.from(candidates).find(el => el.dataset.col === col);
    if (td) {
        td.textContent = value || '';
        td.style.background = '#d1fae5'; // green = edited, pending save
        td.title = 'Edited — not saved yet';
    }
    _updateSaveBar();
}

/** Toggles the currently-open cell popover's row between marked/unmarked for deletion. */
function _toggleRowDelete() {
    if (_cellChatRow === null) return;
    if (_pendingRowDeletes.has(_cellChatRow)) {
        _pendingRowDeletes.delete(_cellChatRow);
    } else {
        _pendingRowDeletes.add(_cellChatRow);
    }
    _closeCellChatPopover();

    const tr = document.querySelector(`#fullViewBody tr[data-row="${_cellChatRow}"]`);
    if (tr) {
        const marked = _pendingRowDeletes.has(_cellChatRow);
        tr.style.background = marked ? '#fee2e2' : '';
        tr.style.opacity = marked ? '.5' : '';
        tr.style.textDecoration = marked ? 'line-through' : '';
        tr.title = marked ? 'Marked for deletion — right-click a cell to undo' : '';
    }
    _updateSaveBar();
}

/** Toggles the currently-open column popover's column between marked/unmarked for deletion. */
function _toggleColumnDelete() {
    if (!_colChatColumn) return;
    const col = _colChatColumn;
    if (_pendingColDeletes.has(col)) {
        _pendingColDeletes.delete(col);
    } else {
        _pendingColDeletes.add(col);
    }
    _closeColumnChatPopover();

    const marked = _pendingColDeletes.has(col);
    document.querySelectorAll('#fullViewBody td[data-col]').forEach(td => {
        if (td.dataset.col !== col) return;
        td.style.background = marked ? '#fee2e2' : '';
        td.style.opacity = marked ? '.5' : '';
        td.style.textDecoration = marked ? 'line-through' : '';
    });
    const th = Array.from(document.querySelectorAll('#fullViewHead th[data-col]')).find(el => el.dataset.col === col);
    if (th) {
        th.style.background = marked ? '#fee2e2' : '';
        th.style.opacity = marked ? '.5' : '';
        th.style.textDecoration = marked ? 'line-through' : '';
    }
    _updateSaveBar();
}

function _updateSaveBar() {
    const bar = document.getElementById('fullViewSaveBar');
    const countEl = document.getElementById('fullViewEditCount');
    if (!bar) return;
    const total = _pendingCellEdits.size + _pendingRowDeletes.size + _pendingColDeletes.size;
    if (total > 0) {
        bar.classList.remove('hidden');
        if (countEl) countEl.textContent = total;
    } else {
        bar.classList.add('hidden');
    }
}

function _discardCellEdits() {
    _pendingCellEdits.clear();
    _pendingRowDeletes.clear();
    _pendingColDeletes.clear();
    // Simplest reliable way to revert cell text/highlights is to reload the view.
    _openFullDataViewImpl(_fullViewDatasetId, _fullViewIssuesMode, _fullViewSource);
}

async function _saveCellEdits() {
    const hasDeletes = _pendingRowDeletes.size > 0 || _pendingColDeletes.size > 0;
    if (_pendingCellEdits.size === 0 && !hasDeletes) return;
    const saveBtn = document.getElementById('fullViewSaveBtn');
    if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }

    const edits = Array.from(_pendingCellEdits.entries()).map(([key, value]) => {
        const sep = key.indexOf('|');
        return { row: parseInt(key.slice(0, sep), 10), column: key.slice(sep + 1), value };
    });

    try {
        const resp = await API.post(`/datasets/${_fullViewDatasetId}/apply-cell-edits`, {
            edits,
            delete_rows: Array.from(_pendingRowDeletes),
            delete_columns: Array.from(_pendingColDeletes),
            source: _fullViewSource,
        }, true);

        const parts = [];
        if (resp.applied) parts.push(`${resp.applied} cell change(s)`);
        if (resp.deleted_rows) parts.push(`${resp.deleted_rows} row(s) deleted`);
        if (resp.deleted_columns) parts.push(`${resp.deleted_columns} column(s) deleted`);
        Notifications.success(`Saved: ${parts.join(', ') || 'no changes'}.`);

        _pendingCellEdits.clear();
        _pendingRowDeletes.clear();
        _pendingColDeletes.clear();

        if (hasDeletes) {
            // Row/column counts changed — reload for a correct, consistent view
            // rather than trying to patch positions/columns in place.
            await _openFullDataViewImpl(_fullViewDatasetId, _fullViewIssuesMode, _fullViewSource);
        } else {
            // Cell-edit-only save: don't reload (would reset infinite scroll
            // back to page 1). DOM already shows the correct values — just
            // clear the "pending" highlight in place.
            document.querySelectorAll('#fullViewBody td[data-row]').forEach(td => {
                td.style.background = '';
                td.title = '';
            });
            _updateSaveBar();
        }
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; }
    } catch (e) {
        Notifications.error(`Failed to save changes: ${e.message || 'unknown error'}`);
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save Changes'; }
    }
}

// ── Per-column chat editor (right-click a column header) ─────────────────────

let _colChatColumn = null;
let _colChatHistory = [];
let _colChatPendingAction = null;

function _onFullViewHeaderRightClick(e) {
    const th = e.target.closest('th[data-col]');
    if (!th) return;
    e.preventDefault();
    _openColumnChatPopover(th);
}

function _closeColumnChatPopover() {
    document.getElementById('columnChatPopover')?.remove();
}

function _openColumnChatPopover(th) {
    _closeCellChatPopover();
    _closeColumnChatPopover();

    const column = th.dataset.col;
    _colChatColumn = column;
    _colChatHistory = [];
    _colChatPendingAction = null;

    const isCleaned = _fullViewSource === 'cleaned';
    const colMarked = _pendingColDeletes.has(column);

    const popover = document.createElement('div');
    popover.id = 'columnChatPopover';
    popover.className = 'bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col';
    popover.style.cssText = 'position:fixed; width:360px; max-height:500px; z-index:2000;';
    popover.innerHTML = `
        <div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <div class="min-w-0">
                <p class="text-xs text-gray-400">Whole column</p>
                <p class="text-sm font-semibold text-gray-800 truncate">${_escH(column)}</p>
            </div>
            <button type="button" onclick="_closeColumnChatPopover()" class="text-gray-400 hover:text-gray-600 flex-shrink-0 ml-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
        <div id="colChatMessages" class="flex-1 overflow-y-auto px-4 py-3 space-y-2" style="min-height:100px; max-height:260px;">
            <p class="text-xs text-gray-400">Ask about this column, or tell me what to do to every cell — e.g. "make all dates the same format" or "trim extra spaces".</p>
        </div>
        <div class="px-3 py-2.5 border-t border-gray-100 flex gap-2">
            <input type="text" id="colChatInput" placeholder="Type a message…"
                   class="flex-1 text-sm border border-gray-300 rounded-lg px-3 py-1.5 outline-none focus:ring-2" style="--tw-ring-color:#5eead4;">
            <button type="button" id="colChatSendBtn" onclick="_sendColumnChatMessage()"
                    class="px-3 py-1.5 text-sm rounded-lg text-white font-semibold" style="background:#0d9488;">Send</button>
        </div>
        ${isCleaned ? `<div class="px-3 pb-2.5 pt-1 border-t border-gray-100">
            <button type="button" onclick="_toggleColumnDelete()" class="w-full text-xs font-semibold px-3 py-1.5 rounded-lg border ${colMarked ? 'border-emerald-300 text-emerald-700 bg-emerald-50' : 'border-red-300 text-red-700 bg-red-50 hover:bg-red-100'}">
                ${colMarked ? 'Undo — keep this column' : 'Delete this column'}
            </button>
        </div>` : ''}`;
    document.body.appendChild(popover);

    const rect = th.getBoundingClientRect();
    const maxLeft = window.innerWidth - 376;
    const maxTop = window.innerHeight - 476;
    popover.style.left = `${Math.max(8, Math.min(rect.left, maxLeft))}px`;
    popover.style.top = `${Math.max(8, Math.min(rect.bottom + 6, maxTop))}px`;

    document.getElementById('colChatInput').addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') _sendColumnChatMessage();
    });
    setTimeout(() => document.getElementById('colChatInput')?.focus(), 50);
    setTimeout(() => document.addEventListener('click', _onColumnChatOutsideClick), 0);
}

function _onColumnChatOutsideClick(e) {
    const popover = document.getElementById('columnChatPopover');
    if (popover && !popover.contains(e.target)) {
        popover.remove();
        document.removeEventListener('click', _onColumnChatOutsideClick);
    }
}

async function _sendColumnChatMessage() {
    const input = document.getElementById('colChatInput');
    const sendBtn = document.getElementById('colChatSendBtn');
    const messages = document.getElementById('colChatMessages');
    const text = (input?.value || '').trim();
    if (!text || !messages) return;

    messages.insertAdjacentHTML('beforeend',
        `<div class="text-sm bg-gray-100 rounded-lg px-3 py-1.5 ml-6">${_escH(text)}</div>`);
    _colChatHistory.push({ role: 'user', content: text });
    input.value = '';
    input.disabled = true;
    if (sendBtn) sendBtn.disabled = true;
    messages.insertAdjacentHTML('beforeend', `<div id="colChatThinking" class="text-xs text-gray-400">Thinking…</div>`);
    messages.scrollTop = messages.scrollHeight;

    try {
        const resp = await API.post(`/datasets/${_fullViewDatasetId}/column-chat`, {
            column: _colChatColumn,
            message: text,
            history: _colChatHistory,
            source: _fullViewSource,
        }, true);

        document.getElementById('colChatThinking')?.remove();
        _colChatHistory.push({ role: 'assistant', content: resp.reply });

        let bubble = `<div class="text-sm bg-teal-50 border border-teal-100 rounded-lg px-3 py-1.5 mr-6">${_escH(resp.reply)}</div>`;

        if (resp.action && resp.preview && !resp.preview.error) {
            _colChatPendingAction = resp.action;
            const { affected_count, examples, unresolved_count } = resp.preview;
            const exampleLines = (examples || [])
                .map(ex => `<div class="text-xs text-gray-500">Row ${ex.row}: <span class="line-through text-gray-400">${_escH(ex.from ?? '(empty)')}</span> → <strong>${_escH(ex.to ?? '(empty)')}</strong></div>`)
                .join('');
            const unresolvedNote = unresolved_count > 0
                ? `<p class="text-xs text-amber-700 mt-1.5">${unresolved_count.toLocaleString()} cell(s) couldn't be confidently converted and will be left as-is.</p>`
                : '';
            bubble += `
                <div class="mr-6 border border-amber-200 bg-amber-50 rounded-lg p-3">
                    <p class="text-xs font-semibold text-amber-800 mb-1.5">Will change ${affected_count.toLocaleString()} cell(s):</p>
                    ${exampleLines || '<p class="text-xs text-gray-400">No differences to preview.</p>'}
                    ${unresolvedNote}
                    <button type="button" onclick="_applyColumnAction()" ${affected_count === 0 ? 'disabled' : ''}
                            class="mt-2 text-xs font-semibold px-3 py-1.5 rounded-md text-white disabled:opacity-40" style="background:#0d9488;">
                        Stage change for the whole column
                    </button>
                </div>`;
        } else if (resp.action && resp.preview && resp.preview.error) {
            bubble += `<div class="text-xs text-red-600 mr-6">Couldn't preview that change: ${_escH(resp.preview.error)}</div>`;
        }

        messages.insertAdjacentHTML('beforeend', bubble);
        messages.scrollTop = messages.scrollHeight;
    } catch (e) {
        document.getElementById('colChatThinking')?.remove();
        messages.insertAdjacentHTML('beforeend',
            `<div class="text-sm bg-red-50 border border-red-100 text-red-700 rounded-lg px-3 py-1.5 mr-6">${_escH(e.message || 'The assistant is unavailable right now.')}</div>`);
        messages.scrollTop = messages.scrollHeight;
    } finally {
        input.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        input.focus();
    }
}

/**
 * Stages every affected cell from a column action into the SAME pending-edits
 * queue single-cell edits use, instead of writing immediately — so the
 * "Save Changes" bar appears here too and nothing is persisted until the
 * user explicitly clicks it.
 */
async function _applyColumnAction() {
    if (!_colChatPendingAction || !_colChatColumn) return;
    const messages = document.getElementById('colChatMessages');
    try {
        const resp = await API.post(`/datasets/${_fullViewDatasetId}/compute-column-diff`, {
            column: _colChatColumn,
            action: _colChatPendingAction,
            source: _fullViewSource,
        }, true);

        (resp.edits || []).forEach(e => _pendingCellEdits.set(`${e.row}|${e.column}`, e.value));

        // Update any already-rendered rows so the change is visible immediately.
        document.querySelectorAll(`#fullViewBody td[data-col]`).forEach(td => {
            if (td.dataset.col !== _colChatColumn) return;
            const key = `${td.dataset.row}|${td.dataset.col}`;
            if (_pendingCellEdits.has(key)) {
                td.textContent = _pendingCellEdits.get(key) || '';
                td.style.background = '#d1fae5';
                td.title = 'Edited — not saved yet';
            }
        });
        _updateSaveBar();

        let note = `Staged ${resp.applied_count.toLocaleString()} cell change(s) in "${_colChatColumn}" — click Save Changes below to persist.`;
        if (resp.unresolved_count > 0) {
            note += ` ${resp.unresolved_count.toLocaleString()} cell(s) couldn't be confidently converted and were left as-is.`;
        }
        if (resp.truncated) {
            note += ` Only the first ${resp.applied_count.toLocaleString()} changes were staged (very large column) — save these, then run the same request again for the rest.`;
        }
        Notifications.success(note);
        _colChatPendingAction = null;
        _closeColumnChatPopover();
    } catch (e) {
        if (messages) {
            messages.insertAdjacentHTML('beforeend',
                `<div class="text-sm bg-red-50 border border-red-100 text-red-700 rounded-lg px-3 py-1.5 mr-6">Failed to apply: ${_escH(e.message || 'unknown error')}</div>`);
            messages.scrollTop = messages.scrollHeight;
        }
    }
}

// ── Live dataset refresh (Google Sheets sources) ─────────────────────────────

let _liveModalDatasetId = null;

function openLiveModal(datasetId) {
    const ds = datasets.find(d => d.id === datasetId);
    if (!ds) return;
    _liveModalDatasetId = datasetId;

    document.getElementById('liveModalName').textContent = ds.original_filename || ds.filename;
    document.getElementById('liveModalMeta').textContent =
        (ds.refresh_interval_minutes
            ? `Auto-refreshes every ${ds.refresh_interval_minutes} min`
            : 'No auto-refresh interval set')
        + (ds.last_refreshed ? ` · last fetched ${new Date(ds.last_refreshed).toLocaleString()}` : '');

    // Build the Apps Script push snippet from this dataset's secret token
    const webhookUrl = `${CONFIG.API_BASE_URL}${CONFIG.API_V1}/datasets/ingest/${ds.ingest_token || 'TOKEN_MISSING'}`;
    document.getElementById('liveModalSnippet').value =
`function push_() {
  UrlFetchApp.fetch("${webhookUrl}",
    { method: "post", muteHttpExceptions: true });
}`;

    const warn = document.getElementById('liveModalWarn');
    warn.textContent = webhookUrl.includes('localhost') || webhookUrl.includes('127.0.0.1')
        ? 'Note: Google can only reach this URL once the app is deployed (or tunneled, e.g. ngrok).'
        : '';

    const btn = document.getElementById('liveModalRefreshBtn');
    btn.onclick = () => refreshLiveDataset(datasetId, btn);

    const modal = document.getElementById('liveModal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeLiveModal() {
    const modal = document.getElementById('liveModal');
    modal?.classList.add('hidden');
    modal?.classList.remove('flex');
    _liveModalDatasetId = null;
}

function copyLiveSnippet() {
    const ta = document.getElementById('liveModalSnippet');
    ta.select();
    navigator.clipboard.writeText(ta.value)
        .then(() => Notifications.success('Code copied — paste it in Apps Script'))
        .catch(() => document.execCommand('copy'));
}

async function refreshLiveDataset(datasetId, btn) {
    if (btn) { btn.disabled = true; btn.style.opacity = '0.5'; }
    try {
        const resp = await API.post(`/datasets/${datasetId}/refresh`, {}, true);
        Notifications.success(resp.message || 'Dataset refreshed from source');
        loadDatasets();
    } catch (e) {
        Notifications.error(e.message || 'Refresh failed — check that the sheet is still shared publicly');
        if (btn) { btn.disabled = false; btn.style.opacity = ''; }
    }
}

// ── Interactive cleaning review: propose -> approve -> apply ─────────────────

let _cleanPlan = null;
let _cleanOverrides = {};
let _cleanDatasetId = null;
let _cleanDeselected = new Set();   // op ids the user unticked (survives re-render)
let _cleanPolicyIdents = null;      // CP-11: identity → {selected, override} from last apply

const _escH = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const _CLEAN_CATEGORY_META = {
    sanitation:    { label: 'Structural fixes',       color: 'text-blue-700 bg-blue-50 border-blue-200' },
    conversion:    { label: 'Type conversion',        color: 'text-indigo-700 bg-indigo-50 border-indigo-200' },
    missing:       { label: 'Missing values',         color: 'text-amber-700 bg-amber-50 border-amber-200' },
    duplicates:    { label: 'Duplicates',             color: 'text-red-700 bg-red-50 border-red-200' },
    normalization: { label: 'Label standardization',  color: 'text-green-700 bg-green-50 border-green-200' },
};

/** Stable op identity, mirrors backend cleaning_plan._op_kind. */
function _opKind(opId, column) {
    if (column != null && opId.endsWith('.' + column)) {
        return opId.slice(0, opId.length - String(column).length - 1);
    }
    return opId;
}
const _opIdent = (op) => _opKind(op.id, op.column) + '|' + (op.column ?? '');

async function openCleaningReview(datasetId) {
    _cleanDatasetId = datasetId;
    _cleanOverrides = {};
    _cleanDeselected = new Set();
    _cleanPolicyIdents = null;
    const modal = document.getElementById('previewModal');
    const content = document.getElementById('previewContent');
    modal.classList.remove('hidden');
    content.innerHTML = '<p class="text-center text-gray-400 py-10">Analyzing your data — building the cleaning plan…</p>';

    try {
        _cleanPlan = await API.get(`/datasets/${datasetId}/cleaning-plan`, true);

        // CP-11: pre-select checkboxes + overrides from the previously applied policy
        const policy = _cleanPlan.applied_policy;
        if (policy) {
            _cleanPolicyIdents = {};
            for (const [oldId, meta] of Object.entries(policy.plan_summary || {})) {
                const key = (meta.kind || _opKind(oldId, meta.column)) + '|' + (meta.column ?? '');
                _cleanPolicyIdents[key] = {
                    selected: (policy.selected_ids || []).includes(oldId),
                    override: (policy.overrides || {})[oldId] || null,
                };
            }
            (_cleanPlan.operations || []).forEach(op => {
                const p = _cleanPolicyIdents[_opIdent(op)];
                if (p) {
                    if (!p.selected) _cleanDeselected.add(op.id);
                    if (p.override) _cleanOverrides[op.id] = p.override;
                }
            });
        }
        _renderCleaningPlan();
    } catch (e) {
        content.innerHTML = `<p class="text-center text-red-500 py-10">Could not build cleaning plan: ${_escH(e.message)}</p>`;
    }
}

/** Is op currently ticked? (default enabled unless explicitly deselected) */
function _opChecked(op) {
    if (_cleanDeselected.has(op.id)) return false;
    return op.enabled !== false;
}

/** CP-11 status badge for an op, given the previously-applied policy. */
function _opStatusBadge(op) {
    if (!_cleanPolicyIdents) return '';
    const p = _cleanPolicyIdents[_opIdent(op)];
    if (!p) {
        return `<span class="ml-2 text-xs font-semibold bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">New</span>`;
    }
    if (p.selected) {
        return `<span class="ml-2 text-xs font-semibold bg-green-100 text-green-700 px-2 py-0.5 rounded-full">Applied ✓</span>`;
    }
    return `<span class="ml-2 text-xs font-semibold bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Skipped</span>`;
}

/**
 * CP-09: per-op choice control. Returns HTML for a <select> (+ optional value
 * input) when the op carries choices (separator / dayfirst) or is a missing/
 * residual op with fill options. Writes the SAME overrides[op.id] the chat does.
 */
function _opChoiceControl(op) {
    const ov = _cleanOverrides[op.id] || {};
    const overr = op.overridable || [];

    // Explicit radio-style choices (CP-01 separator, CP-10 dayfirst)
    if (op.choices && Array.isArray(op.choices.options)) {
        const kind = op.choices.kind;
        const cur = ov.action === kind ? ov.value : (op.choices.options.find(o => o.default) || {}).id;
        const opts = op.choices.options.map(o =>
            `<option value="${_escH(o.id)}" ${o.id === cur ? 'selected' : ''}>${_escH(o.label)}</option>`).join('');
        return `<div class="pl-8 mt-1.5">
            <select onchange="_setOpChoice('${_escH(op.id)}','${_escH(kind)}', this.value)"
                class="text-xs border border-gray-300 rounded-lg px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-400">
                ${opts}
            </select></div>`;
    }

    // Missing / residual ops: a "what to do" dropdown
    const isMissing = op.id.startsWith('missing.');
    if (isMissing && (overr.includes('fill_zero') || overr.includes('fill_value')
                      || overr.includes('drop_rows') || overr.includes('keep_text'))) {
        const cur = ov.action || 'leave';
        const opt = (v, label, on) => `<option value="${v}" ${on ? 'selected' : ''}>${label}</option>`;
        const isNumeric = overr.includes('fill_zero');
        let opts = '';
        opts += opt('leave', isNumeric ? 'Leave blank (recommended)' : 'Fill with "Unknown" (recommended)', cur === 'leave' || (!ov.action));
        if (overr.includes('fill_zero')) opts += opt('fill_zero', 'Fill with 0', cur === 'fill_zero');
        if (overr.includes('fill_value')) opts += opt('fill_value', 'Fill with a value…', cur === 'fill_value');
        if (overr.includes('drop_rows')) opts += opt('drop_rows', 'Drop these rows', cur === 'drop_rows');
        if (overr.includes('keep_text')) opts += opt('keep_text', 'Keep column as text', cur === 'keep_text');
        const valInput = cur === 'fill_value'
            ? `<input type="text" value="${_escH(ov.value ?? '')}" placeholder="value"
                  oninput="_setOpFillValue('${_escH(op.id)}', this.value)"
                  class="text-xs border border-gray-300 rounded-lg px-2 py-1 ml-2 w-28 focus:outline-none focus:ring-1 focus:ring-indigo-400">`
            : '';
        return `<div class="pl-8 mt-1.5 flex items-center">
            <select onchange="_setOpMissing('${_escH(op.id)}', this.value)"
                class="text-xs border border-gray-300 rounded-lg px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-400">
                ${opts}
            </select>${valInput}</div>`;
    }
    return '';
}

// Choice/override setters — all write _cleanOverrides then re-render
function _setOpChoice(opId, kind, value) {
    _cleanOverrides[opId] = { action: kind, value };
    _renderCleaningPlan();
}
function _setOpMissing(opId, value) {
    if (value === 'leave') delete _cleanOverrides[opId];
    else if (value === 'fill_value') _cleanOverrides[opId] = { action: 'fill_value', value: (_cleanOverrides[opId]?.value) || '' };
    else _cleanOverrides[opId] = { action: value };
    _renderCleaningPlan();
}
function _setOpFillValue(opId, value) {
    _cleanOverrides[opId] = { action: 'fill_value', value };   // no re-render (keeps input focus)
}
function _toggleCleanOp(opId, checked) {
    if (checked) _cleanDeselected.delete(opId);
    else _cleanDeselected.add(opId);
}

// ── CH-19: guided review mode state ──────────────────────────────────────────
let _guidedMode = false;
let _guidedIndex = 0;

function _toggleGuidedMode() {
    _guidedMode = !_guidedMode;
    _guidedIndex = 0;
    _renderCleaningPlan();
}

/** CH-19: deliberate "use raw data" — applies with nothing selected. */
function skipCleaningUseRaw() {
    if (!window.confirm(
        'Use the raw data without any cleaning?\n\n' +
        'No values will be changed or filled. You can re-open Review Cleaning at any time — ' +
        'the original file is never modified.')) return;
    _cleanDeselected = new Set((_cleanPlan?.operations || []).map(o => o.id));
    _cleanOverrides = {};
    applyCleaningPlan();
}

function _renderCleaningPlan() {
    const content = document.getElementById('previewContent');
    const ops = _cleanPlan?.operations || [];

    if (ops.length === 0) {
        content.innerHTML = '<p class="text-center text-green-600 py-10 font-semibold">✓ Your data is already clean — no changes proposed.</p>';
        return;
    }

    if (_guidedMode) {
        _renderGuidedCard();
        return;
    }

    // Group by category
    const groups = {};
    ops.forEach((op, i) => {
        (groups[op.category] = groups[op.category] || []).push([op, i]);
    });

    const policy = _cleanPlan.applied_policy;
    const appliedNote = policy
        ? `<div class="mb-4 p-4 bg-green-50 border border-green-100 rounded-xl text-sm text-green-800">
              <strong>Last cleaned ${policy.applied_at ? new Date(policy.applied_at).toLocaleString() : ''}.</strong>
              Re-running is safe — your original file is never modified. Items are marked
              <span class="font-semibold">Applied</span>, <span class="font-semibold">Skipped</span> or
              <span class="font-semibold">New</span>; adjust and apply again.
          </div>`
        : `<div class="mb-4 p-4 bg-indigo-50 border border-indigo-100 rounded-xl text-sm text-indigo-800">
              <strong>${ops.length} change(s) proposed — nothing has been modified yet.</strong>
              Review each one below, untick anything you don't want, pick an option from a dropdown,
              or type an instruction (e.g. <em>"fill missing Revenue with 0"</em>) and click Apply.
          </div>`;
    let html = appliedNote;

    // CH-19: mode switch + explicit raw-data escape hatch
    html += `<div class="flex flex-wrap items-center gap-2 mb-4">
        <button onclick="_toggleGuidedMode()"
            class="text-xs font-bold text-indigo-700 border border-indigo-300 bg-indigo-50 hover:bg-indigo-100 px-4 py-2 rounded-lg">
            🧭 Guide me — one question at a time
        </button>
        <span class="flex-1"></span>
        <button onclick="skipCleaningUseRaw()"
            class="text-xs font-semibold text-gray-500 border border-gray-300 hover:bg-gray-50 px-4 py-2 rounded-lg"
            title="Apply nothing — proceed with the data exactly as uploaded">
            Use raw data (skip cleaning)
        </button>
    </div>`;

    for (const [cat, items] of Object.entries(groups)) {
        const meta = _CLEAN_CATEGORY_META[cat] || { label: cat, color: 'text-gray-700 bg-gray-50 border-gray-200' };
        html += `<div class="mb-4">
            <span class="inline-block text-xs font-bold uppercase tracking-wide px-3 py-1 rounded-full border ${meta.color} mb-2">${meta.label}</span>`;
        for (const [op, i] of items) {
            const ov = _cleanOverrides[op.id];
            const exs = (op.examples || []).slice(0, 3).map(ex => {
                const loc = ex.row ? `Row ${ex.row}` : 'All rows';
                return `<div class="text-xs text-gray-500 font-mono pl-8">
                    ${_escH(loc)} · <span class="font-semibold">${_escH(ex.column)}</span>:
                    <span class="text-red-500 line-through">${_escH(ex.from ?? '(blank)')}</span>
                    → <span class="text-green-600">${_escH(ex.to ?? '(blank)')}</span>
                    ${ex.note ? `<span class="text-gray-400">· ${_escH(ex.note)}</span>` : ''}
                </div>`;
            }).join('');
            const choice = _opChoiceControl(op);
            html += `
            <div class="border border-gray-100 rounded-lg px-4 py-3 mb-1.5 hover:bg-gray-50">
                <label class="flex items-start gap-3 cursor-pointer">
                    <input type="checkbox" id="cleanop-${i}" ${_opChecked(op) ? 'checked' : ''}
                           onchange="_toggleCleanOp('${_escH(op.id)}', this.checked)"
                           class="mt-0.5 w-4 h-4 accent-indigo-600">
                    <span class="flex-1">
                        <span class="text-sm font-semibold text-gray-800">${_escH(op.title)}</span>
                        <span class="text-xs text-gray-400 ml-1">· ${op.affected_count} cell(s)/row(s)</span>
                        ${_opStatusBadge(op)}
                        ${ov ? `<span class="ml-2 text-xs font-semibold bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full">${_escH(ov.action)}${ov.value !== undefined && ov.value !== '' ? ' = ' + _escH(ov.value) : ''}</span>` : ''}
                        <span class="block text-xs text-gray-500 mt-0.5">${_escH(op.description)}</span>
                    </span>
                </label>
                ${exs}
                ${choice}
            </div>`;
        }
        html += `</div>`;
    }

    html += `
        <div class="sticky bottom-0 bg-white border-t border-gray-100 pt-3 mt-4">
            <div class="flex gap-2 mb-2">
                <input id="cleanChatInput" type="text"
                    placeholder='Adjust in plain English — "fill missing Revenue with 0" · "don&#39;t touch Currency" · "keep duplicates" · "drop rows with missing Date"'
                    class="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    onkeydown="if(event.key==='Enter')handleCleanChat()">
                <button onclick="handleCleanChat()"
                    class="bg-gray-800 hover:bg-gray-900 text-white font-semibold px-4 py-2.5 rounded-lg text-sm">Adjust</button>
            </div>
            <p id="cleanChatFeedback" class="text-xs text-gray-400 mb-3"></p>
            <div class="flex gap-3">
                <button onclick="applyCleaningPlan()"
                    class="flex-1 bg-gradient-to-r from-indigo-600 to-indigo-600 hover:from-indigo-700 hover:to-indigo-700
                           text-white font-bold py-3 rounded-xl text-sm shadow">
                    Apply Selected Changes
                </button>
                <button onclick="document.getElementById('previewModal').classList.add('hidden')"
                    class="px-6 py-3 border border-gray-300 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-50">
                    Cancel — change nothing
                </button>
            </div>
        </div>`;

    content.innerHTML = html;
    if (window.lucide) { try { lucide.createIcons(); } catch (_) {} }
}

// ── CH-19: guided one-question-at-a-time review ───────────────────────────────

/** Rephrase an op title as a question with its options as buttons. */
function _guidedQuestion(op) {
    const n = op.affected_count;
    if (op.category === 'quality') {
        return `${op.title} — how should this be treated?`;
    }
    if (op.id.startsWith('missing.') || op.id.startsWith('residual.')) {
        return `"${op.column}" has ${n} value(s) that are blank or couldn't be read — what should happen to them?`;
    }
    if (op.id.startsWith('normalize.')) {
        return `"${op.column}" has ${n} label variant(s) that look like the same thing — merge them?`;
    }
    if (op.id === 'duplicates.remove') {
        return `${n} row(s) are exact duplicates — remove them?`;
    }
    if (op.id.startsWith('convert.')) {
        return `Convert "${op.column}" (${n} value(s)) as proposed?`;
    }
    return `${op.title} (${n} cell(s)/row(s)) — apply this fix?`;
}

function _guidedSetAndNext(fn) {
    fn();
    if (_guidedIndex < (_cleanPlan?.operations || []).length - 1) _guidedIndex++;
    _renderCleaningPlan();
}
function guidedAccept(opId) {
    _guidedSetAndNext(() => _cleanDeselected.delete(opId));
}
function guidedSkip(opId) {
    _guidedSetAndNext(() => { _cleanDeselected.add(opId); delete _cleanOverrides[opId]; });
}
function guidedChoose(opId, action, value) {
    _guidedSetAndNext(() => {
        _cleanDeselected.delete(opId);
        if (action === 'leave') delete _cleanOverrides[opId];
        else _cleanOverrides[opId] = value !== undefined ? { action, value } : { action };
    });
}
function guidedChooseFillValue(opId) {
    const v = window.prompt('Fill the blanks with what value?');
    if (v === null) return;
    guidedChoose(opId, 'fill_value', v);
}
function guidedNav(delta) {
    const max = (_cleanPlan?.operations || []).length - 1;
    _guidedIndex = Math.max(0, Math.min(max, _guidedIndex + delta));
    _renderCleaningPlan();
}

function _renderGuidedCard() {
    const content = document.getElementById('previewContent');
    const ops = _cleanPlan.operations;
    const op = ops[_guidedIndex];
    const total = ops.length;
    const ov = _cleanOverrides[op.id];
    const checked = _opChecked(op);

    const exs = (op.examples || []).slice(0, 5).map(ex => `
        <div class="text-xs text-gray-500 font-mono">
            ${ex.row != null ? `Row ${_escH(ex.row)}` : 'All rows'} ·
            <span class="font-semibold">${_escH(ex.column)}</span>:
            <span class="text-red-500 line-through">${_escH(ex.from ?? '(blank)')}</span>
            → <span class="text-green-600">${_escH(ex.to ?? '(blank)')}</span>
        </div>`).join('');

    // Option buttons: mirror exactly what the checkbox/dropdown UI can do
    const overr = op.overridable || [];
    const btn = (label, onclick, style = 'border-gray-300 text-gray-700 hover:bg-gray-50') =>
        `<button onclick="${onclick}" class="text-sm font-semibold border ${style} px-4 py-2.5 rounded-xl">${label}</button>`;
    let options = '';
    if (op.category === 'quality') {
        options += btn('Leave as is (just flag) — recommended', `guidedSkip('${_escH(op.id)}')`,
                       'border-indigo-400 text-indigo-700 bg-indigo-50 hover:bg-indigo-100');
    } else if (op.id.startsWith('missing.')) {
        const isNumeric = overr.includes('fill_zero');
        options += btn(isNumeric ? 'Leave blank (recommended)' : 'Fill with "Unknown" (recommended)',
                       `guidedChoose('${_escH(op.id)}','leave')`,
                       'border-indigo-400 text-indigo-700 bg-indigo-50 hover:bg-indigo-100');
        if (overr.includes('fill_zero'))  options += btn('Fill with 0', `guidedChoose('${_escH(op.id)}','fill_zero')`);
        if (overr.includes('fill_value')) options += btn('Fill with a value…', `guidedChooseFillValue('${_escH(op.id)}')`);
        if (overr.includes('drop_rows'))  options += btn('Drop these rows', `guidedChoose('${_escH(op.id)}','drop_rows')`);
        if (overr.includes('keep_text'))  options += btn('Keep column as text', `guidedChoose('${_escH(op.id)}','keep_text')`);
        options += btn('Skip this fix', `guidedSkip('${_escH(op.id)}')`);
    } else if (op.choices && Array.isArray(op.choices.options)) {
        op.choices.options.forEach(o => {
            options += btn(_escH(o.label) + (o.default ? ' (recommended)' : ''),
                           `guidedChoose('${_escH(op.id)}','${_escH(op.choices.kind)}','${_escH(o.id)}')`,
                           o.default ? 'border-indigo-400 text-indigo-700 bg-indigo-50 hover:bg-indigo-100' : undefined);
        });
        options += btn('Skip this fix', `guidedSkip('${_escH(op.id)}')`);
    } else {
        options += btn('Yes, apply it (recommended)', `guidedAccept('${_escH(op.id)}')`,
                       'border-indigo-400 text-indigo-700 bg-indigo-50 hover:bg-indigo-100');
        options += btn('Skip this fix', `guidedSkip('${_escH(op.id)}')`);
    }
    // Manual cell fixing for value-level ops with a known column
    if (op.column && !op.id.startsWith('sanitation.')) {
        options += btn('✍ Fix cells myself', `guidedOpenManualEditor('${_escH(op.id)}')`,
                       'border-amber-400 text-amber-700 bg-amber-50 hover:bg-amber-100');
    }

    const currentState = _cleanDeselected.has(op.id)
        ? '<span class="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full font-semibold">currently: skipped</span>'
        : ov
        ? `<span class="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-semibold">currently: ${_escH(ov.action)}${ov.value !== undefined && ov.value !== '' ? ' = ' + _escH(String(ov.value)) : ''}</span>`
        : checked
        ? '<span class="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-semibold">currently: will apply (default)</span>'
        : '<span class="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full font-semibold">currently: off by default</span>';

    content.innerHTML = `
        <div class="flex items-center justify-between mb-4">
            <button onclick="_toggleGuidedMode()" class="text-xs font-semibold text-gray-500 hover:text-gray-800">← Back to full list</button>
            <span class="text-xs text-gray-400 font-semibold">Question ${_guidedIndex + 1} of ${total}</span>
            <button onclick="skipCleaningUseRaw()" class="text-xs font-semibold text-gray-400 hover:text-gray-600">Use raw data</button>
        </div>
        <div class="w-full bg-gray-100 rounded-full h-1.5 mb-6">
            <div class="bg-indigo-500 h-1.5 rounded-full" style="width:${Math.round(((_guidedIndex + 1) / total) * 100)}%"></div>
        </div>
        <div class="border border-gray-200 rounded-2xl p-6 mb-4">
            <p class="text-base font-bold text-gray-800 mb-1">${_escH(_guidedQuestion(op))}</p>
            <p class="text-sm text-gray-500 mb-1">${_escH(op.description || '')}</p>
            <div class="mb-3">${currentState}</div>
            <div class="space-y-1 mb-4">${exs}</div>
            <div class="flex flex-wrap gap-2">${options}</div>
            <div id="guidedManualEditor" class="mt-4"></div>
        </div>
        <div class="flex items-center gap-3">
            <button onclick="guidedNav(-1)" ${_guidedIndex === 0 ? 'disabled' : ''}
                class="px-5 py-2.5 border border-gray-300 rounded-xl text-sm font-semibold text-gray-600 disabled:opacity-40 hover:bg-gray-50">← Back</button>
            <button onclick="guidedNav(1)" ${_guidedIndex >= total - 1 ? 'disabled' : ''}
                class="px-5 py-2.5 border border-gray-300 rounded-xl text-sm font-semibold text-gray-600 disabled:opacity-40 hover:bg-gray-50">Next →</button>
            <span class="flex-1"></span>
            <button onclick="applyCleaningPlan()"
                class="bg-gradient-to-r from-indigo-600 to-indigo-600 hover:from-indigo-700 hover:to-indigo-700 text-white font-bold px-8 py-2.5 rounded-xl text-sm shadow">
                Finish — apply my answers
            </button>
        </div>`;
}

/** CH-19: inline cell editor — user's literal values become a manual_edits override. */
async function guidedOpenManualEditor(opId) {
    const box = document.getElementById('guidedManualEditor');
    if (!box) return;
    box.innerHTML = '<p class="text-xs text-gray-400">Loading affected cells…</p>';
    try {
        const resp = await API.get(`/datasets/${_cleanDatasetId}/cells?op_id=${encodeURIComponent(opId)}&limit=50`, true);
        const cells = resp.cells || [];
        if (!cells.length) { box.innerHTML = '<p class="text-xs text-gray-400">No editable cells found for this fix.</p>'; return; }
        const existing = (_cleanOverrides[opId]?.action === 'manual_edits')
            ? Object.fromEntries((_cleanOverrides[opId].edits || []).map(e => [`${e.row}|${e.column}`, e.value]))
            : {};
        box.innerHTML = `
            <div class="border border-amber-200 bg-amber-50 rounded-xl p-4">
                <p class="text-xs font-bold text-amber-800 mb-2">
                    Type the correct value for each cell (leave a box empty to leave that cell alone).
                    ${resp.total_affected > cells.length ? `Showing ${cells.length} of ${resp.total_affected} affected cells.` : ''}
                </p>
                <div class="max-h-56 overflow-y-auto space-y-1.5 mb-3">
                    ${cells.map(c => `
                        <div class="flex items-center gap-2 text-xs font-mono">
                            <span class="text-gray-500 w-16 flex-shrink-0">Row ${_escH(c.row)}</span>
                            <span class="font-semibold text-gray-700 w-28 flex-shrink-0 truncate">${_escH(c.column)}</span>
                            <span class="text-red-500 line-through truncate max-w-28">${_escH(c.from ?? '(blank)')}</span>
                            <input type="text" data-row="${_escH(c.row)}" data-col="${_escH(c.column)}"
                                   value="${_escH(existing[`${c.row}|${c.column}`] ?? '')}"
                                   placeholder="correct value"
                                   class="guided-cell-input flex-1 border border-amber-300 rounded-lg px-2 py-1 bg-white">
                        </div>`).join('')}
                </div>
                <button onclick="guidedSaveManualEdits('${_escH(opId)}')"
                    class="text-xs font-bold bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded-lg">
                    Save my fixes
                </button>
            </div>`;
    } catch (e) {
        box.innerHTML = `<p class="text-xs text-red-500">Could not load cells: ${_escH(e.message)}</p>`;
    }
}

function guidedSaveManualEdits(opId) {
    const inputs = document.querySelectorAll('#guidedManualEditor .guided-cell-input');
    const edits = [];
    inputs.forEach(inp => {
        const v = inp.value.trim();
        if (v !== '') edits.push({ row: parseInt(inp.dataset.row, 10), column: inp.dataset.col, value: v });
    });
    if (!edits.length) { Notifications.error('Type at least one corrected value first.'); return; }
    _cleanOverrides[opId] = { action: 'manual_edits', edits };
    _cleanDeselected.delete(opId);
    Notifications.success(`${edits.length} manual fix(es) recorded — they'll apply with the plan`);
    _renderCleaningPlan();
}

/** Rule-based English instruction parser for the cleaning plan. */
function handleCleanChat() {
    const input = document.getElementById('cleanChatInput');
    const fb = document.getElementById('cleanChatFeedback');
    const raw = (input?.value || '').trim();
    if (!raw || !_cleanPlan) return;
    const cmd = raw.toLowerCase();
    const ops = _cleanPlan.operations;

    const columns = [...new Set(ops.map(o => o.column).filter(Boolean))];
    const findColumn = () => columns.find(c => cmd.includes(c.toLowerCase()));
    // deselect/select via the state set (survives re-render) instead of DOM
    const setSelected = (pred, val) => {
        let n = 0;
        ops.forEach(op => {
            if (pred(op)) { if (val) _cleanDeselected.delete(op.id); else _cleanDeselected.add(op.id); n++; }
        });
        return n;
    };

    let msg = null, changed = false;
    const col = findColumn();

    if (/keep|leave|don'?t\s+(remove|delete)/.test(cmd) && /duplicate/.test(cmd)) {
        setSelected(op => op.id === 'duplicates.remove', false);
        msg = '✓ Duplicates will be kept.'; changed = true;
    } else if (/fill\s+missing/.test(cmd) && col) {
        const zeroMatch = /with\s+(0|zero)\b/.test(cmd);
        const valMatch = raw.match(/with\s+["']?([^"']+?)["']?\s*$/i);
        const op = ops.find(o => o.id.startsWith('missing.') && o.column === col);
        if (op) {
            if (zeroMatch) _cleanOverrides[op.id] = { action: 'fill_zero' };
            else if (valMatch) _cleanOverrides[op.id] = { action: 'fill_value', value: valMatch[1].trim() };
            msg = `✓ Missing values in "${col}" will be filled with ${zeroMatch ? '0' : '"' + (valMatch ? valMatch[1].trim() : 'Unknown') + '"'}.`;
            changed = true;
        } else {
            msg = `"${col}" has no missing values to fill.`;
        }
    } else if (/(drop|remove|delete)\s+rows?/.test(cmd) && /missing|blank|empty/.test(cmd) && col) {
        const op = ops.find(o => o.id.startsWith('missing.') && o.column === col);
        if (op) {
            _cleanOverrides[op.id] = { action: 'drop_rows' };
            msg = `✓ Rows with missing "${col}" will be removed.`; changed = true;
        } else {
            msg = `"${col}" has no missing values.`;
        }
    } else if (/(day.?first|day\s*\/?\s*month|dd.?mm)/.test(cmd) && col) {
        const op = ops.find(o => o.id.startsWith('convert.datetime.') && o.column === col);
        if (op) { _cleanOverrides[op.id] = { action: 'dayfirst', value: 'day' }; msg = `✓ "${col}" read as day/month.`; changed = true; }
        else msg = `"${col}" is not a date column.`;
    } else if (/(month.?first|month\s*\/?\s*day|mm.?dd)/.test(cmd) && col) {
        const op = ops.find(o => o.id.startsWith('convert.datetime.') && o.column === col);
        if (op) { _cleanOverrides[op.id] = { action: 'dayfirst', value: 'month' }; msg = `✓ "${col}" read as month/day.`; changed = true; }
        else msg = `"${col}" is not a date column.`;
    } else if (/(don'?t|do not|skip|leave|ignore|exclude)/.test(cmd) && col) {
        const n = setSelected(op => op.column === col, false);
        Object.keys(_cleanOverrides).forEach(k => {
            const op = ops.find(o => o.id === k);
            if (op && op.column === col) delete _cleanOverrides[k];
        });
        msg = `✓ "${col}" will not be touched (${n} operation(s) unticked).`; changed = true;
    } else if (/(select|enable|apply|check)\s+(all|everything)/.test(cmd)) {
        setSelected(() => true, true); msg = '✓ All operations selected.'; changed = true;
    } else if (/(unselect|deselect|uncheck|disable)\s+(all|everything)/.test(cmd)) {
        setSelected(() => true, false); msg = '✓ All operations unticked — nothing will change unless you re-tick.'; changed = true;
    } else {
        msg = 'Not understood. Try: "fill missing Revenue with 0" · "drop rows with missing Date" · "don\'t touch Currency" · "keep duplicates" · "deselect all"';
    }

    if (input && msg.startsWith('✓')) input.value = '';
    if (changed) _renderCleaningPlan();
    const fb2 = document.getElementById('cleanChatFeedback');
    if (fb2) fb2.textContent = msg;
    else if (fb) fb.textContent = msg;
}

async function applyCleaningPlan() {
    if (!_cleanPlan || !_cleanDatasetId) return;
    const ops = _cleanPlan.operations;
    const selected = ops.filter(op => _opChecked(op)).map(op => op.id);
    // Overridden ops must be included even if unticked (e.g. a fill choice)
    Object.keys(_cleanOverrides).forEach(id => { if (!selected.includes(id)) selected.push(id); });

    const content = document.getElementById('previewContent');
    content.innerHTML = '<p class="text-center text-gray-400 py-10">Applying approved changes…</p>';

    try {
        const resp = await API.post(`/datasets/${_cleanDatasetId}/cleaning-apply`, {
            plan: _cleanPlan,
            selected_ids: selected,
            overrides: _cleanOverrides,
        }, true);
        content.innerHTML = `
            <div class="text-center py-8">
                <p class="mb-2"><i data-lucide="check-circle-2" style="width:34px;height:34px;color:#16A34A;"></i></p>
                <p class="font-bold text-gray-800 mb-3">${_escH(resp.message)} — ${resp.rows} rows · ${resp.columns} columns</p>
                <div class="text-left max-w-lg mx-auto text-sm text-gray-600 space-y-1">
                    ${Object.values(resp.actions || {}).map(a => `<p>• ${_escH(a)}</p>`).join('')}
                </div>
            </div>`;
        Notifications.success('Cleaning applied');
        loadDatasets();
    } catch (e) {
        content.innerHTML = `<p class="text-center text-red-500 py-10">Apply failed: ${_escH(e.message)}</p>`;
    }
}

/** Marks one preview-modal action button "active" (solid fill) and un-marks the rest. */
function _setActivePreviewBtn(btn) {
    document.querySelectorAll('.preview-action-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
}

async function previewDataset(datasetId) {
    _fullViewDatasetId = datasetId;
    const modal = document.getElementById('previewModal');
    const previewContent = document.getElementById('previewContent');

    // Fresh dataset preview — no view button should look "active" yet.
    document.querySelectorAll('.preview-action-btn').forEach(b => b.classList.remove('active'));

    const reviewCleanedBtn = document.getElementById('reviewCleanedBtn');
    if (reviewCleanedBtn) {
        const ds = datasets.find(d => d.id === datasetId);
        const hasCleanedCopy = !!ds?.cleaned_status;
        reviewCleanedBtn.disabled = !hasCleanedCopy;
        reviewCleanedBtn.title = hasCleanedCopy
            ? 'Review the cleaned data for anything cleaning couldn\'t fix'
            : 'Run Review Cleaning first — no cleaned copy exists yet';
    }

    modal.classList.remove('hidden');
    Loading.showInline('previewContent', 'Loading preview...');
    
    try {
        // Fetch preview from API
        const response = await API.get(`/datasets/${datasetId}/preview`, true);
        
        // Build preview HTML with data table
        const columns = response.column_names || [];
        const rows = response.preview_rows || [];
        const dataTypes = response.data_types || {};
        const dataQuality = response.data_quality || null;
        
        // Build data quality section
        let qualityHTML = '';
        if (dataQuality) {
            const missing = dataQuality.missing_values || {};
            const duplicates = dataQuality.duplicates || {};
            const outliers = dataQuality.outliers || {};
            
            qualityHTML = `
                <div class="mb-4 p-4 bg-gray-50 rounded-lg">
                    <h4 class="font-semibold text-lg mb-3">Data Quality Analysis</h4>
                    <div class="grid grid-cols-3 gap-4 text-sm">
                        <div class="bg-white p-3 rounded shadow-sm">
                            <div class="text-gray-600 mb-1">Missing Values</div>
                            <div class="text-2xl font-bold ${missing.missing_percentage > 5 ? 'text-red-600' : 'text-green-600'}">
                                ${missing.missing_percentage || 0}%
                            </div>
                            <div class="text-xs text-gray-500">
                                ${missing.total_missing_cells || 0} cells affected
                            </div>
                            ${missing.columns_affected > 0 ? `
                                <div class="mt-2 text-xs">
                                    <strong>${missing.columns_affected} columns:</strong>
                                    ${Object.entries(missing.columns_with_missing || {}).slice(0, 3).map(([col, info]) => 
                                        `<div>${col}: ${info.percentage}%</div>`
                                    ).join('')}
                                    ${Object.keys(missing.columns_with_missing || {}).length > 3 ? 
                                        `<div class="text-gray-400">...and ${Object.keys(missing.columns_with_missing).length - 3} more</div>` : 
                                        ''}
                                </div>
                            ` : ''}
                        </div>
                        <div class="bg-white p-3 rounded shadow-sm">
                            <div class="text-gray-600 mb-1">Duplicate Rows</div>
                            <div class="text-2xl font-bold ${duplicates.duplicate_percentage > 5 ? 'text-orange-600' : 'text-green-600'}">
                                ${duplicates.duplicate_percentage || 0}%
                            </div>
                            <div class="text-xs text-gray-500">
                                ${duplicates.duplicate_rows || 0} duplicates found
                            </div>
                        </div>
                        <div class="bg-white p-3 rounded shadow-sm">
                            <div class="text-gray-600 mb-1">Outliers Detected</div>
                            <div class="text-2xl font-bold ${Object.keys(outliers).length > 0 ? 'text-yellow-600' : 'text-green-600'}">
                                ${Object.keys(outliers).length || 0}
                            </div>
                            <div class="text-xs text-gray-500">
                                columns with outliers
                            </div>
                            ${Object.keys(outliers).length > 0 ? `
                                <div class="mt-2 text-xs">
                                    ${Object.entries(outliers).slice(0, 2).map(([col, info]) => 
                                        `<div>${col}: ${info.count} (${info.percentage}%)</div>`
                                    ).join('')}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                    ${missing.missing_percentage > 0 || duplicates.duplicate_percentage > 0 ? `
                        <div class="mt-3">
                            <button onclick="processDataset(${datasetId})" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                                Clean This Dataset
                            </button>
                            <span class="ml-2 text-xs text-gray-600">
                                This will handle missing values and remove duplicates
                            </span>
                        </div>
                    ` : ''}
                </div>
            `;
        }
        
        previewContent.innerHTML = `
            <div class="mb-4">
                <h4 class="font-semibold text-lg mb-2">Dataset Information</h4>
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div><strong>Rows:</strong> ${response.row_count}</div>
                    <div><strong>Columns:</strong> ${response.column_count}</div>
                </div>
            </div>
            ${qualityHTML}
            <div class="mb-4">
                <h4 class="font-semibold text-lg mb-2">Column Types</h4>
                <div class="flex flex-wrap gap-2">
                    ${columns.map(col => {
                        const type = dataTypes[col] || 'unknown';
                        const colorClass = 
                            type === 'numeric' ? 'bg-blue-100 text-blue-800' :
                            type === 'categorical' ? 'bg-indigo-100 text-indigo-800' :
                            type === 'datetime' ? 'bg-green-100 text-green-800' :
                            type === 'boolean' ? 'bg-yellow-100 text-yellow-800' :
                            'bg-gray-100 text-gray-800';
                        return `
                            <span class="inline-block px-3 py-1 ${colorClass} rounded-full text-sm">
                                ${col}: ${type}
                            </span>
                        `;
                    }).join('')}
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-lg mb-2">Preview (First 100 rows)</h4>
                <div class="overflow-x-auto" style="max-height: 400px;">
                    <table class="w-full border-collapse">
                        <thead class="bg-gray-100 sticky top-0">
                            <tr>
                                ${columns.map(col => `<th class="border px-3 py-2 text-left text-sm">${col}</th>`).join('')}
                            </tr>
                        </thead>
                        <tbody>
                            ${rows.map(row => `
                                <tr class="hover:bg-gray-50">
                                    ${columns.map(col => `<td class="border px-3 py-2 text-sm">${row[col] !== null && row[col] !== undefined ? row[col] : '<span class="text-gray-400 italic">null</span>'}</td>`).join('')}
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        
    } catch (error) {
        previewContent.innerHTML = `
            <div class="alert alert-error">
                Failed to load preview: ${error.message}
            </div>
        `;
    }
}

/**
 * View cleaning report for a cleaned dataset
 */
async function viewCleaningReport(datasetId) {
    const modal = document.getElementById('previewModal');
    const previewContent = document.getElementById('previewContent');
    
    modal.classList.remove('hidden');
    Loading.showInline('previewContent', 'Loading cleaning report...');
    
    try {
        const response = await API.get(`/datasets/${datasetId}/cleaning-report`, true);
        
        const report = response || {};
        const before = report.before_cleaning || {};
        const after = report.after_cleaning || {};
        const improvements = report.improvements || {};
        const actions = report.actions_taken || {};
        
        previewContent.innerHTML = `
            <div class="mb-4">
                <h4 class="font-semibold text-lg mb-3">Data Cleaning Report</h4>
                <p class="text-sm text-gray-600 mb-4">This dataset was cleaned on ${formatDate(report.processed_at || new Date())}</p>
            </div>
            
            <div class="mb-4">
                <h5 class="font-semibold mb-3">Before vs After</h5>
                <div class="grid grid-cols-2 gap-4">
                    <div class="bg-gray-50 p-4 rounded">
                        <h6 class="font-semibold mb-2 text-gray-700">Before Cleaning</h6>
                        <div class="text-sm space-y-1">
                            <div><strong>Rows:</strong> ${before.total_rows || 0}</div>
                            <div><strong>Columns:</strong> ${before.total_columns || 0}</div>
                            <div><strong>Missing Cells:</strong> ${before.total_missing_cells || 0} (${before.missing_percentage || 0}%)</div>
                            <div><strong>Duplicates:</strong> ${before.duplicate_rows || 0}</div>
                        </div>
                    </div>
                    <div class="bg-green-50 p-4 rounded">
                        <h6 class="font-semibold mb-2 text-green-700">After Cleaning</h6>
                        <div class="text-sm space-y-1">
                            <div><strong>Rows:</strong> ${after.total_rows || 0}</div>
                            <div><strong>Columns:</strong> ${after.total_columns || 0}</div>
                            <div><strong>Missing Cells:</strong> ${after.total_missing_cells || 0} (${after.missing_percentage || 0}%)</div>
                            <div><strong>Duplicates:</strong> ${after.duplicate_rows || 0}</div>
                        </div>
                    </div>
                </div>
            </div>
            
            ${improvements && Object.keys(improvements).length > 0 ? `
                <div class="mb-4 bg-blue-50 p-4 rounded">
                    <h6 class="font-semibold mb-2 text-blue-800">Improvements</h6>
                    <div class="text-sm space-y-1">
                        ${improvements.missing_cells_reduced !== undefined ? `<div>Missing cells reduced: ${improvements.missing_cells_reduced}</div>` : ''}
                        ${improvements.duplicate_rows_removed !== undefined ? `<div>Duplicate rows removed: ${improvements.duplicate_rows_removed}</div>` : ''}
                        ${improvements.rows_removed !== undefined ? `<div>Total rows removed: ${improvements.rows_removed}</div>` : ''}
                    </div>
                </div>
            ` : ''}
            
            ${Object.keys(actions).length > 0 ? `
                <div class="mb-4">
                    <h6 class="font-semibold mb-2">Actions Taken by Column</h6>
                    <div class="text-sm space-y-2 max-h-64 overflow-y-auto">
                        ${Object.entries(actions).map(([column, action]) => `
                            <div class="bg-gray-50 p-2 rounded">
                                <strong class="text-gray-700">${column}:</strong> 
                                <span class="text-gray-600">${action}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
            
            <div class="flex gap-2">
                <button onclick="previewDataset(${datasetId})" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                    View Dataset Preview
                </button>
                <button onclick="document.getElementById('previewModal').classList.add('hidden')" class="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400">
                    Close
                </button>
            </div>
        `;
        
    } catch (error) {
        console.error('Error loading cleaning report:', error);
        previewContent.innerHTML = `
            <div class="alert alert-error">
                Failed to load cleaning report: ${error.message}
            </div>
            <button onclick="document.getElementById('previewModal').classList.add('hidden')" 
                    class="mt-4 px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400">
                Close
            </button>
        `;
    }
}

/**
 * Process dataset with cleaning
 */
async function processDataset(datasetId) {
    if (!confirm('Clean this dataset? This will handle missing values and remove duplicates.')) {
        return;
    }
    
    const modal = document.getElementById('previewModal');
    const previewContent = document.getElementById('previewContent');
    
    Loading.showInline('previewContent', 'Processing dataset...');
    
    try {
        // Process with auto strategy
        const response = await API.post(`/datasets/${datasetId}/process`, {
            clean_data: true,
            cleaning_strategy: 'auto'
        }, true);
        
        if (response.success) {
            Notifications.success('Dataset cleaned successfully!');
            
            // Show cleaning report
            const report = response.cleaning_report || {};
            const before = report.before_cleaning || {};
            const after = report.after_cleaning || {};
            const improvements = report.improvements || {};
            const actions = report.actions_taken || {};
            
            previewContent.innerHTML = `
                <div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
                    <h4 class="font-semibold text-lg text-green-800 mb-2">✓ Dataset Cleaned Successfully</h4>
                    <p class="text-sm text-green-700">Your dataset has been processed and cleaned.</p>
                </div>
                
                <div class="mb-4">
                    <h4 class="font-semibold text-lg mb-3">Cleaning Summary</h4>
                    <div class="grid grid-cols-2 gap-4">
                        <div class="bg-gray-50 p-4 rounded">
                            <h5 class="font-semibold mb-2 text-gray-700">Before Cleaning</h5>
                            <div class="text-sm space-y-1">
                                <div><strong>Rows:</strong> ${before.total_rows || 0}</div>
                                <div><strong>Columns:</strong> ${before.total_columns || 0}</div>
                                <div><strong>Missing Cells:</strong> ${before.total_missing_cells || 0} (${before.missing_percentage || 0}%)</div>
                                <div><strong>Duplicates:</strong> ${before.duplicate_rows || 0}</div>
                            </div>
                        </div>
                        <div class="bg-green-50 p-4 rounded">
                            <h5 class="font-semibold mb-2 text-green-700">After Cleaning</h5>
                            <div class="text-sm space-y-1">
                                <div><strong>Rows:</strong> ${after.total_rows || 0}</div>
                                <div><strong>Columns:</strong> ${after.total_columns || 0}</div>
                                <div><strong>Missing Cells:</strong> ${after.total_missing_cells || 0} (${after.missing_percentage || 0}%)</div>
                                <div><strong>Duplicates:</strong> ${after.duplicate_rows || 0}</div>
                            </div>
                        </div>
                    </div>
                </div>
                
                ${improvements ? `
                    <div class="mb-4 bg-blue-50 p-4 rounded">
                        <h5 class="font-semibold mb-2 text-blue-800">Improvements</h5>
                        <div class="text-sm space-y-1">
                            <div>Missing cells reduced: ${improvements.missing_cells_reduced || 0}</div>
                            <div>Duplicate rows removed: ${improvements.duplicate_rows_removed || 0}</div>
                        </div>
                    </div>
                ` : ''}
                
                ${Object.keys(actions).length > 0 ? `
                    <div class="mb-4">
                        <h5 class="font-semibold mb-2">Actions Taken</h5>
                        <div class="text-sm space-y-2">
                            ${Object.entries(actions).map(([column, action]) => `
                                <div class="bg-gray-50 p-2 rounded">
                                    <strong>${column}:</strong> ${action}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
                
                <div class="flex gap-2">
                    <button onclick="previewDataset(${datasetId})" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                        View Updated Preview
                    </button>
                    <button onclick="document.getElementById('previewModal').classList.add('hidden')" class="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400">
                        Close
                    </button>
                </div>
            `;
            
            // Reload datasets to update the list
            await loadDatasets();
        } else {
            throw new Error(response.message || 'Processing failed');
        }
        
    } catch (error) {
        console.error('Error processing dataset:', error);
        Notifications.error(`Failed to process dataset: ${error.message}`);
        
        previewContent.innerHTML = `
            <div class="alert alert-error">
                Failed to process dataset: ${error.message}
            </div>
            <button onclick="previewDataset(${datasetId})" class="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                Back to Preview
            </button>
        `;
    }
}

/**
 * Use dataset in query
 */
function useDataset(datasetId) {
    // Store selected dataset ID and redirect to query page
    Storage.set('selected_dataset_id', datasetId);
    window.location.href = 'query.html';
}

/**
 * Confirm delete
 */
function confirmDelete(datasetId) {
    datasetToDelete = datasetId;
    document.getElementById('deleteModal').classList.remove('hidden');
}

/**
 * Delete dataset
 */
async function deleteDataset() {
    if (!datasetToDelete) return;
    
    try {
        // Delete dataset via API
        await API.delete(`/datasets/${datasetToDelete}`, true);
        
        Notifications.success('Dataset deleted successfully');
        document.getElementById('deleteModal').classList.add('hidden');
        
        // Reload datasets
        await loadDatasets();
        
    } catch (error) {
        Notifications.error('Failed to delete dataset');
    }
    
    datasetToDelete = null;
}

/**
 * Open the rename modal, pre-filled with the dataset's current name.
 */
let datasetToRename = null;
function renameDataset(datasetId) {
    const ds = datasets.find(d => d.id === datasetId);
    if (!ds) return;
    datasetToRename = datasetId;
    const input = document.getElementById('renameInput');
    input.value = ds.original_filename || ds.filename || '';
    document.getElementById('renameModal').classList.remove('hidden');
    setTimeout(() => { input.focus(); input.select(); }, 50);
}

async function saveRename(e) {
    e.preventDefault();
    if (!datasetToRename) return;
    const input = document.getElementById('renameInput');
    const newName = input.value.trim();
    if (!newName) return;

    try {
        const updated = await API.patch(`/datasets/${datasetToRename}`, { name: newName }, true);
        const ds = datasets.find(d => d.id === datasetToRename);
        if (ds) ds.original_filename = updated.original_filename;
        renderDatasets();
        Notifications.success('Dataset renamed.');
        document.getElementById('renameModal').classList.add('hidden');
    } catch (error) {
        Notifications.error(error.message || 'Failed to rename dataset');
    }
    datasetToRename = null;
}

/**
 * Setup modal functionality
 */
function setupModals() {
    // Preview modal
    document.getElementById('closePreviewBtn').addEventListener('click', () => {
        document.getElementById('previewModal').classList.add('hidden');
    });
    
    document.getElementById('closePreviewBtn2').addEventListener('click', () => {
        document.getElementById('previewModal').classList.add('hidden');
    });

    // CH-02: "Use This Dataset" hands the previewed dataset to the query builder
    document.getElementById('useDatasetBtn').addEventListener('click', () => {
        if (_fullViewDatasetId) useDataset(_fullViewDatasetId);
    });

    // Delete modal
    document.getElementById('cancelDeleteBtn').addEventListener('click', () => {
        document.getElementById('deleteModal').classList.add('hidden');
        datasetToDelete = null;
    });
    
    document.getElementById('confirmDeleteBtn').addEventListener('click', deleteDataset);

    // Rename modal
    document.getElementById('cancelRenameBtn').addEventListener('click', () => {
        document.getElementById('renameModal').classList.add('hidden');
        datasetToRename = null;
    });
    document.getElementById('renameForm').addEventListener('submit', saveRename);
}

/**
 * Utility functions
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
    });
}

function formatNumber(num) {
    return num.toLocaleString('en-US');
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}
