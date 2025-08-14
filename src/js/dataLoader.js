// dataLoader.js - load JSON from file or URL and normalize entries
import { safeNum } from './utils.js';
let uidCounter = 0;
export function parseEntries(json) {
  if (!json || !Array.isArray(json.entries)) throw new Error('Missing entries array');
  const processed = json.entries.map(e => {
    const stat = e.season_match_statistics || {};
    const played = safeNum(stat.played);
    const won = safeNum(stat.won);
    const lost = safeNum(stat.lost);
    const winRate = played ? (won / played * 100) : 0;
    const isTeam = !!e.team;
    let memberNames = [];
    if (isTeam && e.team?.members) {
      memberNames = e.team.members.map(m => m.character?.name || '').filter(Boolean);
    }
    return {
      uid: uidCounter++,
      raw: e,
      isTeam,
      rank: e.rank ?? null,
      rating: safeNum(e.rating),
      played, won, lost, winRate,
      memberNames,
      teamName: e.team?.name ?? null,
      teamRealm: e.team?.realm?.slug ?? null,
      members: e.team?.members ?? null,
      charName: e.character?.name ?? null,
      charRealm: e.character?.realm?.slug ?? null,
      charClassId: e.character?.playable_class?.id ?? null,
      charClassName: e.character?.playable_class?.name ?? null,
      charRaceId: e.character?.playable_race?.id ?? null,
      charRaceName: e.character?.playable_race?.name ?? null
    };
  });
  processed.sort((a,b)=> b.rating - a.rating);
  return processed;
}
export async function loadFromFile(file) {
  const text = await file.text();
  const json = JSON.parse(text);
  uidCounter = 0;
  return parseEntries(json);
}
export async function loadFromUrl(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  uidCounter = 0;
  return parseEntries(json);
}
