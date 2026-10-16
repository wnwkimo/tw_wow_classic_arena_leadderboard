// utils.js - small helpers
export function safeNum(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, m => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]
  ));
}

export const fmt = n => Math.round(n).toLocaleString('zh-TW');

export const pct = (part, whole) => (whole ? (part / whole) * 100 : 0);
