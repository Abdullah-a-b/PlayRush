from fastapi import Request


def get_client_ip(request: Request) -> str:
    """جلب عنوان IP الحقيقي للمستخدم (يدعم reverse proxy عبر X-Forwarded-For)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def extract_bearer_token(request: Request) -> str | None:
    """استخراج توكن JWT من الهيدر Authorization أو من query string."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return request.query_params.get("token")
