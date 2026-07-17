from fastapi import APIRouter, Depends, Form, BackgroundTasks, UploadFile, File, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.http_utils import get_client_ip
from app.core.limiter import limiter
from app.infrastructure.database import get_db
from app.domains.users.models import User
from app.domains.users.repository import UserRepository
from app.domains.users import service

router = APIRouter()


def get_user_repo(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


async def _token_from_request(request: Request) -> str | None:
    """يلتقط التوكن من query أو Authorization أو FormData بهذا الترتيب."""
    token = request.query_params.get("token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
    if not token:
        try:
            form = await request.form()
            token = form.get("token")
        except Exception:
            pass
    return token


@router.post("/register")
@limiter.limit("5/hour")  # يمنع إنشاء عشرات الحسابات من نفس IP
async def register(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    password: str = Form(...),
    repo: UserRepository = Depends(get_user_repo),
):
    return await service.register_user(repo, background_tasks, email, password)


@router.post("/verify-code")
@limiter.limit("10/minute")  # يمنع brute force على OTP
async def verify_code(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    code: str = Form(...),
    flow: str = Form("register"),
    repo: UserRepository = Depends(get_user_repo),
):
    return service.verify_account_code(repo, background_tasks, email, code, flow)


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    background_tasks: BackgroundTasks,
    form_data: OAuth2PasswordRequestForm = Depends(),
    repo: UserRepository = Depends(get_user_repo),
):
    result = await service.login_user(
        repo, background_tasks,
        username=form_data.username,
        password=form_data.password,
        client_ip=get_client_ip(request),
    )
    if result.get("action") == "redirect_to_verify":
        return JSONResponse(status_code=403, content=result)
    return result


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    repo: UserRepository = Depends(get_user_repo),
):
    return service.request_password_reset(repo, background_tasks, email)


@router.post("/reset-password")
@limiter.limit("5/minute")  # يمنع brute force على إعادة التعيين
async def reset_password(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    code: str = Form(...),
    new_password: str = Form(...),
    repo: UserRepository = Depends(get_user_repo),
):
    return await service.reset_password(repo, background_tasks, email, code, new_password)


@router.get("/google/login")
@limiter.limit("10/minute")  # يمنع redirect spam
async def google_login(request: Request):
    return RedirectResponse(url=service.build_google_auth_url())


@router.get("/google/callback")
@limiter.limit("10/minute")
async def google_callback(
    request: Request,
    code: str,
    background_tasks: BackgroundTasks,
    repo: UserRepository = Depends(get_user_repo),
):
    target_url = await service.handle_google_callback(repo, background_tasks, code)
    return RedirectResponse(url=target_url)


@router.post("/logout")
async def logout(token: str = Form(...)):
    return {"message": "تم تسجيل الخروج بنجاح وتأمين الحساب"}


@router.post("/setup-profile")
@limiter.limit("10/hour")  # يمنع spam لرفع الصور وتغيير الاسم
async def setup_profile(
    request: Request,
    player_name: str = Form(...),
    country: str = Form(...),
    avatar_url: str = Form(None),
    avatar_file: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    repo: UserRepository = Depends(get_user_repo),
):
    has_avatar_file = bool(avatar_file and avatar_file.filename)
    return service.setup_profile(
        repo, current_user, player_name, country, avatar_url, has_avatar_file
    )


@router.get("/me")
@limiter.limit("60/minute")  # يمنع profile scraping
async def get_my_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resp = service.build_profile_response(current_user)
    # 📆 تتابع الدخول اليومي (5→50🪙) — يُمنح مرة يومياً عند فتح المنصة
    try:
        from app.domains.wallet.reward_service import claim_login_streak
        streak_reward = claim_login_streak(db, current_user)
        if streak_reward:
            if isinstance(resp, dict):
                resp["login_streak_reward"] = streak_reward
    except Exception as _e:
        print(f"⚠️ [login-streak] {_e}")
    return resp


@router.post("/settings/request-otp")
@limiter.limit("3/minute")  # يمنع spam emails
async def request_settings_otp(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str = Form(...),
    repo: UserRepository = Depends(get_user_repo),
):
    return service.request_settings_otp(repo, background_tasks, token)


@router.post("/settings/update-security")
@limiter.limit("5/minute")  # يمنع brute force على OTP
async def update_security(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str = Form(...),
    otp: str = Form(...),
    action: str = Form(...),
    new_value: str = Form(...),
    repo: UserRepository = Depends(get_user_repo),
):
    return await service.update_security(repo, background_tasks, token, otp, action, new_value)


