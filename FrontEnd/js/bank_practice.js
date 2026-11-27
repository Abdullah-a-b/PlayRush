/* مباراة البنك الفردية تستخدم أحداث واجهة البنك نفسها. */
function attachBankPractice(socket, difficulty) {
    const human = 'local-player', bot = 'local-bank-bot';
    const profiles = {
        beginner: { knowledge: [.57,.30,.12], think: 5.5 },
        medium:   { knowledge: [.72,.48,.24], think: 4.6 },
        hard:     { knowledge: [.84,.66,.40], think: 3.8 },
        expert:   { knowledge: [.93,.80,.58], think: 3.2 }
    };
    const profile = profiles[difficulty] || profiles.medium;
    const safe = { [human]: 0, [bot]: 0 };
    const usedAids = new Set(), timers = new Set(), seen = new Set();
    let round = 0, finished = false, players;
    const send = (name, data={}) => socket.listeners(name).slice().forEach(fn => fn(data));
    const notify = (name, data) => send('bank_'+name, data);
    const later = (seconds, fn) => {
        const id = setTimeout(() => { timers.delete(id); if (!finished) fn(); }, seconds*1000);
        timers.add(id);
    };
    const activity = (type, amount) => notify('opp_activity', {type,amount});
    const remaining = p => Math.max(0,(p.end-(p.paused || Date.now()))/1000);
    function endMatch(winner) {
        finished=true;
        timers.forEach(clearTimeout);
        timers.clear();
        notify('match_over',{safe,winner});
    }
    function newRound() {
        round++;
        players = {};
        for (const id of [human,bot]) players[id]={temp:0,phase:'ready',tierStart:60,paused:0,bonus:0};
        notify('round_start',{round,totalRounds:4,turnSeconds:60,safe});
    }
    function done(id) {
        const p=players[id];
        if (p.phase==='done') return;
        const amount=p.temp;
        safe[id]+=amount; p.temp=0; p.phase='done';
        if(id===human) notify('player_done',{safe,autoBanked:amount});
        else activity('done');
        notify('safe_update',{safe});
        if(Object.values(players).every(v=>v.phase==='done')){
            if(round===4) endMatch(safe[human]===safe[bot]?null:safe[human]>safe[bot]?human:bot);
            else later(1.5,newRound);
        }
    }
    function watch(id,p) {
        if(players[id]!==p || p.phase==='done')return;
        if(remaining(p)<=0)done(id);
        else later(.25,()=>watch(id,p));
    }
    function question(id) {
        const p=players[id];
        if(p.phase==='done'||!remaining(p))return;
        const tier=Math.min(2,Math.max(0,Math.floor((p.tierStart+p.bonus-remaining(p))/20)));
        const pool=BANK_PRACTICE.questions[['easy','medium','hard'][tier]];
        let choices=pool.filter(q=>!seen.has(q));
        if(id===human && !choices.length){pool.forEach(q=>seen.delete(q));choices=pool;}
        const key='pr.bank.recent.'+(globalThis.localStorage?.getItem('pr_last_player')||'guest')+'.'+tier;
        let history=[];
        if(id===human){
            try{history=JSON.parse(localStorage.getItem(key)||'[]');}catch{}
            const fresh=choices.filter(q=>!history.includes(q.q));
            choices=fresh.length ? fresh : [choices.reduce((a,b)=>history.indexOf(a.q)<history.indexOf(b.q)?a:b)];
        } else choices=pool;
        const card=choices[Math.floor(Math.random()*choices.length)];
        if(id===human){
            seen.add(card);
            try{localStorage.setItem(key,JSON.stringify([...history.filter(q=>q!==card.q),card.q].slice(-pool.length)));}catch{}
        } p.card=card;p.tier=tier;p.phase='question';
        if(id===human)notify('question',{category:card.cat,text:card.q,remaining:remaining(p)});
        else later(profile.think+Math.random()*3,()=>{if(players[id]===p && p.phase==='question')write(id);});
    }
    function write(id) {
        const p=players[id];
        if(p.phase!=='question'||!remaining(p))return;
        p.phase='writing';p.paused=Date.now();
        const card=p.card;
        if(id===human){
            notify('answering',{answerWindow:8});
            later(8,()=>{if(p.phase==='writing' && p.card===card)judge(id,false,true);});
        }else{
            activity('answering');
            later(1.3+Math.random()*2.5,()=>judge(id,Math.random()<practiceRecall("bank",difficulty,profile.knowledge[p.tier]),false));
        }
    }
    function bank(id) {
        const p=players[id];
        if(p.phase!=='decision'||!remaining(p))return;
        const amount=p.temp;
        safe[id]+=amount;p.temp=0;p.tierStart=remaining(p)-p.bonus;p.phase='between';
        if(id===human)notify('banked',{amount,safe,remaining:remaining(p)});
        else activity('banked',amount);
        notify('safe_update',{safe});later(.6,()=>question(id));
    }
    function judge(id,correct,timedOut) {
        const p=players[id];
        if(p.phase!=='writing')return;
        p.end+=Date.now()-p.paused;p.paused=0;
        const points=p.tier+1,lost=p.temp,card=p.card;
        p.temp=correct?p.temp+points:0;
        if(!correct)p.tierStart=remaining(p)-p.bonus;
        p.phase='feedback';
        if(id===human)notify('answer_result',{correct,timedOut,points,lost:correct?0:lost,temp:p.temp,safe,correctAnswer:card.a,remaining:remaining(p)});
        else activity(correct?'correct':'wrong');
        later(1.2,()=>{
            if(players[id]!==p || p.phase!=='feedback')return;
            if(!correct)return question(id);
            p.phase='decision';
            if(id===human)notify('decision',{temp:p.temp,remaining:remaining(p)});
            else {
                const behind=safe[human]-safe[bot];
                const gapBin=behind>2?2:behind< -1?0:1;
                const timeBin=remaining(p)<13?0:remaining(p)<30?1:2;
                const row=(gapBin*3+timeBin)*3+p.tier;
                const riskModel=BANK_RISK[difficulty] || BANK_RISK.medium;
                const preferredBalance=({beginner:2,medium:3,hard:4,expert:5}[difficulty] || 3)
                    +(behind>3?2:0)-(remaining(p)<12?1:0);
                const baseline=p.temp>=preferredBalance?.8:.18;
                const bankChance=.65*baseline+.35*riskModel[row][Math.min(8,p.temp)-1];
                if(Math.random()<bankChance)later(.8+Math.random(),()=>bank(id));
            }
            later(5,()=>{if(players[id]===p && p.card===card && p.phase==='decision')question(id);});
        });
    }
    function normalize(s){
        return String(s).trim().toLowerCase().replace(/[٠-٩]/g,c=>'٠١٢٣٤٥٦٧٨٩'.indexOf(c))
            .replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/ة/g,'ه').replace(/[\sـ\u064b-\u065f]/g,'');
    }
    socket.id=human;
    socket.emit=(name,data={})=>{
        if(finished)return socket;
        const p=players?.[human];
        if(name==='join_room' && !round){
            const people=[{sid:human,name:data.player_name,stats:{name:data.player_name,avatar:data.avatar}},
                {sid:bot,name:'الكمبيوتر',stats:{name:'الكمبيوتر',avatar:'avatar_2.svg'}}];
            send('room_joined',{players:people});later(3.3,newRound);
        }else if(name==='get_help_loadout'){
            queueMicrotask(()=>send('help_loadout_data',{game:'bank',catalog:BANK_PRACTICE.helps,
                loadout:BANK_PRACTICE.helps.map(h=>h.id),inventory:Object.fromEntries(BANK_PRACTICE.helps.map(h=>[h.id,1]))}));
        }else if(name==='bank_surrender')endMatch(bot);
        else if(p && name==='bank_practice_ready' && p.phase==='ready'){
            for(const id of [human,bot]){players[id].end=Date.now()+60000;question(id);watch(id,players[id]);}
        }else if(p && name==='bank_answer_start')write(human);
        else if(p?.phase==='writing' && name==='bank_submit_answer'){
            judge(human,[p.card.a,...p.card.accepted].some(a=>normalize(a)===normalize(data.answer)),false);
        }else if(p && name==='bank_bank')bank(human);
        else if(p && name==='bank_use_help' && p.phase!=='ready' && p.phase!=='done' && !usedAids.has(data.helpId)){
            const id=data.helpId;
            let info;
            if(id==='b_time_plus'){p.end+=10000;p.bonus+=10;info='أضيفت عشر ثوانٍ';}
            else if(p.phase==='question' && id==='b_first_letter')info='الحرف الأول: '+p.card.a[0];
            else if(p.phase==='question' && id==='b_skip'){question(human);info='تم تغيير السؤال';}
            else return socket;
            usedAids.add(id);notify('help_result',{ok:true,helpId:id,info,remaining:p.paused?undefined:remaining(p)});
        }
        return socket;
    };
    setTimeout(()=>send('connect'),0);
}
