// main.js - application bootstrap and wiring
import { loadFromFile, loadFromUrl } from './dataLoader.js';
import { renderTable, clearTable } from './tableRenderer.js';
import { renderChart, clearChart } from './chartRenderer.js';

let currentVisible = [];

function renderSummary(list){
  const count = list.length;
  const totalRating = list.reduce((s,i)=>s+i.rating,0);
  const totalMatches = list.reduce((s,i)=>s+i.played,0);
  const maxRating = count ? Math.max(...list.map(i=>i.rating)) : 0;
  document.getElementById('summaryTeams').textContent = `隊伍/角色數: ${count}`;
  document.getElementById('summaryRating').textContent = `平均 Rating: ${count ? (totalRating/count).toFixed(1) : '-'}`;
  document.getElementById('summaryMatches').textContent = `總場次: ${totalMatches}`;
  document.getElementById('summaryMax').textContent = `最高 Rating: ${maxRating}`;
}

async function onFileSelected(file){
  try {
    const list = await loadFromFile(file);
    currentVisible = list;
    // 檔案匯入時沒有季節選擇，預設傳 0
    renderTable(list, 0);
    renderChart(list);
    renderSummary(list);
  } catch (err) { console.error(err); alert('Failed to load file: ' + err.message); }
}

async function onLoadFromGithub(){
  const season = document.getElementById('seasonSelect').value;
  const bracket = document.getElementById('bracketSelect').value;
  const url = `https://wnwkimo.github.io/tw_wow_classic_arena_leadderboard/data/season_${season}_${bracket}_tw_arena.json`;
  try {
    const list = await loadFromUrl(url);
    currentVisible = list;
    renderTable(list, parseInt(season, 10)); // 🔹 傳 season 給 tableRenderer
    renderChart(list);
    renderSummary(list);
  } catch (err){ console.error(err); alert('Failed to fetch JSON: ' + err.message); }
}

function clearAll(){
  clearTable();
  clearChart();
  document.getElementById('summaryTeams').textContent = '隊伍/角色數: -';
  document.getElementById('summaryRating').textContent = '平均 Rating: -';
  document.getElementById('summaryMatches').textContent = '總場次: -';
  document.getElementById('summaryMax').textContent = '最高 Rating: -';
  currentVisible = [];
}

document.getElementById('fileInput').addEventListener('change', ev => {
  const f = ev.target.files[0];
  if (f) onFileSelected(f);
  ev.target.value = '';
});

document.getElementById('clearBtn').addEventListener('click', clearAll);
document.getElementById('loadGithubBtn').addEventListener('click', onLoadFromGithub);
