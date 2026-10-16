// main.js - 狀態管理與事件
import { loadManifest, loadBracket, loadRewards, loadFile } from './dataLoader.js';
import { renderStats, renderTitles, renderPodium, renderRows } from './render.js';
import { renderClassChart, renderRatingChart, clearChart } from './charts.js';
import { SEASONS, BRACKETS, CLASSES } from './constants.js';
import { escapeHtml, fmt } from './utils.js';

const PAGE = 100;
const $ = id => document.getElementById(id);

const el = {
  season: $('seasonSelect'),
  brackets: $('bracketTabs'),
  heading: $('boardHeading'),
  status: $('seasonStatus'),
  stats: $('stats'),
  titles: $('titles'),
  podium: $('podium'),
  search: $('searchInput'),
  faction: $('factionFilter'),
  classFilter: $('classFilter'),
  sort: $('sortSelect'),
  count: $('resultCount'),
  list: $('leaderboard'),
  listHead: $('listHead'),
  more: $('loadMore'),
  message: $('message'),
  classChart: $('classChart'),
  ratingChart: $('ratingChart'),
  file: $('fileInput'),
};

const state = {
  manifest: null,
  season: null,
  bracket: null,
  rows: [],
  isTeam: false,
  filtered: [],
  shown: 0,
  token: 0,
  tiers: [],
  rewards: new Map(),
};

// ---- 賽季 / 賽制選擇 ----

function availableBrackets(season) {
  const info = state.manifest?.seasons?.[season] || {};
  return Object.keys(BRACKETS).filter(b => b in info);
}

function fillSeasonSelect() {
  const seasons = Object.keys(state.manifest.seasons).map(Number).sort((a, b) => b - a);
  const groups = new Map();
  for (const s of seasons) {
    const exp = SEASONS[s]?.expansion || '其他';
    if (!groups.has(exp)) groups.set(exp, []);
    groups.get(exp).push(s);
  }
  el.season.innerHTML = [...groups].map(([exp, list]) => `
    <optgroup label="${escapeHtml(exp)}">
      ${list.map(s => `<option value="${s}">S${s}　${escapeHtml(SEASONS[s]?.title || '')}</option>`).join('')}
    </optgroup>`).join('');
}

function renderBracketTabs() {
  el.brackets.innerHTML = availableBrackets(state.season).map(b => `
    <button type="button" role="tab" class="tab" data-bracket="${b}" aria-selected="${b === state.bracket}">${BRACKETS[b]}</button>`).join('');
}

