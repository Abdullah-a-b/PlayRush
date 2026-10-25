// FrontEnd/js/config.js

//  ط§ظƒطھط´ط§ظپ ط¹ظ†ظˆط§ظ† ط§ظ„ط®ط§ط¯ظ… طھظ„ظ‚ط§ط¦ظٹط§ظ‹:
// - ظ…ظ† localhost/127.0.0.1 â†’ ط®ط§ط¯ظ… ظ…ط­ظ„ظٹ ط¹ظ„ظ‰ ظ†ظپط³ ط§ظ„ط¬ظ‡ط§ط²
// - ظ…ظ† ط¹ظ†ظˆط§ظ† ط´ط¨ظƒط© (ظ‡ط§طھظپ ط¹ط¨ط± WiFi ظ…ط«ظ„ 192.168.x.x) â†’ ظ†ظپط³ ط§ظ„ط¹ظ†ظˆط§ظ† + ط§ظ„ظ…ظ†ظپط° 8000
// ظ‡ط°ط§ ظٹطھظٹط­ ظپطھط­ ط§ظ„ظ…ط´ط±ظˆط¹ ظ…ظ† ط§ظ„ظ‡ط§طھظپ ط¨ظ„ط§ طھط¹ط¯ظٹظ„ ظٹط¯ظˆظٹ.
// ًںŒگ ط¯ظˆظ…ظٹظ† ط§ظ„ط¥ظ†طھط§ط¬ â€” ط¹ط¯ظ‘ظ„ظ‡ ظ‡ظ†ط§ ظ…ط±ط© ظˆط§ط­ط¯ط© ط¹ظ†ط¯ ط¥ط·ظ„ط§ظ‚ ط§ظ„ط¯ظˆظ…ظٹظ†ط§طھ
// (ظٹظڈط³طھط®ط¯ظ… طھظ„ظ‚ط§ط¦ظٹط§ظ‹ ظپظٹ ط§ظ„ط¥ظ†طھط§ط¬ ظˆظپظٹ طھط·ط¨ظٹظ‚ط§طھ Android/iOS)
const PROD_API_ORIGIN = 'https://playrush-server.azurewebsites.net';   // â†گ ط¶ط¹ ط¯ظˆظ…ظٹظ† ط§ظ„ط¨ط§ظƒ ط¥ظ†ط¯ ط§ظ„ظپط¹ظ„ظٹ

// ًں“± ظƒط´ظپ ط¨ظٹط¦ط© ط§ظ„طھط·ط¨ظٹظ‚ (Capacitor/WebView): ط§ظ„طھط·ط¨ظٹظ‚ ظٹط­ظ…ظ‘ظ„ ط§ظ„ظˆط§ط¬ظ‡ط© ظ…ظ†
// ط­ط²ظ…ط© ظ…ط­ظ„ظٹط©. ظ…ط¹ androidScheme:"https" ظٹظƒظˆظ† ط§ظ„ط¹ظ†ظˆط§ظ† https://localhostطŒ
// ظپظ„ط§ ظٹظƒظپظٹ ظپط­طµ ط§ظ„ط¨ط±ظˆطھظˆظƒظˆظ„ â€” ظ†ط¹طھظ…ط¯ ط¬ط³ط± Capacitor ظ†ظپط³ظ‡ (window.Capacitor)
// ظˆظ‡ظˆ ظٹظڈط­ظ‚ظ† ط¯ط§ط¦ظ…ط§ظ‹ ط¯ط§ط®ظ„ ط§ظ„طھط·ط¨ظٹظ‚ ظˆظ„ط§ ظٹظˆط¬ط¯ ط¥ط·ظ„ط§ظ‚ط§ظ‹ ظپظٹ ظ…طھطµظپط­ ط¹ط§ط¯ظٹ.
const PR_IS_APP = window.PR_IS_APP === true
    || (typeof window.Capacitor !== 'undefined')
    || /^(capacitor|file|ionic):$/.test(window.location.protocol);

window.PR_IS_APP = PR_IS_APP;  // ظ…طھط§ط­ ظ„ظƒظ„ ط§ظ„ظ…ظ†طµط© (ط§ظ„ط¬ظ„ط³ط§طھ/ط§ظ„ظˆط§ط¬ظ‡ط§طھ)

