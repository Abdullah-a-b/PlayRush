// ============================================================
//  presence.js — نظام الحضور بالفروقات (Delta Presence)
// ============================================================
// المشكلة القديمة: الخادم كان يبث قائمة المتصلين *كاملة للجميع* عند
// كل انضمام/خروج — عند 5000 متصل: حدث واحد = 5000 رسالة × 5000 سجل.
// الحل: snapshot كامل مرة واحدة عند الانضمام، ثم فروق صغيرة فقط:
//   online_players_snapshot : القائمة الكاملة (تصل للمنضم فقط)
//   online_player_delta     : { op: 'join'|'update'|'leave', pid, player }
// هذه الوحدة تحتفظ بخريطة محلية وتعيد بناء المصفوفة وتمررها لنفس
// دالة العرض القديمة — لا حاجة لتغيير منطق الرسم في الصفحات.
//
// الاستخدام:  initPresence(socket, (players) => { ...نفس الكود القديم... });
// ============================================================

const __presenceMap = new Map();   // pid → player
let __presenceRenderFn = null;
let __presenceTimer = null;

// ⏱ دمج الفروق المتتالية برسمة واحدة كل 400ms كحد أقصى —
// يحمي المتصفح من إعادة بناء DOM آلاف المرات وقت الذروة.
const PRESENCE_RENDER_THROTTLE_MS = 400;

function presencePlayers() {
    return Array.from(__presenceMap.values());
}

function __schedulePresenceRender() {
    if (__presenceTimer) return; // رسمة مجدولة بالفعل — الفروق الجديدة ستُشمل فيها
    __presenceTimer = setTimeout(() => {
        __presenceTimer = null;
        if (__presenceRenderFn) {
            try { __presenceRenderFn(presencePlayers()); }
            catch (e) { console.error('presence render error:', e); }
        }
    }, PRESENCE_RENDER_THROTTLE_MS);
}

function initPresence(sock, renderFn) {
    __presenceRenderFn = renderFn;

    // القائمة الكاملة — تصل مرة واحدة عند الانضمام/إعادة الاتصال
    sock.on('online_players_snapshot', (data) => {
        // الصيغتان: قائمة مباشرة، أو {players, total} عند الأعداد الكبيرة
        const list = Array.isArray(data) ? data : (data && data.players) || [];
        window.__presenceTotal = Array.isArray(data) ? null : (data && data.total) || null;
        __presenceMap.clear();
        list.forEach(p => { if (p && p.pid) __presenceMap.set(p.pid, p); });
        __schedulePresenceRender();
    });

    // فرق صغير — لاعب واحد تغيّر
    sock.on('online_player_delta', (d) => {
        if (!d || !d.op) return;
        if (d.op === 'leave') {
            __presenceMap.delete(d.pid);
        } else if (d.player && d.player.pid) {
            // 🔁 منع التكرار: انسحبتَ وعدت للوبي باتصال جديد بينما سجلّك
            // القديم (داخل اللعبة) حي حتى انتهاء مهلته → نحذف أي مدخل
            // بنفس الاسم وpid مختلف (الأحدث يفوز)
            const nm = d.player.name;
            if (nm) {
                for (const [pid, pl] of __presenceMap) {
                    if (pl && pl.name === nm && pid !== d.player.pid) {
                        __presenceMap.delete(pid);
                    }
                }
            }
            __presenceMap.set(d.player.pid, d.player);
        }
        __schedulePresenceRender();
    });

    //  توافق خلفي: لو العميل الجديد قابل خادماً قديماً يبث القائمة الكاملة
    sock.on('update_online_players', (list) => {
        __presenceMap.clear();
        (list || []).forEach((p, i) => {
            if (p) __presenceMap.set(p.pid || ('legacy_' + i), p);
        });
        __schedulePresenceRender();
    });
}
