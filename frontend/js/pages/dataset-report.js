/**
 * Dataset Cleaning Report Page
 * Shows raw vs cleaned data and operations log for a dataset
 */

let datasetId = null;
let reportData = null;

// ─── Bootstrap ──────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    datasetId = parseInt(params.get('id'));

    if (!datasetId) {
        showError('Invalid dataset ID.');
        return;
    }

    setupTabs();
    loadReport();
});

// ─── Data Loading ────────────────────────────────────────────────────────────

async function loadReport() {
    try {
        reportData = await API.get(`/datasets/${datasetId}/cleaning-report`, true);
        renderPage(reportData);
    } catch (err) {
        // If no cleaning report yet, fall back to the analysis endpoint
        try {
            const analysisData = await API.get(`/datasets/${datasetId}/analysis`, true);
            renderPageFromAnalysis(analysisData);
        } catch (err2) {
            showError('Could not load cleaning report. The dataset may not have been processed yet.');
        }
    }
}

// ─── Rendering ───────────────────────────────────────────────────────────────

function renderPage(data) {
    // Header
    const original = data.original_shape || data.cleaning_report?.original || {};
    const cleaned  = data.cleaned_shape  || data.cleaning_report?.cleaned  || {};
    const report   = data.cleaning_report || {};
    const improvements = report.improvements || {};
    const dataQuality  = data.data_quality  || {};
    const typeMap      = data.type_detection?.type_map || {};

    document.getElementById('datasetName').textContent = `Cleaning Report`;
    document.getElementById('datasetMeta').textContent =
        `Dataset ID: ${datasetId}  ·  Processed: ${formatTs(report.cleaning_timestamp || data.cleaning_timestamp)}`;

    // Summary cards
    const cards = [
        {
            label: 'Rows Removed',
            value: fmtNum(improvements.rows_removed ?? (original.rows ?? 0) - (cleaned.rows ?? 0)),
            sub: `${fmtNum(original.rows ?? 0)} → ${fmtNum(cleaned.rows ?? 0)}`,
            color: 'bg-red-50 border border-red-200',
            icon: '<i data-lucide="trash-2"></i>'
        },
        {
            label: 'Missing Cells Fixed',
            value: fmtNum(improvements.missing_cells_fixed ?? dataQuality?.missing_values?.total_missing_cells ?? 0),
            sub: `${fmtNum(original.missing_cells ?? dataQuality?.missing_values?.total_missing_cells ?? 0)} → 0`,
            color: 'bg-yellow-50 border border-yellow-200',
            icon: '🩹'
        },
        {
            label: 'Duplicates Removed',
            value: fmtNum(improvements.duplicates_removed ?? dataQuality?.duplicates?.duplicate_rows ?? 0),
            sub: `from ${fmtNum(dataQuality?.duplicates?.duplicate_rows ?? 0)} found`,
            color: 'bg-orange-50 border border-orange-200',
            icon: '<i data-lucide="copy-x"></i>'
        },
        {
            label: 'Columns Detected',
            value: fmtNum(cleaned.columns ?? original.columns ?? 0),
            sub: `${Object.keys(typeMap).length} typed`,
            color: 'bg-blue-50 border border-blue-200',
            icon: '<i data-lucide="clipboard-list"></i>'
        }
    ];

    document.getElementById('summaryCards').innerHTML = cards.map(c => `
        <div class="stat-card ${c.color}">
            <div class="text-2xl">${c.icon}</div>
            <div class="text-3xl font-bold text-gray-800">${c.value}</div>
            <div class="text-sm font-semibold text-gray-700">${c.label}</div>
            <div class="text-xs text-gray-500">${c.sub}</div>
        </div>
    `).join('');

    // What was changed (CP-20)
    renderAppliedChanges(data.applied_cleaning);

    // Operations log
    renderOperationsLog(report.actions_taken || data.actions_taken || {}, dataQuality, typeMap);

    // Column analysis
    renderColumnAnalysis(typeMap, report.actions_taken || data.actions_taken || {}, dataQuality);

    show('pageContent');
    hide('loadingState');

    // Lazy-load table data only when that tab is first activated
}

