// render.js - 統計、前三名、排行榜列表
import { CLASSES, RACES, FACTIONS, iconUrl, realmName } from './constants.js';
import { escapeHtml, fmt, pct } from './utils.js';

const cls = id => CLASSES[id] || null;

function avatar(row, size = '') {
  if (row.isTeam) {
    const initial = escapeHtml([...row.name][0] || '?');
    return `<span class="avatar avatar-team ${size}" style="--crest:${row.crest || 'var(--surface-3)'}">${initial}</span>`;
  }
  const c = cls(row.classId);
  if (!c) return `<span class="avatar avatar-unknown ${size}" aria-hidden="true">?</span>`;
  return `<img class="avatar ${size}" src="${iconUrl(c.icon)}" alt="" loading="lazy" style="--cls:${c.color}">`;
}

function nameStyle(row) {
  const c = cls(row.classId);
  return c ? ` style="color:${c.color}"` : '';
}

function metaParts(row) {
  const parts = [];
  if (row.isTeam) {
    if (row.members.length) parts.push(`${row.members.length} 名成員`);
  } else {
    const c = cls(row.classId), r = RACES[row.raceId];
    parts.push(c ? c.name : '職業未知');
    if (r) parts.push(r.name);
  }
  parts.push(realmName(row.realm));
  return parts.map(escapeHtml).join('<i class="sep">·</i>');
}

export function titleBadge(title) {
  if (!title) return '';
  return `<span class="title-badge title-${title.tier}">${escapeHtml(title.title)}</span>`;
}

function factionBadge(faction) {
  if (!FACTIONS[faction]) return '';
  return `<span class="faction faction-${faction.toLowerCase()}" title="${FACTIONS[faction].name}">${FACTIONS[faction].name}</span>`;
}

// ---- 統計 ----
export function renderStats(el, rows, isTeam) {
  if (!rows.length) { el.innerHTML = ''; return; }
  const ratings = rows.map(r => r.rating);
  const avg = ratings.reduce((a, b) => a + b, 0) / rows.length;
  const horde = rows.filter(r => r.faction === 'HORDE').length;
  const alliance = rows.filter(r => r.faction === 'ALLIANCE').length;
  const hordePct = pct(horde, horde + alliance);

  el.innerHTML = `
    <div class="stat"><span class="stat-label">上榜${isTeam ? '隊伍' : '角色'}</span><span class="stat-value">${fmt(rows.length)}</span></div>
    <div class="stat"><span class="stat-label">最高分</span><span class="stat-value">${fmt(Math.max(...ratings))}</span></div>
    <div class="stat"><span class="stat-label">平均分</span><span class="stat-value">${fmt(avg)}</span></div>
    <div class="stat">
      <span class="stat-label">陣營比例</span>
      <span class="faction-split" role="img" aria-label="部落 ${horde}，聯盟 ${alliance}">
        <span class="split-bar"><i class="horde" style="width:${hordePct}%"></i><i class="alliance" style="width:${100 - hordePct}%"></i></span>
        <span class="split-legend"><span><b class="dot horde"></b>部落 ${Math.round(hordePct)}%</span><span><b class="dot alliance"></b>聯盟 ${Math.round(100 - hordePct)}%</span></span>
      </span>
    </div>`;
}

// ---- 頭銜門檻 ----
function titlesNote(rewards) {
  if (rewards?.estimated) return 'API 沒有這季的門檻，依 S1 實際門檻反推的規則估算：打滿 30 場的隊伍為母數，依隊伍分數排名';
  return rewards?.final ? '賽季結算門檻' : '進行中，門檻會隨天梯變動';
}