// طµظ†ظپ ط¹ظ„ظ‰ <html> طھط³طھظ‡ط¯ظپظ‡ css/app_perf.css ظ„طھط®ظپظٹظپ ط§ظ„ظ…ط¤ط«ط±ط§طھ ط¯ط§ط®ظ„ ط§ظ„طھط·ط¨ظٹظ‚
// (ط§ظ„ظ…ظˆظ‚ط¹ ط¹ظ„ظ‰ ط§ظ„ظ…طھطµظپط­ ظٹط¨ظ‚ظ‰ ط¨ظƒط§ظ…ظ„ ظ…ط¤ط«ط±ط§طھظ‡).
try {
    if (PR_IS_APP) document.documentElement.classList.add('pr-app');
    var _coarse = (typeof window.matchMedia === 'function'
                    && window.matchMedia('(pointer: coarse)').matches)
                  || ('ontouchstart' in window)
                  || (navigator.maxTouchPoints > 0);
    if (_coarse) document.documentElement.classList.add('pr-touch');
} catch (e) {}

/* ============================================================
   ط¥ط®ظپط§ط، ط´ط§ط´ط© ط§ظ„ط¨ط¯ط، ط§ظ„ط£طµظ„ظٹط© ط¹ظ†ط¯ ط¬ظ‡ظˆط²ظٹط© ط§ظ„طµظپط­ط© (ط§ظ„طھط·ط¨ظٹظ‚ ظپظ‚ط·)
   ------------------------------------------------------------
   ظƒط§ظ† ط§ظ„ط¥ط¹ط¯ط§ط¯ launchShowDuration: 400 ظ…ط¹ launchAutoHide: trueطŒ
   ط£ظٹ ط£ظ† ط´ط§ط´ط© ط§ظ„ط¨ط¯ط، طھط®طھظپظٹ ط¨ط¹ط¯ 400ms ط¨ظٹظ†ظ…ط§ ط§ظ„ظ€WebView ظ…ط§ ط²ط§ظ„ ظٹظڈظ‚ظ„ط¹
   ظˆظٹط­ظ…ظ‘ظ„ ط§ظ„ط¬ظ„ط³ط© â€” ظˆط§ظ„ظپط¬ظˆط© ط¨ظٹظ†ظ‡ظ…ط§ ظ‡ظٹ ط§ظ„ط´ط§ط´ط© ط§ظ„ط³ظˆط¯ط§ط، ط§ظ„طھظٹ طھط±ط§ظ‡ط§.
   ط§ظ„ط¢ظ† ط§ظ„ط¥ط¹ط¯ط§ط¯ launchAutoHide: falseطŒ ظˆظ†ط­ظ† ظ…ظ† ظٹظڈط®ظپظٹظ‡ط§ ظ‡ظ†ط§ ط­ظٹظ†
   طھطµط¨ط­ ط§ظ„طµظپط­ط© ط¬ط§ظ‡ط²ط© ظپط¹ظ„ط§ظ‹.
   ============================================================ */
if (PR_IS_APP) {
    (function () {
        var hidden = false;
        function hideSplash() {
            if (hidden) return;
            hidden = true;
            try {
                var S = window.Capacitor
                    && window.Capacitor.Plugins
                    && window.Capacitor.Plugins.SplashScreen;
                if (S && S.hide) S.hide({ fadeOutDuration: 200 });
            } catch (e) {}
        }
        // ط¨ط¹ط¯ ط§ظƒطھظ…ط§ظ„ ط§ظ„طھط­ظ…ظٹظ„ ط¨ظ‚ظ„ظٹظ„طŒ ظ…ط¹ ظ…ظ‡ظ„ط© ظ‚طµظˆظ‰ ظƒظٹ ظ„ط§ طھط¹ظ„ظ‚ ط§ظ„ط´ط§ط´ط© ط£ط¨ط¯ط§ظ‹
        if (document.readyState === 'complete') setTimeout(hideSplash, 200);
        else window.addEventListener('load', function () { setTimeout(hideSplash, 200); });
        setTimeout(hideSplash, 5000);
    })();
}

