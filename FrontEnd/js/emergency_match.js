/* محرك محلي يغذي نفس أحداث واجهة المباراة عند تعذر الاتصال. */
window.startEmergencyMatch = function(socket, game, checkpoint, resume) {
    const me=checkpoint.sid || socket.id || 'practice-human', bot='practice-cpu';
    const levels={beginner:.34, medium:.53, hard:.72, expert:.86};
    const skill=levels[checkpoint.level] || levels.medium;
    const recall=prior=>practiceRecall(game,checkpoint.level,prior);
    const deck=OFFLINE_DECK[game], key='pr.match.local.2.'+game+'.'+checkpoint.level;
    const pick=items=>items[Math.floor(Math.random()*items.length)];
    const norm=x=>String(x||'').trim().toLowerCase().replace(/[\u064b-\u065fـ]/g,'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/ة/g,'ه').replace(/[\s-]+/g,'');
    const send=(event,data)=>socket.listeners(event).slice().forEach(fn=>fn.call(socket,data));
    const event=(name,data)=>send(game+'_'+name,data);
    const keyed=values=>({[me]:values[0],[bot]:values[1]});
    let state,timer;
    let preparing = !checkpoint.live;
    if(resume)try{state=JSON.parse(localStorage.getItem(key));}catch{}
    if(resume && !state)try{
        const legacyKey='pr.practice.v1.'+game;
        const legacy=JSON.parse(localStorage.getItem(legacyKey));
        if(legacy && !legacy.done && legacy.level===checkpoint.level){
            state={...legacy,color:'green'};
            if(game==='huroof')state.cells=state.cells.map(c=>({...c,owner:c.owner==='me'?0:c.owner==='bot'?1:null}));
            state.turn=['botTurn','botChoose'].includes(state.phase)?1:0;
            if(state.phase==='botTurn')state.phase='play';
            if(state.phase==='botChoose')state.phase='choose';
            localStorage.setItem(key,JSON.stringify(state));localStorage.removeItem(legacyKey);
        }
    }catch{}
    if(!state)state={round:checkpoint.round,points:checkpoint.points.slice(),color:checkpoint.color||'green',seen:[],phase:'new'};
    const color=i=>i===0?state.color:(state.color==='green'?'orange':'green');
    const colors=()=>({[color(0)]:state.points[0],[color(1)]:state.points[1]});
    function save(){try{localStorage.setItem(key,JSON.stringify(state));}catch{}}
    function after(ms,fn){clearTimeout(timer);deadline=Date.now()+ms;onDeadline=fn;timer=setTimeout(fn,ms);}
    function newRound() {
        state.strikes=[0,0];state.used=[];state.step=0;state.turn=0;state.phase='play';
        if(game==='huroof'){
            const groups=new Map();
            for(const [i,q] of deck.entries()){
                const l=norm(q.a)[0];if(!groups.has(l))groups.set(l,[]);groups.get(l).push(i);
            }
            const options=[...groups.values()];
            state.cells=Array.from({length:25},()=>({q:pick(options.splice(Math.floor(Math.random()*options.length),1)[0]),owner:null}));
            state.selected=Math.floor(Math.random()*25);
        }else{
            let options=deck.map((_,i)=>i).filter(i=>!state.seen.includes(i));
            if(!options.length){state.seen=[];options=deck.map((_,i)=>i);}
            state.index=pick(options);state.seen.push(state.index);
        }
        present(true);
    }
    function finish(winner){
        clearTimeout(timer);state.phase='done';
        try{localStorage.removeItem(key);}catch{}
        const sid=winner===0?me:bot;
        event('match_over',{winner:game==='huroof'?color(winner):sid,winner_sid:sid,
            scores:keyed(state.points), points:game==='huroof'?colors():keyed(state.points)});
    }
    function nextRound(winner,points){
        if(game==='knowledge' && winner===null)state.points=state.points.map((v,i)=>v+3-state.strikes[i]);
        if(winner!==null) state.points[winner]+=points;
        if(game==='knowledge')event('round_over',{points:keyed(state.points),strikes:keyed(state.strikes),gains:winner===null?{}:{[winner?bot:me]:points},loser_sid:winner?me:bot,loser_name:winner?'أنت':'الكمبيوتر',exhausted:winner===null});
        if(game==='huroof')event('round_over',{points:colors(),winner:color(winner),next_round:state.round+1});
        const done=game==='huroof'?Math.max(...state.points)>=2:state.round>=5&&state.points[0]!==state.points[1];
        state.phase=done?'ending':'between';save();
        after(1800,advanceRound);
    }
    function advanceRound(){
        if(state.phase==='ending')return finish(state.points[0]>state.points[1]?0:1);
        state.round++;newRound();
    }
    function connectedPath(owner){
        const todo=[], seen=new Set(), vertical=color(owner)==='green';
        state.cells.forEach((c,i)=>{if(c.owner===owner&&(vertical?i<5:i%5===0))todo.push(i);});
        while(todo.length){
            const i=todo.pop();if(seen.has(i))continue;seen.add(i);
            const r=Math.floor(i/5),c=i%5;if(vertical?r===4:c===4)return true;
            const d=r%2?1:-1;
            for(const [y,x] of [[r,c-1],[r,c+1],[r-1,c],[r+1,c],[r-1,c+d],[r+1,c+d]]){
                const j=y*5+x;if(y>=0&&y<5&&x>=0&&x<5&&state.cells[j].owner===owner)todo.push(j);
            }
        }return false;
    }
    const aids = [{"id": "extend_time", "name": "تمديد الوقت", "desc": "يضيف 10 ثوانٍ إضافية لمؤقّت إجابتك. يُستخدم بعد اختيار الحرف.", "icon": "⏱️", "rarity": "common", "timing": "post"}, {"id": "change_question", "name": "تغيير السؤال", "desc": "يحذف السؤال الحالي ويجلب سؤالاً جديداً لنفس الحرف.", "icon": "🔄", "rarity": "common", "timing": "post"}, {"id": "count_letters", "name": "كاشف عدد الحروف", "desc": "يكشف عدد حروف الإجابة المطلوبة، مما يضيّق نطاق التفكير.", "icon": "🔢", "rarity": "common", "timing": "post"}];
    state.aidsUsed ??= checkpoint.aidsUsed || [];
    let deadline, onDeadline, questionDeadline;
    function showAids(){
        const ids=aids.map(h=>h.id);
        event('helps_catalog',{catalog:aids,loadout:ids,used:state.aidsUsed,
            inventory:Object.fromEntries(ids.map(id=>[id,state.aidsUsed.includes(id)?0:1]))});
    }
    function useAid(id){
        if(!aids.some(h=>h.id===id)||state.aidsUsed.includes(id)||!['typing','play'].includes(state.phase))return;
        const cell=state.cells[state.selected], q=deck[cell.q];
        const result={ok:true,helpId:id,effect:id};
        if(id==='change_question'){
            if(state.phase!=='play')return;
            const options=deck.map((item,i)=>i!==cell.q && norm(item.a)[0]===norm(q.a)[0]?i:null).filter(i=>i!==null);
            if(!options.length){event('help_result',{ok:false,msg:'لا يوجد سؤال بديل لهذا الحرف'});return;}
            cell.q=pick(options);present(false);
        }else if(id==='count_letters')result.count=norm(q.a).length;
        else {
            if(!onDeadline)return;
            const end=state.phase==='play'?questionDeadline:deadline;
            result.new_total=Math.max(0,Math.ceil((end-Date.now())/1000))+10;
            after(deadline-Date.now()+10000,onDeadline);
        }
        state.aidsUsed.push(id);save();event('help_result',result);
    }
    function pathCost(owner){
        const distance=Array(25).fill(26),todo=[],vertical=color(owner)==='green';
        function visit(i,base){
            const held=state.cells[i].owner;
            if(held!==null && held!==owner)return;
            const cost=base+(held===null?1:0);
            if(cost<distance[i]){distance[i]=cost;todo.push(i);}
        }
        for(let n=0;n<5;n++)visit(vertical?n:n*5,0);
        while(todo.length){
            const i=todo.pop(),r=Math.floor(i/5),c=i%5,d=r%2?1:-1;
            for(const [y,x] of [[r,c-1],[r,c+1],[r-1,c],[r+1,c],[r-1,c+d],[r+1,c+d]])
                if(y>=0&&y<5&&x>=0&&x<5)visit(y*5+x,distance[i]);
        }
        return Math.min(...Array.from({length:5},(_,n)=>distance[vertical?20+n:5*n+4]));
    }
    function chooseCell(){
        const open=state.cells.map((c,i)=>c.owner===null?i:null).filter(i=>i!==null);
        if(Math.random()>skill)return pick(open);
        let best=-Infinity,choice;
        for(const i of open){
            state.cells[i].owner=1;
            const score=pathCost(0)-2*pathCost(1)+Math.random()*.5;
            state.cells[i].owner=null;
            if(score>best){best=score;choice=i;}
        }
        return choice;
    }
    function botAnswer(){
        state.phase='botTyping';save();event('buzzed',{sid:bot,time:10});
        after(1800+Math.random()*2200,()=>claim(1));
    }
    function claim(owner){
        const i=state.selected;state.cells[i].owner=owner;
        event('answer_result',{correct:true,hexIndex:i,color:color(owner),answer:deck[state.cells[i].q].a});
        const won=connectedPath(owner);
        state.selected=null;state.turn=owner;state.phase='choose';save();
        if(won)return nextRound(owner,1);
        state.phase='feedback';
        after(2300,()=>{state.phase='choose';present(false);});
    }
    function showBoard(initial){
        if(initial){
            event('new_round_started',{turn:me});
            event('board_init',{board:state.cells.map(c=>({letter:deck[c.q].a[0],color:c.owner===null?null:color(c.owner)}))});
        }
        event('turn_changed',{turn_sid:state.turn?bot:me,turn_color:color(state.turn)});
        if(state.phase==='choose'){
            if(state.turn)after(2000+Math.random()*1800,()=>{state.selected=chooseCell();state.phase='play';present(false);});
            return;
        }
        const q=deck[state.cells[state.selected].q];
        event('hex_locked',{hexIndex:state.selected,letter:q.a[0]});
        questionDeadline=Date.now()+30000;
        event('new_question',{timer:30,questionData:{question:q.q}});
        if(state.phase==='typing'){event('buzzed',{sid:me,time:10});after(10000,()=>letterMiss(''));return;}
        if(Math.random()<recall(skill))after(4500+(1-skill)*5000+Math.random()*4500,botAnswer);
        else after(30000,()=>letterMiss(''));
    }
    function letterMiss(text){
        event('answer_result',{correct:false,hexIndex:state.selected,answer:text});
        if(text && Math.random()<recall(skill)){state.phase='feedback';after(2300,botAnswer);return;}
        state.phase='choose';state.selected=null;state.turn=0;present(false);
    }
    function listAnswer(owner,text){
        const q=deck[state.index],idx=q.answers.findIndex(g=>g.some(a=>norm(a)===norm(text)));
        const correct=idx>=0&&!state.used.includes(idx), sid=owner?bot:me;
        if(correct){state.used.push(idx);event('correct',{sid,name:owner?'الكمبيوتر':'أنت',answer:q.answers[idx][0]});}
        else {state.strikes[owner]++;event('strike',{sid,name:owner?'الكمبيوتر':'أنت',reason:!text?'timeout':idx>=0?'repeat':'wrong',answer:text,count:state.strikes[owner],max:3,strikes:keyed(state.strikes)});}
        if(state.strikes[owner]>=3)return nextRound(1-owner,3-state.strikes[1-owner]);
        if(state.used.length===q.answers.length)return nextRound(null,0);
        state.turn=1-owner;present(false);
    }
    function showList(initial){
        const q=deck[state.index];
        if(initial){
            event('round_start',{index:state.round,total:5,q:q.q,category:'',tiebreak:state.round>5});
            for(const idx of state.used)event('correct',{sid:me,answer:q.answers[idx][0]});
        }
        const data={sid:state.turn?bot:me,name:state.turn?'الكمبيوتر':'أنت',points:keyed(state.points),strikes:keyed(state.strikes),seconds:10,turn_ends_at:Date.now()/1000+10};
        event('turn',data);
        if(!state.turn){event('your_turn',data);after(10000,()=>listAnswer(0,''));}
        else after(2200+Math.random()*1800,()=>{
            const choices=q.answers.filter((_,i)=>!state.used.includes(i));
            listAnswer(1,choices.length && Math.random()<recall(skill*(1-.55*state.used.length/q.answers.length))?pick(choices)[0]:state.used.length?q.answers[pick(state.used)][0]:'');
        });
    }
    const points=()=>game==='career'?(state.step===0?2:1):Math.max(1,4-state.step);
    function clueResult(owner,correct){
        const card=deck[state.index], sid=owner?bot:me;
        event('answer_result',{sid,correct,points:points(),name:card.answers[0],playerName:card.answers[0],
            scores:keyed(state.points.map((v,i)=>v+(correct&&owner===i?points():0)))});
        if(correct)return nextRound(owner,points());
        state.strikes[owner]++;state.phase='play';
        event('strike',{sid,count:state.strikes[owner],maxStrikes:2,strikes:keyed(state.strikes)});
        present(false);
    }
    function showClues(initial){
        const card=deck[state.index], clues=card.clues.slice(0,state.step+1);
        const data={charIndex:state.round,playerIndex:state.round,totalCharacters:5,totalPlayers:5,
            scores:keyed(state.points),strikes:keyed(state.strikes),pointsIfAnswer:points(),windowSeconds:8,
            hints:clues,clubs:clues.map(name=>({name})),totalHints:card.clues.length};
        if(initial)event(game==='career'?'new_player':'new_character',data);
        event('reveal_state',data);
        if(state.phase==='typing'){event('buzzed',{sid:me,answerWindow:10});after(10000,()=>clueResult(0,false));return;}
        after(8000,()=>{
            if(Math.random()<recall(skill*clues.length/card.clues.length)){
                event('buzzed',{sid:bot,answerWindow:10});state.phase='botTyping';save();
                after(1400,()=>clueResult(1,true));return;
            }
            if(state.step+1<card.clues.length){state.step++;present(false);}
            else{event('reveal_answer',{name:card.answers[0],playerName:card.answers[0]});after(1700,newRound);}
        });
    }
    function present(initial){
        clearTimeout(timer);save();
        if(game==='knowledge')showList(initial);
        else if(game==='huroof')showBoard(initial);
        else showClues(initial);
    }
    function handleAction(name,data={}){
        if(!name.startsWith(game+'_') || state.phase==='done')return socket;
        const action=name.slice(game.length+1);
        if(game==='huroof' && action==='get_helps_catalog'){showAids();return socket;}
        if(preparing && action!=='surrender')return socket;
        if(action==='surrender')finish(1);
        else if(game==='huroof' && action==='use_help')useAid(data.helpId);
        else if(action==='buzz'&&state.phase==='play'&&game!=='knowledge'&&(game==='huroof'||state.strikes[0]<2)){
            state.phase='typing';save();clearTimeout(timer);event('buzzed',{sid:me,time:10,answerWindow:10});after(10000,()=>game==='huroof'?letterMiss(''):clueResult(0,false));
        }else if(action==='submit_answer'&&data.answer){
            if(game==='knowledge'&&state.phase==='play'&&!state.turn)listAnswer(0,data.answer);
            else if(state.phase==='typing'){
                if(game==='huroof'){const a=deck[state.cells[state.selected].q].a;if(norm(a)===norm(data.answer))claim(0);else letterMiss(data.answer);}
                else clueResult(0,deck[state.index].answers.some(a=>norm(a)===norm(data.answer)));
            }
        }else if(action==='select_hex'&&game==='huroof'&&state.phase==='choose'&&!state.turn&&state.cells[data.hexIndex]?.owner===null){
            state.selected=data.hexIndex;state.phase='play';present(false);
        }else if(action==='vote_skip'&&game==='huroof'&&state.phase==='play'){
            const cell=state.cells[state.selected], options=deck.map((q,i)=>i!==cell.q&&norm(q.a)[0]===norm(deck[cell.q].a)[0]?i:null).filter(i=>i!==null);
            if(options.length){cell.q=pick(options);present(false);}
        }
        return socket;
    };
    socket.emit=function(name,data){
        queueMicrotask(()=>handleAction(name,data));
        return socket;
    };
    if(checkpoint.live && state.phase==='new'){
        const clues=checkpoint.clues;
        if(game==='huroof' && checkpoint.board?.length===25){
            const cells=checkpoint.board.map((c,i)=>{
                const candidates=deck.map((q,n)=>norm(q.a)[0]===norm(c.letter)[0]?n:null).filter(n=>n!==null);
                const exact=candidates.find(n=>deck[n].q===checkpoint.question && i===checkpoint.selected);
                return {q:exact??pick(candidates),owner:c.color===color(0)?0:c.color===color(1)?1:null};
            });
            if(cells.every(c=>c.q!==undefined)){
                Object.assign(state,{cells,step:0,used:[],strikes:[0,0],turn:checkpoint.turn||0,selected:checkpoint.selected,phase:checkpoint.selected==null?'choose':'play'});
                if(checkpoint.typing && deck[cells[state.selected]?.q]?.q===checkpoint.question)state.phase='typing';
            }
        }else{
            const matches=deck.map((c,i)=>(game==='knowledge'?c.q===checkpoint.question:clues?.length && clues.every((h,j)=>c.clues[j]===h))?i:null).filter(i=>i!==null);
            if(matches.length===1){
                const index=matches[0],card=deck[index];
                const used=(checkpoint.said||[]).map(a=>card.answers.findIndex(group=>Array.isArray(group)&&group.some(v=>norm(a)===norm(v)))).filter(i=>i>=0);
                Object.assign(state,{index,seen:[index],step:Math.max(0,(clues?.length||1)-1),strikes:checkpoint.strikes||[0,0],used,turn:checkpoint.turn||0,phase:checkpoint.typing?'typing':'play'});
            }
        }
    }
    socket.id=me;
    const people=[me,bot].map((sid,i)=>({sid,color:color(i),name:i?'الكمبيوتر':sessionStorage.getItem('playerName')||'لاعب',stats:{global:{wins:0,losses:0,total:0},[game]:{wins:0,losses:0,total:0},flag:i?'../assets/flags/EARTH.svg':'../assets/flags/SA.svg',name:i?'الكمبيوتر':sessionStorage.getItem('playerName')||'لاعب',avatar:'../assets/avatars/avatar_'+(i+1)+'.svg'}}));
    document.body.classList.add('solo-mode');
    if(!checkpoint.live){
    send('connect');
    send('solo_started',{room_code:'local',your_color:color(0)});
    send('room_joined',{your_sid:me,players:people});
    }
    function begin() {
        preparing = false;
        if(game==='huroof')showAids();
        if(state.phase==='done')return;
        if(state.phase==='new')newRound();
        else if(['ending','between'].includes(state.phase))advanceRound();
        else {if(state.phase==='botTyping')state.phase='play';present(true);}
    }
    if(preparing){
        const reveal=document.getElementById('matchRevealOverlay');
        const ready=()=>send('practice_ready',begin);
        if(reveal?.classList.contains('show')){
            const observer=new MutationObserver(()=>{
                if(reveal.classList.contains('show'))return;
                observer.disconnect();
                ready();
            });
            observer.observe(reveal,{attributes:true,attributeFilter:['class']});
        }else ready();
    }else begin();
    const exit=document.getElementById('backToLobbyBtn') || document.querySelector('#winMessageOverlay button[onclick]');
    exit?.addEventListener('click',e=>{e.stopImmediatePropagation();location.assign('../categories.html?practice=1');},true);
};
