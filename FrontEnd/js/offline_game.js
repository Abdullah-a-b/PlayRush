(() => {
    const names = {whoami:'من أنا', career:'مسيرة لاعب', knowledge:'ماذا تعرف', huroof:'خلية الحروف'};
    const skill = {beginner:.34,medium:.53,hard:.72,expert:.86};
    const params = new URLSearchParams(location.search);
    const $ = id => document.getElementById(id);
    const pick = list => list[Math.floor(Math.random()*list.length)];
    const norm = text => text.trim().toLowerCase().replace(/[\u064b-\u065fـ]/g,'').replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/ة/g,'ه').replace(/[\s-]+/g,'');
    const key = game => 'pr.practice.v1.'+game;
    let s, timer;
    function save() {
        try { localStorage.setItem(key(s.game),JSON.stringify(s)); } catch { $('notice').textContent='تعذّر حفظ التقدم على الجهاز'; }
    }
    function restore(game) {
        try { const data=JSON.parse(localStorage.getItem(key(game))); return data?.game===game && !data.done ? data : null; } catch { return null; }
    }
    function menu() {
        clearTimeout(timer); $('menu').hidden=false; $('match').hidden=true; $('games').replaceChildren();
        for (const game of Object.keys(names)) {
            const b=document.createElement('button');
            b.textContent=(restore(game)?'استئناف ':'')+names[game];
            b.onclick=()=>start(game); $('games').append(b);
        }
    }
    function start(game, partial) {
        s=partial ? null : restore(game);
        if (!s) {
            s={game,level:$('level').value,round:1,points:[0,0],seen:[],done:false};
            if(partial) Object.assign(s,partial);
            newRound();
            if(partial){s.message='انقطع الاتصال. حفظنا الجولة والنقاط وبدأنا سؤالاً محلياً.';save();}
        }
        $('menu').hidden=true; $('match').hidden=false; render();
    }
    function freshIndex() {
        const pool=OFFLINE_DECK[s.game];
        let ids=pool.map((_,i)=>i).filter(i=>!s.seen.includes(i));
        if(!ids.length){s.seen=[];ids=pool.map((_,i)=>i);}
        const i=pick(ids);s.seen.push(i);return i;
    }
    function newRound() {
        s.message='';s.step=0;s.used=[];s.strikes=[0,0];s.phase='play';
        if(s.game==='huroof') {
            const letters=new Map();
            for(const [i,q] of OFFLINE_DECK.huroof.entries()){
                const l=norm(q.a)[0]; if(!letters.has(l))letters.set(l,[]);
                letters.get(l).push(i);
            }
            const groups=[...letters.values()];s.cells=[];
            while(s.cells.length<25){const g=groups.splice(Math.floor(Math.random()*groups.length),1)[0];s.cells.push({q:pick(g),owner:''});}
            s.selected=Math.floor(Math.random()*25);
        } else s.index=freshIndex();
        save();
    }
    function path(owner) {
        const stack=[],seen=new Set();
        for(let i=0;i<25;i++)if(s.cells[i].owner===owner && (owner==='me'?i<5:i%5===0))stack.push(i);
        while(stack.length){
            const i=stack.pop();if(seen.has(i))continue;seen.add(i);
            const r=Math.floor(i/5),c=i%5;
            if(owner==='me'?r===4:c===4)return true;
            const d=r%2?1:-1;
            for(const [y,x] of [[r,c-1],[r,c+1],[r-1,c],[r+1,c],[r-1,c+d],[r+1,c+d]]){
                const j=y*5+x;if(y>=0&&y<5&&x>=0&&x<5&&s.cells[j].owner===owner)stack.push(j);
            }
        }return false;
    }
    function finish(who,points,message) {
        if(who!==null)s.points[who]+=points;
        s.message=message;
        s.done=s.game==='huroof'?Math.max(...s.points)>=2:s.round>=5&&s.points[0]!==s.points[1];
        s.phase=s.done?'done':'between';
    }
    function cellResult(owner){
        const cell=s.cells[s.selected];cell.owner=owner;
        if(path(owner))finish(owner==='me'?0:1,1,'اكتمل المسار!');
        else {s.selected=null;s.phase=owner==='me'?'choose':'botChoose';}
    }
    function respond(text){
        if(s.phase!=='play')return;
        const guess=norm(text);if(!guess)return;
        const bot=skill[s.level]; const q=OFFLINE_DECK[s.game][s.index];
        if(s.game==='huroof'){
            if(guess===norm(OFFLINE_DECK.huroof[s.cells[s.selected].q].a)){s.message='إجابة صحيحة';cellResult('me');}
            else if(Math.random()<bot){s.message='أجاب الكمبيوتر وأخذ الخلية';cellResult('bot');}
            else {s.message='لم يعرفها أي منكما. اختر خلية.';s.selected=null;s.phase='choose';}
        } else if(s.game==='knowledge'){
            const index=q.answers.findIndex(group=>group.some(a=>norm(a)===guess));
            if(index<0||s.used.includes(index)){s.strikes[0]++;s.message=index<0?'إجابة خاطئة':'إجابة مكررة';}
            else {s.used.push(index);s.message='إجابة صحيحة';}
            if(s.strikes[0]>=3)finish(1,1,'انتهت محاولاتك');
            else if(s.used.length>=q.answers.length)finish(null,0,'اكتملت القائمة');
            else s.phase='botTurn';
        } else if(q.answers.some(a=>norm(a)===guess)){
            finish(0,Math.max(1,Math.min(4,q.clues.length-s.step)),'إجابة صحيحة');
        } else {s.message='إجابة خاطئة';advanceClue();}
        save();render();
    }
    function advanceClue(){
        const q=OFFLINE_DECK[s.game][s.index];
        if(Math.random()<skill[s.level]*(s.step+1)/q.clues.length)finish(1,Math.max(1,Math.min(4,q.clues.length-s.step)),'عرفها الكمبيوتر: '+q.answers[0]);
        else if(s.step+1<q.clues.length)s.step++;
        else {const answer=q.answers[0];newRound();s.message='الإجابة كانت '+answer+'، نكمل بنفس الجولة';}
    }
    function render(){
        clearTimeout(timer);const q=OFFLINE_DECK[s.game][s.index];
        $('title').textContent=names[s.game];$('score').textContent='الجولة '+s.round+' · أنت '+s.points[0]+' — الكمبيوتر '+s.points[1];
        $('notice').textContent=s.message;$('board').replaceChildren();$('history').textContent='';
        $('answerForm').hidden=s.phase!=='play';$('next').hidden=true;
        if(s.game==='huroof'){
            for(let r=0;r<5;r++){const row=document.createElement('div');row.className='row';
                for(let c=0;c<5;c++){const i=r*5+c,cell=s.cells[i],b=document.createElement('button');b.className='cell '+cell.owner+(s.selected===i?' sel':'');b.textContent=OFFLINE_DECK.huroof[cell.q].a[0];b.disabled=s.phase!=='choose'||!!cell.owner;b.onclick=()=>{s.selected=i;s.phase='play';save();render();};row.append(b);}
                $('board').append(row);
            }
            $('prompt').textContent=s.selected!=null?OFFLINE_DECK.huroof[s.cells[s.selected].q].q:'صل الأخضر من الأعلى إلى الأسفل';
        } else if(s.game==='knowledge'){
            $('prompt').textContent=q.q;$('history').textContent=s.used.map(i=>q.answers[i][0]).join(' · ');
        } else {
            $('prompt').textContent=q.clues.slice(0,s.step+1).join(' · ');$('next').hidden=s.phase!=='play';$('next').textContent='التلميح التالي';
        }
        if(s.phase==='play'){
            const seconds = s.game==='huroof'?24:s.game==='knowledge'?12:8;
            timer=setTimeout(()=>{
                if(s.game==='knowledge'){
                    s.strikes[0]++;
                    if(s.strikes[0]>=3)finish(1,1,'انتهت محاولاتك');
                    else {s.message='انتهى وقت الإجابة';s.phase='botTurn';}
                }else if(s.game==='huroof'){
                    if(Math.random()<skill[s.level]) {s.message='أجاب الكمبيوتر وأخذ الخلية';cellResult('bot');}
                    else {s.message='انتهى الوقت. اختر خلية.';s.phase='choose';s.selected=null;}
                }else advanceClue();
                save();render();
            }, seconds*1000);
        }
        if(s.phase==='botChoose'||s.phase==='botTurn'){
            timer=setTimeout(()=>{
                if(s.phase==='botChoose'){s.selected=pick(s.cells.map((c,i)=>c.owner?null:i).filter(i=>i!==null));s.phase='play';}
                else {
                    const options=q.answers.map((_,i)=>i).filter(i=>!s.used.includes(i));
                    if(Math.random()<skill[s.level]){const i=pick(options);s.used.push(i);s.message='الكمبيوتر: '+q.answers[i][0];}
                    else{s.strikes[1]++;s.message='أخطأ الكمبيوتر';}
                    s.phase='play';
                    if(s.strikes[1]>=3)finish(0,1,'انتهت محاولات الكمبيوتر');
                    else if(s.used.length===q.answers.length)finish(null,0,'اكتملت القائمة');
                }save();render();
            },1200);
        }
        if(s.phase==='between'){$('next').hidden=false;$('next').textContent='الجولة التالية';}
        if(s.done)$('notice').textContent+=' · '+(s.points[0]>s.points[1]?'فزت بالمباراة':'فاز الكمبيوتر');
    }
    $('next').onclick=()=>{if(s.phase==='between'){s.round++;newRound();}else advanceClue();save();render();};
    $('answerForm').onsubmit=e=>{e.preventDefault();const text=$('answer').value;$('answer').value='';respond(text);};
    $('back').onclick=menu;
    menu();
    const game=params.get('game');
    if(Object.hasOwn(names,game)){
        let partial;
        if(params.has('transfer')){
            try{partial=JSON.parse(sessionStorage.getItem('pr.practice.transfer'));sessionStorage.removeItem('pr.practice.transfer');}catch{}
            if(partial?.game!==game)partial=null;
        }
        if(skill[params.get('difficulty')])$('level').value=params.get('difficulty');
        start(game,partial);
        history.replaceState(null,'','offline.html?game='+game);
    }
})();
