import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import UniverPresetSheetsCoreArSA from '@univerjs/preset-sheets-core/locales/ar-SA';
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets';
import '@univerjs/preset-sheets-core/lib/index.css';

function getCsrfToken() {
  return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

function setStatus(message, tone = 'secondary') {
  const status = document.getElementById('spreadsheet-status');
  if (!status) return;
  status.className = `badge text-bg-${tone}`;
  status.textContent = message;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.method && options.method !== 'GET' ? { 'X-CSRFToken': getCsrfToken() } : {}),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || payload.detail || `HTTP ${response.status}`);
  }
  return payload;
}

async function startEditor() {
  const root = document.getElementById('budget-spreadsheet-app');
  if (!root) return;
  const dataUrl = root.dataset.dataUrl;
  const saveUrl = root.dataset.saveUrl;
  const canEdit = root.dataset.canEdit === 'true';

  setStatus('جارٍ تحميل النموذج…', 'info');
  const payload = await requestJson(dataUrl);
  const { univer, univerAPI } = createUniver({
    locale: LocaleType.AR_SA,
    locales: {
      [LocaleType.AR_SA]: mergeLocales(UniverPresetSheetsCoreArSA),
    },
    presets: [
      UniverSheetsCorePreset({
        container: root,
      }),
    ],
  });
  univerAPI.createWorkbook(payload.workbook);
  window.budgetSpreadsheetEditor = { univer, univerAPI };
  setStatus(canEdit ? 'جاهز للتحرير' : 'عرض فقط', canEdit ? 'success' : 'secondary');

  const saveButton = document.getElementById('save-spreadsheet');
  if (!canEdit && saveButton) saveButton.disabled = true;
  saveButton?.addEventListener('click', async () => {
    try {
      saveButton.disabled = true;
      setStatus('جارٍ الحفظ والمزامنة…', 'warning');
      const workbook = univerAPI.getActiveWorkbook()?.save();
      if (!workbook) throw new Error('تعذر قراءة بيانات المصنف.');
      const result = await requestJson(saveUrl, {
        method: 'POST',
        body: JSON.stringify({ workbook }),
      });
      setStatus(`تم الحفظ · ${result.rows} صف · ${result.columns} عمود`, 'success');
    } catch (error) {
      console.error(error);
      setStatus(error.message || 'تعذر حفظ النموذج', 'danger');
    } finally {
      saveButton.disabled = !canEdit;
    }
  });

  window.addEventListener('beforeunload', () => univer.dispose(), { once: true });
}

startEditor().catch((error) => {
  console.error(error);
  setStatus(error.message || 'تعذر تشغيل محرر الجداول', 'danger');
});
