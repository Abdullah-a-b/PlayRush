from slowapi import Limiter
from slowapi.util import get_remote_address

# إنشاء الحارس الذي يعتمد على IP المستخدم
limiter = Limiter(key_func=get_remote_address)