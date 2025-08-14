// utils.js - small helpers
export function safeNum(v) {
  if (typeof v === 'number' && !Number.isNaN(v)) return v;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
export function escapeHtml(s) {
  return String(s||'').replace(/[&<>\"]/g, function(m){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m];
  });
}
