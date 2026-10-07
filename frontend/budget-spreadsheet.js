import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import UniverPresetSheetsCoreArSA from '@univerjs/preset-sheets-core/locales/ar-SA';
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets';
import '@univerjs/preset-sheets-core/lib/index.css';

function installRtlCanvasTextPatch() {
  const prototype = window.CanvasRenderingContext2D?.prototype;
  if (!prototype || prototype.__budgetRtlTextPatched) return;
  window.__budgetRtlSpreadsheetActive = true;

  const shouldMirrorText = (context) => (
    window.__budgetRtlSpreadsheetActive
    && (
      !context.canvas?.id
      || (
        context.canvas.id.startsWith('univer-sheet-main-canvas_')
        && context.canvas.closest('#budget-spreadsheet-app')
      )
    )
  );
  const wrapTextMethod = (methodName) => {
    const original = prototype[methodName];
    if (typeof original !== 'function') return;
    prototype[methodName] = function budgetRtlCanvasText(text, x, y, maxWidth) {
      if (!shouldMirrorText(this)) {
        return maxWidth === undefined
          ? original.call(this, text, x, y)
          : original.call(this, text, x, y, maxWidth);
      }
      const measuredWidth = this.measureText(String(text)).width;
      const textWidth = maxWidth === undefined ? measuredWidth : Math.min(measuredWidth, maxWidth);
      const direction = this.direction === 'rtl' ? 'rtl' : 'ltr';
      const align = this.textAlign;
      const alignsLeft = align === 'left' || (align === 'start' && direction === 'ltr') || (align === 'end' && direction === 'rtl');
      const alignsRight = align === 'right' || (align === 'end' && direction === 'ltr') || (align === 'start' && direction === 'rtl');
      const textCenter = alignsLeft ? x + (textWidth / 2) : (alignsRight ? x - (textWidth / 2) : x);
      this.save();
      this.translate(textCenter * 2, 0);
      this.scale(-1, 1);
      const result = maxWidth === undefined
        ? original.call(this, text, x, y)
        : original.call(this, text, x, y, maxWidth);
      this.restore();
      return result;
    };
  };

  wrapTextMethod('fillText');
  wrapTextMethod('strokeText');
  Object.defineProperty(prototype, '__budgetRtlTextPatched', { value: true });
}

function enableRtlWorksheetSurface(root) {
  const apply = () => {
    const canvas = root.querySelector('canvas[id^="univer-sheet-main-canvas_"]');
    const surface = canvas?.parentElement;
    if (!surface) return false;
    surface.classList.add('budget-spreadsheet-rtl-surface');
    return true;
  };
  if (apply()) return;
  const observer = new MutationObserver(() => {
    if (apply()) observer.disconnect();
  });
  observer.observe(root, { childList: true, subtree: true });
}

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

  installRtlCanvasTextPatch();
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
  enableRtlWorksheetSurface(root);
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

  document.getElementById('print-spreadsheet')?.addEventListener('click', () => {
    window.print();
  });

  window.addEventListener('beforeunload', () => {
    window.__budgetRtlSpreadsheetActive = false;
    univer.dispose();
  }, { once: true });
}

startEditor().catch((error) => {
  console.error(error);
  setStatus(error.message || 'تعذر تشغيل محرر الجداول', 'danger');
});