/**
 * CP-20 · "What was changed" — the applied-cleaning diff. Lists each op that
 * actually ran (with counts + cell examples) and a per-column null
 * reconciliation table so every remaining blank is accounted for.
 */
function renderAppliedChanges(applied) {
    const box = document.getElementById('appliedChanges');
    if (!box) return;
    if (!applied || (!(applied.applied_ops || []).length && !Object.keys(applied.null_reconciliation || {}).length)) {
        box.innerHTML = '';
        return;
    }
    const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const when = applied.applied_at ? new Date(applied.applied_at).toLocaleString() : '';

    const opRows = (applied.applied_ops || []).map(op => {
        const exs = (op.examples || []).slice(0, 3).map(ex => {
            const loc = ex.row ? `Row ${ex.row}` : 'All rows';
            const from = ex.from == null ? '(blank)' : esc(ex.from);
            const to = ex.to == null ? '(blank)' : esc(ex.to);
            return `<div class="text-xs text-gray-500 font-mono pl-4">${esc(loc)} · <span class="text-red-500 line-through">${from}</span> → <span class="text-green-600">${to}</span></div>`;
        }).join('');
        const ovr = op.override ? `<span class="text-xs font-semibold bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full ml-2">${esc(op.override)}</span>` : '';
        return `<div class="border border-gray-100 rounded-lg px-4 py-3">
            <div class="text-sm font-semibold text-gray-800">${esc(op.title)}${ovr}
                <span class="text-xs text-gray-400 font-normal ml-1">· ${op.affected_count} cell(s)/row(s)</span></div>
            ${exs}
        </div>`;
    }).join('');

    // Null reconciliation table
    const recon = applied.null_reconciliation || {};
    let reconTable = '';
    if (Object.keys(recon).length) {
        const rows = Object.entries(recon).map(([col, r]) => `
            <tr class="border-t border-gray-100">
                <td class="px-3 py-1.5 text-sm font-medium text-gray-700">${esc(col)}</td>
                <td class="px-3 py-1.5 text-sm text-right tabular">${r.nulls_before_convert ?? 0}</td>
                <td class="px-3 py-1.5 text-sm text-right tabular text-amber-600">+${r.parse_failures ?? 0}</td>
                <td class="px-3 py-1.5 text-sm text-right tabular text-green-600">−${r.filled ?? 0}</td>
                <td class="px-3 py-1.5 text-sm text-right tabular font-semibold">${r.final_nulls ?? 0}</td>
            </tr>`).join('');
        reconTable = `
            <h4 class="text-sm font-bold text-gray-700 mt-5 mb-2">Null reconciliation — every remaining blank accounted for</h4>
            <div class="overflow-x-auto border border-gray-100 rounded-lg">
                <table class="w-full">
                    <thead class="bg-gray-50"><tr>
                        <th class="px-3 py-2 text-left text-xs font-semibold text-gray-500">Column</th>
                        <th class="px-3 py-2 text-right text-xs font-semibold text-gray-500">Blanks before</th>
                        <th class="px-3 py-2 text-right text-xs font-semibold text-gray-500">Parse failures</th>
                        <th class="px-3 py-2 text-right text-xs font-semibold text-gray-500">Filled</th>
                        <th class="px-3 py-2 text-right text-xs font-semibold text-gray-500">Final blanks</th>
                    </tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;
    }

    box.innerHTML = `
        <div class="bg-white border border-gray-200 rounded-xl p-6">
            <div class="flex items-center gap-2 mb-1">
                <i data-lucide="check-circle-2" style="width:18px;height:18px;color:#16A34A;"></i>
                <h3 class="text-lg font-bold text-gray-800">What was changed</h3>
            </div>
            <p class="text-xs text-gray-400 mb-4">Approved cleaning applied ${when ? 'on ' + esc(when) : ''} · your original file is never modified.</p>
            ${opRows ? `<div class="space-y-2">${opRows}</div>` : '<p class="text-sm text-gray-500">No value-level changes were applied.</p>'}
            ${reconTable}
        </div>`;
    if (window.lucide) { try { lucide.createIcons(); } catch (_) {} }
}

function renderPageFromAnalysis(data) {
    renderAppliedChanges(data.applied_cleaning);
    // No cleaning report saved — show analysis only
    document.getElementById('datasetName').textContent = 'Data Quality Analysis';
    document.getElementById('datasetMeta').textContent = `Dataset ID: ${datasetId}`;
    document.getElementById('cleanedBadge').textContent = 'Not yet cleaned';
    document.getElementById('cleanedBadge').className = 'px-4 py-1.5 bg-yellow-100 text-yellow-800 rounded-full text-sm font-semibold';
    document.getElementById('processBtn').classList.remove('hidden'); // show Process button

    const dq = data.data_quality || {};
    const typeMap = data.type_detection?.type_map || {};
    const missing = dq.missing_values || {};
    const dupes   = dq.duplicates   || {};

    document.getElementById('summaryCards').innerHTML = `
        <div class="stat-card bg-yellow-50 border border-yellow-200">
            <div><i data-lucide="alert-triangle" style="width:24px;height:24px;color:#D97706;"></i></div>
            <div class="text-3xl font-bold text-gray-800">${fmtNum(missing.total_missing_cells ?? 0)}</div>
            <div class="text-sm font-semibold text-gray-700">Missing Cells</div>
            <div class="text-xs text-gray-500">${missing.missing_percentage ?? 0}% of data</div>
        </div>
        <div class="stat-card bg-orange-50 border border-orange-200">
            <div><i data-lucide="repeat-2" style="width:24px;height:24px;color:#0d9488;"></i></div>
            <div class="text-3xl font-bold text-gray-800">${fmtNum(dupes.duplicate_rows ?? 0)}</div>
            <div class="text-sm font-semibold text-gray-700">Duplicate Rows</div>
            <div class="text-xs text-gray-500">${dupes.duplicate_percentage ?? 0}%</div>
        </div>
        <div class="stat-card bg-blue-50 border border-blue-200">
            <div><i data-lucide="clipboard-list" style="width:24px;height:24px;color:#0d9488;"></i></div>
            <div class="text-3xl font-bold text-gray-800">${Object.keys(typeMap).length}</div>
            <div class="text-sm font-semibold text-gray-700">Columns Typed</div>
            <div class="text-xs text-gray-500">type detection complete</div>
        </div>
        <div class="stat-card bg-indigo-50 border border-indigo-200">
            <div><i data-lucide="scan-search" style="width:24px;height:24px;color:#0d9488;"></i></div>
            <div class="text-3xl font-bold text-gray-800">${Object.keys(dq.outliers || {}).length}</div>
            <div class="text-sm font-semibold text-gray-700">Columns w/ Outliers</div>
            <div class="text-xs text-gray-500">detected via IQR</div>
        </div>
    `;

    renderColumnAnalysis(typeMap, {}, dq);

    // Hide cleaned tab since there's no cleaned file
    document.querySelector('[data-tab="cleaned"]').closest('button').disabled = true;
    document.querySelector('[data-tab="cleaned"]').closest('button').classList.add('opacity-40', 'cursor-not-allowed');

    show('pageContent');
    hide('loadingState');
}

// ─── Process Dataset ─────────────────────────────────────────────────────────

async function processDataset() {
    const btn = document.getElementById('processBtn');
    const badge = document.getElementById('cleanedBadge');
    btn.disabled = true;
    btn.textContent = 'Processing…';
    badge.textContent = 'Processing…';
    badge.className = 'px-4 py-1.5 bg-blue-100 text-blue-800 rounded-full text-sm font-semibold';
    try {
        await API.post(`/datasets/${datasetId}/process`, {}, true);
        // Reload the page to show the full cleaning report
        window.location.reload();
    } catch (err) {
        badge.textContent = 'Processing failed';
        badge.className = 'px-4 py-1.5 bg-red-100 text-red-800 rounded-full text-sm font-semibold';
        btn.disabled = false;
        btn.textContent = 'Retry Processing';
        alert('Processing failed: ' + (err.message || 'Unknown error'));
    }
}

// ─── Operations Log ──────────────────────────────────────────────────────────

function renderOperationsLog(actionsTaken, dataQuality, typeMap) {
    const container = document.getElementById('operationsList');
    const ops = [];

    // 1. Type detection
    const typeCount = Object.keys(typeMap).length;
    if (typeCount > 0) {
        const typeSummary = {};
        Object.values(typeMap).forEach(t => { typeSummary[t] = (typeSummary[t] || 0) + 1; });
        ops.push({
            icon: '<i data-lucide="scan-search"></i>',
            category: 'Type Detection',
            categoryColor: 'bg-indigo-100 text-indigo-800',
            title: `Detected types for ${typeCount} columns`,
            detail: Object.entries(typeSummary)
                .map(([t, n]) => `${n} ${t}`)
                .join(', '),
            rows: Object.entries(typeMap).map(([col, type]) => ({
                left: col,
                right: `→ ${type}`,
                rightClass: typeClass(type)
            }))
        });
    }

    // 2. Missing values
    const missingOps = actionsTaken.missing_values || {};
    const missingCols = Object.entries(missingOps).filter(([, v]) => typeof v === 'string');
    if (missingCols.length > 0) {
        ops.push({
            icon: '<i data-lucide="bandage"></i>',
            category: 'Missing Values',
            categoryColor: 'bg-yellow-100 text-yellow-800',
            title: `Handled missing values in ${missingCols.length} column(s)`,
            detail: missingCols.length + ' imputation / fill actions performed',
            rows: missingCols.map(([col, action]) => ({ left: col, right: action, rightClass: 'text-yellow-700' }))
        });
    }
    if (typeof missingOps.strategy === 'string') {
        ops.push({
            icon: '<i data-lucide="bandage"></i>',
            category: 'Missing Values',
            categoryColor: 'bg-yellow-100 text-yellow-800',
            title: missingOps.strategy,
            detail: 'Row-level drop strategy applied',
            rows: []
        });
    }

    // 3. Duplicates
    const dupAction = actionsTaken.duplicates;
    if (dupAction) {
        ops.push({
            icon: '<i data-lucide="copy-x"></i>',
            category: 'Duplicates',
            categoryColor: 'bg-orange-100 text-orange-800',
            title: typeof dupAction === 'string' ? dupAction : 'Duplicate rows removed',
            detail: 'Exact-match duplicate rows eliminated, first occurrence kept',
            rows: []
        });
    }

    // 4. Categorical normalisation
    const normReport = actionsTaken.categorical_normalization || {};
    const normCols = Object.entries(normReport);
    if (normCols.length > 0) {
        // Flatten all per-column changes into rows
        const detailRows = [];
        normCols.forEach(([col, colActions]) => {
            if (typeof colActions === 'object' && colActions !== null) {
                Object.entries(colActions).forEach(([action, detail]) => {
                    if (typeof detail === 'string') {
                        detailRows.push({ left: `${col} → ${action}`, right: detail, rightClass: 'text-green-700' });
                    } else if (Array.isArray(detail) && detail.length > 0) {
                        detailRows.push({ left: `${col} → ${action}`, right: `${detail.length} value(s) changed`, rightClass: 'text-green-700' });
                    }
                });
            } else if (typeof colActions === 'string') {
                detailRows.push({ left: col, right: colActions, rightClass: 'text-green-700' });
            }
        });
        if (detailRows.length > 0) {
            ops.push({
                icon: '<i data-lucide="spell-check-2"></i>',
                category: 'Normalisation',
                categoryColor: 'bg-green-100 text-green-800',
                title: `Normalised values in ${normCols.length} column(s)`,
                detail: 'Case standardisation, whitespace trim, typo correction applied',
                rows: detailRows
            });
        }
    }

    if (ops.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 text-gray-400">
                <div class="mb-3"><i data-lucide="check-circle-2" style="width:38px;height:38px;color:#16A34A;"></i></div>
                <p>No operations recorded — dataset was already clean or no report was saved.</p>
            </div>`;
        return;
    }

    container.innerHTML = ops.map((op, i) => `
        <div class="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
            <!-- Header row -->
            <div class="flex items-center gap-3 px-5 py-4 cursor-pointer select-none hover:bg-gray-50"
                 onclick="toggleOp(${i})">
                <span class="text-2xl">${op.icon}</span>
                <div class="flex-1 min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="op-badge ${op.categoryColor}">${op.category}</span>
                        <span class="font-semibold text-gray-800 text-sm">${op.title}</span>
                    </div>
                    <p class="text-xs text-gray-500 mt-0.5">${op.detail}</p>
                </div>
                ${op.rows.length > 0 ? `
                    <svg id="op-arrow-${i}" class="w-4 h-4 text-gray-400 flex-shrink-0 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                    </svg>
                ` : ''}
            </div>
            <!-- Detail rows -->
            ${op.rows.length > 0 ? `
                <div id="op-detail-${i}" class="hidden border-t border-gray-100 px-5 py-3 bg-gray-50">
                    <table class="w-full text-xs">
                        ${op.rows.map(r => `
                            <tr class="border-b border-gray-100 last:border-0">
                                <td class="py-1.5 pr-4 font-mono text-gray-600 w-1/2">${escHtml(String(r.left))}</td>
                                <td class="py-1.5 ${r.rightClass || 'text-gray-700'}">${escHtml(String(r.right))}</td>
                            </tr>
                        `).join('')}
                    </table>
                </div>
            ` : ''}
        </div>
    `).join('');
}

