/**
 * Query Builder Page Logic
 * Handles dataset selection, NLP queries, template queries, and chart generation
 */

let datasets = [];
let templates = [];
let selectedDataset = null;
let selectedTemplate = null;
let datasetColumns = [];
let currentChart = null;
let currentQueryResult = null;
let currentInsights = [];
// True once the user has hand-customized the current chart (color, title,
// legend, gridlines) and hasn't added it to a dashboard yet — navigating
// away now (a full page reload) would silently discard that customization,
// since it only lives in this page's memory until "Add to Dashboard" saves
// it. Used to warn before that happens instead of losing it silently.
let _chartCustomizedUnsaved = false;

window.addEventListener('beforeunload', (e) => {
    if (!_chartCustomizedUnsaved) return;
    e.preventDefault();
    e.returnValue = ''; // required for the native "leave site?" prompt to show
});

// In-app navigation (navbar links, any same-app <a href>) doesn't have to go
// through the browser's native prompt — intercept it and show our own
// modal instead. Only an actual tab close / typed URL / refresh falls back
// to the native beforeunload prompt above (browsers block replacing that
// one with custom UI).
let _pendingNavHref = null;
document.addEventListener('click', (e) => {
    if (!_chartCustomizedUnsaved) return;
    const link = e.target.closest('a[href]');
    if (!link) return;
    const href = link.getAttribute('href') || '';
    // Ignore same-page anchors, new-tab links, and non-navigational hrefs.
    if (!href || href.startsWith('#') || link.target === '_blank') return;
    e.preventDefault();
    _pendingNavHref = link.href;
    document.getElementById('unsavedChartModal')?.classList.remove('hidden');
}, true); // capture phase — run before the link's own navigation

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('unsavedChartCancelBtn')?.addEventListener('click', () => {
        _pendingNavHref = null;
        document.getElementById('unsavedChartModal')?.classList.add('hidden');
    });
    document.getElementById('unsavedChartLeaveBtn')?.addEventListener('click', () => {
        _chartCustomizedUnsaved = false; // about to navigate away deliberately
        if (_pendingNavHref) window.location.href = _pendingNavHref;
    });
});

// Forecast state
let _forecastActive    = false;
let _forecastParams    = null;   // {dataset_id, parameters} for the current trend chart
let _forecastBaseTraceCount = 0; // number of Plotly traces before forecast was added

// NLP state
let nlpLastResult = null;

// ─── Initialisation ──────────────────────────────────────────────────────────

async function initQueryPage() {
    await loadDatasets();
    await loadTemplates();
    setupEventListeners();
    applyDatasetHandoff();   // CH-02: honor "Use in Query Builder" / ?dataset= deep links
    restoreQueryState();     // CH-08: bring back the last chart built in this tab
}

/**
 * CH-02 — consume a dataset preselection from either the URL (?dataset=ID,
 * written by upload.js) or Storage ('selected_dataset_id', written by
 * datasets.js useDataset()). One-shot: cleared after use so a later manual
 * visit to this page doesn't re-force an old selection.
 * Returns the preselected id (or null) so restoreQueryState can defer to it.
 */
let _handoffDatasetId = null;
function applyDatasetHandoff() {
    const urlId = parseInt(new URLSearchParams(window.location.search).get('dataset'));
    const storedId = parseInt(Storage.get('selected_dataset_id'));
    Storage.remove('selected_dataset_id');
    const id = urlId || storedId;
    if (!id) return;

    const select = document.getElementById('datasetSelect');
    const match = [...select.options].some(o => o.value === String(id));
    if (!match) return;   // dataset was deleted or belongs elsewhere — ignore silently

    _handoffDatasetId = id;
    select.value = String(id);
    select.dispatchEvent(new Event('change'));   // runs handleDatasetChange: columns + NLP
}

// ─── Dataset loading ──────────────────────────────────────────────────────────

async function loadDatasets() {
    try {
        const response = await API.get('/datasets', true);
        datasets = response || [];

        const datasetSelect = document.getElementById('datasetSelect');
        datasetSelect.innerHTML = '<option value="">-- Choose a dataset --</option>';

        datasets.forEach(dataset => {
            const option = document.createElement('option');
            option.value = dataset.id;
            option.textContent = `${dataset.original_filename || dataset.filename} (${dataset.row_count || '?'} rows)`;
            datasetSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading datasets:', error);
        Notifications.error('Failed to load datasets');
    }
}

// ─── Templates ───────────────────────────────────────────────────────────────

async function loadTemplates() {
    try {
        const response = await API.get('/queries/templates', true);
        templates = response.templates || [];

        const templateSelect = document.getElementById('templateSelect');
        templateSelect.innerHTML = '<option value="">-- Choose a template --</option>';

        templates.forEach(template => {
            const option = document.createElement('option');
            option.value = template.template_type;
            option.textContent = template.name;
            templateSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading templates:', error);
    }
}

// ─── Event listeners ─────────────────────────────────────────────────────────

function setupEventListeners() {
    document.getElementById('datasetSelect').addEventListener('change', handleDatasetChange);
    document.getElementById('templateSelect').addEventListener('change', handleTemplateChange);
    document.getElementById('executeButton').addEventListener('click', executeQuery);
    document.getElementById('addToDashboardButton').addEventListener('click', addChartToDashboard);

    // NLP
    document.getElementById('nlpAnalyzeBtn').addEventListener('click', runNaturalQuery);
    document.getElementById('nlpExecuteBtn').addEventListener('click', executeNlpResult);
    document.getElementById('nlpInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') runNaturalQuery();
    });

    // Query history
    document.getElementById('historyCloseBtn').addEventListener('click', () => {
        document.getElementById('queryHistoryPanel').classList.add('hidden');
    });

    // Add-to-dashboard picker modal
    document.getElementById('closeAddToDashModal')?.addEventListener('click', _closeAddToDashModal);
    document.getElementById('addToNewDashboardBtn')?.addEventListener('click', addChartToNewDashboard);
    document.getElementById('addToDashModal')?.addEventListener('click', (e) => {
        if (e.target.id === 'addToDashModal') _closeAddToDashModal();   // backdrop click
    });
}

// ─── Dataset selection & info panel ──────────────────────────────────────────

async function handleDatasetChange(e) {
    const datasetId = parseInt(e.target.value);

    // Reset UI state
    document.getElementById('datasetInfoPanel').classList.add('hidden');
    document.getElementById('datasetEmptyHint').classList.remove('hidden');
    setNlpEnabled(false);
    document.getElementById('nlpResultPanel').classList.add('hidden');
    document.getElementById('templateSelect').disabled = true;
    document.getElementById('executeButton').disabled = true;
    selectedDataset = null;
    selectedTemplate = null;
    document.getElementById('templateDescription').classList.add('hidden');
    document.getElementById('parameterForm').classList.add('hidden');

    if (!datasetId) return;

    selectedDataset = datasets.find(d => d.id === datasetId);
    if (!selectedDataset) return;

    // Show info panel
    renderDatasetInfo(selectedDataset);

    // Load columns
    await loadDatasetColumns(datasetId);

    // Load query history for this dataset
    loadQueryHistory(datasetId);

    // Enable downstream controls
    setNlpEnabled(true);
    document.getElementById('templateSelect').disabled = false;
    document.getElementById('templateSelect').innerHTML = '<option value="">-- Choose a template --</option>';
    templates.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.template_type;
        opt.textContent = t.name;
        document.getElementById('templateSelect').appendChild(opt);
    });
}

function renderDatasetInfo(dataset) {
    document.getElementById('datasetEmptyHint').classList.add('hidden');
    document.getElementById('datasetInfoPanel').classList.remove('hidden');

    document.getElementById('dsInfoName').textContent = dataset.original_filename || dataset.filename || 'Dataset';
    document.getElementById('dsInfoRows').textContent = (dataset.row_count || 0).toLocaleString();
    document.getElementById('dsInfoCols').textContent = dataset.column_count || '?';

    // Cleaned badge
    const cleanedBadge = document.getElementById('dsInfoCleanedBadge');
    if (dataset.cleaned_status) {
        cleanedBadge.classList.remove('hidden');
        cleanedBadge.classList.add('flex');
    } else {
        cleanedBadge.classList.add('hidden');
    }

    // Upload date
    const dateEl = document.getElementById('dsInfoDate');
    if (dataset.upload_date) {
        const d = new Date(dataset.upload_date);
        dateEl.textContent = 'Uploaded ' + d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    } else {
        dateEl.textContent = '';
    }

    // Column type pills (will be populated after loadDatasetColumns)
    document.getElementById('dsInfoColumns').innerHTML = '<span class="text-xs text-gray-400 italic">Loading columns...</span>';
}

