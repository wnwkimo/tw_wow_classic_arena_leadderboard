// dataLoader.js - 讀取 manifest / 排行榜 JSON，並整理成畫面用的資料
import { safeNum, pct } from './utils.js';
import { realmName } from './constants.js';

export async function loadManifest() {
  const res = await fetch('data/manifest.json', { cache: 'no-cache' });
  if (!res.ok) throw new Error(`manifest.json HTTP ${res.status}`);
  return res.json();
}

export async function loadBracket(season, bracket) {
  const res = await fetch(`data/season_${season}_${bracket}_tw_arena.json`, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return parseLeaderboard(await res.json());
}

export async function loadFile(file) {
  return parseLeaderboard(JSON.parse(await file.text()));
}

function stats(source) {
  const s = source?.season_match_statistics || {};
  const played = safeNum(s.played), won = safeNum(s.won), lost = safeNum(s.lost);
  return { played, won, lost, winRate: pct(won, played) };
}

function character(c) {
  return {
    name: c?.name || '-',
    realm: c?.realm?.slug || null,
    classId: c?.playable_class?.id ?? null,
    raceId: c?.playable_race?.id ?? null,
  };
}

export function parseLeaderboard(json) {
  if (!json || typeof json !== 'object') throw new Error('不是排行榜 JSON');
  const entries = Array.isArray(json.entries) ? json.entries : [];

  const rows = entries.map((e, i) => {
    const team = e.team;
    const base = {
      id: i,
      rank: e.rank ?? null,
      rating: safeNum(e.rating),
      faction: e.faction?.type || null,
      ...stats(e),
    };
    if (team) {
      const members = (team.members || []).map(m => ({
        ...character(m.character),
        rating: m.rating ?? null,
        ...stats(m),
      }));
      const bg = team.crest?.background?.color?.rgba;
      return {
        ...base,
        isTeam: true,
        name: team.name || '-',
        realm: team.realm?.slug || null,
        classId: null,
        raceId: null,
        members,
        crest: bg ? `rgb(${bg.r} ${bg.g} ${bg.b})` : null,
        search: [team.name, realmName(team.realm?.slug), ...members.map(m => m.name)].join(' ').toLowerCase(),
      };
    }
    const c = character(e.character);
    return {
      ...base,
      ...c,
      isTeam: false,
      members: [],
      search: [c.name, realmName(c.realm)].join(' ').toLowerCase(),
    };
  });

  rows.sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity) || b.rating - a.rating);
  return { rows, isTeam: rows.some(r => r.isTeam) };
}
