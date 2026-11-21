package app.playrush.game;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(android.os.Bundle savedInstanceState) {
        if (android.os.Build.VERSION.SDK_INT >= 28) {
            android.view.WindowManager.LayoutParams layout = getWindow().getAttributes();
            layout.layoutInDisplayCutoutMode =
                android.view.WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            getWindow().setAttributes(layout);
        }
        getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_FULLSCREEN);
        super.onCreate(savedInstanceState);
        getWindow().setBackgroundDrawable(
            new android.graphics.drawable.ColorDrawable(0xff0b1018));
        android.webkit.WebView view = getBridge().getWebView();
        view.setVerticalScrollBarEnabled(false);
        view.setHorizontalScrollBarEnabled(false);
        view.setOverScrollMode(android.view.View.OVER_SCROLL_NEVER);
    }

    private android.net.ConnectivityManager connectivity;
    private final android.net.ConnectivityManager.NetworkCallback networkChanges =
        new android.net.ConnectivityManager.NetworkCallback() {
            @Override public void onLost(android.net.Network network) { checkConnection(); }
            @Override public void onCapabilitiesChanged(android.net.Network network,
                    android.net.NetworkCapabilities capabilities) { checkConnection(); }
        };
    private final android.os.Handler networkHandler = new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable notifyConnection = () -> {
        if (connectivity == null || getBridge() == null) return;
        android.net.NetworkCapabilities caps = connectivity.getNetworkCapabilities(connectivity.getActiveNetwork());
        boolean online = caps != null && caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED);
        getBridge().getWebView().evaluateJavascript(
            "window.dispatchEvent(new Event('" + (online ? "pr-native-online" : "pr-native-offline") + "'))", null);
    };
    private void checkConnection() {
        networkHandler.removeCallbacks(notifyConnection);
        networkHandler.postDelayed(notifyConnection, 1000);
    }
    @Override public void onStart() {
        super.onStart();
        connectivity = getSystemService(android.net.ConnectivityManager.class);
        if (android.os.Build.VERSION.SDK_INT >= 24) connectivity.registerDefaultNetworkCallback(networkChanges);
        checkConnection();
    }
    @Override public void onStop() {
        if (android.os.Build.VERSION.SDK_INT >= 24) connectivity.unregisterNetworkCallback(networkChanges);
        networkHandler.removeCallbacks(notifyConnection);
        connectivity = null;
        super.onStop();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            androidx.core.view.WindowInsetsControllerCompat controller =
                androidx.core.view.WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
            controller.setSystemBarsBehavior(
                androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            controller.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars());
        }
    }
}
