const DB_NAME = "sars-logbook";
const DB_VERSION = 1;

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("pendingPoints")) {
        db.createObjectStore("pendingPoints", { keyPath: "id", autoIncrement: true });
      }
      if (!db.objectStoreNames.contains("queuedTrips")) {
        db.createObjectStore("queuedTrips", { keyPath: "client_trip_uuid" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function addPendingPoint(tripLocalId, point) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("pendingPoints", "readwrite");
    tx.objectStore("pendingPoints").add({ tripLocalId, ...point });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function clearPendingPoints(tripLocalId) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("pendingPoints", "readwrite");
    const store = tx.objectStore("pendingPoints");
    const req = store.getAll();
    req.onsuccess = () => {
      req.result.filter((p) => p.tripLocalId === tripLocalId).forEach((p) => store.delete(p.id));
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function queueTrip(trip) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("queuedTrips", "readwrite");
    tx.objectStore("queuedTrips").put(trip);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getQueuedTrips() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("queuedTrips", "readonly");
    const req = tx.objectStore("queuedTrips").getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function removeQueuedTrip(clientTripUuid) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("queuedTrips", "readwrite");
    tx.objectStore("queuedTrips").delete(clientTripUuid);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export { addPendingPoint, clearPendingPoints, queueTrip, getQueuedTrips, removeQueuedTrip };
