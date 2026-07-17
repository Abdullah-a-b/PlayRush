/* ============================================================
   progression_api.js — طبقة الوصول لنظام التقدّم (Ranked/Quests/Pass)
   يُستخدم في اللوبي وcategories. يعتمد API_URL من config.js.
   ============================================================ */
(function () {
  'use strict';

  function _token() {
    if (typeof getToken === 'function') return getToken();
    return localStorage.getItem('token') || sessionStorage.getItem('token') || '';
  }

  async function _get(path) {
    const res = await fetch(API_URL + path, {
      headers: { 'Authorization': 'Bearer ' + _token() },
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  async function _post(path, body) {
    const res = await fetch(API_URL + path, {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + _token(),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body || {}),
    });
    return res.json();
  }

  window.ProgressionAPI = {
    myRanks: () => _get('/progression/rank/me'),
    gameRank: (mode) => _get('/progression/rank/' + mode),
    leaderboard: (mode) => _get('/progression/leaderboard/' + mode),
    globalLeaderboard: () => _get('/progression/leaderboard'),
    quests: () => _get('/progression/quests'),
    claimQuest: (key) => _post('/progression/quests/claim', { quest_key: key }),
    pass: () => _get('/progression/pass'),
    buyPremium: () => _post('/progression/pass/buy-premium', {}),
    claimPassTier: (tier, track) => _post('/progression/pass/claim', { tier, track }),
  };
})();
