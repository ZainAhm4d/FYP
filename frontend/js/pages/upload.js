/**
 * Upload Page Logic
 * Handles file upload with drag-and-drop and the external data connector tab.
 */

document.addEventListener('DOMContentLoaded', () => {
    // ── Tab switching ─────────────────────────────────────────────────────────
    const uploadTabPanel   = document.getElementById('uploadTabPanel');
    const connectTabPanel  = document.getElementById('connectTabPanel');

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;

            document.querySelectorAll('.tab-btn').forEach(b => {
                const active = b.dataset.tab === tab;
                b.classList.toggle('text-blue-600',   active);
                b.classList.toggle('border-blue-600', active);
                b.classList.toggle('text-gray-500',  !active);
                b.classList.toggle('border-transparent', !active);
                b.setAttribute('aria-selected', String(active));
            });

            uploadTabPanel.classList.toggle('hidden',  tab !== 'upload');
            connectTabPanel.classList.toggle('hidden', tab !== 'connect');
        });
    });

    // ── Source type selector (inside Connect tab) ─────────────────────────────
    let activeSource = 'google_sheets';
    const sheetsPanel = document.getElementById('sheetsPanel');
    const dbPanel     = document.getElementById('dbPanel');

    document.querySelectorAll('.source-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            activeSource = btn.dataset.source;

            // Update button styles
            document.querySelectorAll('.source-btn').forEach(b => {
                const on = b.dataset.source === activeSource;
                b.classList.toggle('border-green-500', on);
                b.classList.toggle('bg-green-50',      on);
                b.classList.toggle('text-green-700',   on);
                b.classList.toggle('border-gray-200',  !on);
                b.classList.toggle('text-gray-600',    !on);
            });

            sheetsPanel.classList.toggle('hidden', activeSource !== 'google_sheets');
            dbPanel.classList.toggle('hidden',     activeSource === 'google_sheets');

            // Set default port when switching DB type
            if (activeSource === 'mysql')    document.getElementById('dbPort').value = '3306';
            if (activeSource === 'postgres') document.getElementById('dbPort').value = '5432';

            // Reset table picker when switching source
            document.getElementById('tablePickerArea').classList.add('hidden');
            _connectHideAll();
        });
    });

    // ── Connect tab helpers ───────────────────────────────────────────────────
    function _connectHideAll() {
        document.getElementById('connectProgress').classList.add('hidden');
        document.getElementById('connectError').classList.add('hidden');
        document.getElementById('connectSuccess').classList.add('hidden');
    }
    function _connectShowProgress(msg) {
        _connectHideAll();
        document.getElementById('connectProgressText').textContent = msg;
        document.getElementById('connectProgress').classList.remove('hidden');
    }
    function _connectShowError(msg) {
        _connectHideAll();
        document.getElementById('connectErrorText').textContent = msg;
        document.getElementById('connectError').classList.remove('hidden');
    }
    function _connectShowSuccess(msg) {
        _connectHideAll();
        document.getElementById('connectSuccessText').textContent = msg;
        document.getElementById('connectSuccess').classList.remove('hidden');
    }

    // CH-10: reveal the interval picker only in "Scheduled only" mode
    document.querySelectorAll('input[name="sheetsRefreshMode"]').forEach(r => {
        r.addEventListener('change', () => {
            const scheduled = document.querySelector('input[name="sheetsRefreshMode"]:checked')?.value === 'scheduled';
            document.getElementById('sheetsRefresh')?.classList.toggle('hidden', !scheduled);
        });
    });

    // ── Google Sheets import ──────────────────────────────────────────────────
    document.getElementById('importSheetsBtn').addEventListener('click', async () => {
        const url  = document.getElementById('sheetsUrl').value.trim();
        const name = document.getElementById('sheetsName').value.trim();

        if (!url) {
            _connectShowError('Please enter a Google Sheets URL.');
            return;
        }

        _connectShowProgress('Downloading sheet and processing data…');
        document.getElementById('importSheetsBtn').disabled = true;

        // CH-10: Live mode = push webhook (primary) + hourly reconciliation
        // safety net; Scheduled mode = the user-picked interval only.
        const liveMode = document.querySelector('input[name="sheetsRefreshMode"]:checked')?.value !== 'scheduled';
        const interval = liveMode
            ? 60
            : (parseInt(document.getElementById('sheetsRefresh')?.value) || undefined);

        try {
            const res = await fetch(API.getUrl('/datasets/connect'), {
                method: 'POST',
                headers: API.getAuthHeaders(),
                body: JSON.stringify({
                    source_type: 'google_sheets',
                    url,
                    dataset_name: name || undefined,
                    refresh_interval_minutes: interval,
                }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `Server error ${res.status}`);
            }

            const dataset = await res.json();
            _connectShowSuccess(
                `"${dataset.original_filename}" imported — ${dataset.row_count.toLocaleString()} rows, ${dataset.column_count} columns.`
            );
            Notifications.success('Sheet imported and processed');
            setTimeout(loadRecentUploads, 600);
            // CH-10.2: Live mode → take the user straight to the one-time
            // Apps Script push setup instead of hoping they find it later.
            if (liveMode && dataset.id) {
                setTimeout(() => { window.location.href = `datasets.html?livesetup=${dataset.id}`; }, 1400);
            }
        } catch (err) {
            _connectShowError(err.message || 'Import failed. Please try again.');
        } finally {
            document.getElementById('importSheetsBtn').disabled = false;
        }
    });

    // ── DB: Load Tables ───────────────────────────────────────────────────────
    document.getElementById('loadTablesBtn').addEventListener('click', async () => {
        const host     = document.getElementById('dbHost').value.trim();
        const port     = parseInt(document.getElementById('dbPort').value, 10);
        const username = document.getElementById('dbUsername').value.trim();
        const password = document.getElementById('dbPassword').value;
        const database = document.getElementById('dbDatabase').value.trim();

        if (!host || !port || !username || !database) {
            _connectShowError('Host, Port, Username, and Database are required.');
            return;
        }

        _connectShowProgress('Connecting to database…');
        document.getElementById('loadTablesBtn').disabled = true;

        try {
            const res = await fetch(API.getUrl('/datasets/connect/tables'), {
                method: 'POST',
                headers: API.getAuthHeaders(),
                body: JSON.stringify({
                    source_type: activeSource,
                    host, port, username, password, database,
                }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `Server error ${res.status}`);
            }

            const { tables } = await res.json();
            _connectHideAll();

            if (!tables || tables.length === 0) {
                _connectShowError('No tables found in this database.');
                return;
            }

            const sel = document.getElementById('tableSelect');
            sel.innerHTML = tables.map(t => `<option value="${t}">${t}</option>`).join('');
            document.getElementById('tablePickerArea').classList.remove('hidden');
        } catch (err) {
            _connectShowError(err.message || 'Could not connect to database.');
        } finally {
            document.getElementById('loadTablesBtn').disabled = false;
        }
    });

    // ── DB: Import Table ──────────────────────────────────────────────────────
    document.getElementById('importTableBtn').addEventListener('click', async () => {
        const host       = document.getElementById('dbHost').value.trim();
        const port       = parseInt(document.getElementById('dbPort').value, 10);
        const username   = document.getElementById('dbUsername').value.trim();
        const password   = document.getElementById('dbPassword').value;
        const database   = document.getElementById('dbDatabase').value.trim();
        const table_name = document.getElementById('tableSelect').value;
        const name       = document.getElementById('dbDatasetName').value.trim();

        _connectShowProgress(`Importing table "${table_name}"…`);
        document.getElementById('importTableBtn').disabled = true;

        try {
            const res = await fetch(API.getUrl('/datasets/connect'), {
                method: 'POST',
                headers: API.getAuthHeaders(),
                body: JSON.stringify({
                    source_type: activeSource,
                    host, port, username, password, database, table_name,
                    dataset_name: name || undefined,
                }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `Server error ${res.status}`);
            }

            const dataset = await res.json();
            _connectShowSuccess(
                `"${dataset.original_filename}" imported — ${dataset.row_count.toLocaleString()} rows, ${dataset.column_count} columns.`
            );
            Notifications.success('Table imported and processed');
            setTimeout(loadRecentUploads, 600);
        } catch (err) {
            _connectShowError(err.message || 'Import failed. Please try again.');
        } finally {
            document.getElementById('importTableBtn').disabled = false;
        }
    });

    // ── Upload tab ────────────────────────────────────────────────────────────
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const fileInfo = document.getElementById('fileInfo');
    const uploadProgress = document.getElementById('uploadProgress');
    const uploadBtn = document.getElementById('uploadBtn');
    const removeFileBtn = document.getElementById('removeFileBtn');
    const errorMessage = document.getElementById('errorMessage');
    const successMessage = document.getElementById('successMessage');
    
    let selectedFile = null;
    const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB in bytes
    
    // Click to browse
    dropZone.addEventListener('click', () => {
        fileInput.click();
    });
    
    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    
    // Highlight drop zone when dragging over it
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });
    
    // Handle dropped files
    dropZone.addEventListener('drop', handleDrop, false);
    
    // Handle file selection via input
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFile(e.target.files[0]);
        }
    });
    
    // Remove file button
    removeFileBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        clearFileSelection();
    });
    
    // Upload button
    uploadBtn.addEventListener('click', uploadFile);
    
    // Helper functions
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight(e) {
        dropZone.classList.add('border-blue-500', 'bg-blue-50');
    }
    
    function unhighlight(e) {
        dropZone.classList.remove('border-blue-500', 'bg-blue-50');
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            handleFile(files[0]);
        }
    }
    
    // Limits mirror the server: Excel is heavier per row (formatting, formulas,
    // multiple sheets), so it gets a lower cap than CSV.
    const MAX_CSV_SIZE   = 50 * 1024 * 1024;  // 50 MB
    const MAX_EXCEL_SIZE = 20 * 1024 * 1024;  // 20 MB

    function handleFile(file) {
        // Validate file type
        const validExtensions = ['.csv', '.xlsx', '.xls'];
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();

        if (!validExtensions.includes(fileExtension)) {
            showError('Invalid file type. Please upload a CSV, XLSX, or XLS file.');
            return;
        }

        // Validate file size (differentiated by type)
        const isExcel = fileExtension === '.xlsx' || fileExtension === '.xls';
        const maxSize = isExcel ? MAX_EXCEL_SIZE : MAX_CSV_SIZE;
        if (file.size > maxSize) {
            const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
            const limitMB = maxSize / (1024 * 1024);
            showError(
                isExcel
                    ? `Excel file is ${sizeMB} MB — the Excel limit is ${limitMB} MB (Excel files carry formatting overhead). Tip: export large tables to CSV, which allows up to 50 MB.`
                    : `CSV file is ${sizeMB} MB — the limit is ${limitMB} MB. Consider splitting the file or removing unused columns.`
            );
            return;
        }
        
        // Store file and show info
        selectedFile = file;
        showFileInfo(file);
        hideMessage(errorMessage);
        hideMessage(successMessage);
    }
    
    function showFileInfo(file) {
        const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);
        
        document.getElementById('selectedFileName').textContent = file.name;
        document.getElementById('selectedFileSize').textContent = `${fileSizeMB} MB`;
        
        fileInfo.classList.remove('hidden');
    }
    
    function clearFileSelection() {
        selectedFile = null;
        fileInput.value = '';
        fileInfo.classList.add('hidden');
        uploadProgress.classList.add('hidden');
        hideMessage(errorMessage);
        hideMessage(successMessage);
    }
    
    async function uploadFile() {
        if (!selectedFile) {
            showError('Please select a file to upload.');
            return;
        }
        
        // Show progress
        uploadProgress.classList.remove('hidden');
        document.getElementById('uploadFileName').textContent = selectedFile.name;
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Uploading...';
        
        try {
            // Create form data with the file
            const formData = new FormData();
            formData.append('file', selectedFile);
            
            // Show initial progress
            document.getElementById('uploadPercentage').textContent = '0%';
            Loading.showProgress(0, 'progressBarContainer');

            // Real byte-level upload progress (not a simulated animation) —
            // reaches 100% only once the browser has actually sent every
            // byte; the request may still take a bit longer to respond
            // while the server parses the file, which is why the label
            // switches to "Processing…" once uploading itself completes.
            const response = await API.uploadFile('/datasets', formData, true, (percent) => {
                document.getElementById('uploadPercentage').textContent = `${percent}%`;
                Loading.showProgress(percent, 'progressBarContainer');
                if (percent >= 100) {
                    uploadBtn.textContent = 'Processing…';
                }
            });

            // Show 100% completion
            document.getElementById('uploadPercentage').textContent = '100%';
            Loading.showProgress(100, 'progressBarContainer');
            
            // Show success — cleaning is NOT applied automatically; the data is
            // analyzed in the background and the user approves fixes in Review
            showSuccess(`"${selectedFile.name}" uploaded! We're analyzing it for issues — nothing is changed without your approval.`);
            Notifications.success(
                response && response.id
                    ? `Uploaded! <a href="datasets.html?review=${response.id}" style="text-decoration:underline;font-weight:700;">Review &amp; Clean →</a>`
                    : 'Dataset uploaded'
            );
            
            // Reload recent uploads to show the new dataset
            setTimeout(() => {
                loadRecentUploads();
            }, 500);
            
            // Clear selection after short delay
            setTimeout(() => {
                clearFileSelection();
                // Optionally redirect to datasets page
                // window.location.href = 'datasets.html';
            }, 2000);
            
        } catch (error) {
            console.error('Upload error:', error);
            const errorMsg = error.message || 'Upload failed. Please try again.';
            showError(errorMsg);
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'Upload Dataset';
            uploadProgress.classList.add('hidden');
        }
    }
    
    function showError(message) {
        errorMessage.querySelector('#errorText').textContent = message;
        errorMessage.classList.remove('hidden');
    }
    
    function showSuccess(message) {
        successMessage.querySelector('#successText').textContent = message;
        successMessage.classList.remove('hidden');
    }
    
    function hideMessage(element) {
        element.classList.add('hidden');
    }
    
    // Load recent uploads on page load
    loadRecentUploads();
    
    async function loadRecentUploads() {
        const recentUploads = document.getElementById('recentUploads');
        
        try {
            // Show loading state
            recentUploads.innerHTML = '<div class="text-center py-8"><p class="text-gray-500">Loading recent uploads...</p></div>';
            
            // Fetch datasets from API
            const response = await API.get('/datasets', true);
            
            if (!response || response.length === 0) {
                // Show empty state
                EmptyStates.show(recentUploads, 'upload');
                return;
            }
            
            // Get only the 5 most recent uploads
            const recentDatasets = response.slice(0, 5);
            
            // Render recent uploads
            renderRecentUploads(recentDatasets);
            
        } catch (error) {
            console.error('Failed to load recent uploads:', error);
            recentUploads.innerHTML = `
                <div class="text-center py-8">
                    <p class="text-red-600">Failed to load recent uploads</p>
                    <button onclick="location.reload()" class="text-blue-600 hover:text-blue-800 mt-2">
                        Try Again
                    </button>
                </div>
            `;
        }
    }
    
    function renderRecentUploads(datasets) {
        const recentUploads = document.getElementById('recentUploads');
        
        const html = datasets.map(dataset => {
            const uploadDate = new Date(dataset.upload_date).toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            
            return `
                <div class="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-lg transition-shadow duration-200">
                    <div class="flex items-start justify-between">
                        <div class="flex items-start gap-4 flex-1">
                            <!-- File Icon -->
                            <div class="bg-gradient-to-br from-blue-500 to-indigo-600 p-3 rounded-lg flex-shrink-0">
                                <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                                </svg>
                            </div>
                            
                            <!-- Dataset Info -->
                            <div class="flex-1 min-w-0">
                                <h3 class="font-bold text-gray-800 text-lg truncate mb-1">
                                    ${dataset.original_filename || dataset.filename}
                                </h3>
                                <div class="flex flex-wrap gap-3 text-sm text-gray-600 mb-2">
                                    <span class="flex items-center gap-1">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                        </svg>
                                        ${uploadDate}
                                    </span>
                                    <span class="flex items-center gap-1">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"></path>
                                        </svg>
                                        ${dataset.row_count.toLocaleString()} rows
                                    </span>
                                    <span class="flex items-center gap-1">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"></path>
                                        </svg>
                                        ${dataset.column_count} columns
                                    </span>
                                    <span class="flex items-center gap-1">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path>
                                        </svg>
                                        ${dataset.file_size || 'N/A'}
                                    </span>
                                </div>
                                
                                <!-- Status Badge -->
                                <div class="flex items-center gap-2 mt-2">
                                    ${dataset.cleaned_status ? 
                                        '<span class="inline-flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full font-medium"><svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>Processed & Ready</span>' 
                                        : '<span class="inline-flex items-center gap-1 text-xs bg-yellow-100 text-yellow-700 px-2 py-1 rounded-full font-medium">Processing...</span>'
                                    }
                                </div>
                            </div>
                        </div>
                        
                        <!-- Action Buttons -->
                        <div class="flex gap-2 ml-4 flex-shrink-0">
                            <a href="query.html?dataset=${dataset.id}" 
                               class="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg transition-all shadow-sm hover:shadow-md text-sm font-medium">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                                </svg>
                                Create Query
                            </a>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        
        recentUploads.innerHTML = html;
    }
});
