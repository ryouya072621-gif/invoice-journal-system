/**
 * 請求書自動仕訳システム フロントエンド
 */

// グローバル変数
let entries = [];
let vendors = [];
let banks = [];
let previewItems = [];  // プレビュー用データ
let currentEditIndex = null;  // 現在編集中のインデックス

// DOM読み込み完了時
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadMasterData();
    initForms();
    initFileUpload();
    initBatchControls();
    initEntriesControls();
    initHistoryControls();
});

// ====== タブ切り替え ======

function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    const contents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetId = tab.dataset.tab;

            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            tab.classList.add('active');
            document.getElementById(targetId).classList.add('active');
        });
    });
}

// ====== マスタデータ読み込み ======

async function loadMasterData() {
    try {
        // 取引先読み込み
        const vendorRes = await fetch('/api/master/vendors');
        const vendorData = await vendorRes.json();
        vendors = vendorData.vendors || [];

        // 銀行読み込み
        const bankRes = await fetch('/api/master/banks');
        const bankData = await bankRes.json();
        banks = bankData.banks || [];

        // セレクトボックスを更新
        updateVendorSelects();
        updateBankSelects();
    } catch (error) {
        showMessage('マスタデータの読み込みに失敗しました', 'error');
    }
}

function updateVendorSelects() {
    const clientVendors = vendors.filter(v => v.type === 'client');
    const supplierVendors = vendors.filter(v => v.type === 'supplier');

    // 売上・入金用（クライアント）
    const salesSelects = ['sales-vendor', 'payment-vendor'];
    salesSelects.forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            select.innerHTML = '<option value="">選択してください</option>';
            clientVendors.forEach(v => {
                select.innerHTML += `<option value="${v.name}">${v.name}</option>`;
            });
        }
    });

    // 仕入・支払用（サプライヤー）
    const purchaseSelects = ['purchase-vendor', 'payment-make-vendor'];
    purchaseSelects.forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            select.innerHTML = '<option value="">選択してください</option>';
            supplierVendors.forEach(v => {
                select.innerHTML += `<option value="${v.name}">${v.name}</option>`;
            });
        }
    });
}

function updateBankSelects() {
    const bankSelects = ['payment-bank', 'payment-make-bank'];
    bankSelects.forEach(id => {
        const select = document.getElementById(id);
        if (select) {
            select.innerHTML = '<option value="">選択してください</option>';
            banks.forEach(b => {
                select.innerHTML += `<option value="${b.id}">${b.name}</option>`;
            });
        }
    });
}

// ====== フォーム処理 ======

function initForms() {
    // 売上計上フォーム
    document.getElementById('sales-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData);

        try {
            const res = await fetch('/api/sales/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await res.json();

            if (result.success) {
                addEntry(result.entry);
                showMessage('売上計上を追加しました', 'success');
                e.target.reset();
            } else {
                showMessage(result.error, 'error');
            }
        } catch (error) {
            showMessage('エラーが発生しました', 'error');
        }
    });

    // 入金処理フォーム
    document.getElementById('payment-receive-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData);

        try {
            const res = await fetch('/api/payment/receive', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await res.json();

            if (result.success) {
                addEntry(result.entry);
                showMessage('入金処理を追加しました', 'success');
                e.target.reset();
            } else {
                showMessage(result.error, 'error');
            }
        } catch (error) {
            showMessage('エラーが発生しました', 'error');
        }
    });

    // 仕入計上フォーム
    document.getElementById('purchase-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData);

        try {
            const res = await fetch('/api/purchase/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await res.json();

            if (result.success) {
                addEntry(result.entry);
                showMessage('仕入計上を追加しました', 'success');
                e.target.reset();
            } else {
                showMessage(result.error, 'error');
            }
        } catch (error) {
            showMessage('エラーが発生しました', 'error');
        }
    });

    // 支払処理フォーム
    document.getElementById('payment-make-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData);

        try {
            const res = await fetch('/api/payment/make', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await res.json();

            if (result.success) {
                addEntry(result.entry);
                showMessage('支払処理を追加しました', 'success');
                e.target.reset();
            } else {
                showMessage(result.error, 'error');
            }
        } catch (error) {
            showMessage('エラーが発生しました', 'error');
        }
    });

    // CSVエクスポート
    document.getElementById('export-csv-btn').addEventListener('click', exportCsv);
}

// ====== ファイルアップロード（一括対応） ======

