// مسار بدء تطبيق أندرويد قبل تحميل بقية الواجهة.
(() => {
    if (!window.Capacitor?.isNativePlatform?.()) return;
    let savedToken;
    try {
        if (sessionStorage.getItem('pr_logged_out') === '1') return;
        savedToken = localStorage.getItem('token') || sessionStorage.getItem('token');
    } catch { return; }
    if (!savedToken) return;

    const params = new URLSearchParams(location.search);
    if (document.currentScript.dataset.entry !== undefined) {
        document.documentElement.classList.add('pr-app-resuming');
        location.replace('categories.html?resume=1');
        return;
    }
    if (params.get('resume') !== '1' || params.has('token')) return;

    document.documentElement.classList.add('pr-app-resuming');
    const abort = new AbortController();
    let complete = false;
    let watchdog;
    function showRecovery() {
        const status = document.getElementById('appResumeStatus');
        if (!status || complete) return;
        status.textContent = 'تعذّر استئناف الجلسة. حاول مرة ثانية أو افتح صفحة تسجيل الدخول.';
        document.getElementById('appResumeRetry').hidden = false;
        document.getElementById('appResumeLogin').hidden = false;
    }

    let deadline;
    const timeout = new Promise(resolve => {
        deadline = setTimeout(() => {
            resolve({ status: 0, user: null });
            abort.abort();
        }, 8000);
    });
    const request = Promise.resolve().then(() => fetch(CONFIG.API_URL + '/auth/me', {
        headers: { Authorization: 'Bearer ' + savedToken },
        signal: abort.signal,
    })).then(async response => ({
        status: response.status,
        user: response.ok ? await response.json() : null,
    })).catch(() => ({ status: 0, user: null }));
    const account = Promise.race([request, timeout]).finally(() => clearTimeout(deadline));
    account.then(result => { if (!result.user) showRecovery(); });
    watchdog = setTimeout(showRecovery, 10000);

    window.PRAppStartup = {
        account,
        finish() {
            complete = true;
            clearTimeout(watchdog);
            document.documentElement.classList.remove('pr-app-resuming');
            document.getElementById('mainLobbyContainer').inert = false;
            params.delete('resume');
            const query = params.toString();
            history.replaceState(history.state, '', location.pathname + (query ? '?' + query : '') + location.hash);
        },
        retry: showRecovery,
    };
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('mainLobbyContainer').inert = true;
        document.getElementById('appResumeRetry').onclick = () => location.reload();
        account.then(result => { if (!result.user) showRecovery(); });
    }, { once: true });
})();
