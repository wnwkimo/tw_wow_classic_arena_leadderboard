// charts.js - 職業分佈、分數分佈（純 HTML / CSS，不用圖表套件）
import { CLASSES, iconUrl } from './constants.js';
import { escapeHtml, fmt, pct } from './utils.js';

export function renderClassChart(el, rows) {
  const counts = new Map();
  let total = 0;
  for (const row of rows) {
    const ids = row.isTeam ? row.members.map(m => m.classId) : [row.classId];
    for (const id of ids) {
      if (!CLASSES[id]) continue;
      counts.set(id, (counts.get(id) || 0) + 1);
      total++;
    }
  }
  if (!total) {
    el.innerHTML = '<p class="chart-empty">這個賽制沒有職業資料</p>';
    return;
  }
  const sorted = [...counts].sort((a, b) => b[1] - a[1]);
  const max = sorted[0][1];
  el.innerHTML = `<ul class="hbars">${sorted.map(([id, n]) => {
    const c = CLASSES[id];
    const share = pct(n, total);
    return `<li class="hbar" title="${c.name}：${fmt(n)} 人（${share.toFixed(1)}%）">
      <span class="hbar-label"><img src="${iconUrl(c.icon)}" alt="" loading="lazy">${c.name}</span>
      <span class="hbar-track"><i style="width:${pct(n, max)}%;background:${c.color}"></i></span>
      <span class="hbar-value">${fmt(n)}<small>${share.toFixed(0)}%</small></span>
    </li>`;
  }).join('')}</ul>`;
}

function binSize(span) {
  if (span <= 400) return 25;
  if (span <= 900) return 50;
  return 100;
}

export function renderRatingChart(el, rows) {
  if (rows.length < 2) {
    el.innerHTML = '<p class="chart-empty">資料太少，無法畫分佈</p>';
    return;
  }
  const ratings = rows.map(r => r.rating);
  const min = Math.min(...ratings), max = Math.max(...ratings);
  const size = binSize(max - min);
  const start = Math.floor(min / size) * size;
  const bins = Array.from({ length: Math.floor((max - start) / size) + 1 }, (_, i) => ({ from: start + i * size, n: 0 }));
  for (const r of ratings) bins[Math.floor((r - start) / size)].n++;
  const peak = Math.max(...bins.map(b => b.n));

  // x 軸只標幾個刻度，避免手機上擠在一起
  const step = Math.ceil(bins.length / 6);
  el.innerHTML = `
    <div class="histogram" style="--bins:${bins.length}">
      ${bins.map(b => `<button type="button" class="hist-bar" style="--h:${pct(b.n, peak)}%"
        data-tip="${b.from}–${b.from + size - 1}：${fmt(b.n)}" aria-label="${b.from} 到 ${b.from + size - 1} 分，${b.n} 筆"><i></i></button>`).join('')}
    </div>
    <div class="hist-axis" style="--bins:${bins.length}">
      ${bins.map((b, i) => `<span>${i % step === 0 ? b.from : ''}</span>`).join('')}
    </div>
    <p class="chart-note">每格 ${size} 分 · 最高一格 ${fmt(peak)} 筆</p>`;
}

export function clearChart(el, message) {
  el.innerHTML = `<p class="chart-empty">${escapeHtml(message)}</p>`;
}