function renderColumnPills(columns) {
    const container = document.getElementById('dsInfoColumns');
    if (!columns || columns.length === 0) {
        container.innerHTML = '';
        return;
    }

    const colorMap = {
        metric: 'bg-blue-100 text-blue-700 border-blue-200',
        date: 'bg-green-100 text-green-700 border-green-200',
        dimension: 'bg-indigo-100 text-indigo-700 border-indigo-200',
    };
    const iconMap = {
        metric: '#',
        date: '\u{1F4C5}',
        dimension: 'T',
    };

    // Show at most 12 pills; add "+N more" if clipped
    const shown = columns.slice(0, 12);
    const rest  = columns.length - shown.length;

    container.innerHTML = shown.map(col => {
        const cls = colorMap[col.category] || 'bg-gray-100 text-gray-600 border-gray-200';
        const icon = iconMap[col.category] || '';
        return `<span class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border ${cls} font-medium">
            <span class="opacity-60">${icon}</span>${col.name}
        </span>`;
    }).join('') + (rest > 0 ? `<span class="text-xs text-gray-400 self-center">+${rest} more</span>` : '');
}

async function loadDatasetColumns(datasetId) {
    try {
        const response = await API.get(`/queries/datasets/${datasetId}/columns`, true);
        datasetColumns = response.columns || [];
        renderColumnPills(datasetColumns);
    } catch (error) {
        console.error('Error loading dataset columns:', error);
        document.getElementById('dsInfoColumns').innerHTML = '<span class="text-xs text-red-400">Could not load columns</span>';
    }
}

// ─── Manual builder toggle ────────────────────────────────────────────────────

function toggleManualBuilder() {
    const body    = document.getElementById('manualBuilderBody');
    const chevron = document.getElementById('manualBuilderChevron');
    const stepNum = document.getElementById('manualBuilderStepNum');

    const isOpen = body.classList.contains('open');

    if (isOpen) {
        body.classList.remove('open');
        chevron.classList.remove('rotated');
        stepNum.classList.remove('bg-indigo-600');
        stepNum.classList.add('bg-gray-400');
    } else {
        body.classList.add('open');
        chevron.classList.add('rotated');
        stepNum.classList.remove('bg-gray-400');
        stepNum.classList.add('bg-indigo-600');
    }
}

// ─── NLP enable/disable helper ───────────────────────────────────────────────

function setNlpEnabled(enabled) {
    const card = document.getElementById('nlpCard');
    if (enabled) {
        card.classList.remove('opacity-50', 'pointer-events-none');
    } else {
        card.classList.add('opacity-50', 'pointer-events-none');
    }
}

// ─── Template selection & parameter form ─────────────────────────────────────

function handleTemplateChange(e) {
    const templateType = e.target.value;

    if (!templateType) {
        selectedTemplate = null;
        document.getElementById('templateDescription').classList.add('hidden');
        document.getElementById('parameterForm').classList.add('hidden');
        document.getElementById('executeButton').disabled = true;
        return;
    }

    selectedTemplate = templates.find(t => t.template_type === templateType);

    const descriptionDiv = document.getElementById('templateDescription');
    descriptionDiv.querySelector('p').textContent = selectedTemplate.description;
    descriptionDiv.classList.remove('hidden');

    buildParameterForm();
    document.getElementById('executeButton').disabled = false;
}

function buildParameterForm() {
    const container = document.getElementById('parametersContainer');
    container.innerHTML = '';

    selectedTemplate.parameters.forEach(param => {
        const div = document.createElement('div');

        const label = document.createElement('label');
        label.className = 'block text-sm font-semibold text-gray-700 mb-2';
        label.textContent = param.description + (param.required ? ' *' : '');
        div.appendChild(label);

        let input;

        if (param.type === 'metric') {
            input = makeSelect(`param-${param.name}`, param.required);
            input.innerHTML = '<option value="">-- Select column --</option>';
            datasetColumns.filter(c => c.category === 'metric').forEach(c => {
                const o = document.createElement('option');
                o.value = c.name;
                o.textContent = `${c.name} (${c.dtype})`;
                input.appendChild(o);
            });

        } else if (param.type === 'dimension') {
            input = makeSelect(`param-${param.name}`, param.required);
            input.innerHTML = '<option value="">-- Select column --</option>';
            datasetColumns.filter(c => c.category === 'dimension').forEach(c => {
                const o = document.createElement('option');
                o.value = c.name;
                o.textContent = c.name;
                input.appendChild(o);
            });

        } else if (param.type === 'date') {
            input = makeSelect(`param-${param.name}`, param.required);
            input.innerHTML = '<option value="">-- Select column --</option>';
            datasetColumns.filter(c => c.category === 'date').forEach(c => {
                const o = document.createElement('option');
                o.value = c.name;
                o.textContent = c.name;
                input.appendChild(o);
            });

        } else if (param.type === 'column') {
            input = makeSelect(`param-${param.name}`, param.required);
            input.innerHTML = '<option value="">-- Select column --</option>';
            datasetColumns.forEach(c => {
                const o = document.createElement('option');
                o.value = c.name;
                o.textContent = `${c.name} (${c.category})`;
                input.appendChild(o);
            });

        } else if (param.type === 'number') {
            input = document.createElement('input');
            input.type = 'number';
            input.id = `param-${param.name}`;
            input.className = 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500';
            input.value = param.default || '';
            input.required = param.required;

        } else if (param.type === 'aggregation') {
            input = makeSelect(`param-${param.name}`, false);
            ['sum', 'mean', 'count', 'min', 'max'].forEach(v => {
                const o = document.createElement('option');
                o.value = v;
                o.textContent = v.charAt(0).toUpperCase() + v.slice(1);
                if (param.default === v) o.selected = true;
                input.appendChild(o);
            });

        } else if (param.type === 'granularity') {
            input = makeSelect(`param-${param.name}`, false);
            ['day', 'week', 'month', 'quarter', 'year'].forEach(v => {
                const o = document.createElement('option');
                o.value = v;
                o.textContent = v.charAt(0).toUpperCase() + v.slice(1);
                if (param.default === v) o.selected = true;
                input.appendChild(o);
            });

        } else if (param.type === 'sort') {
            input = makeSelect(`param-${param.name}`, false);
            [['desc', 'Descending'], ['asc', 'Ascending'], ['none', 'None']].forEach(([v, l]) => {
                const o = document.createElement('option');
                o.value = v; o.textContent = l;
                if (param.default === v) o.selected = true;
                input.appendChild(o);
            });

        } else if (param.type === 'direction') {
            input = makeSelect(`param-${param.name}`, false);
            [['top', 'Top'], ['bottom', 'Bottom']].forEach(([v, l]) => {
                const o = document.createElement('option');
                o.value = v; o.textContent = l;
                if (param.default === v) o.selected = true;
                input.appendChild(o);
            });

        } else if (param.type === 'chart_type') {
            input = makeSelect(`param-${param.name}`, false);
            ['auto', 'histogram', 'pie'].forEach(v => {
                const o = document.createElement('option');
                o.value = v;
                o.textContent = v.charAt(0).toUpperCase() + v.slice(1);
                if (param.default === v) o.selected = true;
                input.appendChild(o);
            });
        }

        if (input) div.appendChild(input);
        container.appendChild(div);
    });

    document.getElementById('parameterForm').classList.remove('hidden');
}

function makeSelect(id, required) {
    const s = document.createElement('select');
    s.id = id;
    s.required = required;
    s.className = 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500';
    return s;
}

// ─── Template query execution ─────────────────────────────────────────────────