@router.delete("/delete-account")
@limiter.limit("3/hour")
async def delete_account(
    request: Request,
    current_user: User = Depends(get_current_user),
    repo: UserRepository = Depends(get_user_repo),
):
    return service.delete_account(repo, current_user)


@router.delete("/cancel-registration")
@limiter.limit("5/hour")
async def cancel_registration(
    request: Request,
    current_user: User = Depends(get_current_user),
    repo: UserRepository = Depends(get_user_repo),
):
    return service.cancel_registration(repo, current_user)


@router.post("/resend-otp")
@limiter.limit("3/minute")  # يمنع spam emails
async def resend_otp(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    repo: UserRepository = Depends(get_user_repo),
):
    return service.resend_otp(repo, background_tasks, email)


@router.post("/self-ban", tags=["Anti-Cheat"])
@limiter.limit("5/minute")
async def self_ban(
    request: Request,
    repo: UserRepository = Depends(get_user_repo),
):
    """يحظر اللاعب الذي تجاوز محاولات فتح أدوات المطور.

    يُستدعى من الواجهة (anti_cheat.js) عند بلوغ الحد الأقصى للمحاولات.
    """
    token = await _token_from_request(request)
    return service.self_ban(repo, token)


@router.post("/anticheat-report", tags=["Anti-Cheat"])
@limiter.limit("20/minute")  # حد عالٍ للسماح بالتقارير المتعددة
async def anticheat_report(
    request: Request,
    repo: UserRepository = Depends(get_user_repo),
):
    """يستقبل تقارير anti-cheat (مستوى التحذير) من الواجهة."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    try:
        form = await request.form()
        if not token:
            token = form.get("token")
        reason = form.get("reason", "unknown")
    except Exception:
        return {"received": False}

    return service.record_anticheat_report(repo, token, reason, get_client_ip(request))


@router.get("/ban-status", tags=["Anti-Cheat"])
@limiter.limit("60/minute")
async def ban_status(
    request: Request,
    repo: UserRepository = Depends(get_user_repo),
):
    """يفحص حالة الحظر الحالية — الواجهة تستدعيه عند تحميل أي صفحة."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    elif request.query_params.get("token"):
        token = request.query_params.get("token")

    return service.check_ban_status(repo, token)

NAME_CHANGE_COST_GEMS = 25
_NAME_COLS_READY = False


@router.post("/settings/change-name")
@limiter.limit("5/minute")
async def change_player_name(
    request: Request,
    new_name: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """✏️ تغيير اسم اللاعب: أول مرة مجاناً ثم 25💎 (حسب الوثيقة)."""
    global _NAME_COLS_READY
    from sqlalchemy import text as _text
    new_name = (new_name or "").strip()
    if not (2 <= len(new_name) <= 20):
        return {"ok": False, "error": "الاسم يجب أن يكون بين 2 و20 حرفاً"}
    if not _NAME_COLS_READY:
        try:
            db.execute(_text("ALTER TABLE users ADD COLUMN IF NOT EXISTS name_changes INTEGER DEFAULT 0"))
            db.commit()
        except Exception:
            db.rollback()
        _NAME_COLS_READY = True
    row = db.execute(_text(
        "SELECT COALESCE(name_changes,0), COALESCE(gems,0) FROM users WHERE id=:uid"),
        {"uid": current_user.id}).fetchone()
    changes, gems = row[0], row[1]
    cost = 0 if changes == 0 else NAME_CHANGE_COST_GEMS
    if cost and gems < cost:
        return {"ok": False, "error": f"تحتاج {cost}💎 لتغيير الاسم (رصيدك {gems}💎)"}
    db.execute(_text(
        "UPDATE users SET player_name=:n, name_changes=COALESCE(name_changes,0)+1, "
        "gems=COALESCE(gems,0)-:c WHERE id=:uid"),
        {"n": new_name, "c": cost, "uid": current_user.id})
    db.commit()
    return {"ok": True, "new_name": new_name, "cost": cost,
            "next_cost": NAME_CHANGE_COST_GEMS,
            "msg": ("✅ تغيّر اسمك مجاناً (أول مرة)" if cost == 0
                    else f"✅ تغيّر اسمك (−{cost}💎)")}