function initFileUpload() {
    const dropArea = document.getElementById('drop-area');
    const fileInput = document.getElementById('file-input');
    const uploadBtn = document.getElementById('upload-btn');
    const uploadForm = document.getElementById('upload-form');
    const selectedFiles = document.getElementById('selected-files');

    // ドラッグ＆ドロップ
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.add('dragover'));
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.remove('dragover'));
    });

    dropArea.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        fileInput.files = files;
        updateSelectedFiles(files);
        uploadBtn.disabled = false;
    });

    fileInput.addEventListener('change', () => {
        updateSelectedFiles(fileInput.files);
        uploadBtn.disabled = !fileInput.files.length;
    });

    function updateSelectedFiles(files) {
        if (files.length === 0) {
            selectedFiles.textContent = '';
        } else if (files.length === 1) {
            selectedFiles.textContent = `選択: ${files[0].name}`;
        } else {
            selectedFiles.textContent = `選択: ${files.length}件のファイル`;
        }
    }

    // アップロード処理（一括）
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const files = fileInput.files;

        if (files.length === 0) return;

        uploadBtn.disabled = true;
        uploadBtn.textContent = `OCR処理中... (0/${files.length})`;

        previewItems = [];
        let successCount = 0;
        let errorCount = 0;
        let learnedCount = 0;

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            uploadBtn.textContent = `OCR処理中... (${i + 1}/${files.length})`;

            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch('/api/invoice/upload', {
                    method: 'POST',
                    body: formData
                });
                const result = await res.json();

                if (result.success) {
                    previewItems.push({
                        filename: file.name,
                        ocrData: result.data,
                        suggestedEntry: result.suggested_entry,
                        learningApplied: result.learning_applied,
                        selected: true,
                        error: null,
                        editing: false
                    });
                    successCount++;
                    if (result.learning_applied) learnedCount++;
                } else {
                    previewItems.push({
                        filename: file.name,
                        ocrData: null,
                        suggestedEntry: null,
                        learningApplied: false,
                        selected: false,
                        error: result.error || 'OCR処理に失敗しました',
                        editing: false
                    });
                    errorCount++;
                }
            } catch (error) {
                previewItems.push({
                    filename: file.name,
                    ocrData: null,
                    suggestedEntry: null,
                    learningApplied: false,
                    selected: false,
                    error: 'OCR処理に失敗しました（通信エラー）',
                    editing: false
                });
                errorCount++;
            }
        }

        // プレビュー表示
        showBatchPreview(successCount, errorCount, learnedCount);
        showMessage(`OCR処理完了: 成功 ${successCount}件, エラー ${errorCount}件`, successCount > 0 ? 'success' : 'error');

        // フォームリセット
        uploadForm.reset();
        selectedFiles.textContent = '';
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'OCR一括処理実行';
    });
}

// ====== バッチプレビュー ======

function initBatchControls() {
    // 全選択チェックボックス
    document.getElementById('select-all-preview').addEventListener('change', (e) => {
        previewItems.forEach((item, index) => {
            if (!item.error) {
                item.selected = e.target.checked;
            }
        });
        updatePreviewTable();
    });

    // 選択した仕訳を一括追加
    document.getElementById('add-selected-btn').addEventListener('click', () => {
        addSelectedEntries(false);
    });

    // 選択した仕訳を学習して追加
    document.getElementById('learn-selected-btn').addEventListener('click', () => {
        addSelectedEntries(true);
    });

    // クリア
    document.getElementById('clear-preview-btn').addEventListener('click', () => {
        previewItems = [];
        currentEditIndex = null;
        document.getElementById('batch-preview-section').style.display = 'none';
    });
}

function showBatchPreview(successCount, errorCount, learnedCount) {
    const section = document.getElementById('batch-preview-section');
    const summary = document.getElementById('batch-summary');

    // 合計金額計算
    const totalAmount = previewItems
        .filter(item => item.selected && item.suggestedEntry)
        .reduce((sum, item) => sum + (item.suggestedEntry.debit_amount || 0), 0);

    summary.innerHTML = `
        <div class="stat">
            <span class="stat-value">${successCount}</span>
            <span class="stat-label">処理成功</span>
        </div>
        <div class="stat">
            <span class="stat-value">${errorCount}</span>
            <span class="stat-label">エラー</span>
        </div>
        <div class="stat">
            <span class="stat-value">${learnedCount}</span>
            <span class="stat-label">学習適用</span>
        </div>
        <div class="stat">
            <span class="stat-value">¥${totalAmount.toLocaleString()}</span>
            <span class="stat-label">合計金額</span>
        </div>
    `;

    updatePreviewTable();
    section.style.display = 'block';
}

