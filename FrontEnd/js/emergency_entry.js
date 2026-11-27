/* مدخل الطوارئ يسبق التحقق الشبكي ويعرض ساحة الألعاب المعتادة. */
(() => {
    const params=new URLSearchParams(location.search);
    const entry=document.currentScript.hasAttribute('data-entry');
    const practice=params.get('practice')==='1';
    const enterPractice=()=>location.replace('categories.html?practice=1');
    if(!practice && (entry || document.currentScript.hasAttribute('data-auth')))window.watchNetworkLoss(enterPractice);
    if(document.currentScript.hasAttribute('data-auth')){
        if(!navigator.onLine)enterPractice();

        return;
    }
    if(entry && (!navigator.onLine || practice)){
        location.replace('categories.html?practice=1');return;
    }
    if(entry){
        if(window.Capacitor?.isNativePlatform?.() && !localStorage.getItem('token') && !sessionStorage.getItem('token')){
            document.addEventListener('DOMContentLoaded',async ()=>{
                const controller=new AbortController();
                const timeout=setTimeout(()=>controller.abort(),3200);
                try{
                    const res=await fetch(CONFIG.API_URL+'/health',{signal:controller.signal,cache:'no-store'});
                    if(!res.ok)throw new Error();
                }catch{if(!document.hidden && !navigator.onLine)enterPractice();}
                finally{clearTimeout(timeout);}
            },{once:true});
        }
        return;
    }
    if(!practice && !navigator.onLine){location.replace('categories.html?practice=1');return;}
    if(!practice){
        window.watchPracticeLobbySocket=socket=>window.watchNetworkLoss(enterPractice,socket);
        return;
    }
    window.PRPracticeLobby=true;
    document.addEventListener('DOMContentLoaded',()=>{
        document.documentElement.classList.remove('pr-app-resuming','pr-resume-recovery');
        const container=document.getElementById('mainLobbyContainer');
        container.inert=false;container.style.visibility='visible';
        document.getElementById('appResume').hidden=true;
        const headings=container.querySelectorAll('h1');
        for(const heading of headings)heading.textContent='ساحة التدريب دون اتصال';
        const presence=document.querySelector('#globalPlayersList p');
        if(presence)presence.textContent='تظهر قائمة اللاعبين عند عودة الاتصال.';
        const avatar=document.querySelector('.player-profile img, #playerAvatar');
        if(avatar && !avatar.getAttribute('src'))avatar.src='assets/avatars/avatar_1.svg';
        const name=document.getElementById('playerName');
        if(name)name.textContent=sessionStorage.getItem('playerName')||'لاعب';
        for(const card of document.querySelectorAll('.game-card')){
            const button=card.querySelector('[data-solo]');
            card.addEventListener('click',e=>{
                e.preventDefault();e.stopImmediatePropagation();
                if(button)window.openSoloLevelPicker(button.dataset.solo);
                else window.showToast?.('هذه اللعبة تحتاج اتصالاً بالإنترنت');
            },true);
        }
        async function reconnect(){
            try {
                const response=await fetch(CONFIG.API_URL+'/health',{cache:'no-store',signal:AbortSignal.timeout(4000)});
                if(response.ok)location.replace('index.html');
            }catch{}
        }
        for(const event of ['online','pr-native-online','pr-native-resume'])window.addEventListener(event,reconnect);
        document.addEventListener('visibilitychange',()=>{if(!document.hidden && navigator.onLine)reconnect();});

    });
})();
