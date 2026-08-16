import { getQueuedTrips, removeQueuedTrip } from "/static/js/db.js";

async function syncQueuedTrips() {
  const queued = await getQueuedTrips();
  const readyToSync = queued.filter((t) => t.category); // only fully-classified trips can sync
  if (readyToSync.length === 0) return { synced: 0, remaining: queued.length };

  try {
    const resp = await fetch("/api/trips/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readyToSync),
    });
    if (!resp.ok) return { synced: 0, remaining: queued.length, error: true };
    const data = await resp.json();
    for (const result of data.synced) {
      await removeQueuedTrip(result.client_trip_uuid);
    }
    return { synced: data.synced.length, remaining: queued.length - data.synced.length };
  } catch (e) {
    return { synced: 0, remaining: queued.length, error: true };
  }
}

export { syncQueuedTrips };