function toggleOp(i) {
    const detail = document.getElementById(`op-detail-${i}`);
    const arrow  = document.getElementById(`op-arrow-${i}`);
    if (!detail) return;
    detail.classList.toggle('hidden');
    if (arrow) arrow.style.transform = detail.classList.contains('hidden') ? '' : 'rotate(180deg)';
}

// ─── Column Analysis ─────────────────────────────────────────────────────────

function renderColumnAnalysis(typeMap, actionsTaken, dataQuality) {
    const container = document.getElementById('columnAnalysisList');
    const missingCols = dataQuality?.missing_values?.columns_with_missing || {};
    const outlierCols = dataQuality?.outliers || {};
    const missingActions = actionsTaken.missing_values || {};

    const cols = Object.entries(typeMap);
    if (cols.length === 0) {
        container.innerHTML = '<p class="text-gray-400 col-span-2 text-center py-10">No column information available.</p>';
        return;
    }

    container.innerHTML = cols.map(([col, type]) => {
        const missing  = missingCols[col];
        const outlier  = outlierCols[col];
        const action   = typeof missingActions[col] === 'string' ? missingActions[col] : null;
        const normAction = actionsTaken.categorical_normalization?.[col];

        const badges = [];
        if (missing)   badges.push(`<span class="op-badge bg-yellow-100 text-yellow-800">⚠ ${missing.count} missing (${missing.percentage}%)</span>`);
        if (outlier)   badges.push(`<span class="op-badge bg-red-100 text-red-700">⬆ ${outlier.count} outliers</span>`);
        if (action)    badges.push(`<span class="op-badge bg-green-100 text-green-800">✓ ${escHtml(action)}</span>`);
        if (normAction && typeof normAction === 'object') {
            const parts = Object.keys(normAction);
            if (parts.length) badges.push(`<span class="op-badge bg-indigo-100 text-indigo-800">✏ normalised</span>`);
        }

        return `
            <div class="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
                <div class="flex items-center justify-between gap-2 mb-2">
                    <span class="font-mono font-semibold text-gray-800 text-sm truncate" title="${escHtml(col)}">${escHtml(col)}</span>
                    <span class="op-badge ${typeClass(type)} flex-shrink-0">${type}</span>
                </div>
                ${badges.length > 0 ? `<div class="flex flex-wrap gap-1.5 mt-2">${badges.join('')}</div>` : `<p class="text-xs text-gray-400 mt-1">No issues detected</p>`}
            </div>
        `;
    }).join('');
}