function getSelectOptionsHtml(templateId, selectedValue) {
    const template = document.getElementById(templateId);
    if (!template) return '';

    let html = template.innerHTML;
    if (selectedValue) {
        html = html.replace(`value="${selectedValue}"`, `value="${selectedValue}" selected`);
    }
    return html;
}

function updatePreviewTable() {
    const tbody = document.getElementById('preview-body');
    tbody.innerHTML = '';

    previewItems.forEach((item, index) => {
        const entry = item.suggestedEntry;
        const statusClass = item.error ? 'error' : (item.learningApplied ? 'learned' : 'new');
        const statusText = item.error ? 'エラー' : (item.learningApplied ? '学習適用' : '新規');
        const isEditing = item.editing;
        const rowClass = item.error ? 'error-row' : (item.selected ? 'selected' : '');

        // メイン行
        let row = `
            <tr class="${rowClass}" data-index="${index}">
                <td>
                    <input type="checkbox"
                           ${item.selected ? 'checked' : ''}
                           ${item.error ? 'disabled' : ''}
                           onchange="togglePreviewItem(${index}, this.checked)">
                </td>
                <td title="${item.filename}">${truncate(item.filename, 15)}</td>
                <td>${item.ocrData?.issuer || '-'}</td>
                <td>${entry?.date || '-'}</td>
                <td>${entry?.debit_account || '-'}</td>
                <td>${entry?.credit_account || '-'}</td>
                <td>${entry?.debit_amount?.toLocaleString() || '-'}</td>
                <td title="${entry?.description || ''}">${truncate(entry?.description || '-', 20)}</td>
                <td>
                    <span class="preview-status ${statusClass}">${statusText}</span>
                    ${item.error ? `<div class="error-detail">${truncate(item.error, 30)}</div>` : ''}
                </td>
                <td>
                    ${!item.error ? `
                        <button class="btn edit-btn" onclick="toggleEditPreviewItem(${index})">
                            ${isEditing ? '閉じる' : '編集'}
                        </button>
                    ` : ''}
                </td>
            </tr>
        `;

        tbody.innerHTML += row;

        // 編集行（展開時のみ）
        if (isEditing && !item.error) {
            const editRow = `
                <tr class="inline-edit-row" data-edit-index="${index}">
                    <td colspan="10">
                        <div class="inline-edit-form">
                            <div class="edit-grid">
                                <div class="edit-field">
                                    <label>日付</label>
                                    <input type="date" id="edit-date-${index}" value="${entry?.date || ''}">
                                </div>
                                <div class="edit-field">
                                    <label>借方科目</label>
                                    <select id="edit-debit-${index}">
                                        ${getSelectOptionsHtml('debit-account-options', entry?.debit_account)}
                                    </select>
                                </div>
                                <div class="edit-field">
                                    <label>借方補助</label>
                                    <input type="text" id="edit-debit-sub-${index}" value="${entry?.debit_sub_account || ''}">
                                </div>
                                <div class="edit-field">
                                    <label>借方税区分</label>
                                    <select id="edit-debit-tax-${index}">
                                        ${getSelectOptionsHtml('tax-category-options', entry?.debit_tax_category)}
                                    </select>
                                </div>
                                <div class="edit-field">
                                    <label>貸方科目</label>
                                    <select id="edit-credit-${index}">
                                        ${getSelectOptionsHtml('credit-account-options', entry?.credit_account)}
                                    </select>
                                </div>
                                <div class="edit-field">
                                    <label>貸方補助</label>
                                    <input type="text" id="edit-credit-sub-${index}" value="${entry?.credit_sub_account || ''}">
                                </div>
                                <div class="edit-field">
                                    <label>貸方税区分</label>
                                    <select id="edit-credit-tax-${index}">
                                        ${getSelectOptionsHtml('tax-category-options', entry?.credit_tax_category)}
                                    </select>
                                </div>
                                <div class="edit-field">
                                    <label>金額</label>
                                    <input type="number" id="edit-amount-${index}" value="${entry?.debit_amount || 0}">
                                </div>
                                <div class="edit-field" style="grid-column: span 2;">
                                    <label>摘要</label>
                                    <input type="text" id="edit-description-${index}" value="${entry?.description || ''}">
                                </div>
                            </div>
                            <div class="edit-actions">
                                <button class="btn" onclick="saveInlineEdit(${index})">保存</button>
                                <button class="btn danger" onclick="toggleEditPreviewItem(${index})">キャンセル</button>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
            tbody.innerHTML += editRow;
        }
    });
}

function toggleEditPreviewItem(index) {
    // 他の編集を閉じる
    previewItems.forEach((item, i) => {
        if (i !== index) item.editing = false;
    });

    // トグル
    previewItems[index].editing = !previewItems[index].editing;
    currentEditIndex = previewItems[index].editing ? index : null;

    updatePreviewTable();
}

function saveInlineEdit(index) {
    const item = previewItems[index];
    if (!item || !item.suggestedEntry) return;

    const amount = parseInt(document.getElementById(`edit-amount-${index}`).value) || 0;

    item.suggestedEntry = {
        ...item.suggestedEntry,
        date: document.getElementById(`edit-date-${index}`).value,
        debit_account: document.getElementById(`edit-debit-${index}`).value,
        debit_sub_account: document.getElementById(`edit-debit-sub-${index}`).value,
        debit_tax_category: document.getElementById(`edit-debit-tax-${index}`).value,
        credit_account: document.getElementById(`edit-credit-${index}`).value,
        credit_sub_account: document.getElementById(`edit-credit-sub-${index}`).value,
        credit_tax_category: document.getElementById(`edit-credit-tax-${index}`).value,
        debit_amount: amount,
        credit_amount: amount,
        description: document.getElementById(`edit-description-${index}`).value
    };

    item.editing = false;
    currentEditIndex = null;

    updatePreviewTable();
    updateBatchSummary();
    showMessage('編集を保存しました', 'success');
}

function togglePreviewItem(index, checked) {
    previewItems[index].selected = checked;
    updatePreviewTable();
    updateBatchSummary();
}

function updateBatchSummary() {
    const selectedCount = previewItems.filter(item => item.selected).length;
    const totalAmount = previewItems
        .filter(item => item.selected && item.suggestedEntry)
        .reduce((sum, item) => sum + (item.suggestedEntry.debit_amount || 0), 0);

    const summary = document.getElementById('batch-summary');
    const stats = summary.querySelectorAll('.stat');
    if (stats.length >= 4) {
        stats[3].querySelector('.stat-value').textContent = `¥${totalAmount.toLocaleString()}`;
    }
}

async function addSelectedEntries(shouldLearn) {
    const selectedItems = previewItems.filter(item => item.selected && item.suggestedEntry);

    if (selectedItems.length === 0) {
        showMessage('追加する項目を選択してください', 'warning');
        return;
    }

    let learnCount = 0;

    // 履歴記録用データ
    const historyEntries = [];
    const sourceFiles = [];
    const learningFlags = [];

    for (const item of selectedItems) {
        // 学習機能
        if (shouldLearn && item.ocrData) {
            try {
                const res = await fetch('/api/learn/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        original: item.ocrData,
                        corrected: item.suggestedEntry
                    })
                });
                const result = await res.json();
                if (result.success) learnCount++;
            } catch (error) {
                console.error('学習データ保存エラー:', error);
            }
        }

        // 仕訳を追加
        addEntry(item.suggestedEntry);

        // 履歴データ準備
        historyEntries.push(item.suggestedEntry);
        sourceFiles.push(item.filename || null);
        learningFlags.push(item.learningApplied || false);
    }

    // 履歴に一括記録
    try {
        await fetch('/api/history/entries/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                entries: historyEntries,
                source_files: sourceFiles,
                source_type: 'ocr_batch',
                learning_applied_flags: learningFlags
            })
        });
    } catch (error) {
        console.error('履歴記録エラー:', error);
    }

    const msg = shouldLearn
        ? `${selectedItems.length}件の仕訳を追加し、${learnCount}件を学習しました`
        : `${selectedItems.length}件の仕訳を追加しました`;
    showMessage(msg, 'success');

    // プレビューをクリア
    previewItems = [];
    currentEditIndex = null;
    document.getElementById('batch-preview-section').style.display = 'none';

    // 仕訳一覧タブに切り替え
    document.querySelector('[data-tab="entries"]').click();
}

// ====== 仕訳一覧 ======

function initEntriesControls() {
    // 全選択チェックボックス
    document.getElementById('select-all-entries').addEventListener('change', (e) => {
        entries.forEach(entry => {
            entry._selected = e.target.checked;
        });
        updateEntriesTable();
        updateDeleteButton();
    });

    // 全選択ボタン
    document.getElementById('select-all-entries-btn').addEventListener('click', () => {
        const allSelected = entries.every(e => e._selected);
        entries.forEach(entry => {
            entry._selected = !allSelected;
        });
        document.getElementById('select-all-entries').checked = !allSelected;
        updateEntriesTable();
        updateDeleteButton();
    });

    // 選択削除ボタン
    document.getElementById('delete-selected-btn').addEventListener('click', () => {
        const selectedCount = entries.filter(e => e._selected).length;
        if (selectedCount === 0) return;

        if (confirm(`${selectedCount}件の仕訳を削除しますか？`)) {
            entries = entries.filter(e => !e._selected);
            document.getElementById('select-all-entries').checked = false;
            updateEntriesTable();
            updateDeleteButton();
            showMessage(`${selectedCount}件を削除しました`, 'success');
        }
    });
}

function updateDeleteButton() {
    const selectedCount = entries.filter(e => e._selected).length;
    document.getElementById('delete-selected-btn').disabled = selectedCount === 0;
}

function addEntry(entry, historyId = null) {
    entry._selected = false;
    entry._historyId = historyId || generateUUID();
    entries.push(entry);
    updateEntriesTable();
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function removeEntry(index) {
    entries.splice(index, 1);
    updateEntriesTable();
}

function toggleEntrySelection(index, checked) {
    entries[index]._selected = checked;
    updateEntriesTable();
    updateDeleteButton();
}

function updateEntriesTable() {
    const tbody = document.getElementById('entries-body');
    const countSpan = document.getElementById('entry-count');
    const totalAmountSpan = document.getElementById('total-amount');
    const exportBtn = document.getElementById('export-csv-btn');

    // 合計金額計算
    const totalAmount = entries.reduce((sum, e) => sum + (e.debit_amount || 0), 0);

    tbody.innerHTML = '';
    entries.forEach((entry, index) => {
        tbody.innerHTML += `
            <tr class="${entry._selected ? 'selected' : ''}">
                <td>
                    <input type="checkbox"
                           ${entry._selected ? 'checked' : ''}
                           onchange="toggleEntrySelection(${index}, this.checked)">
                </td>
                <td>${entry.date}</td>
                <td>${entry.debit_account}</td>
                <td>${entry.debit_sub_account || '-'}</td>
                <td class="tax-category">${entry.debit_tax_category || '対象外'}</td>
                <td>${entry.debit_amount.toLocaleString()}</td>
                <td>${entry.credit_account}</td>
                <td>${entry.credit_sub_account || '-'}</td>
                <td class="tax-category">${entry.credit_tax_category || '対象外'}</td>
                <td>${entry.credit_amount.toLocaleString()}</td>
                <td title="${entry.description}">${truncate(entry.description, 20)}</td>
                <td><button class="btn danger edit-btn" onclick="removeEntry(${index})">削除</button></td>
            </tr>
        `;
    });

    countSpan.textContent = `${entries.length}件`;
    totalAmountSpan.textContent = `合計: ¥${totalAmount.toLocaleString()}`;
    exportBtn.disabled = entries.length === 0;
}

async function exportCsv() {
    if (entries.length === 0) return;

    try {
        const exportData = entries.map(e => ({
            date: e.date,
            debit_account: e.debit_account,
            debit_sub_account: e.debit_sub_account,
            debit_tax_category: e.debit_tax_category || '対象外',
            credit_account: e.credit_account,
            credit_sub_account: e.credit_sub_account,
            credit_tax_category: e.credit_tax_category || '対象外',
            amount: e.debit_amount,
            description: e.description
        }));

        const res = await fetch('/api/csv/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entries: exportData })
        });
        const result = await res.json();

        if (result.success) {
            // 履歴に出力記録
            const entryIds = entries.map(e => e._historyId).filter(id => id);
            if (entryIds.length > 0) {
                try {
                    await fetch('/api/history/exports', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            filename: result.filename,
                            entry_ids: entryIds
                        })
                    });
                } catch (err) {
                    console.error('出力履歴記録エラー:', err);
                }
            }

            // ダウンロード
            window.location.href = `/api/csv/download/${result.filename}`;
            showMessage(`弥生会計CSV（${entries.length}件）を出力しました`, 'success');

            // 出力後にエントリをクリア
            entries = [];
            updateEntriesTable();
        } else {
            showMessage(result.error, 'error');
        }
    } catch (error) {
        showMessage('CSV生成に失敗しました', 'error');
    }
}

// ====== 履歴機能 ======

function initHistoryControls() {
    // フィルタ変更
    document.getElementById('history-filter').addEventListener('change', loadHistory);

    // 更新ボタン
    document.getElementById('refresh-history-btn').addEventListener('click', loadHistory);

    // タブ切り替え時に履歴を読み込み
    document.querySelector('[data-tab="history"]').addEventListener('click', loadHistory);
}

async function loadHistory() {
    const filter = document.getElementById('history-filter').value;
    let url = '/api/history/entries?limit=100';

    if (filter === 'unexported') {
        url += '&exported=false';
    } else if (filter === 'exported') {
        url += '&exported=true';
    }

    try {
        // 統計情報と履歴を並列取得
        const [entriesRes, statsRes, exportsRes] = await Promise.all([
            fetch(url),
            fetch('/api/history/stats'),
            fetch('/api/history/exports?limit=20')
        ]);

        const entriesData = await entriesRes.json();
        const statsData = await statsRes.json();
        const exportsData = await exportsRes.json();

        if (entriesData.success) {
            updateHistoryTable(entriesData.entries);
        }

        if (statsData.success) {
            updateHistoryStats(statsData.stats);
        }

        if (exportsData.success) {
            updateExportsTable(exportsData.exports);
        }
    } catch (error) {
        console.error('履歴取得エラー:', error);
        showMessage('履歴の取得に失敗しました', 'error');
    }
}

function updateHistoryStats(stats) {
    const statsSpan = document.getElementById('history-stats');
    statsSpan.innerHTML = `
        総件数: <strong>${stats.total_entries}</strong> 件 |
        未出力: <strong>${stats.unexported_entries}</strong> 件 |
        出力済: <strong>${stats.exported_entries}</strong> 件 |
        CSV出力回数: <strong>${stats.total_exports}</strong> 回
    `;
}

function updateHistoryTable(historyEntries) {
    const tbody = document.getElementById('history-body');
    tbody.innerHTML = '';

    if (historyEntries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #999;">履歴がありません</td></tr>';
        return;
    }

    historyEntries.forEach(item => {
        const entry = item.entry || {};
        const createdAt = new Date(item.created_at).toLocaleString('ja-JP');
        const sourceType = {
            'ocr_batch': 'OCR一括',
            'ocr_single': 'OCR',
            'manual': '手動',
            'sales': '売上',
            'purchase': '仕入',
            'payment': '入金/支払'
        }[item.source_type] || item.source_type;

        tbody.innerHTML += `
            <tr>
                <td>${createdAt}</td>
                <td title="${item.source_file || ''}">${truncate(item.source_file || '-', 15)}</td>
                <td>${sourceType}</td>
                <td>${entry.date || '-'}</td>
                <td>${entry.debit_account || '-'}</td>
                <td>${entry.credit_account || '-'}</td>
                <td>${(entry.debit_amount || entry.amount || 0).toLocaleString()}</td>
                <td title="${entry.description || ''}">${truncate(entry.description || '-', 15)}</td>
                <td>${item.learning_applied ? '✓' : '-'}</td>
                <td>${item.exported ? '✓' : '-'}</td>
            </tr>
        `;
    });
}

function updateExportsTable(exports) {
    const tbody = document.getElementById('exports-body');
    tbody.innerHTML = '';

    if (exports.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: #999;">出力履歴がありません</td></tr>';
        return;
    }

    exports.forEach(exp => {
        const exportedAt = new Date(exp.exported_at).toLocaleString('ja-JP');
        tbody.innerHTML += `
            <tr>
                <td>${exportedAt}</td>
                <td>${exp.filename}</td>
                <td>${exp.entry_count}件</td>
            </tr>
        `;
    });
}

// ====== ユーティリティ ======

function truncate(str, maxLen) {
    if (!str) return '';
    return str.length > maxLen ? str.substring(0, maxLen) + '...' : str;
}

function showMessage(text, type) {
    const msg = document.getElementById('message');
    msg.textContent = text;
    msg.className = `message ${type}`;

    setTimeout(() => {
        msg.className = 'message';
    }, 3000);
}
