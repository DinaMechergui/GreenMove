/* traffic_history.js : Récupération des snapshots et tracé Chart.js */
document.addEventListener('DOMContentLoaded', function() {
  const app = document.getElementById('traffic-history-app');
  if (!app) return;

  const historyUrl = app.dataset.historyUrl;
  const i18n = JSON.parse(document.getElementById('history-i18n')?.textContent || '{}');

  const form = document.getElementById('history-form');
  const pointSelect = document.getElementById('history_point_select');
  const daysSelect = document.getElementById('history_days_select');

  const loadingEl = document.getElementById('history-loading');
  const errorEl = document.getElementById('history-error');
  const kpisEl = document.getElementById('history-kpis');
  const chartCard = document.getElementById('history-chart-card');
  const tableCard = document.getElementById('history-table-card');
  const tableBody = document.getElementById('history-table-body');

  const kpiAvg = document.getElementById('kpi-avg');
  const kpiMax = document.getElementById('kpi-max');
  const kpiCount = document.getElementById('kpi-count');

  let chartInstance = null;

  function loadHistory() {
    const pointId = pointSelect.value;
    const days = daysSelect.value;
    if (!pointId) return;

    loadingEl.classList.add('is-active');
    errorEl.classList.add('d-none');

    const url = `${historyUrl}?point=${encodeURIComponent(pointId)}&days=${encodeURIComponent(days)}`;

    fetch(url)
      .then(r => {
        if (!r.ok) return r.json().then(e => { throw new Error(e.error || 'Erreur lors du chargement'); });
        return r.json();
      })
      .then(data => {
        loadingEl.classList.remove('is-active');
        const snaps = data.snapshots || [];

        if (snaps.length === 0) {
          errorEl.textContent = i18n.empty || 'Aucune donnée enregistrée pour ce point.';
          errorEl.classList.remove('d-none');
          kpisEl.classList.add('d-none');
          chartCard.classList.add('d-none');
          tableCard.classList.add('d-none');
          return;
        }

        kpisEl.classList.remove('d-none');
        chartCard.classList.remove('d-none');
        tableCard.classList.remove('d-none');

        // Calcul stats
        let sum = 0, maxVal = 0;
        snaps.forEach(s => {
          sum += s.congestion;
          if (s.congestion > maxVal) maxVal = s.congestion;
        });
        const avg = Math.round((sum / snaps.length) * 100);
        const maxPct = Math.round(maxVal * 100);

        kpiAvg.textContent = `${avg} %`;
        kpiMax.textContent = `${maxPct} %`;
        kpiCount.textContent = snaps.length;

        // Préparation Chart.js
        const labels = snaps.map(s => s.label);
        const realData = snaps.map(s => Math.round(s.congestion * 100));
        const predData = snaps.map(s => s.predicted != null ? Math.round(s.predicted * 100) : null);

        const ctx = document.getElementById('historyChart')?.getContext('2d');
        if (ctx) {
          if (chartInstance) chartInstance.destroy();

          const datasets = [{
            label: i18n.real || 'Congestion enregistrée (%)',
            data: realData,
            borderColor: '#335C45',
            backgroundColor: 'rgba(51, 92, 69, 0.1)',
            borderWidth: 2,
            fill: true,
            pointRadius: snaps.length > 50 ? 0 : 3,
            tension: 0.2
          }];

          if (data.model_available) {
            datasets.push({
              label: i18n.predicted || 'Prévision du modèle (%)',
              data: predData,
              borderColor: '#E8730C',
              backgroundColor: 'transparent',
              borderWidth: 2,
              borderDash: [5, 5],
              pointRadius: 0,
              tension: 0.2
            });
          }

          chartInstance = new Chart(ctx, {
            type: 'line',
            data: { labels: labels, datasets: datasets },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: 'index', intersect: false },
              scales: {
                y: {
                  min: 0,
                  max: 100,
                  title: { display: true, text: 'Congestion (%)' }
                },
                x: {
                  ticks: { maxTicksLimit: 12 }
                }
              }
            }
          });
        }

        // Tableau accessible
        tableBody.innerHTML = snaps.slice(-40).reverse().map(s => `
          <tr>
            <th scope="row">${s.label}</th>
            <td>${Math.round(s.current_speed)} km/h</td>
            <td><strong>${Math.round(s.congestion * 100)} %</strong></td>
            <td>${s.predicted != null ? `${Math.round(s.predicted * 100)} %` : '—'}</td>
            <td>${s.precipitation_mm > 0 ? `${s.precipitation_mm} mm` : '0 mm'}</td>
          </tr>
        `).join('');
      })
      .catch(err => {
        loadingEl.classList.remove('is-active');
        errorEl.textContent = err.message || (i18n.error || 'Erreur technique');
        errorEl.classList.remove('d-none');
      });
  }

  form.addEventListener('submit', function(e) {
    e.preventDefault();
    loadHistory();
  });

  pointSelect.addEventListener('change', loadHistory);
  daysSelect.addEventListener('change', loadHistory);

  // Chargement initial automatique
  loadHistory();
});
