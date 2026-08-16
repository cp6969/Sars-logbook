import { trackDistanceKm, watchPosition, getCurrentPositionOnce } from "/static/js/gps.js";
import { addPendingPoint, clearPendingPoints, queueTrip } from "/static/js/db.js";

const POINT_FLUSH_INTERVAL_MS = 20000;

const root = document.getElementById("trip-capture-app");
if (root) {
  const resumeTripId = root.dataset.resumeTripId || null;

  const idleState = document.getElementById("trip-idle-state");
  const activeState = document.getElementById("trip-active-state");
  const classifyState = document.getElementById("trip-classify-state");
  const errorEl = document.getElementById("trip-error");
  const distanceEl = document.getElementById("live-distance");
  const elapsedEl = document.getElementById("live-elapsed");

  let tripId = resumeTripId;
  let clientTripUuid = null;
  let watchId = null;
  let flushTimer = null;
  let elapsedTimer = null;
  let startedAt = null;
  let localPoints = [];
  let startFix = null;
  let endFix = null;

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function showState(name) {
    idleState.hidden = name !== "idle";
    activeState.hidden = name !== "active";
    classifyState.hidden = name !== "classify";
  }

  function formatElapsed(ms) {
    const totalSec = Math.floor(ms / 1000);
    const min = String(Math.floor(totalSec / 60)).padStart(2, "0");
    const sec = String(totalSec % 60).padStart(2, "0");
    return `${min}:${sec}`;
  }

  function updateLiveDisplay() {
    const km = trackDistanceKm(localPoints);
    distanceEl.textContent = `${km.toFixed(1)} km`;
    if (startedAt) elapsedEl.textContent = formatElapsed(Date.now() - startedAt.getTime());
  }

  async function flushPoints() {
    if (!tripId || localPoints.length === 0) return;
    const toSend = localPoints.slice();
    try {
      const resp = await fetch(`/api/trips/${tripId}/points`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ points: toSend }),
      });
      if (resp.ok) await clearPendingPoints(tripId);
    } catch (e) {
      // offline -- points stay buffered locally, retried on the next flush
    }
  }

  async function startTrip() {
    errorEl.hidden = true;
    clientTripUuid = crypto.randomUUID();
    startedAt = new Date();
    localPoints = [];

    try {
      startFix = await getCurrentPositionOnce();
    } catch (e) {
      startFix = null; // proceed without a fix -- distance just starts at 0 until real movement is detected
    }
    if (startFix) localPoints.push(startFix);

    try {
      const resp = await fetch("/api/trips/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_trip_uuid: clientTripUuid,
          started_at: startedAt.toISOString(),
          lat: startFix ? startFix.lat : null,
          lon: startFix ? startFix.lon : null,
          accuracy: startFix ? startFix.accuracy : null,
        }),
      });
      if (resp.ok) {
        const data = await resp.json();
        tripId = data.trip_id;
      }
    } catch (e) {
      // offline start -- tripId stays null; the trip is queued whole once it ENDS
    }

    watchId = watchPosition(
      (point) => {
        localPoints.push(point);
        addPendingPoint(tripId || "pending", point);
        updateLiveDisplay();
      },
      (err) => showError("Location error: " + err.message)
    );
    flushTimer = setInterval(flushPoints, POINT_FLUSH_INTERVAL_MS);
    elapsedTimer = setInterval(updateLiveDisplay, 1000);

    showState("active");
  }

  async function endTrip() {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    clearInterval(flushTimer);
    clearInterval(elapsedTimer);

    try {
      endFix = await getCurrentPositionOnce();
    } catch (e) {
      endFix = null;
    }
    if (endFix) localPoints.push(endFix);

    const endedAt = new Date();

    if (tripId) {
      await flushPoints();
      try {
        const resp = await fetch(`/api/trips/${tripId}/end`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ended_at: endedAt.toISOString(),
            lat: endFix ? endFix.lat : null,
            lon: endFix ? endFix.lon : null,
            accuracy: endFix ? endFix.accuracy : null,
          }),
        });
        if (resp.ok) {
          const data = await resp.json();
          renderClassify(data.distance_km, data.start_address, data.end_address, data.suggested_category, data.suggested_purpose);
          return;
        }
      } catch (e) {
        // fall through to the offline queue below
      }
    }

    // Offline fallback: the trip never got a server-assigned tripId, or the
    // /end call itself failed -- queue the whole trip locally by its
    // client_trip_uuid so "Sync now" (or the next successful load) can
    // upload it complete, exactly once.
    const distanceKm = trackDistanceKm(localPoints);
    await queueTrip({
      client_trip_uuid: clientTripUuid,
      started_at: startedAt.toISOString(),
      ended_at: endedAt.toISOString(),
      start_lat: startFix ? startFix.lat : null,
      start_lon: startFix ? startFix.lon : null,
      end_lat: endFix ? endFix.lat : null,
      end_lon: endFix ? endFix.lon : null,
      gps_track: localPoints,
      category: null,
      purpose: "",
    });
    renderClassify(distanceKm, null, null, null, null, /* offline */ true);
  }

  function renderClassify(distanceKm, fromAddr, toAddr, suggestedCategory, suggestedPurpose, offline) {
    document.getElementById("classify-distance").textContent = distanceKm != null ? Number(distanceKm).toFixed(1) : "?";
    document.getElementById("classify-from").textContent = fromAddr || "—";
    document.getElementById("classify-to").textContent = toAddr || "—";
    if (offline) {
      showError("You're offline — this trip is saved on your phone and will sync once you're back online. Tap Save now to store your classification too.");
    }
    if (suggestedCategory) {
      const radio = document.getElementById(suggestedCategory === "business" ? "cat-business" : "cat-private");
      if (radio) radio.checked = true;
    }
    if (suggestedPurpose) {
      document.getElementById("purpose-input").value = suggestedPurpose;
    }
    showState("classify");
  }

  document.getElementById("start-trip-btn")?.addEventListener("click", startTrip);
  document.getElementById("end-trip-btn")?.addEventListener("click", endTrip);

  document.getElementById("classify-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const category = form.category.value;
    const purpose = form.purpose.value;
    const odometerOpen = form.odometer_open.value ? parseFloat(form.odometer_open.value) : null;
    const odometerClose = form.odometer_close.value ? parseFloat(form.odometer_close.value) : null;

    if (!category) {
      showError("Please choose Business or Private.");
      return;
    }

    if (tripId) {
      try {
        await fetch(`/api/trips/${tripId}/classify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ category, purpose, odometer_open: odometerOpen, odometer_close: odometerClose }),
        });
      } catch (e) {
        // best-effort -- if this fails the trip stays "pending_review" server-side and can be classified from the Trips list instead
      }
    } else {
      // fully-offline trip -- re-queue with the classification now attached
      await queueTrip({
        client_trip_uuid: clientTripUuid,
        started_at: startedAt.toISOString(),
        ended_at: new Date().toISOString(),
        start_lat: startFix ? startFix.lat : null,
        start_lon: startFix ? startFix.lon : null,
        end_lat: endFix ? endFix.lat : null,
        end_lon: endFix ? endFix.lon : null,
        gps_track: localPoints,
        category,
        purpose,
        odometer_open: odometerOpen,
        odometer_close: odometerClose,
      });
    }
    window.location.href = "/dashboard";
  });

  if (resumeTripId) {
    // A trip is already open server-side (e.g. the tab was closed and
    // reopened mid-trip). We've lost the in-memory localPoints from
    // before the reload, but that's fine: the server already has every
    // point synced up to the last flush, and End Trip's distance recompute
    // always uses the FULL stored track, not this client's own partial
    // view of it -- we just keep appending new points from here.
    tripId = resumeTripId;
    startedAt = new Date(); // approximation, used only for the live elapsed-time display
    localPoints = [];
    watchId = watchPosition(
      (point) => {
        localPoints.push(point);
        addPendingPoint(tripId, point);
        updateLiveDisplay();
      },
      (err) => showError("Location error: " + err.message)
    );
    flushTimer = setInterval(flushPoints, POINT_FLUSH_INTERVAL_MS);
    elapsedTimer = setInterval(updateLiveDisplay, 1000);
    showState("active");
  } else {
    showState("idle");
  }
}
