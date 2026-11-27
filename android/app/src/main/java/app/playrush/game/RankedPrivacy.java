package app.playrush.game;

import android.os.Build;
import android.view.Window;
import android.view.WindowManager;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "RankedPrivacy")
public class RankedPrivacy extends Plugin {
    @PluginMethod
    public void setRanked(PluginCall call) {
        boolean enabled = Boolean.TRUE.equals(call.getBoolean("enabled", false));
        getActivity().runOnUiThread(() -> {
            Window window = getActivity().getWindow();
            if (enabled) window.addFlags(WindowManager.LayoutParams.FLAG_SECURE);
            else window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
            if (Build.VERSION.SDK_INT >= 31) window.setHideOverlayWindows(enabled);
            call.resolve();
        });
    }
}