// ─── Table Rendering ─────────────────────────────────────────────────────────

let rawLoaded     = false;
let cleanedLoaded = false;

async function lazyLoadRaw() {
    if (rawLoaded) return;
    rawLoaded = true;
    try {
        const data = await API.get(`/datasets/${datasetId}/preview`, true);
        renderTable('rawTableContainer', 'rawTableLoading', data.column_names, data.preview_rows);
    } catch (e) {
        document.getElementById('rawTableLoading').textContent = 'Failed to load raw data.';
    }
}

async function lazyLoadCleaned() {
    if (cleanedLoaded) return;
    cleanedLoaded = true;
    try {
        const data = await API.get(`/datasets/${datasetId}/cleaned-preview`, true);
        let note = data.source === 'original'
            ? '<p class="text-xs text-yellow-600 mb-2">⚠ No cleaned file found — showing original data.</p>'
            : '';
        if (data.needs_manual_review) {
            const cellCount = (data.issues || []).length;
            const rowCount = (data.row_issues || []).length;
            note += `
                <div class="mb-3 flex items-start gap-2 bg-purple-50 border border-purple-200 rounded-lg px-4 py-3">
                    <svg class="w-5 h-5 text-purple-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                    </svg>
                    <div class="text-sm text-purple-800">
                        <strong>Needs manual review.</strong> Cleaning couldn't (or by design doesn't) fix everything —
                        ${cellCount ? `${cellCount} cell(s)` : ''}${cellCount && rowCount ? ' and ' : ''}${rowCount ? `${rowCount} row(s)` : ''}
                        still need your attention (highlighted below). Right-click a cell or column header on
                        <strong>Highlight Issues</strong> to fix them directly, or accept the data as-is if these are expected.
                    </div>
                </div>`;
        }
        renderTable('cleanedTableContainer', 'cleanedTableLoading', data.column_names, data.preview_rows, note,
                    { rowIndices: data.row_indices, issues: data.issues, rowIssues: data.row_issues });
    } catch (e) {
        document.getElementById('cleanedTableLoading').textContent = 'Failed to load cleaned data.';
    }
}

