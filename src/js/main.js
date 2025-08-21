// main.js
import { loadFromFile, loadFromUrl } from './dataLoader.js';
import { renderTable, clearTable } from './tableRenderer.js';
import { renderChart, clearChart } from './chartRenderer.js';

let currentVisible = [];

// Loading indicator
function showLoading(message = '⏳ Loading...') {
  const loadingDiv = document.getElementById('loadingIndicator');
  if (loadingDiv) {
    loadingDiv.textContent = message;
    loadingDiv.style.display = 'block';
  }
}
function hideLoading() {
  const loadingDiv = document.getElementById('loadingIndicator');
  if (loadingDiv) loadingDiv.style.display = 'none';
}

// Summary panel
function renderSummary(list) {
  const count = list.length;
  const totalRating = list.reduce((s, i) => s + i.rating, 0);
  const totalMatches = list.reduce((s, i) => s + i.played, 0);
  const maxRating = count ? Math.max(...list.map(i => i.rating)) : 0;

  document.getElementById('summaryTeams').textContent = `隊伍/角色數: ${count}`;
  document.getElementById('summaryRating').textContent = `平均 Rating: ${count ? (totalRating / count).toFixed(1) : '-'}`;
  document.getElementById('summaryMatches').textContent = `總場次: ${totalMatches}`;
  document.getElementById('summaryMax').textContent = `最高 Rating: ${maxRating}`;
}

// Load from file
async function onFileSelected(file) {
  try {
    showLoading('📂 Loading file...');
    const list = await loadFromFile(file);
    currentVisible = list;
    renderTable(list, 0);
    renderChart(list);
    renderSummary(list);
  } catch (err) {
    console.error(err);
    alert('Failed to load file: ' + err.message);
  } finally {
    hideLoading();
  }
}

// Load from GitHub
async function onLoadFromGithub() {
  const season = document.getElementById('seasonSelect').value;
  const bracket = document.getElementById('bracketSelect').value;
  const url = `https://wnwkimo.github.io/tw_wow_classic_arena_leadderboard/data/season_${season}_${bracket}_tw_arena.json`;

  showLoading(`⏳ Loading Season ${season} ${bracket}...`);

  try {
    const list = await loadFromUrl(url);
    currentVisible = list;
    renderTable(list, parseInt(season, 10));
    renderChart(list);
    renderSummary(list);
  } catch (err) {
    console.error(err);
    alert('Failed to fetch JSON: ' + err.message);
  } finally {
    hideLoading();
  }
}

// Clear all views
function clearAll() {
  clearTable();
  clearChart();
  document.getElementById('summaryTeams').textContent = '隊伍/角色數: -';
  document.getElementById('summaryRating').textContent = '平均 Rating: -';
  document.getElementById('summaryMatches').textContent = '總場次: -';
  document.getElementById('summaryMax').textContent = '最高 Rating: -';
  currentVisible = [];
}

// Event bindings
document.getElementById('fileInput').addEventListener('change', ev => {
  const f = ev.target.files[0];
  if (f) onFileSelected(f);
  ev.target.value = '';
});
document.getElementById('clearBtn').addEventListener('click', clearAll);
document.getElementById('loadGithubBtn').addEventListener('click', onLoadFromGithub);

// Auto-load Season 12
document.addEventListener('DOMContentLoaded', () => {
  const seasonSelect = document.getElementById('seasonSelect');
  seasonSelect.value = "12";
  onLoadFromGithub();
});
