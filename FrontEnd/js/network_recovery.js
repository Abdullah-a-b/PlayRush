// A suspended WebView socket can disconnect while the phone still has internet.
window.watchNetworkLoss = function (onLoss, socket) {
    let pending=false, timer, generation=0, failures=0, wasBackground=false, stopped=false;
    function resume(){
        if(document.hidden || stopped) return;
        if(socket && !socket.connected && navigator.onLine) socket.connect();
        if(pending || !navigator.onLine || (socket && !socket.connected)){pending=true;schedule();}
    }
    function cancel() {
        pending=false;failures=0;
        generation++;
        clearTimeout(timer);
    }
    function schedule() {
        if (!pending || document.hidden) return;
        clearTimeout(timer);
        const ticket=++generation;
        timer=setTimeout(async () => {
            if (ticket!==generation || document.hidden) return;
            if (navigator.onLine && socket?.connected) return cancel();
            if (navigator.onLine) {
                try {
                    const response=await fetch(CONFIG.API_URL+'/health',{
                        cache:'no-store',signal:AbortSignal.timeout(5000)
                    });
                    if(response.ok) { if(ticket===generation)cancel(); return; }
                } catch {}
            }
            if(ticket!==generation || document.hidden) return;
            if(++failures < 2){schedule();return;}
            cancel();stopped=onLoss() !== false;
        }, navigator.onLine ? 5500 : 1200);
    }
    function suspect() { if(!stopped && !pending){pending=true;schedule();} }
    for (const event of ['offline','pr-native-offline']) window.addEventListener(event,suspect);
    for (const event of ['online','pr-native-online']) window.addEventListener(event,()=>{if(pending)schedule();});
    document.addEventListener('visibilitychange',()=>{
        generation++;clearTimeout(timer);
        if(document.hidden){wasBackground=true;failures=0;}
        else if(wasBackground){wasBackground=false;resume();}
    });
    window.addEventListener('pr-native-resume',resume);
    window.addEventListener('pageshow',event=>{if(event.persisted)resume();});
    socket?.on('disconnect',suspect);
    socket?.on('connect_error',suspect);
    socket?.on('connect',cancel);
};