function renderTable(containerId, loadingId, columns, rows, prefixHtml = '', issueInfo = null) {
    hide(loadingId);
    const container = document.getElementById(containerId);
    if (!columns || !rows) {
        container.innerHTML = '<p class="p-4 text-gray-400">No data available.</p>';
        container.classList.remove('hidden');
        return;
    }

    const issueMap = new Map();
    const rowIssueMap = new Map();
    if (issueInfo) {
        (issueInfo.issues || []).forEach(iss => issueMap.set(`${iss.row}|${iss.column}`, iss));
        (issueInfo.rowIssues || []).forEach(ri => rowIssueMap.set(ri.row, ri.reason));
    }
    const rowIndices = issueInfo?.rowIndices || [];

    const tableRows = rows.map((row, i) => {
        const rowIdx = rowIndices[i];
        const rowReason = rowIssueMap.get(rowIdx);
        const rowAttrs = rowReason
            ? ` style="background:#fee2e2;" title="${escHtml(rowReason)}"`
            : '';
        return `
        <tr${rowAttrs}>
            ${columns.map(col => {
                const val = row[col];
                const isNull = val === null || val === undefined || val === '';
                const iss = rowIndices.length ? issueMap.get(`${rowIdx}|${col}`) : null;
                const bg = iss ? (iss.tier === 'review' ? 'background:#f3e8ff;' : 'background:#fef3c7;') : '';
                const cellAttrs = iss ? ` style="${bg}" title="${escHtml(iss.reason)}"` : '';
                return `<td class="${isNull ? 'null-cell' : ''}"${cellAttrs}>${isNull ? 'null' : escHtml(String(val))}</td>`;
            }).join('')}
        </tr>`;
    }).join('');

    const legend = issueInfo ? `
        <div class="flex items-center gap-3 text-xs font-medium mb-2 flex-wrap">
            <span class="inline-flex items-center gap-1.5 text-amber-700"><span class="w-3 h-3 rounded-sm" style="background:#fef3c7;border:1px solid #f59e0b;"></span>Cleaning would fix (re-run cleaning to apply)</span>
            <span class="inline-flex items-center gap-1.5 text-purple-700"><span class="w-3 h-3 rounded-sm" style="background:#f3e8ff;border:1px solid #a855f7;"></span>Flagged — needs manual review</span>
            <span class="inline-flex items-center gap-1.5 text-red-700"><span class="w-3 h-3 rounded-sm" style="background:#fee2e2;border:1px solid #ef4444;"></span>Problem row</span>
        </div>` : '';

    container.innerHTML = `
        ${prefixHtml}
        ${legend}
        <table class="report-table">
            <thead>
                <tr>${columns.map(c => `<th>${escHtml(c)}</th>`).join('')}</tr>
            </thead>
            <tbody>${tableRows}</tbody>
        </table>
        <p class="text-xs text-gray-400 p-2">Showing first ${rows.length} rows of ${rows.length >= 100 ? '100+' : rows.length} total.</p>
    `;
    container.classList.remove('hidden');
}

