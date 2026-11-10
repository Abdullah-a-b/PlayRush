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
    const deadline = setTimeout(() => abort.abort(), 8000);
    const account = fetch(CONFIG.API_URL + '/auth/me', {
        headers: { Authorization: 'Bearer ' + savedToken },
        signal: abort.signal,
    }).then(async response => ({
        status: response.status,
        user: response.ok ? await response.json() : null,
    })).catch(() => ({ status: 0, user: null })).finally(() => clearTimeout(deadline));

    window.PRAppStartup = {
        account,
        finish() {
            params.delete('resume');
            const query = params.toString();
            history.replaceState(history.state, '', location.pathname + (query ? '?' + query : '') + location.hash);
            document.documentElement.classList.remove('pr-app-resuming');
            document.getElementById('mainLobbyContainer').inert = false;
        },
        retry() {
            document.getElementById('appResumeStatus').textContent = 'تعذّر الاتصال. تأكد من الإنترنت وحاول مرة ثانية.';
            const button = document.getElementById('appResumeRetry');
            button.hidden = false;
            button.onclick = () => location.reload();
        },
    };
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('mainLobbyContainer').inert = true;
    }, { once: true });
})();