export function renderTitles(el, tiers, rows, rewards) {
  if (!tiers.length) { el.hidden = true; el.innerHTML = ''; return; }
  el.hidden = false;
  const count = tier => rows.filter(r => r.title?.tier === tier).length;
  el.innerHTML = `
    <div class="titles-head">
      <h3 class="card-title">頭銜門檻${rewards?.estimated ? '<span class="estimate-tag">推估</span>' : ''}</h3>
      <p class="card-sub">${titlesNote(rewards)} · 需在本季贏得 50 場</p>
    </div>
    <ul class="titles-list">${tiers.map(t => `
      <li class="titles-item">
        ${titleBadge(t)}
        <span class="titles-cutoff">${fmt(t.rating_cutoff)}<small>分以上</small></span>
        <span class="titles-count">${fmt(count(t.tier))} ${rows.some(r => r.isTeam) ? '隊' : '人'}</span>
      </li>`).join('')}
    </ul>`;
}

// ---- 前三名 ----
export function renderPodium(el, rows) {
  const top = rows.slice(0, 3);
  if (!top.length) { el.innerHTML = ''; return; }
  el.innerHTML = top.map((row, i) => `
    <article class="podium-card place-${i + 1} tier-${Math.min(row.rank ?? i + 1, 3)}">
      <span class="podium-rank">#${row.rank ?? i + 1}</span>
      ${avatar(row, 'avatar-lg')}
      <div class="podium-who">
        <h3 class="podium-name"><span class="name-text"${nameStyle(row)}>${escapeHtml(row.name)}</span>${titleBadge(row.title)}</h3>
        <p class="podium-meta">${metaParts(row)}</p>
      </div>
      <div class="podium-score">
        <span class="podium-rating">${fmt(row.rating)}</span>
        <span class="podium-record">${row.won}勝 ${row.lost}敗 · ${row.winRate.toFixed(0)}%</span>
      </div>
    </article>`).join('');
}

// ---- 排行榜 ----
function memberList(row) {
  if (!row.members.length) return '<p class="members-empty">這支隊伍沒有成員資料</p>';
  return `<ul class="members">${row.members.map(m => {
    const c = cls(m.classId), r = RACES[m.raceId];
    return `<li class="member">
      ${avatar({ ...m, isTeam: false }, 'avatar-sm')}
      <span class="member-who">
        <span class="member-name"${nameStyle(m)}>${escapeHtml(m.name)}</span>
        <span class="member-meta">${escapeHtml([c?.name || '職業未知', r?.name].filter(Boolean).join(' · '))}</span>
      </span>
      <span class="member-rating">${m.rating ?? '-'}</span>
      <span class="member-record">${m.won}-${m.lost}</span>
    </li>`;
  }).join('')}</ul>`;
}

function rowHtml(row) {
  const rank = row.rank ?? '-';
  const medal = row.rank && row.rank <= 3 ? ` medal-${row.rank}` : '';
  const inner = `
    <span class="cell-rank${medal}">${rank}</span>
    <span class="cell-who">
      ${avatar(row)}
      <span class="who-text">
        <span class="who-line"><span class="who-name"${nameStyle(row)}>${escapeHtml(row.name)}</span>${titleBadge(row.title)}</span>
        <span class="who-meta">${factionBadge(row.faction)}${metaParts(row)}</span>
      </span>
    </span>
    <span class="cell-rating">${fmt(row.rating)}</span>
    <span class="cell-record"><span class="won">${row.won}</span><span class="dash">-</span><span class="lost">${row.lost}</span><span class="pct-inline">${row.winRate.toFixed(0)}%</span></span>
    <span class="cell-winrate" title="勝率 ${row.winRate.toFixed(1)}%">
      <span class="winbar"><i style="width:${row.winRate}%"></i></span>
      <span class="winrate-num">${row.winRate.toFixed(1)}%</span>
    </span>`;

  if (!row.isTeam) return `<li class="row"><div class="row-main">${inner}</div></li>`;
  return `<li class="row is-team">
    <button class="row-main" type="button" aria-expanded="false" data-id="${row.id}">${inner}<span class="chevron" aria-hidden="true"></span></button>
    <div class="row-detail" hidden>${memberList(row)}</div>
  </li>`;
}

export function renderRows(listEl, rows, start, end) {
  const html = rows.slice(start, end).map(rowHtml).join('');
  if (start === 0) listEl.innerHTML = html;
  else listEl.insertAdjacentHTML('beforeend', html);
}