// ─── Tabs ────────────────────────────────────────────────────────────────────

function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            if (btn.disabled) return;

            // Update button styles
            document.querySelectorAll('.tab-btn').forEach(b => {
                b.classList.remove('active');
                b.classList.add('text-gray-500');
                b.classList.remove('text-blue-600');
            });
            btn.classList.add('active');
            btn.classList.remove('text-gray-500');

            // Show/hide content
            document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
            document.getElementById(`tab-${tab}`).classList.remove('hidden');

            // Lazy load table data
            if (tab === 'raw')     lazyLoadRaw();
            if (tab === 'cleaned') lazyLoadCleaned();
            if (tab === 'anomalies') initAnomaliesTab();   // CH-20
        });
    });
}

// ─── CH-20: Anomalies tab (wires the standalone anomaly-scan API) ────────────

let _anomTabReady = false;

async function initAnomaliesTab() {
    if (!_anomTabReady) {
        _anomTabReady = true;
        // Populate the column selector with numeric columns
        try {
            const resp = await API.get(`/queries/datasets/${datasetId}/columns`, true);
            const sel = document.getElementById('anomalyColumnSelect');
            (resp.columns || [])
                .filter(c => c.category === 'metric' || c.dtype?.startsWith('float') || c.dtype?.startsWith('int'))
                .forEach(c => {
                    const o = document.createElement('option');
                    o.value = c.name; o.textContent = c.name;
                    sel.appendChild(o);
                });
        } catch (_) { /* selector stays "all columns" */ }
        document.getElementById('anomalyRescanBtn')?.addEventListener('click', () => runAnomalyScan(true));
        document.getElementById('anomalyColumnSelect')?.addEventListener('change', () => runAnomalyScan(false));
        document.getElementById('anomalySensitivity')?.addEventListener('change', () => runAnomalyScan(true));
    }
    runAnomalyScan(false);
}