function readHash() {
  const m = location.hash.match(/^#s(\d+)(?:\/(\w+))?/);
  return m ? { season: Number(m[1]), bracket: m[2] } : {};
}

function select(season, bracket) {
  const seasons = state.manifest.seasons;
  if (!(season in seasons)) season = state.manifest.current_season in seasons
    ? state.manifest.current_season
    : Math.max(...Object.keys(seasons).map(Number));
  const brackets = availableBrackets(season);
  if (!brackets.includes(bracket)) bracket = brackets.includes(state.bracket) ? state.bracket : brackets[0];

  state.season = season;
  state.bracket = bracket;
  el.season.value = String(season);
  renderBracketTabs();
  history.replaceState(null, '', `#s${season}/${bracket}`);
  load();
}

// ---- 讀取資料 ----

function setHeading(title, sub, live) {
  el.heading.textContent = title;
  el.status.innerHTML = `${live ? '<span class="live-dot"></span>' : ''}${escapeHtml(sub)}`;
  el.status.classList.toggle('is-live', !!live);
}

function showMessage(text, retry) {
  el.message.hidden = !text;
  el.message.innerHTML = text ? `<p>${escapeHtml(text)}</p>${retry ? '<button type="button" class="btn" id="retryBtn">重試</button>' : ''}` : '';
  if (retry) $('retryBtn').addEventListener('click', load);
}

function setLoading(on) {
  document.body.classList.toggle('is-loading', on);
}

async function load() {
  const token = ++state.token;
  const { season, bracket } = state;
  const meta = SEASONS[season];
  const live = season === state.manifest.current_season;
  setHeading(`S${season} ${BRACKETS[bracket]}`, `${meta ? `${meta.expansion} · ${meta.title}` : `第 ${season} 季`}${live ? ' · 進行中' : ' · 已結束'}`, live);
  setLoading(true);
  showMessage('');
  try {
    const [data, rewards] = await Promise.all([loadBracket(season, bracket), seasonRewards(season)]);
    if (token !== state.token) return;
    setData(data, rewards?.brackets?.[bracket] || [], rewards);
  } catch (err) {
    if (token !== state.token) return;
    console.error(err);
    setData({ rows: [], isTeam: false });
    showMessage(`讀取失敗：${err.message}`, true);
  } finally {
    if (token === state.token) setLoading(false);
  }
}

// 頭銜門檻檔（每季一個，失敗時當作沒有門檻，不影響排行榜）
function seasonRewards(season) {
  if (!state.manifest.rewards?.includes(season)) return Promise.resolve(null);
  if (!state.rewards.has(season)) {
    state.rewards.set(season, loadRewards(season).catch(err => {
      console.warn('頭銜門檻讀取失敗', err);
      state.rewards.delete(season);
      return null;
    }));
  }
  return state.rewards.get(season);
}

// 門檻為 1 之類的是 API 的佔位值，不當成真的門檻
const MIN_CUTOFF = 2;
const MIN_WINS = 50;

function setData({ rows, isTeam }, tiers = [], rewards = null) {
  state.tiers = tiers.filter(t => t.rating_cutoff >= MIN_CUTOFF);
  for (const row of rows) {
    row.title = row.won >= MIN_WINS ? state.tiers.find(t => row.rating >= t.rating_cutoff) || null : null;
  }
  state.rows = rows;
  state.isTeam = isTeam;
  fillClassFilter();
  renderStats(el.stats, rows, isTeam);
  renderTitles(el.titles, state.tiers, rows, rewards);
  renderPodium(el.podium, rows);
  if (rows.length) {
    renderClassChart(el.classChart, rows);
    renderRatingChart(el.ratingChart, rows);
  } else {
    clearChart(el.classChart, '沒有資料');
    clearChart(el.ratingChart, '沒有資料');
  }
  document.body.classList.toggle('is-empty', !rows.length);
  applyFilters();
  if (!rows.length && el.message.hidden) showMessage('這個賽制沒有上榜資料');
}

// ---- 篩選 / 排序 ----

function fillClassFilter() {
  const present = new Set();
  for (const r of state.rows) {
    if (r.isTeam) r.members.forEach(m => present.add(m.classId));
    else present.add(r.classId);
  }
  const prev = el.classFilter.value;
  const ids = Object.keys(CLASSES).map(Number).filter(id => present.has(id));
  el.classFilter.innerHTML = `<option value="">全部職業</option>` +
    ids.map(id => `<option value="${id}">${CLASSES[id].name}</option>`).join('');
  el.classFilter.value = ids.includes(Number(prev)) ? prev : '';
  el.classFilter.disabled = !ids.length;
}

const SORTERS = {
  rank: (a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity) || b.rating - a.rating,
  winrate: (a, b) => b.winRate - a.winRate || b.played - a.played,
  played: (a, b) => b.played - a.played || b.rating - a.rating,
  won: (a, b) => b.won - a.won || b.rating - a.rating,
};

function applyFilters() {
  const query = el.search.value.trim().toLowerCase();
  const faction = el.faction.value;
  const classId = Number(el.classFilter.value) || null;

  state.filtered = state.rows.filter(r =>
    (!query || r.search.includes(query)) &&
    (!faction || r.faction === faction) &&
    (!classId || (r.isTeam ? r.members.some(m => m.classId === classId) : r.classId === classId))
  ).sort(SORTERS[el.sort.value] || SORTERS.rank);

  state.shown = Math.min(PAGE, state.filtered.length);
  renderRows(el.list, state.filtered, 0, state.shown);
  updateCount();
}

function updateCount() {
  const total = state.rows.length, n = state.filtered.length;
  el.count.textContent = !total ? '' : n === total
    ? `共 ${fmt(total)} 筆`
    : `符合 ${fmt(n)} / ${fmt(total)} 筆`;
  el.listHead.hidden = !n;
  el.more.hidden = state.shown >= n;
  el.more.textContent = `顯示更多（${fmt(state.shown)} / ${fmt(n)}）`;
  if (total && !n) el.list.innerHTML = '<li class="list-empty">沒有符合條件的結果</li>';
}

// ---- 事件 ----

el.season.addEventListener('change', () => select(Number(el.season.value), state.bracket));

el.brackets.addEventListener('click', e => {
  const tab = e.target.closest('[data-bracket]');
  if (tab && tab.dataset.bracket !== state.bracket) select(state.season, tab.dataset.bracket);
});

let searchTimer;
el.search.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(applyFilters, 150);
});
[el.faction, el.classFilter, el.sort].forEach(s => s.addEventListener('change', applyFilters));

el.more.addEventListener('click', () => {
  const next = Math.min(state.shown + PAGE, state.filtered.length);
  renderRows(el.list, state.filtered, state.shown, next);
  state.shown = next;
  updateCount();
});

el.list.addEventListener('click', e => {
  const btn = e.target.closest('.row-main[data-id]');
  if (!btn) return;
  const open = btn.getAttribute('aria-expanded') !== 'true';
  btn.setAttribute('aria-expanded', String(open));
  btn.nextElementSibling.hidden = !open;
});

window.addEventListener('hashchange', () => {
  const { season, bracket } = readHash();
  if (season !== state.season || bracket !== state.bracket) select(season, bracket);
});

el.file.addEventListener('change', async () => {
  const file = el.file.files[0];
  el.file.value = '';
  if (!file) return;
  state.token++;
  try {
    const data = await loadFile(file);
    setHeading(file.name, '本機檔案', false);
    el.brackets.querySelectorAll('.tab').forEach(t => t.setAttribute('aria-selected', 'false'));
    showMessage('');
    setData(data);
    document.getElementById('board').scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    showMessage(`無法讀取檔案：${err.message}`);
  }
});

// ---- 啟動 ----

(async function init() {
  setLoading(true);
  try {
    state.manifest = await loadManifest();
  } catch (err) {
    console.error(err);
    setLoading(false);
    showMessage(`無法讀取賽季清單：${err.message}`);
    return;
  }
  fillSeasonSelect();
  const { season, bracket } = readHash();
  select(season, bracket || '2v2');
})();
