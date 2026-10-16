// render.js - 統計、排行榜列表
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
        <span class="who-name"${nameStyle(row)}>${escapeHtml(row.name)}</span>
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
