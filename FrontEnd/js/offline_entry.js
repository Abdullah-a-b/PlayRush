const practiceEntry = document.getElementById('offlineEntry');
function updatePracticeEntry(){ practiceEntry.hidden=navigator.onLine && !window.Capacitor?.isNativePlatform?.(); }
updatePracticeEntry();
addEventListener('online',updatePracticeEntry);
addEventListener('offline',updatePracticeEntry);
