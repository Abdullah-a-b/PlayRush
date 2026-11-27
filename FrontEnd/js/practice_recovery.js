/* انتقال فردي فقط. تبقى النقاط المحلية خارج حساب اللاعب. */
window.attachPracticeRecovery = function(socket, game) {
    const params = new URLSearchParams(location.search);
    if (params.get('solo') !== '1') { window.watchNetworkLoss(()=>false,socket); return; }
    let active=false, finished=false, leaving=false, sid, color;
    const checkpoint={game, level:params.get('difficulty') || 'medium',round:1,points:[0,0]};
    const localRequested = params.get('practice')==='1' || !navigator.onLine;
    window.PRPracticeAllowed=localRequested;
    function transfer() {
        if (leaving || finished) return;
        leaving=true;
        window.PRPracticeAllowed=true;
        socket.disconnect();
        socket.sendBuffer.length=0;
        checkpoint.color=color;
        checkpoint.sid=sid;
        checkpoint.live=active;
        const field=document.querySelector('#answerInput, #playerAnswerInput');
        const draft=field?.value;

        const url=new URL(location.href);
        url.searchParams.set('practice','1');
        history.replaceState(null,'',url);
        window.startEmergencyMatch(socket,game,checkpoint,!active);
        if(!localRequested)window.showToast?.('انقطع الاتصال. تتابع الآن ضد الكمبيوتر بدون إنترنت.');
        if(draft && checkpoint.typing && field && field.offsetWidth)field.value=draft;
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
    socket.onAny((name,d={})=>{
        if(leaving)return;
        if(name==='huroof_helps_catalog')checkpoint.aidsUsed=[...(d.used||[])];
        if(name==='huroof_help_result' && d.ok && d.helpId)(checkpoint.aidsUsed??=[]).push(d.helpId);
        if(name===game+'_new_character'||name===game+'_new_player'||name==='knowledge_round_start'){
            checkpoint.clues=null;checkpoint.typing=false;checkpoint.strikes=[0,0];
            checkpoint.question=d.q;checkpoint.said=[];
        }
        if(name===game+'_reveal_state'){
            checkpoint.clues=d.hints || d.clubs?.map(c=>c.name);
            scores(d.scores);
        }
        if(d.strikes && sid)checkpoint.strikes=[d.strikes[sid]||0,Object.entries(d.strikes).find(([k])=>k!==sid)?.[1]||0];
        if(name==='knowledge_correct')checkpoint.said?.push(d.answer);
        if(name==='knowledge_turn')checkpoint.turn=d.sid===sid?0:1;
        if(name==='huroof_board_init'){checkpoint.board=d.board.map(c=>({...c}));checkpoint.selected=null;}
        if(name==='huroof_turn_changed'){checkpoint.turn=d.turn_color===color?0:1;checkpoint.selected=null;}
        if(name==='huroof_hex_locked')checkpoint.selected=d.hexIndex;
        if(name==='huroof_new_question')checkpoint.question=d.questionData?.question;
        if(name==='huroof_answer_result'&&d.correct&&checkpoint.board?.[d.hexIndex]){
            checkpoint.board[d.hexIndex].color=d.color;checkpoint.selected=null;
        }
        if(name===game+'_buzzed')checkpoint.typing=d.sid===sid;
        if(name===game+'_answer_result'||name===game+'_strike')checkpoint.typing=false;
    });
    socket.on(game+'_match_over',()=>{finished=true;});
    if(!localRequested)window.watchNetworkLoss(transfer,socket);
    if(localRequested)setTimeout(transfer,0);
};
