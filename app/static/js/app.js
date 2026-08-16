if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

// Opportunistic sync of any offline-queued trips on every page load --
// the manual "Sync now" button on the dashboard is the reliable fallback,
// since Background Sync isn't supported on iOS Safari.
import("/static/js/sync.js").then(({ syncQueuedTrips }) => {
  syncQueuedTrips().then((result) => {
    if (result.synced > 0) console.log(`Synced ${result.synced} offline trip(s).`);
  });
});
