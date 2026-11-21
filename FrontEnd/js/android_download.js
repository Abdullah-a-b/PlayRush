if (/Android/i.test(navigator.userAgent) && !window.Capacitor?.isNativePlatform?.()) {
    document.querySelectorAll('.android-download').forEach(link => {
        link.hidden = false;
    });
}
