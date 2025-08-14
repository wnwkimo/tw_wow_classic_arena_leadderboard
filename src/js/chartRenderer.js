// chartRenderer.js - rating distribution chart
let ratingChart = null;
export function renderChart(list) {
  const labels = list.map(i => i.isTeam ? (i.teamName||i.charName) : (i.charName||i.teamName));
  const ratings = list.map(i => i.rating);
  const ctx = document.getElementById('ratingChart').getContext('2d');
  if (ratingChart) try { ratingChart.destroy(); } catch(e){}
  ratingChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ label: 'Rating', data: ratings }] },
    options: { responsive:true, plugins:{legend:{display:false}} }
  });
}
export function clearChart() {
  if (ratingChart) try { ratingChart.destroy(); } catch(e){}
  ratingChart = null;
}