const _host = window.location.hostname;
const _isLocalHost = (_host === '127.0.0.1' || _host === 'localhost' || _host === '');
const _isLanIp = /^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(_host);
const _backendOrigin =
    PR_IS_APP        ? PROD_API_ORIGIN                     // ًں“± طھط·ط¨ظٹظ‚ â†’ ط¯ظˆظ…ظٹظ† ط§ظ„ط¥ظ†طھط§ط¬
    : _isLocalHost   ? 'http://127.0.0.1:8000'             // ًں’» طھط·ظˆظٹط± ظ…ط­ظ„ظٹ
    : _isLanIp       ? `http://${_host}:8000`              // ًں“¶ ظ‡ط§طھظپ ط¹ط¨ط± WiFi ظ„ظ„طھط·ظˆظٹط±
    : PROD_API_ORIGIN;                                     // ًںŒگ ط§ظ„ظˆظٹط¨ ط¨ط§ظ„ط¥ظ†طھط§ط¬ â†’ ط¯ظˆظ…ظٹظ† API

const CONFIG = {
    // ط§ظ„ط¯ظˆظ…ظٹظ† ط§ظ„ط®ط§طµ ط¨ط§ظ„ط¨ط§ظƒ ط¥ظ†ط¯ (API)
    API_URL: _backendOrigin,

    // ط§ظ„ط¯ظˆظ…ظٹظ† ط§ظ„ط®ط§طµ ط¨ط§ظ„ط§طھطµط§ظ„ ط§ظ„ظ…ط¨ط§ط´ط± (Socket.io)
    WS_URL: _backendOrigin
};

// ============================================================
//  ط±ظˆط§ط¨ط· ط§ظ„طھظˆط§طµظ„ ط§ظ„ط§ط¬طھظ…ط§ط¹ظٹ â€” ظ…طµط¯ط± ظˆط§ط­ط¯ ظ„ظƒظ„ ط§ظ„ظ…ظ†طµط©
// ط¹ط¯ظ‘ظ„ ط§ظ„ط±ظˆط§ط¨ط· ظ‡ظ†ط§ ظپظ‚ط·طŒ ظˆط³طھطھط­ط¯ظ‘ط« ظپظٹ ظƒظ„ ط§ظ„طµظپط­ط§طھ طھظ„ظ‚ط§ط¦ظٹط§ظ‹.
// ظ„ط¥ط®ظپط§ط، ظ…ظ†طµط©: ط§ط¬ط¹ظ„ ط±ط§ط¨ط·ظ‡ط§ '' (ظپط±ط§ط؛) ط£ظˆ ط§ط­ط°ظپ ط§ظ„ط³ط·ط±.
// ============================================================
const SOCIAL_LINKS = {
    twitter:   'https://x.com/PlayRushApp',      // X (طھظˆظٹطھط±)
    instagram: 'https://www.instagram.com/playrush_app?igsh=MWhuZnQyb3ByN2V6aQ==',    // ط¥ظ†ط³طھط؛ط±ط§ظ…
    tiktok:    'https://www.tiktok.com/@playrushapp',      // طھظٹظƒ طھظˆظƒ
    snapchat:  'https://www.snapchat.com/add/playrushapp?share_id=vLlm4hBExyw&locale=ar-EG', // ط³ظ†ط§ط¨ ط´ط§طھ
    threads:   'https://www.threads.com/@playrush_app',     // ط«ط±ظٹط¯ط²
    facebook:  'https://www.facebook.com/share/1E4AC4MxYV/',     // ظپظٹط³ط¨ظˆظƒ
};
//  ط§ط³طھط¨ط¯ظ„ "PlayRush" ط£ط¹ظ„ط§ظ‡ ط¨ط§ط³ظ… ط§ظ„ظ…ط³طھط®ط¯ظ… ط§ظ„ظپط¹ظ„ظٹ ظ„ظƒظ„ ط­ط³ط§ط¨.

// ط¯ط§ظ„ط© ظ…ط³ط§ط¹ط¯ط© ظ„طھط³ظ‡ظٹظ„ ط¬ظ„ط¨ ط§ظ„طھظˆظƒظ† ظ…ظ† ط£ظٹ ظ…ظƒط§ظ†
const getToken = () => localStorage.getItem('token') || sessionStorage.getItem('token');