async function runAnomalyScan(refresh) {
    const box = document.getElementById('anomalyResults');
    if (!box) return;
    box.innerHTML = '<p class="text-sm text-gray-400 py-4">Scanning for outliers…</p>';
    const col = document.getElementById('anomalyColumnSelect')?.value || '';
    const thr = document.getElementById('anomalySensitivity')?.value || '3.0';
    try {
        const qs = `method=zscore&threshold=${thr}&refresh=${refresh ? 'true' : 'false'}`
                 + (col ? `&column=${encodeURIComponent(col)}` : '');
        const resp = await API.get(`/datasets/${datasetId}/anomalies?${qs}`, true);
        const rows = resp.anomalies || [];
        const sensLabel = document.getElementById('anomalySensitivity')?.selectedOptions?.[0]?.textContent || `${thr}σ`;
        const scopeLabel = col ? `"${escHtml(col)}"` : 'all numeric columns';
        if (!rows.length) {
            box.innerHTML = `<p class="text-sm text-green-600 font-semibold py-4">
                ✓ No statistical outliers found in ${scopeLabel} at ${escHtml(sensLabel)} sensitivity
                — try "High" sensitivity if you expect more to show up.</p>`;
            return;
        }
        const fmtVal = (v) => typeof v === 'number'
            ? v.toLocaleString(undefined, { maximumFractionDigits: 2 })
            : (typeof v === 'object' && v !== null
                ? Object.entries(v).map(([k, x]) => `${escHtml(k)}: ${Number(x).toLocaleString()}`).join(', ')
                : escHtml(v));
        box.innerHTML = `
            <p class="text-sm text-gray-600 mb-3">
                <strong>${rows.length}</strong> outlier(s) flagged in ${scopeLabel} at
                <strong>${escHtml(sensLabel)}</strong> sensitivity
                ${resp.cached ? '<span class="text-xs text-gray-400">(cached — Re-scan for fresh results)</span>' : ''}
                — these are signals to review, not errors; the data is untouched.
                Fewer results than expected? Try a higher sensitivity.
            </p>
            <div class="table-scroll">
                <table class="w-full text-sm">
                    <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
                        <tr><th class="px-3 py-2">Row</th><th class="px-3 py-2">Column</th>
                            <th class="px-3 py-2">Value</th><th class="px-3 py-2">Why flagged</th></tr>
                    </thead>
                    <tbody>
                        ${rows.slice(0, 200).map(a => {
                            const sevColor = { high: 'bg-red-100 text-red-700', medium: 'bg-orange-100 text-orange-700', low: 'bg-yellow-100 text-yellow-700' }[a.severity] || 'bg-gray-100 text-gray-600';
                            const why = [
                                a.severity ? `<span class="px-2 py-0.5 rounded-full font-semibold ${sevColor}">${escHtml(a.severity)}</span>` : '',
                                a.zscore != null ? `${Number(a.zscore).toFixed(2)}σ from typical` : '',
                                a.anomaly_score != null ? `score ${Number(a.anomaly_score).toFixed(2)}` : '',
                                escHtml(a.method || ''),
                            ].filter(Boolean).join(' · ');
                            return `
                            <tr class="border-t border-gray-100">
                                <td class="px-3 py-2 text-gray-500">${escHtml(a.label ?? a.row_index ?? '—')}</td>
                                <td class="px-3 py-2 font-semibold">${escHtml(a.extra?.source_column ?? (a.column_name === '__all__' ? 'multiple' : (a.column_name ?? '')))}</td>
                                <td class="px-3 py-2 font-mono">${fmtVal(a.value)}</td>
                                <td class="px-3 py-2 text-xs text-gray-500">${why}</td>
                            </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>`;
    } catch (e) {
        box.innerHTML = `<p class="text-sm text-red-500 py-4">Scan failed: ${escHtml(e.message || 'error')}</p>`;
    }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }

function showError(msg) {
    hide('loadingState');
    show('errorState');
    const el = document.getElementById('errorMessage');
    if (el) el.textContent = msg;
}

function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function fmtNum(n) {
    if (n === null || n === undefined) return '—';
    return Number(n).toLocaleString();
}

function formatTs(ts) {
    if (!ts) return 'unknown';
    try { return new Date(ts).toLocaleString(); } catch { return ts; }
}

function typeClass(type) {
    switch (type) {
        case 'numeric':     return 'bg-blue-100 text-blue-800';
        case 'categorical': return 'bg-indigo-100 text-indigo-800';
        case 'datetime':    return 'bg-green-100 text-green-800';
        case 'boolean':     return 'bg-indigo-100 text-indigo-800';
        default:            return 'bg-gray-100 text-gray-600';
    }
}
