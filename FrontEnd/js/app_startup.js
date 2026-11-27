// مسار بدء تطبيق أندرويد قبل تحميل بقية الواجهة.
(() => {
    if (!window.Capacitor?.isNativePlatform?.()) return;
    if (window.PRPracticeLobby || !navigator.onLine) return;
    let savedToken;
    try {
        if (sessionStorage.getItem('pr_logged_out') === '1') return;
        savedToken = localStorage.getItem('token') || sessionStorage.getItem('token');
    } catch { return; }
    if (!savedToken && !new URLSearchParams(location.search).has('token')) return;
    const resumeKey = 'pr_mobile_resume';
    const api = () => CONFIG.API_URL;
    const current = () => localStorage.getItem('token') || sessionStorage.getItem('token');
    async function enroll(access) {
        const response = await fetch(api() + '/auth/mobile-enroll', {method:'POST', headers:{Authorization:'Bearer ' + access}});
        if (response.ok) {
            const data = await response.json();
            if (current() === access && data.credential) localStorage.setItem(resumeKey, data.credential);
        }
    }

    const params = new URLSearchParams(location.search);
    if (document.currentScript.dataset.entry !== undefined) {
        document.documentElement.classList.add('pr-app-resuming');
        location.replace('categories.html?resume=1');
        return;
    }
    const arrivalKey = 'pr_resume_arrival';
    if (sessionStorage.getItem(arrivalKey)) {
        sessionStorage.removeItem(arrivalKey);
        document.documentElement.classList.add('pr-resume-arrived');
    }
    if (params.get('resume') !== '1' || params.has('token')) {
        document.addEventListener('DOMContentLoaded', () => {
            const access = current();
            if (access && !localStorage.getItem(resumeKey)) enroll(access).catch(() => {});
        }, {once:true});
        return;
    }

    document.documentElement.classList.add('pr-app-resuming');
    const abort = new AbortController();
    let complete = false;
    let companyFinished;
    const companyIntro = new Promise(resolve => { companyFinished = resolve; });
    document.addEventListener('DOMContentLoaded', () => {
        if (!window.PRSplash) companyFinished();
    }, {once:true});
    let watchdog;
    function showRecovery() {
        const status = document.getElementById('appResumeStatus');
        if (!status || complete) return;
        document.documentElement.classList.add('pr-resume-recovery');
        status.textContent = 'تعذّر الاتصال. جلستك محفوظة، حاول الاستئناف مرة أخرى.';
        document.getElementById('appResumeRetry').hidden = false;
    }

    let deadline;
    const timeout = new Promise(resolve => {
        deadline = setTimeout(() => {
            resolve({ status: 0, user: null });
            abort.abort();
        }, 8000);
    });
    const request = Promise.resolve().then(async () => {
        const credential = localStorage.getItem(resumeKey);
        if (credential) {
            const body = new URLSearchParams({credential});
            const response = await fetch(api() + '/auth/mobile-resume', {method:'POST', body, signal:abort.signal});
            if (response.ok) {
                const data = await response.json();
                if (data.token && current() === savedToken) {
                    localStorage.setItem('token', data.token);
                    sessionStorage.setItem('token', data.token);
                    sessionStorage.setItem(arrivalKey, '1');
                    await companyIntro;
                    location.replace('categories.html');
                    return new Promise(() => {});
                }
            } else if (response.status === 401) localStorage.removeItem(resumeKey);
            else throw new Error('resume unavailable');
        }
        await enroll(savedToken);
        return fetch(CONFIG.API_URL + '/auth/me', {
        headers: { Authorization: 'Bearer ' + savedToken },
        signal: abort.signal,
    }); }).then(async response => ({
        status: response.status,
        user: response.ok ? await response.json() : null,
    })).catch(() => ({ status: 0, user: null }));
    const account = Promise.race([request, timeout]).finally(() => clearTimeout(deadline));
    account.then(result => {
        if (!result.user && (result.status === 0 || result.status >= 500)) {
            clearTimeout(watchdog);
            if (!document.hidden && !navigator.onLine) location.replace('categories.html?practice=1');
            else showRecovery();
        } else if (!result.user) showRecovery();
    });
    watchdog = setTimeout(showRecovery, 10000);

    window.PRAppStartup = {
        account,
        companyFinished,
        async finish() {
            await companyIntro;
            if (complete) return;
            complete = true;
            window.dispatchEvent(new Event('pr-session-arrived'));
            document.documentElement.classList.add('pr-resume-arrived');
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
