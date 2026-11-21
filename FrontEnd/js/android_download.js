if (/Android/i.test(navigator.userAgent) && !window.Capacitor?.isNativePlatform?.()) {
    document.querySelector('.android-download').hidden = false;
}