document.addEventListener('click', function(e) {
    // ظ†ط±ط§ظ‚ط¨ ط£ظٹ ظ†ظ‚ط±ط© ظپظٹ ط§ظ„ظ…ظˆظ‚ط¹طŒ ظˆط¥ط°ط§ ظƒط§ظ†طھ ط§ظ„ظ†ظ‚ط±ط© ط¹ظ„ظ‰ "ط²ط± ط±ظپط¹ ظ…ظ„ظپ/طµظˆط±ط©"
    if (e.target && e.target.type === 'file') {
        // ظ†ظ‚ظˆظ… ط¨طھظپط±ظٹط؛ ط°ط§ظƒط±ط© ط§ظ„ط²ط± ظپظٹ ظ†ظپط³ ط§ظ„ظ„ط­ط¸ط© (ظ‚ط¨ظ„ ط£ظ† طھظپطھط­ ظ†ط§ظپط°ط© ط§ط®طھظٹط§ط± ط§ظ„طµظˆط±)
        // ظ‡ط°ط§ ظٹط®ط¯ط¹ ط§ظ„ظ…طھطµظپط­ ظˆظٹط¬ط¹ظ„ظ‡ ظٹط¹طھظ‚ط¯ ط£ظ† ط§ظ„طµظˆط±ط© ط§ظ„طھظٹ ط³طھط®طھط§ط±ظ‡ط§ ظ‡ظٹ "طھط؛ظٹظٹط± ط¬ط¯ظٹط¯" ط¯ط§ط¦ظ…ط§ظ‹!
        e.target.value = '';
    }
});

// ===== ط­ظپط¸ ط§ظ„طھظˆظƒظ† ظپظٹ ط§ظ„ظ…ط®ط²ظ†ظٹظ† ظ…ط¹ط§ظ‹ =====
// ظƒط§ظ† ط¨ط¹ط¶ ط§ظ„ظ…ط³ط§ط±ط§طھ (ط¬ظˆط¬ظ„/ط¥ظƒظ…ط§ظ„ ط§ظ„ظ…ظ„ظپ/طھط¬ط¯ظٹط¯ ط§ظ„طھظˆظƒظ†) ظٹط­ظپط¸ ظپظٹ
// sessionStorage ظپظ‚ط·طŒ ظپطھط¶ظٹط¹ ط§ظ„ط¬ظ„ط³ط© ط¨ط¥ط؛ظ„ط§ظ‚ ط§ظ„ظ…طھطµظپط­ ط±ط؛ظ… "طھط°ظƒط±ظ†ظٹ".
window.prSaveToken = function (t) {
    if (!t) return;
    try {
        sessionStorage.setItem('token', t);
        localStorage.setItem('token', t);   // ظٹط¹ظٹط´ ط£ط³ط¨ظˆط¹ط§ظ‹ = طµظ„ط§ط­ظٹط© ط§ظ„طھظˆظƒظ†
    } catch (e) {}
};

// ===== PR_SESSION_BRIDGE: طھط°ظƒظڈظ‘ط± ط§ظ„ط¯ط®ظˆظ„ (ط²ظٹ ط§ظ„ظ…ظˆط§ظ‚ط¹ ط§ظ„ط¹ط§ظ„ظ…ظٹط©) =====
// ظ…ظ† ظپط¹ظ‘ظ„ "طھط°ظƒط±ظ†ظٹ": طھظˆظƒظ†ظ‡ ظپظٹ localStorage (ظٹط¹ظٹط´ 7 ط£ظٹط§ظ… = طµظ„ط§ط­ظٹط© ط§ظ„طھظˆظƒظ†
// ط¨ط§ظ„ط®ط§ط¯ظ…). ط¹ظ†ط¯ ظپطھط­ طھط¨ظˆظٹط¨/ط¬ظ„ط³ط© ط¬ط¯ظٹط¯ط© ظ†ظ†ط³ط®ظ‡ ظ„sessionStorage ظپظٹط¹ظ…ظ„ ظƒظ„
// ط§ظ„ظƒظˆط¯ ط§ظ„ظ‚ط¯ظٹظ… ظƒظ…ط§ ظ‡ظˆ ط¨ظ„ط§ طھط¹ط¯ظٹظ„. ط§ظ„ط®ط§ط¯ظ… ظٹط±ظپط¶ ط§ظ„طھظˆظƒظ† ط§ظ„ظ…ظ†طھظ‡ظٹ طھظ„ظ‚ط§ط¦ظٹط§ظ‹.
(function () {
    try {
        var lt = localStorage.getItem('token');
        if (lt && !sessionStorage.getItem('token')) {
            sessionStorage.setItem('token', lt);
        }
    } catch (e) { /* ظ…طھطµظپط­ ظٹظ…ظ†ط¹ ط§ظ„طھط®ط²ظٹظ† */ }
})();