async function executeQuery() {
    if (!selectedDataset || !selectedTemplate) {
        Notifications.error('Please select a dataset and template');
        return;
    }

    const parameters = {};
    selectedTemplate.parameters.forEach(param => {
        const el = document.getElementById(`param-${param.name}`);
        if (!el) return;
        let value = el.value;
        if (param.type === 'number' && value) value = parseInt(value);
        if (!value && param.default !== undefined) value = param.default;
        if (value || !param.required) parameters[param.name] = value || param.default;
    });

    const missing = selectedTemplate.parameters
        .filter(p => p.required && !parameters[p.name])
        .map(p => p.description);

    if (missing.length > 0) {
        Notifications.error('Missing: ' + missing.join(', '));
        return;
    }

    const btn = document.getElementById('executeButton');
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<svg class="w-5 h-5 animate-spin mr-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path></svg> Running...';

    showChartLoading();   // CH-03: clear stale results the moment a run starts

    try {
        const response = await API.post('/queries/execute', {
            template_type: selectedTemplate.template_type,
            dataset_id: selectedDataset.id,
            parameters,
        }, true);

        if (!response.success) throw new Error(response.message || 'Query failed');
        displayResults(response);
        Notifications.success('Chart generated!');
    } catch (error) {
        showChartError(error.message);
        Notifications.error(`Failed: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = orig;
    }
}

// ─── NLP functions ────────────────────────────────────────────────────────────

function setNlpExample(btn) {
    document.getElementById('nlpInput').value = btn.textContent;
    document.getElementById('nlpInput').focus();
}

async function runNaturalQuery() {
    const queryText = document.getElementById('nlpInput').value.trim();
    if (!queryText) { Notifications.error('Please enter a question first'); return; }
    if (!selectedDataset) { Notifications.error('Please select a dataset first'); return; }

    const btn = document.getElementById('nlpAnalyzeBtn');
    btn.disabled = true;
    btn.innerHTML = '<svg class="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path></svg> Analyzing…';

    document.getElementById('nlpResultPanel').classList.add('hidden');

    // CH-03: a previously rendered chart must not sit there looking current
    // while the new question runs — clear it if one is showing.
    const hadResults = !document.getElementById('resultsSection').classList.contains('hidden');
    if (hadResults) showChartLoading();

    try {
        const response = await API.post('/queries/natural', {
            query_text: queryText,
            dataset_id: selectedDataset.id,
        }, true);
        nlpLastResult = response;
        // No chart in the response (clarification / params-only)? Return the
        // results area to the empty state instead of leaving a skeleton.
        if (hadResults && !(response.success && response.plotly_spec)) {
            document.getElementById('resultsSection').classList.add('hidden');
            document.getElementById('emptyState').classList.remove('hidden');
        }
        renderNlpResult(response);
    } catch (error) {
        Notifications.error(`Analysis failed: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg> Analyze';
    }
}

function renderNlpResult(response) {
    const panel     = document.getElementById('nlpResultPanel');
    const clarDiv   = document.getElementById('nlpClarification');
    const detDiv    = document.getElementById('nlpDetected');

    // NLP mode badge
    const badge = document.getElementById('nlpModeBadge');
    if (response.nlp_mode) {
        const isLLM       = response.nlp_mode === 'llm';
        const isEmbedding = response.nlp_mode === 'embeddings';
        badge.textContent = isLLM ? '✦ LLM Mode' : isEmbedding ? '✦ AI Mode' : 'Keyword Mode';
        badge.className = 'ml-auto text-xs font-medium px-3 py-1 rounded-full ' +
            (isLLM ? 'bg-indigo-100 text-indigo-700' : isEmbedding ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-500');
        badge.classList.remove('hidden');
    }

    panel.classList.remove('hidden');

    if (response.clarification) {
        clarDiv.classList.remove('hidden');
        detDiv.classList.add('hidden');
        document.getElementById('nlpClarificationText').textContent = response.clarification;
    } else if (response.success && response.plotly_spec) {
        clarDiv.classList.add('hidden');
        detDiv.classList.remove('hidden');
        showNlpDetected(response);
        displayResults(response);
        Notifications.success(`Chart generated (${response.nlp_mode || 'keyword'} mode)`);
    } else if (response.detected_parameters && Object.keys(response.detected_parameters).length > 0) {
        clarDiv.classList.add('hidden');
        detDiv.classList.remove('hidden');
        showNlpDetected(response);
    }
}

const INTENT_LABELS = {
    trend_over_time:       'Trend Over Time',
    category_comparison:   'Category Comparison',
    distribution_analysis: 'Distribution Analysis',
    top_k_items:           'Top-K Items',
    scatter_relationship:  'Scatter Relationship',
    correlation_analysis:  'Correlation Analysis',
    grouped_aggregation:   'Aggregation by Group',
    period_over_period:    'Period-over-Period',
};

const INTENT_ICONS = {
    trend_over_time:       '<i data-lucide="trending-up"></i>',
    category_comparison:   '<i data-lucide="bar-chart-3"></i>',
    distribution_analysis: '<i data-lucide="pie-chart"></i>',
    top_k_items:           '<i data-lucide="trophy"></i>',
    scatter_relationship:  '<i data-lucide="scatter-chart"></i>',
    correlation_analysis:  '<i data-lucide="link-2"></i>',
    grouped_aggregation:   '<i data-lucide="layers"></i>',
    period_over_period:    '<i data-lucide="repeat-2"></i>',
};

function showNlpDetected(response) {
    document.getElementById('nlpIntentBadge').textContent = INTENT_LABELS[response.intent] || response.intent || '';
    document.getElementById('nlpConfidence').textContent  =
        response.confidence != null ? `${(response.confidence * 100).toFixed(0)}% confidence` : '';

    const list = document.getElementById('nlpParamsList');
    list.innerHTML = '';
    const params = response.detected_parameters || {};
    Object.entries(params).forEach(([k, v]) => {
        if (v == null) return;
        const d = document.createElement('div');
        if (k === 'filters' && Array.isArray(v)) {
            // Render each filter as "where Region = North"
            v.forEach(f => {
                const fd = document.createElement('div');
                fd.innerHTML = `<span class="text-blue-600 font-medium">filter:</span> <span>${f.column} = <strong>${f.value}</strong></span>`;
                list.appendChild(fd);
            });
        } else {
            d.innerHTML = `<span class="text-green-600 font-medium">${k.replace(/_/g, ' ')}:</span> <span>${v}</span>`;
            list.appendChild(d);
        }
    });

    document.getElementById('nlpExecuteBtn').style.display = response.plotly_spec ? 'none' : 'flex';
}

async function executeNlpResult() {
    if (!nlpLastResult || !selectedDataset) return;
    const btn = document.getElementById('nlpExecuteBtn');
    btn.disabled = true;
    btn.textContent = 'Running…';
    showChartLoading();   // CH-03

    try {
        const response = await API.post('/queries/execute', {
            template_type: nlpLastResult.intent,
            dataset_id:    selectedDataset.id,
            parameters:    nlpLastResult.detected_parameters || {},
        }, true);
        if (!response.success) throw new Error(response.message || 'Query failed');
        displayResults(response);
        Notifications.success('Chart generated!');
    } catch (error) {
        showChartError(error.message);
        Notifications.error(`Failed: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run This Query';
    }
}

// ─── Results rendering ────────────────────────────────────────────────────────

/** CP-21: show a notice when a chart is built on raw (unreviewed) data. */
function _renderDataStateNotice(state, resultsSection) {
    let el = document.getElementById('dataStateNotice');
    if (state === 'raw') {
        if (!el) {
            el = document.createElement('div');
            el.id = 'dataStateNotice';
            el.className = 'mb-4 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800';
            resultsSection.insertBefore(el, resultsSection.firstChild);
        }
        el.innerHTML = `<i data-lucide="alert-triangle" style="width:16px;height:16px;margin-top:1px;flex-shrink:0;"></i>
            <span>Built on <strong>raw data</strong> — this dataset hasn't been cleaned yet, so these numbers may change after you
            <a href="datasets.html" class="underline font-semibold">review &amp; approve cleaning</a>.</span>`;
        if (window.lucide) { try { lucide.createIcons(); } catch (_) {} }
    } else if (el) {
        el.remove();
    }
}

function displayResults(response) {
    currentQueryResult = response.query_result;
    currentInsights = response.insights || [];
    const resultsSection = document.getElementById('resultsSection');
    resultsSection.classList.remove('hidden');
    document.getElementById('emptyState').classList.add('hidden');

    // CP-21: notice when the chart was built on RAW (unreviewed) data
    _renderDataStateNotice(response.data_state, resultsSection);

    displayInsights(response.insights || []);
    renderChart(response.plotly_spec);
    displayDataTable((response.query_result || {}).data || [],
                     (response.query_result || {}).column_labels || null);
    displayAnomalies((response.query_result || {}).anomalies || []);

    const addBtn = document.getElementById('addToDashboardButton');
    addBtn.disabled = false;
    addBtn.classList.remove('opacity-50', 'cursor-not-allowed');

    // Show Forecast button only for trend_over_time charts
    const templateType = response.intent                                    // NLP path
        || response.template_type                                           // template execute path
        || (selectedTemplate && selectedTemplate.template_type)            // fallback from UI state
        || '';
    _resetForecastState();
    // CH-03: pass the spec explicitly — snapshotting the async-set currentChart
    // here raced Plotly.newPlot and left _originalSpec null/stale.
    _initChartControls(templateType, response.plotly_spec);
    // CH-04: reflect the delivered chart type in the switcher + surface any
    // "couldn't honor your requested type" note from the backend.
    _syncChartTypeSelect(response);
    const forecastBtn = document.getElementById('forecastBtn');
    if (forecastBtn) {
        if (templateType === 'trend_over_time' && selectedDataset) {
            _forecastParams = {
                dataset_id:  selectedDataset.id,
                parameters:  response.detected_parameters
                    || (currentQueryResult && currentQueryResult.parameters)
                    || (selectedTemplate && _collectTemplateParams())
                    || {},
            };
            forecastBtn.classList.remove('hidden');
            forecastBtn.classList.add('inline-flex');
        } else {
            forecastBtn.classList.add('hidden');
            forecastBtn.classList.remove('inline-flex');
        }
    }

    document.getElementById('resultsSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
    saveQueryState(response);   // CH-08
}

// ─── CH-08: per-tab persistence of the last built chart ─────────────────────

const _QB_STATE_KEY = 'qb_state_v1';

function saveQueryState(response) {
    try {
        const state = {
            dataset_id:    selectedDataset ? selectedDataset.id : null,
            nlp_text:      document.getElementById('nlpInput')?.value || '',
            template_type: selectedTemplate ? selectedTemplate.template_type : null,
            response,
        };
        const payload = JSON.stringify(state);
        if (payload.length > 2_000_000) return;   // don't bloat sessionStorage
        sessionStorage.setItem(_QB_STATE_KEY, payload);
    } catch (_) { /* quota errors are non-fatal */ }
}

function restoreQueryState() {
    let state;
    try { state = JSON.parse(sessionStorage.getItem(_QB_STATE_KEY) || 'null'); } catch (_) { return; }
    if (!state || !state.dataset_id || !state.response) return;

    // An explicit handoff ("Use in Query Builder") wins over the saved chart.
    if (_handoffDatasetId && _handoffDatasetId !== state.dataset_id) {
        sessionStorage.removeItem(_QB_STATE_KEY);
        return;
    }

    const select = document.getElementById('datasetSelect');
    if (![...select.options].some(o => o.value === String(state.dataset_id))) {
        sessionStorage.removeItem(_QB_STATE_KEY);   // dataset gone — drop the state
        return;
    }

    if (!_handoffDatasetId) {
        select.value = String(state.dataset_id);
        select.dispatchEvent(new Event('change'));
    }
    if (state.nlp_text) {
        const inp = document.getElementById('nlpInput');
        if (inp) inp.value = state.nlp_text;
    }
    displayResults(state.response);   // instant re-render, no re-execution

    // Tell the user this is a restored snapshot, not a fresh run.
    const resultsSection = document.getElementById('resultsSection');
    if (resultsSection && !document.getElementById('qbRestoredNotice')) {
        const strip = document.createElement('div');
        strip.id = 'qbRestoredNotice';
        strip.className = 'flex items-center justify-between gap-3 bg-blue-50 border border-blue-200 text-blue-800 text-sm rounded-xl px-4 py-2.5 mb-4';
        strip.innerHTML = `<span>Restored your last chart — data as of when it ran. Re-run for fresh numbers.</span>
            <button class="text-blue-500 hover:text-blue-700 font-bold" onclick="this.parentElement.remove()">✕</button>`;
        resultsSection.insertBefore(strip, resultsSection.firstChild);
    }
    window.scrollTo({ top: 0 });   // don't auto-scroll to the chart on restore
}

function displayAnomalies(anomalies) {
    const panel = document.getElementById('anomalyPanel');
    const list  = document.getElementById('anomalyList');
    const count = document.getElementById('anomalyCount');

    if (!anomalies || anomalies.length === 0) {
        panel.classList.add('hidden');
        return;
    }

    panel.classList.remove('hidden');
    count.textContent = `${anomalies.length} anomal${anomalies.length === 1 ? 'y' : 'ies'} found`;

    const severityStyle = {
        high:   { bg: 'bg-red-50',    badge: 'bg-red-100 text-red-700',    dot: 'bg-red-500'    },
        medium: { bg: 'bg-orange-50', badge: 'bg-orange-100 text-orange-700', dot: 'bg-orange-500' },
        low:    { bg: 'bg-yellow-50', badge: 'bg-yellow-100 text-yellow-700', dot: 'bg-yellow-500' },
    };

    list.innerHTML = '';
    anomalies
        .sort((a, b) => { const o = {high:0,medium:1,low:2}; return o[a.severity]-o[b.severity]; })
        .forEach(a => {
            const s = severityStyle[a.severity] || severityStyle.low;
            const div = document.createElement('div');
            div.className = `flex items-center justify-between ${s.bg} rounded-lg px-4 py-3`;
            div.innerHTML = `
                <div class="flex items-center gap-3">
                    <span class="w-2.5 h-2.5 rounded-full ${s.dot} flex-shrink-0"></span>
                    <span class="font-medium text-gray-800">${a.label || a.index}</span>
                    <span class="text-gray-600 text-sm">value: <strong>${typeof a.value === 'number' ? a.value.toLocaleString() : a.value}</strong></span>
                    ${a.zscore != null ? `<span class="text-gray-500 text-xs">z=${a.zscore.toFixed(2)}</span>` : ''}
                </div>
                <span class="text-xs font-semibold px-2 py-1 rounded-full ${s.badge}">${a.severity.toUpperCase()}</span>
            `;
            list.appendChild(div);
        });
}

// ── Insight type metadata ────────────────────────────────────────────────────
const INSIGHT_META = {
    trend_up:      { icon: '↑', color: 'text-green-600',  bg: 'bg-green-50',  badge: 'bg-green-100 text-green-700'  },
    trend_down:    { icon: '↓', color: 'text-red-600',    bg: 'bg-red-50',    badge: 'bg-red-100 text-red-700'      },
    trend_stable:  { icon: '→', color: 'text-gray-500',   bg: 'bg-gray-50',   badge: 'bg-gray-100 text-gray-600'    },
    top_performer: { icon: '★', color: 'text-amber-500',  bg: 'bg-amber-50',  badge: 'bg-amber-100 text-amber-700'  },
    peak:          { icon: '▲', color: 'text-indigo-600', bg: 'bg-indigo-50', badge: 'bg-indigo-100 text-indigo-700' },
    trough:        { icon: '▼', color: 'text-indigo-600', bg: 'bg-indigo-50', badge: 'bg-indigo-100 text-indigo-700' },
    sudden_change: { icon: '<i data-lucide="zap"></i>', color: 'text-orange-600', bg: 'bg-orange-50', badge: 'bg-orange-100 text-orange-700' },
    anomaly:       { icon: '⚠', color: 'text-red-600',    bg: 'bg-red-50',    badge: 'bg-red-100 text-red-700'      },
    correlation:   { icon: '⇄', color: 'text-blue-600',   bg: 'bg-blue-50',   badge: 'bg-blue-100 text-blue-700'    },
    concentration: { icon: '◉', color: 'text-indigo-600', bg: 'bg-indigo-50', badge: 'bg-indigo-100 text-indigo-700' },
    distribution:  { icon: '◈', color: 'text-teal-600',   bg: 'bg-teal-50',   badge: 'bg-teal-100 text-teal-700'    },
    summary:       { icon: 'ℹ', color: 'text-blue-500',   bg: 'bg-white',     badge: 'bg-blue-50 text-blue-600'     },
};

function _confidenceLabel(conf) {
    if (conf >= 0.9) return { label: 'High', cls: 'text-green-600' };
    if (conf >= 0.7) return { label: 'Med',  cls: 'text-amber-600' };
    return                  { label: 'Low',  cls: 'text-gray-400'  };
}

function displayInsights(insights) {
    const container  = document.getElementById('insightsList');
    const countBadge = document.getElementById('insightCount');
    container.innerHTML = '';

    if (!insights || insights.length === 0) {
        container.innerHTML = '<p class="text-gray-400 text-sm italic">No insights available.</p>';
        if (countBadge) countBadge.classList.add('hidden');
        return;
    }

    if (countBadge) {
        countBadge.textContent = `${insights.length} finding${insights.length === 1 ? '' : 's'}`;
        countBadge.classList.remove('hidden');
    }

    insights.forEach(insight => {
        // Support both legacy strings and new structured dicts
        const isStr    = typeof insight === 'string';
        const text     = isStr ? insight : insight.text;
        const type     = isStr ? 'summary' : (insight.type || 'summary');
        const conf     = isStr ? null : insight.confidence;

        const meta     = INSIGHT_META[type] || INSIGHT_META.summary;
        const confInfo = conf != null ? _confidenceLabel(conf) : null;

        const div = document.createElement('div');
        div.className = `flex items-start gap-3 rounded-lg px-4 py-3 ${meta.bg}`;
        div.innerHTML = `
            <span class="flex-shrink-0 w-7 h-7 flex items-center justify-center rounded-full text-base font-bold ${meta.color} bg-white shadow-sm border border-gray-100">${meta.icon}</span>
            <span class="flex-1 text-sm text-gray-800 leading-relaxed">${text}</span>
            ${confInfo ? `<span class="flex-shrink-0 text-xs font-semibold ${confInfo.cls} mt-0.5 whitespace-nowrap" title="Confidence: ${Math.round(conf * 100)}%">${confInfo.label}</span>` : ''}
        `;
        container.appendChild(div);
    });
}

function renderChart(plotlySpec) {
    const container = document.getElementById('chartContainer');
    if (!plotlySpec || !plotlySpec.data || !plotlySpec.layout) {
        container.innerHTML = '<div class="text-center py-12 text-gray-500"><p>No chart data available</p></div>';
        return;
    }
    container.innerHTML = '';
    currentChart = plotlySpec;   // CH-03: set synchronously — consumers must not race newPlot
    _chartCustomizedUnsaved = false; // fresh render — no unsaved hand-edits yet
    // CH-05/CH-13: automargin so long tick labels/titles reflow instead of clipping
    const layout = { ...plotlySpec.layout, autosize: true, margin: { l: 60, r: 40, t: 60, b: 60 }, font: { family: 'Inter, sans-serif' } };
    layout.xaxis = { automargin: true, ...(layout.xaxis || {}) };
    layout.yaxis = { automargin: true, ...(layout.yaxis || {}) };
    Plotly.newPlot(container, plotlySpec.data, layout, {
        responsive: true, displayModeBar: true,
        modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
        displaylogo: false,
    }).catch(err => { container.innerHTML = `<div class="text-center py-12 text-red-500"><p>${err.message}</p></div>`; });
}

/**
 * CH-03 — one shared "working on it" state for both query paths: the old
 * chart/insights/table vanish the moment a new query is fired, so a slow
 * response can never masquerade as a fresh result.
 */
function showChartLoading() {
    document.getElementById('emptyState')?.classList.add('hidden');
    const resultsSection = document.getElementById('resultsSection');
    resultsSection?.classList.remove('hidden');
    SkeletonLoader.show(document.getElementById('chartContainer'), 'chart');
    const insights = document.getElementById('insightsList');
    if (insights) insights.innerHTML = '';
    const table = document.getElementById('dataTableContainer');
    if (table) table.innerHTML = '<p class="text-gray-400 text-center py-4 text-sm">Running query…</p>';
    document.getElementById('anomalyPanel')?.classList.add('hidden');
    document.getElementById('chartControls')?.classList.add('hidden');
    document.getElementById('chartChatWrap')?.classList.add('hidden');
}

/**
 * CH-03: a failed query must not leave the dark chart skeleton on screen —
 * show a readable error in the chart area instead.
 */
function showChartError(message) {
    const container = document.getElementById('chartContainer');
    if (container) {
        container.innerHTML = `
            <div class="text-center py-12">
                <p class="text-red-500 font-semibold mb-1">Query failed</p>
                <p class="text-sm text-gray-500 max-w-lg mx-auto">${message || 'Something went wrong — try rephrasing or re-running.'}</p>
            </div>`;
    }
    const table = document.getElementById('dataTableContainer');
    if (table) table.innerHTML = '';
}

const _ANOMALY_META_COLS = new Set(['is_anomaly', 'severity', 'zscore', 'detrended_zscore', 'method']);

function displayDataTable(data, labels) {
    const container = document.getElementById('dataTableContainer');
    if (!data || data.length === 0) { container.innerHTML = '<p class="text-gray-500 text-center py-4">No data</p>'; return; }

    // Strip anomaly metadata columns — they're already shown in the Anomaly panel
    const cols = Object.keys(data[0]).filter(c => !_ANOMALY_META_COLS.has(c));
    const table = document.createElement('table');
    table.className = 'w-full border-collapse';

    const thead = document.createElement('thead');
    thead.className = 'bg-gray-100';
    const hr = document.createElement('tr');
    cols.forEach(c => {
        const th = document.createElement('th');
        th.className = 'border px-4 py-2 text-left text-sm font-semibold';
        // CH-07: real column names ("Revenue (sum)") instead of the executor's
        // generic keys ("value") when the backend supplies a label map
        th.textContent = (labels && labels[c]) || c;
        hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    data.slice(0, 100).forEach((row, i) => {
        const tr = document.createElement('tr');
        tr.className = i % 2 === 0 ? 'bg-white' : 'bg-gray-50';
        cols.forEach(c => {
            const td = document.createElement('td');
            td.className = 'border px-4 py-2 text-sm';
            let v = row[c];
            if (typeof v === 'number') v = v.toLocaleString(undefined, { maximumFractionDigits: 2 });
            td.textContent = v != null ? v : '-';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    container.innerHTML = '';
    container.appendChild(table);
    if (data.length > 100) {
        const note = document.createElement('p');
        note.className = 'text-sm text-gray-500 mt-2';
        note.textContent = `Showing first 100 of ${data.length} rows`;
        container.appendChild(note);
    }
}

// ─── Query History ────────────────────────────────────────────────────────────

async function loadQueryHistory(datasetId) {
    const panel = document.getElementById('queryHistoryPanel');
    const list  = document.getElementById('historyList');

    try {
        const items = await API.get(`/datasets/${datasetId}/queries`, true);
        if (!items || items.length === 0) {
            panel.classList.add('hidden');
            return;
        }
        list.innerHTML = '';
        items.forEach(item => list.appendChild(renderHistoryItem(item)));
        panel.classList.remove('hidden');
    } catch (_) {
        panel.classList.add('hidden');
    }
}

function renderHistoryItem(item) {
    const icon  = INTENT_ICONS[item.template_type]  || '<i data-lucide="clipboard-list"></i>';
    const label = INTENT_LABELS[item.template_type] || item.template_type;

    const when = item.created_at
        ? new Date(item.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
        : '';

    const displayText = item.query_text
        ? `"${item.query_text.length > 60 ? item.query_text.slice(0, 60) + '…' : item.query_text}"`
        : label;

    const params = item.parameters || {};
    const paramSummary = Object.entries(params)
        .filter(([, v]) => v != null && v !== '')
        .slice(0, 3)
        .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
        .join(' · ');

    const div = document.createElement('div');
    div.className = 'flex items-center gap-4 px-6 py-3 hover:bg-gray-50 transition-colors group';
    div.innerHTML = `
        <span class="text-xl flex-shrink-0">${icon}</span>
        <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-gray-800 truncate">${displayText}</p>
            ${paramSummary ? `<p class="text-xs text-gray-400 truncate">${paramSummary}</p>` : ''}
        </div>
        <span class="text-xs text-gray-400 flex-shrink-0 hidden sm:block">${when}</span>
        <button
            class="flex-shrink-0 text-xs font-semibold text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
            onclick="rerunHistoryItem(${JSON.stringify(item).replace(/"/g, '&quot;')})"
        >Re-run</button>
    `;
    return div;
}

async function rerunHistoryItem(item) {
    if (!selectedDataset) { Notifications.error('Please select a dataset first'); return; }

    showChartLoading();   // CH-03: clear stale results the moment a run starts

    try {
        const response = await API.post('/queries/execute', {
            template_type: item.template_type,
            dataset_id:    selectedDataset.id,
            parameters:    item.parameters || {},
        }, true);
        if (!response.success) throw new Error(response.message || 'Query failed');
        displayResults(response);
        Notifications.success(`Re-ran: ${INTENT_LABELS[item.template_type] || item.template_type}`);
    } catch (error) {
        showChartError(error.message);
        Notifications.error(`Re-run failed: ${error.message}`);
    }
}

// ─── Add to Dashboard ─────────────────────────────────────────────────────────

function _buildChartConfigForDashboard() {
    return {
        id: `chart-${Date.now()}`,
        title: (selectedTemplate ? selectedTemplate.name : 'Query') + ' - ' + (selectedDataset.original_filename || selectedDataset.filename),
        plotlySpec: currentChart,
        queryResult: { ...(currentQueryResult || {}), insights: currentInsights },
        template: selectedTemplate ? { type: selectedTemplate.template_type, name: selectedTemplate.name } : null,
        dataset: { id: selectedDataset.id, name: selectedDataset.original_filename || selectedDataset.filename },
        createdAt: new Date().toISOString(),
        size: 'medium',
    };
}

/** Opens the picker: choose an existing dashboard or start a new one. */
async function addChartToDashboard() {
    if (!currentChart || !currentQueryResult) {
        Notifications.error('No chart to add. Please run a query first.');
        return;
    }
    if (!selectedDataset) { Notifications.error('Dataset info missing'); return; }

    const modal = document.getElementById('addToDashModal');
    const list = document.getElementById('addToDashList');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    list.innerHTML = '<p class="text-sm text-gray-400 py-3">Loading your dashboards…</p>';

    try {
        const dashboards = await API.get('/dashboards', true);
        const own = (dashboards || []).filter(d => !(d.description || '').startsWith('[Shared with you'));
        if (!own.length) {
            list.innerHTML = '<p class="text-sm text-gray-400 py-3">No saved dashboards yet — create your first one above.</p>';
            return;
        }
        list.innerHTML = own.map(d => `
            <button onclick="addChartToExistingDashboard(${d.id}, this)"
                class="w-full flex items-center justify-between gap-3 border border-gray-200 hover:border-indigo-300 hover:bg-indigo-50 rounded-xl px-4 py-2.5 text-left transition-colors">
                <span>
                    <span class="block text-sm font-semibold text-gray-800">${_escQH(d.name)}</span>
                    <span class="block text-xs text-gray-400">${d.chart_count} chart(s)${d.updated_at ? ` · updated ${new Date(d.updated_at).toLocaleDateString()}` : ''}</span>
                </span>
                <span class="text-indigo-500 text-lg flex-shrink-0">→</span>
            </button>`).join('');
    } catch (e) {
        list.innerHTML = `<p class="text-sm text-red-400 py-3">Could not load dashboards: ${_escQH(e.message || '')}</p>`;
    }
}

const _escQH = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function _closeAddToDashModal() {
    const modal = document.getElementById('addToDashModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

/** "New dashboard": stage the chart for the builder (existing flow). */
function addChartToNewDashboard() {
    const pending = Storage.get(Storage.userKey('pendingDashboardCharts')) || [];
    const chart = _buildChartConfigForDashboard();
    // Don't stage the same chart twice — repeated clicks used to pile up
    // identical copies that greeted the user on the builder page.
    const key = `${chart.title}|${JSON.stringify(chart.plotlySpec?.data ?? '')}`;
    const isDup = pending.some(c => `${c.title}|${JSON.stringify(c.plotlySpec?.data ?? '')}` === key);
    if (!isDup) {
        pending.push(chart);
        Storage.set(Storage.userKey('pendingDashboardCharts'), pending);
    }
    _chartCustomizedUnsaved = false; // staged/saved — safe to navigate away now
    _closeAddToDashModal();
    Notifications.success(isDup
        ? 'This chart is already staged — opening the Dashboard Builder…'
        : `Chart staged (${pending.length} waiting) — opening the Dashboard Builder…`);
    setTimeout(() => { window.location.href = 'dashboard.html'; }, 600);
}

/** Existing dashboard: append the chart to its saved config directly. */
async function addChartToExistingDashboard(dashboardId, btn) {
    if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }
    try {
        const dash = await API.get(`/dashboards/${dashboardId}`, true);
        const config = dash.config_json || {};
        config.charts = config.charts || [];
        config.charts.push(_buildChartConfigForDashboard());
        config.chart_count = config.charts.length;
        await API.put(`/dashboards/${dashboardId}`, { config_json: config }, true);
        _chartCustomizedUnsaved = false; // saved — safe to navigate away now
        _closeAddToDashModal();
        Notifications.success(
            `Added to "${_escQH(dash.name)}" — <a href="view-dashboard.html?id=${dashboardId}" style="text-decoration:underline;font-weight:700;">view it</a>`);
        const addBtn = document.getElementById('addToDashboardButton');
        addBtn.textContent = '✓ Added — add to another?';
        setTimeout(() => { addBtn.textContent = 'Add to Dashboard'; }, 4000);
    } catch (e) {
        Notifications.error(`Could not add chart: ${e.message || 'error'}`);
        if (btn) { btn.disabled = false; btn.style.opacity = ''; }
    }
}

// ─── Forecast ─────────────────────────────────────────────────────────────────

function _collectTemplateParams() {
    if (!selectedTemplate) return {};
    const params = {};
    selectedTemplate.parameters.forEach(p => {
        const el = document.getElementById(`param-${p.name}`);
        if (el && el.value) params[p.name] = p.type === 'number' ? parseInt(el.value) : el.value;
        else if (p.default !== undefined) params[p.name] = p.default;
    });
    return params;
}

function _resetForecastState() {
    _forecastActive    = false;
    _forecastParams    = null;
    _forecastBaseTraceCount = 0;
    const btn   = document.getElementById('forecastBtn');
    const label = document.getElementById('forecastBtnLabel');
    if (btn)   { btn.classList.remove('bg-indigo-100'); }
    if (label) { label.textContent = 'Show Forecast'; }
}

// ─── Chart controls: type override, recommendation, color, NL chat ──────────

let _originalSpec = null;      // pristine spec from the backend (for 'auto' reset)
let _lastTemplateType = '';

const _CHART_RECOMMENDATIONS = {
    trend_over_time:       { type: 'line',    reason: 'time series — lines show direction and change best' },
    category_comparison:   { type: 'bar',     reason: 'category comparison — bars make magnitude differences obvious' },
    distribution_analysis: { type: 'bar',     reason: 'distribution — histogram bars show the shape of the data' },
    top_k_items:           { type: 'bar',     reason: 'ranking — horizontal bars order items clearly' },
    scatter_relationship:  { type: 'scatter', reason: 'two-variable relationship — points reveal correlation patterns' },
    correlation_analysis:  { type: 'auto',    reason: 'correlation matrix — heatmap is the standard form' },
    grouped_aggregation:   { type: 'bar',     reason: 'grouped comparison — grouped bars separate dimensions' },
    period_over_period:    { type: 'bar',     reason: 'period comparison — side-by-side bars align the periods' },
};

function _initChartControls(templateType, spec) {
    // CH-03: the spec is passed explicitly; reading currentChart here raced
    // Plotly.newPlot's async .then and captured null or the previous chart.
    const src = spec || currentChart;
    _originalSpec = src ? JSON.parse(JSON.stringify(src)) : null;
    _lastTemplateType = templateType;
    document.getElementById('chartControls')?.classList.remove('hidden');
    document.getElementById('chartControls')?.classList.add('flex');
    document.getElementById('chartChatWrap')?.classList.remove('hidden');
    const sel = document.getElementById('chartTypeSelect');
    if (sel) sel.value = 'auto';
    const rec = _CHART_RECOMMENDATIONS[templateType];
    const recEl = document.getElementById('chartRecommendation');
    if (recEl) {
        recEl.textContent = rec ? `Recommended: ${rec.type === 'auto' ? 'current' : rec.type} — ${rec.reason}` : '';
        recEl.style.display = rec ? '' : 'none';
    }
    const fb = document.getElementById('chartChatFeedback');
    if (fb) fb.textContent = '';
}

function _convertTraces(spec, type) {
    // Returns a new {data, layout} with traces converted to the requested type.
    const data = JSON.parse(JSON.stringify(spec.data));
    const layout = JSON.parse(JSON.stringify(spec.layout));

    if (type === 'pie') {
        const t = data.find(tr => (tr.x && tr.y) || (tr.labels && tr.values));
        if (!t) return null;
        const labels = t.labels || t.x;
        const values = t.values || t.y;
        if (!labels || labels.length > 30) return null; // pie is unreadable beyond ~30 slices
        return {
            data: [{ type: 'pie', labels, values, hole: 0.35 }],
            layout: { title: layout.title },
        };
    }

    for (const tr of data) {
        if (tr.type === 'pie') {
            // pie → xy chart
            tr.x = tr.labels; tr.y = tr.values;
            delete tr.labels; delete tr.values; delete tr.hole;
        }
        if (!tr.x || !tr.y) continue;
        delete tr.fill;
        delete tr.orientation;
        if (type === 'line')    { tr.type = 'scatter'; tr.mode = 'lines+markers'; }
        if (type === 'area')    { tr.type = 'scatter'; tr.mode = 'lines'; tr.fill = 'tozeroy'; }
        if (type === 'bar')     { tr.type = 'bar';     delete tr.mode; }
        if (type === 'scatter') { tr.type = 'scatter'; tr.mode = 'markers'; }
        // CH-06: stacked and horizontal bar variants
        if (type === 'stacked_bar')        { tr.type = 'bar'; delete tr.mode; }
        if (type === 'horizontal_bar' || type === 'stacked_horizontal') {
            tr.type = 'bar'; delete tr.mode;
            const x = tr.x; tr.x = tr.y; tr.y = x;      // swap axes
            tr.orientation = 'h';
            delete tr.texttemplate;                       // y-based label template no longer applies
        }
    }
    if (type === 'stacked_bar' || type === 'stacked_horizontal') layout.barmode = 'stack';
    else if (type === 'horizontal_bar' || type === 'bar') layout.barmode = layout.barmode === 'stack' ? 'group' : layout.barmode;
    if (type === 'horizontal_bar' || type === 'stacked_horizontal') {
        // swap axis titles so the labels follow the data
        const xt = layout.xaxis?.title, yt = layout.yaxis?.title;
        layout.xaxis = { ...(layout.xaxis || {}), title: yt, automargin: true };
        layout.yaxis = { ...(layout.yaxis || {}), title: xt, automargin: true };
        // tick formatting travels with the value axis
        if (layout.yaxis.tickformat && !layout.xaxis.tickformat) {
            layout.xaxis.tickformat = layout.yaxis.tickformat;
            delete layout.yaxis.tickformat;
        }
    }
    return { data, layout };
}

/**
 * CH-04 — after a query returns, align the type dropdown with what the backend
 * actually delivered and surface a note when a requested type wasn't possible.
 */
function _syncChartTypeSelect(response) {
    const sel = document.getElementById('chartTypeSelect');
    if (sel) {
        const delivered = response.chart_config?.chart_type
            || response.chart_config?.config?.chart_type || '';
        sel.value = [...sel.options].some(o => o.value === delivered) ? delivered : 'auto';
    }
    const note = response.chart_type_note
        || response.chart_config?.chart_type_note
        || response.chart_config?.config?.chart_type_note;
    if (note) Notifications.info ? Notifications.info(note) : Notifications.success(note);
}

function changeChartType(type) {
    if (!_originalSpec) return;
    _resetForecastState();
    if (type === 'auto') { renderChart(_originalSpec); currentChart = _originalSpec; return; }
    const converted = _convertTraces(_originalSpec, type);
    if (!converted) {
        Notifications.error(type === 'pie'
            ? 'Pie needs a single categorical series with ≤ 30 categories.'
            : 'This chart cannot be converted to that type.');
        document.getElementById('chartTypeSelect').value = 'auto';
        return;
    }
    renderChart(converted);
    currentChart = converted;
}

/** hex -> [h, s, l] (degrees, percent, percent) */
function _hexToHsl(hex) {
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h, s;
    const l = (max + min) / 2;
    if (max === min) {
        h = s = 0;
    } else {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case r: h = (g - b) / d + (g < b ? 6 : 0); break;
            case g: h = (b - r) / d + 2; break;
            default: h = (r - g) / d + 4;
        }
        h /= 6;
    }
    return [h * 360, s * 100, l * 100];
}

function _hslToHex(h, s, l) {
    s /= 100; l /= 100;
    const k = n => (n + h / 30) % 12;
    const a = s * Math.min(l, 1 - l);
    const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    const toHex = x => Math.round(255 * x).toString(16).padStart(2, '0');
    return `#${toHex(f(0))}${toHex(f(8))}${toHex(f(4))}`;
}

/**
 * Light-to-dark gradient of N related colors from one base color — the same
 * idea as PowerBI/Tableau's single-color gradient schemes, used whenever a
 * chart needs more than one color (pie slices, stacked-bar segments,
 * multi-series lines) instead of forcing every slice/segment to one flat
 * color (which is what silently "did nothing" for those chart types before).
 */
function _generateShades(baseHex, n) {
    if (n <= 1) return [baseHex];
    const [h, s] = _hexToHsl(baseHex);
    const sat = Math.max(s, 35);
    const lightMax = 82, lightMin = 28;
    const shades = [];
    for (let i = 0; i < n; i++) {
        const l = lightMax - (i / (n - 1)) * (lightMax - lightMin);
        shades.push(_hslToHex(h, sat, l));
    }
    return shades;
}

/**
 * Plotly.restyle/relayout only mutate the LIVE chart DOM element — they
 * never touch `currentChart`, which is the object actually persisted when
 * "Add to Dashboard" is clicked (and re-rendered from on every later
 * refresh). Without this, any post-creation tweak — color, title, legend,
 * gridlines — looked applied but silently reverted the moment the chart was
 * saved or the page reloaded, because the SAVED spec never had the change.
 * Call this after every Plotly.restyle/relayout so the in-memory spec
 * matches what's actually on screen.
 */
function _syncCurrentChartFromLive() {
    const container = document.getElementById('chartContainer');
    if (!container || !container.data || !currentChart) return;
    currentChart = { ...currentChart, data: container.data, layout: container.layout };
    _chartCustomizedUnsaved = true;
}

function applyChartColor(color) {
    const container = document.getElementById('chartContainer');
    if (!container || !container.data) return;
    const traces = container.data;
    const n = traces.length;
    const indices = [...Array(n).keys()];
    const pieIndices = traces.map((t, i) => (t.type === 'pie' ? i : -1)).filter(i => i >= 0);
    const pending = [];

    if (pieIndices.length) {
        // Pie slices need ONE color EACH via marker.colors (plural, an
        // array) — Plotly ignores a scalar marker.color on pie traces
        // entirely, which is why picking a color here used to visibly do
        // nothing. Generate a gradient sized to the actual slice count.
        pieIndices.forEach(i => {
            const sliceCount = (traces[i].labels || traces[i].values || []).length || 1;
            pending.push(Plotly.restyle(container, { 'marker.colors': [_generateShades(color, sliceCount)] }, [i]));
        });
        const otherIndices = indices.filter(i => !pieIndices.includes(i));
        if (otherIndices.length) {
            pending.push(Plotly.restyle(container, { 'marker.color': color, 'line.color': color }, otherIndices));
        }
    } else if (n > 1) {
        // Multiple traces (stacked-bar segments, multi-series lines) each
        // need their OWN color — forcing every trace to the identical flat
        // color (the old behavior) made a stacked/multi-series chart look
        // unchanged or collapse into one indistinguishable color.
        const shades = _generateShades(color, n);
        pending.push(Plotly.restyle(container, { 'marker.color': shades, 'line.color': shades }, indices));
    } else {
        // Single trace, not a pie — a flat color is exactly what's expected.
        pending.push(Plotly.restyle(container, { 'marker.color': color, 'line.color': color }, indices));
    }

    Promise.all(pending).then(_syncCurrentChartFromLive).catch(() => {});
}

const _COLOR_WORDS = {
    red: '#ef4444', blue: '#3b82f6', green: '#22c55e', purple: '#6366f1', violet: '#6366f1',
    orange: '#f97316', yellow: '#eab308', pink: '#ec4899', teal: '#14b8a6', indigo: '#6366f1',
    black: '#1f2937', gray: '#6b7280', grey: '#6b7280', brown: '#92400e', cyan: '#06b6d4',
};

function handleChartChat() {
    const input = document.getElementById('chartChatInput');
    const fb = document.getElementById('chartChatFeedback');
    const cmd = (input?.value || '').trim().toLowerCase();
    if (!cmd) return;
    const container = document.getElementById('chartContainer');
    let handled = false;

    // 1) Chart type change: "make this a line chart", "change to bar", "stacked horizontal"
    // CH-06: stacked/horizontal vocabulary resolves to the composite types
    const stacked = /\bstack(?:ed)?\b/.test(cmd);
    const horizontal = /\bhorizontal\b|\bsideways\b/.test(cmd);
    const typeMatch = cmd.match(/\b(line|bar|column|area|scatter|pie)\b.*\bchart\b|\b(?:to|into|as)\s+(?:a\s+)?(line|bar|column|area|scatter|pie)\b|^(line|bar|column|area|scatter|pie)$/);
    if (typeMatch || ((stacked || horizontal) && /\bbars?\b|\bchart\b/.test(cmd))) {
        let t = (typeMatch && (typeMatch[1] || typeMatch[2] || typeMatch[3])) || 'bar';
        if (t === 'column') t = 'bar';
        if (t === 'bar' && stacked && horizontal) t = 'stacked_horizontal';
        else if (t === 'bar' && stacked)          t = 'stacked_bar';
        else if (t === 'bar' && horizontal)       t = 'horizontal_bar';
        document.getElementById('chartTypeSelect').value = t;
        changeChartType(t);
        fb.textContent = `✓ Changed to ${t.replace(/_/g, ' ')} chart`;
        handled = true;
    }

    // 2) Color: hex or named color anywhere in the command with a color-ish verb
    if (!handled) {
        const hex = cmd.match(/#[0-9a-f]{3,6}\b/);
        const named = Object.keys(_COLOR_WORDS).find(w => new RegExp(`\\b${w}\\b`).test(cmd));
        if ((hex || named) && /col(?:or|our)|make|change|paint|turn|set/.test(cmd)) {
            const color = hex ? hex[0] : _COLOR_WORDS[named];
            applyChartColor(color);
            document.getElementById('chartColorPicker').value = color.length === 4
                ? '#' + [...color.slice(1)].map(c => c + c).join('') : color;
            fb.textContent = `✓ Color set to ${named || color}`;
            handled = true;
        }
    }

    // 3) Title: 'title Monthly Revenue' / 'set title to ...'
    if (!handled) {
        const tm = (input.value || '').match(/title(?:\s+to)?\s+["']?(.+?)["']?$/i);
        if (tm) {
            Plotly.relayout(container, { 'title.text': tm[1] }).then(_syncCurrentChartFromLive).catch(() => {});
            fb.textContent = `✓ Title updated`;
            handled = true;
        }
    }

    // 4) Legend / grid toggles
    if (!handled && /\b(hide|remove|no)\b.*\blegend\b/.test(cmd)) {
        Plotly.relayout(container, { showlegend: false }).then(_syncCurrentChartFromLive).catch(() => {});
        fb.textContent = '✓ Legend hidden'; handled = true;
    }
    if (!handled && /\b(show|add)\b.*\blegend\b/.test(cmd)) {
        Plotly.relayout(container, { showlegend: true }).then(_syncCurrentChartFromLive).catch(() => {});
        fb.textContent = '✓ Legend shown'; handled = true;
    }
    if (!handled && /\b(hide|remove|no)\b.*\bgrid\b/.test(cmd)) {
        Plotly.relayout(container, { 'xaxis.showgrid': false, 'yaxis.showgrid': false }).then(_syncCurrentChartFromLive).catch(() => {});
        fb.textContent = '✓ Gridlines hidden'; handled = true;
    }
    if (!handled && /\b(show|add)\b.*\bgrid\b/.test(cmd)) {
        Plotly.relayout(container, { 'xaxis.showgrid': true, 'yaxis.showgrid': true }).then(_syncCurrentChartFromLive).catch(() => {});
        fb.textContent = '✓ Gridlines shown'; handled = true;
    }

    if (!handled) {
        fb.textContent = 'Not understood. Try: "make the bars blue" · "change to line chart" · "title Sales by Month" · "hide legend" · "hide grid"';
    } else {
        input.value = '';
    }
}

async function toggleForecast() {
    const btn   = document.getElementById('forecastBtn');
    const label = document.getElementById('forecastBtnLabel');
    const container = document.getElementById('chartContainer');

    if (_forecastActive) {
        // Remove forecast traces (keep only original traces)
        const chart = container._fullData ? container : null;
        if (chart && _forecastBaseTraceCount > 0) {
            const currentCount = container.data ? container.data.length : 0;
            const toRemove = [];
            for (let i = _forecastBaseTraceCount; i < currentCount; i++) toRemove.push(i);
            if (toRemove.length) await Plotly.deleteTraces(container, toRemove);
        }
        _forecastActive = false;
        _forecastBaseTraceCount = 0;
        btn.classList.remove('bg-indigo-100');
        label.textContent = 'Show Forecast';
        return;
    }

    if (!_forecastParams || !_forecastParams.dataset_id) {
        Notifications.error('Run a Trend Over Time query first.');
        return;
    }

    btn.disabled = true;
    label.textContent = 'Forecasting…';

    try {
        const resp = await API.post('/queries/forecast', {
            dataset_id: _forecastParams.dataset_id,
            parameters: _forecastParams.parameters || {},
            n_periods:  6,
            confidence: 0.95,
        }, true);

        if (!resp.success) throw new Error(resp.message || 'Forecast failed');

        const traces = resp.plotly_traces || [];
        if (!traces.length) throw new Error('No forecast data returned');

        // Record how many traces the chart already has before we add forecast
        _forecastBaseTraceCount = container.data ? container.data.length : 0;

        await Plotly.addTraces(container, traces);

        _forecastActive = true;
        btn.classList.add('bg-indigo-100');
        label.textContent = 'Hide Forecast';

        const trendEmoji = { up: '↑', down: '↓', flat: '→' }[resp.trend] || '';
        const r2 = resp.r_squared != null ? resp.r_squared.toFixed(2) : '—';
        Notifications.success(
            `Forecast: ${trendEmoji} ${resp.trend} trend · R²=${r2} · ${resp.n_periods} periods ahead`
        );
    } catch (err) {
        Notifications.error(`Forecast failed: ${err.message}`);
        _resetForecastState();
    } finally {
        btn.disabled = false;
    }
}
