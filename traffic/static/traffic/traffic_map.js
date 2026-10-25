/* traffic_map.js : Carte Leaflet et mise à jour dynamique de la congestion */
document.addEventListener('DOMContentLoaded', function () {
  const app = document.getElementById('traffic-map-app');
  if (!app) return;

  const i18n = JSON.parse(document.getElementById('tm-i18n')?.textContent || '{}');
  const heatmapUrl = app.dataset.heatmapUrl;
  const comfortUrl = app.dataset.comfortUrl;
  const rainUrl = app.dataset.rainUrl;
  const airUrl = app.dataset.airUrl;

  // 1. Initialisation carte Leaflet (centrée sur Tunis)
  const mapElement = document.getElementById('traffic-map');
  const map = L.map('traffic-map').setView([36.8065, 10.1815], 11);

  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19,
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, METI'
  }).addTo(map);

  let markersLayer = L.layerGroup().addTo(map);

  // Éléments DOM
  const dateInput = document.getElementById('tm-date');
  const timeSlider = document.getElementById('tm-time');
  const timeOut = document.getElementById('tm-time-out');
  const statusEl = document.getElementById('tm-status');
  const errorEl = document.getElementById('tm-error');
  const tableBody = document.getElementById('tm-table-body');

  const wxTemp = document.getElementById('wx-temp');
  const wxRain = document.getElementById('wx-rain');
  const wxAir = document.getElementById('wx-air');
  const wxComfort = document.getElementById('wx-comfort');
  const rainAlertBox = document.getElementById('rain-alert');
  const rainAlertText = document.getElementById('rain-alert-text');

  // Helpers pour l'heure
  function sliderToTime(val) {
    const totalMinutes = parseInt(val, 10) * 15;
    const h = String(Math.floor(totalMinutes / 60)).padStart(2, '0');
    const m = String(totalMinutes % 60).padStart(2, '0');
    return `${h}:${m}`;
  }

  function getLevelIcon(code) {
    switch (code) {
      case 'fluide': return '<i class="bi bi-check-lg" aria-hidden="true"></i>';
      case 'modere': return '<i class="bi bi-dash-lg" aria-hidden="true"></i>';
      case 'dense':  return '<i class="bi bi-exclamation-lg" aria-hidden="true"></i>';
      case 'bloque': return '<i class="bi bi-x-lg" aria-hidden="true"></i>';
      default: return '';
    }
  }

  // Chargement météo
  function loadWeather() {
    // Alerte pluie
    if (rainUrl) {
      fetch(rainUrl)
        .then(r => r.json())
        .then(data => {
          if (data && data.alert) {
            rainAlertBox.classList.remove('d-none');
            rainAlertText.textContent = data.message || 'La pluie arrive sous peu !';
          } else {
            rainAlertBox.classList.add('d-none');
          }
        })
        .catch(() => {});
    }

    // Qualité air
    if (airUrl) {
      fetch(airUrl)
        .then(r => r.json())
        .then(data => {
          if (wxAir && data) {
            wxAir.textContent = data.label ? `${data.label} (AQI ${data.aqi ?? '?'})` : 'Bonne';
          }
        })
        .catch(() => { if (wxAir) wxAir.textContent = i18n.unavailable || 'Indisponible'; });
    }

    // Confort & météo
    if (comfortUrl) {
      fetch(comfortUrl)
        .then(r => r.json())
        .then(data => {
          if (data && data.conditions) {
            if (wxTemp) wxTemp.textContent = `${Math.round(data.conditions.temperature)} °C`;
            if (wxRain) wxRain.textContent = `${data.conditions.precipitation_mm || 0} mm`;
          }
          if (wxComfort && data) {
            wxComfort.textContent = `${data.score}/100 (${data.label || ''})`;
          }
        })
        .catch(() => {
          if (wxTemp) wxTemp.textContent = '22 °C';
          if (wxRain) wxRain.textContent = '0 mm';
          if (wxComfort) wxComfort.textContent = i18n.unavailable || 'Indisponible';
        });
    }
  }

  // Chargement Heatmap / Trafic
  let fetchController = null;
  function updateHeatmap() {
    if (fetchController) fetchController.abort();
    fetchController = new AbortController();

    const selectedDate = dateInput.value;
    const selectedTime = sliderToTime(timeSlider.value);
    timeOut.textContent = selectedTime;
    const isoDateTime = `${selectedDate}T${selectedTime}:00`;

    mapElement.setAttribute('aria-busy', 'true');
    statusEl.textContent = i18n.loading || 'Chargement de la prévision…';
    errorEl.classList.add('d-none');

    const url = `${heatmapUrl}?datetime=${encodeURIComponent(isoDateTime)}`;

    fetch(url, { signal: fetchController.signal })
      .then(r => {
        if (!r.ok) return r.json().then(e => { throw new Error(e.error || 'Erreur serveur'); });
        return r.json();
      })
      .then(data => {
        mapElement.setAttribute('aria-busy', 'false');
        markersLayer.clearLayers();

        const counts = { fluide: 0, modere: 0, dense: 0, bloque: 0 };
        const sortedPoints = [...(data.points || [])].sort((a, b) => b.congestion - a.congestion);

        // Mettre à jour les marqueurs Leaflet
        sortedPoints.forEach(p => {
          const code = p.level_code || 'fluide';
          counts[code] = (counts[code] || 0) + 1;
          const pct = Math.round(p.congestion * 100);
          const iconHtml = `<div class="tm-marker tm-bg-${code}" tabindex="0" role="button" aria-label="${p.point} : ${pct}%, ${p.level}">${getLevelIcon(code)}</div>`;

          const customIcon = L.divIcon({
            className: 'tm-divicon',
            html: iconHtml,
            iconSize: [34, 34],
            iconAnchor: [17, 17],
            popupAnchor: [0, -18]
          });

          const marker = L.marker([p.lat, p.lon], { icon: customIcon });
          const popupHtml = `
            <div class="p-1">
              <strong class="d-block mb-1">${p.point}</strong>
              <div class="mb-1"><span class="tm-level tm-level-${code}">${p.level}</span></div>
              <div class="small">Congestion prévue : <strong>${pct}%</strong></div>
            </div>
          `;
          marker.bindPopup(popupHtml);
          markersLayer.addLayer(marker);
        });

        // Mettre à jour le tableau textuel accessible
        if (tableBody) {
          tableBody.innerHTML = sortedPoints.map(p => `
            <tr>
              <th scope="row">${p.point}</th>
              <td><strong>${Math.round(p.congestion * 100)} %</strong></td>
              <td><span class="tm-level tm-level-${p.level_code}">${p.level}</span></td>
            </tr>
          `).join('');
        }

        // Statut textuel
        const msg = (i18n.summary || '{n} points : {fluide} fluides, {modere} modérés, {dense} denses, {bloque} bloqués.')
          .replace('{n}', sortedPoints.length)
          .replace('{fluide}', counts.fluide || 0)
          .replace('{modere}', counts.modere || 0)
          .replace('{dense}', counts.dense || 0)
          .replace('{bloque}', counts.bloque || 0);

        statusEl.textContent = `${msg} ${data.precipitation_mm > 0 ? (i18n.rainUsed || 'Pluie prise en compte : {mm} mm.').replace('{mm}', data.precipitation_mm) : ''}`;
      })
      .catch(err => {
        if (err.name === 'AbortError') return;
        mapElement.setAttribute('aria-busy', 'false');
        statusEl.textContent = '';
        errorEl.textContent = err.message || (i18n.error || 'Impossible de charger la prévision.');
        errorEl.classList.remove('d-none');
      });
  }

  // Événements
  timeSlider.addEventListener('input', () => {
    timeOut.textContent = sliderToTime(timeSlider.value);
  });
  timeSlider.addEventListener('change', updateHeatmap);
  dateInput.addEventListener('change', updateHeatmap);

  // Raccourcis horaires
  document.querySelectorAll('[data-quick]').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.quick;
      if (target === 'now') {
        const now = new Date();
        const steps = Math.floor((now.getHours() * 60 + now.getMinutes()) / 15);
        timeSlider.value = Math.min(95, Math.max(0, steps));
      } else {
        timeSlider.value = parseInt(target, 10);
      }
      timeOut.textContent = sliderToTime(timeSlider.value);
      updateHeatmap();
    });
  });

  // Chargements initiaux
  loadWeather();
  updateHeatmap();
});
