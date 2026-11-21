/* انتقال فردي فقط. تبقى النقاط المحلية خارج حساب اللاعب. */
window.attachPracticeRecovery = function(socket, game) {
    const params = new URLSearchParams(location.search);
    if (params.get('solo') !== '1') return;
    let active=false, finished=false, leaving=false, sid, color;
    const checkpoint={game, level:params.get('difficulty') || 'medium',round:1,points:[0,0]};
    function transfer() {
        if (leaving || finished) return;
        leaving=true;
        sessionStorage.setItem('pr.practice.transfer', JSON.stringify(checkpoint));
        socket.disconnect();
        location.replace('../offline.html?game='+game+'&transfer=1');
    }
    socket.on('solo_started', data=>{active=true;sid=socket.id;color=data.your_color;});
    socket.on('room_joined', data=>{sid=data.your_sid || socket.id;});
    function scores(data) {
        if (!data || !Object.hasOwn(data,sid)) return;
        const other=Object.keys(data).find(k=>k!==sid);
        if(other) checkpoint.points=[data[sid],data[other]];
    }
    socket.on(game+'_new_character',d=>{checkpoint.round=d.charIndex;scores(d.scores);});
    socket.on(game+'_new_player',d=>{checkpoint.round=d.playerIndex;scores(d.scores);});
    socket.on('knowledge_round_start',d=>{checkpoint.round=d.index;});
    socket.on('knowledge_round_over',d=>{checkpoint.round=d.index+1;scores(d.points);});
    socket.on('huroof_round_over',d=>{
        checkpoint.round=d.next_round || checkpoint.round+1;
        if(color && d.points)checkpoint.points=[d.points[color],d.points[color==='green'?'orange':'green']];
    });
    socket.on(game+'_match_over',()=>{finished=true;});
    socket.on('disconnect',()=>{if(active)transfer();});
    window.addEventListener('offline',transfer);
    // قد يظهر الهاتف متصلاً بالواي فاي مع تعذر الوصول إلى الخادم نفسه.
    socket.on('connect_error',()=>{
        if(finished || leaving || document.getElementById('practiceFallback'))return;
        const link=document.createElement('button');
        link.id='practiceFallback';link.textContent='تعذّر الاتصال · العب دون إنترنت';
        link.style.cssText='position:fixed;inset:35% 10% auto;z-index:100001;padding:14px;border-radius:12px';
        link.onclick=transfer;document.body.append(link);
        socket.once('connect',()=>link.remove());
    });
    if(!navigator.onLine)transfer();
};
