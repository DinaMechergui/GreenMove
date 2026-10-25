(() => {
  const status = document.getElementById("gps-status");
  const syncStatus = document.getElementById("sync-status");
  const tracking = document.querySelector("[data-tracker-trip][data-recording='true']");
  const mapElement = document.getElementById("trip-map");
  const pointsElement = document.getElementById("trip-map-points");
  const routeText = document.getElementById("route-text-alternative");
  const csrfToken = document.cookie.split("; ")
    .find(item => item.startsWith("csrftoken="))?.split("=")[1];
  let routeMap = null;
  let routeLine = null;
  let routeCoordinates = [];
  let estimatedDistanceKm = 0;
  let queueKeyPromise = null;

  function distanceKm(first, second) {
    const radians = value => value * Math.PI / 180;
    const deltaLat = radians(second[0] - first[0]);
    const deltaLon = radians(second[1] - first[1]);
    const value = Math.sin(deltaLat / 2) ** 2
      + Math.cos(radians(first[0])) * Math.cos(radians(second[0]))
      * Math.sin(deltaLon / 2) ** 2;
    return 6371.0088 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
  }

  let existingPoints = [];
  if (pointsElement) {
    try { existingPoints = JSON.parse(pointsElement.textContent); } catch (error) {
      console.error("GreenMove GPS data could not be rendered.", error);
      existingPoints = [];
    }
  }
  if (mapElement) {
    if (routeText && existingPoints.length) {
      routeText.replaceChildren(...existingPoints.map((point, index) => {
        const item = document.createElement("li");
        item.textContent = `Point ${index + 1} : ${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)} (${new Date(point.recorded_at).toLocaleTimeString()})`;
        return item;
      }));
    }
    if (window.L) {
      const fallback = [36.8065, 10.1815];
      routeCoordinates = existingPoints.map(point => [point.latitude, point.longitude]);
      for (let index = 1; index < routeCoordinates.length; index += 1) {
        estimatedDistanceKm += distanceKm(routeCoordinates[index - 1], routeCoordinates[index]);
      }
      routeMap = L.map(mapElement).setView(routeCoordinates[0] || fallback, 13);
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 19,
        attribution: "&copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics"
      }).addTo(routeMap);
      routeLine = L.polyline(routeCoordinates, { color: "#335c45", weight: 5 }).addTo(routeMap);
      if (routeCoordinates.length) routeMap.fitBounds(routeCoordinates, { padding: [20, 20] });
    }
  }

  function openQueue() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("greenmove-private-tracker", 1);
      request.onupgradeneeded = () => {
        const db = request.result;
        db.createObjectStore("keys");
        db.createObjectStore("points", { keyPath: "id" });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function getQueueKey(db) {
    if (!queueKeyPromise) {
      queueKeyPromise = (async () => {
        const stored = await new Promise((resolve, reject) => {
          const request = db.transaction("keys").objectStore("keys").get("aes-key");
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(request.error);
        });
        if (stored) return stored;
        const generated = await crypto.subtle.generateKey(
          { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]
        );
        return new Promise((resolve, reject) => {
          const transaction = db.transaction("keys", "readwrite");
          const store = transaction.objectStore("keys");
          const request = store.get("aes-key");
          let result = generated;
          request.onsuccess = () => {
            if (request.result) result = request.result;
            else store.put(generated, "aes-key");
          };
          transaction.oncomplete = () => resolve(result);
          transaction.onerror = () => reject(transaction.error);
        });
      })();
    }
    try {
      return await queueKeyPromise;
    } catch (error) {
      queueKeyPromise = null;
      throw error;
    }
  }

  async function queuePoint(tripId, point) {
    const db = await openQueue();
    const key = await getQueueKey(db);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const bytes = new TextEncoder().encode(JSON.stringify(point));
    const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, bytes);
    await new Promise((resolve, reject) => {
      const request = db.transaction("points", "readwrite").objectStore("points")
        .put({ id: `${tripId}:${point.sequence}`, tripId, sequence: point.sequence, iv: Array.from(iv), ciphertext });
      request.onsuccess = resolve;
      request.onerror = () => reject(request.error);
    });
    db.close();
  }

  async function pendingPoints(tripId) {
    const db = await openQueue();
    const key = await getQueueKey(db);
    const records = await new Promise((resolve, reject) => {
      const request = db.transaction("points").objectStore("points").getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const points = [];
    for (const record of records) {
      const plaintext = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: new Uint8Array(record.iv) }, key, record.ciphertext
      );
      const point = JSON.parse(new TextDecoder().decode(plaintext));
      point.sequence = record.sequence;
      if (record.tripId === tripId) points.push(point);
    }
    db.close();
    return points;
  }

  async function removePoint(tripId, sequence) {
    const db = await openQueue();
    await new Promise((resolve, reject) => {
      const request = db.transaction("points", "readwrite")
        .objectStore("points").delete(`${tripId}:${sequence}`);
      request.onsuccess = resolve;
      request.onerror = () => reject(request.error);
    });
    db.close();
  }

  async function sendPoint(tripId, point) {
    const response = await fetch(`/tracker/trips/${tripId}/points/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify(point),
      credentials: "same-origin"
    });
    if (!response.ok) throw new Error("Le serveur n'a pas accepté le point GPS.");
  }

  async function synchronize() {
    if (!tracking || !navigator.onLine) return;
    const tripId = tracking.dataset.trackerTrip;
    const points = await pendingPoints(tripId);
    if (!points.length) {
      if (syncStatus) syncStatus.textContent = "Synchronisé";
      return;
    }
    if (syncStatus) syncStatus.textContent = "Synchronisation en cours";
    for (const point of points) {
      try {
        await sendPoint(tripId, point);
        await removePoint(tripId, point.sequence);
      } catch (error) {
        if (syncStatus) syncStatus.textContent = "Synchronisation différée : " + error.message;
        return;
      }
    }
    if (syncStatus) syncStatus.textContent = "Synchronisé";
  }

  if (tracking) {
    let sequence = Number(tracking.dataset.nextSequence || 0);
    const startedAt = Date.parse(tracking.dataset.startTime);
    const clock = document.getElementById("trip-clock");
    window.setInterval(() => {
      if (clock) {
        const seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
        clock.textContent = new Date(seconds * 1000).toISOString().slice(11, 19);
      }
    }, 1000);
    if (syncStatus && !navigator.onLine) {
      syncStatus.textContent = "Hors ligne — les prochains points seront chiffrés localement.";
    }
    if (!navigator.geolocation) {
      status.textContent = "Géolocalisation non prise en charge par ce navigateur.";
    } else {
      navigator.geolocation.watchPosition(position => {
        status.textContent = `GPS actif (précision ±${Math.round(position.coords.accuracy)} m)`;
        (async () => {
          try {
            const tripId = tracking.dataset.trackerTrip;
            if ("indexedDB" in window) {
              try {
                const pending = await pendingPoints(tripId);
                sequence = Math.max(sequence, ...pending.map(point => point.sequence + 1));
              } catch (error) {
                console.warn("GreenMove offline queue is unavailable.", error);
              }
            }
            const point = {
              sequence: sequence++,
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
              recorded_at: new Date(position.timestamp).toISOString(),
              accuracy_m: position.coords.accuracy,
              speed_mps: position.coords.speed
            };
            const coordinates = [point.latitude, point.longitude];
            if (routeCoordinates.length) {
              estimatedDistanceKm += distanceKm(routeCoordinates[routeCoordinates.length - 1], coordinates);
            }
            routeCoordinates.push(coordinates);
            if (routeLine) routeLine.addLatLng(coordinates);
            if (routeMap && routeCoordinates.length === 1) routeMap.setView(coordinates, 16);
            const distanceElement = document.getElementById("trip-distance");
            if (distanceElement) distanceElement.textContent = `Distance estimée : ${estimatedDistanceKm.toFixed(2)} km`;
            if (navigator.onLine) {
              try {
                await sendPoint(tripId, point);
              } catch (error) {
                await queuePoint(tripId, point);
                if (syncStatus) syncStatus.textContent = "Échec réseau — point chiffré localement, nouvel essai prévu.";
                window.setTimeout(() => synchronize().catch(syncError => {
                  if (syncStatus) syncStatus.textContent = "Synchronisation différée : " + syncError.message;
                }), 5000);
              }
            } else {
              await queuePoint(tripId, point);
            }
            if (navigator.onLine) await synchronize();
          } catch (error) {
            status.textContent = error.message;
          }
        })();
      }, error => {
        status.textContent = error.code === error.PERMISSION_DENIED
          ? "Autorisation de localisation refusée."
          : "Localisation momentanément indisponible.";
      }, { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
    }
  }

  window.addEventListener("online", () => synchronize().catch(error => {
    if (syncStatus) syncStatus.textContent = "Synchronisation différée : " + error.message;
  }));
  window.addEventListener("offline", () => {
    if (syncStatus) syncStatus.textContent = "Hors ligne — les prochains points seront chiffrés localement.";
  });
  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/tracker/service-worker.js", { scope: "/tracker/" })
      .catch(error => console.warn("GreenMove service worker unavailable:", error));
  }

  if (routeMap && routeCoordinates.length > 1) {
    L.marker(routeCoordinates[0]).addTo(routeMap).bindPopup("Départ");
    L.marker(routeCoordinates[routeCoordinates.length - 1]).addTo(routeMap).bindPopup("Arrivée");
    const description = document.getElementById("route-description");
    if (description) description.textContent += ` Départ ${routeCoordinates[0].join(", ")}; arrivée ${routeCoordinates[routeCoordinates.length - 1].join(", ")}.`;
  }

  if (tracking && navigator.onLine) synchronize().catch(error => {
    if (syncStatus) syncStatus.textContent = "Synchronisation différée : " + error.message;
  });
})();
