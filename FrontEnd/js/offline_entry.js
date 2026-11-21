const practiceEntry = document.getElementById('offlineEntry');
function updatePracticeEntry(){ practiceEntry.hidden=navigator.onLine; }
updatePracticeEntry();
addEventListener('online',updatePracticeEntry);
addEventListener('offline',updatePracticeEntry);
