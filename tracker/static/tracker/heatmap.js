(() => {
  const mapElement = document.getElementById("personal-heatmap");
  const dataElement = document.getElementById("personal-heat-points");
  if (!mapElement || !dataElement || !window.L) return;
  const points = JSON.parse(dataElement.textContent);
  const initial = points.length ? [points[0][0], points[0][1]] : [36.8065, 10.1815];
  const map = L.map(mapElement).setView(initial, points.length ? 12 : 7);
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    attribution: "&copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics"
  }).addTo(map);
  if (window.L.heatLayer && points.length) {
    const weighted = points.map(point => [point[0], point[1], 0.6]);
    L.heatLayer(weighted, { radius: 24, blur: 18, maxZoom: 16 }).addTo(map);
    map.fitBounds(points, { padding: [20, 20] });
  }
})();
