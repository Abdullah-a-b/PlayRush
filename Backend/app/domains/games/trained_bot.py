"""Private inference for experimental solo matches."""
import asyncio
import json
import logging
import os
import time

import httpx

_URL = os.getenv("PLAYRUSH_TRAINED_BOT_URL", (
    "http://127.0.0.1:18767" if os.getenv("WEBSITE_SITE_NAME", "").lower() == "playrush-server" else ""
))
_SYSTEM = (
    "أنت خصم PlayRush. اختر خطوة واحدة قانونية بناء على الحالة الظاهرة فقط. "
    "أخرج JSON فقط بالمفتاحين action وvalue. القيمة نص للإجابة أو رقم الخلية أو null "
    "للأوامر التي لا تحتاج قيمة. راعِ مستوى الخصم والوقت. لا تعِد الإجابات السابقة."
)
_SLOT = asyncio.Lock()
_retry_after = 0.0


def _decision(content, game, legal_actions):
    payload = json.loads(content or "null")
    if not isinstance(payload, dict) or payload.keys() != {"action", "value"}:
        return None
    action, value = payload["action"], payload["value"]
    if action not in legal_actions:
        return None
    if action == "select":
        return (action, value) if type(value) is int else None
    if action == "answer" or (action == "buzz" and game == "career"):
        return (action, value.strip()) if isinstance(value, str) and 0 < len(value.strip()) <= 120 else None
    return (action, None) if value is None else None


async def decide(game, level, stage, legal_actions, **visible):
    global _retry_after
    if not _URL or _SLOT.locked() or time.monotonic() < _retry_after:
        return None
    state = json.dumps({
        "game": game, "level": level, "stage": stage, "legal_actions": legal_actions, **visible,
    }, ensure_ascii=False)
    prompt = (
        f"<|im_start|>system\n{_SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\n{state}<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )
    try:
        async with _SLOT, asyncio.timeout(2.5), httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(_URL.rstrip("/") + "/completion", json={
                "prompt": prompt, "temperature": 0, "n_predict": 45, "cache_prompt": True,
                "stop": ["<|im_end|>", "<|endoftext|>"],
            })
            response.raise_for_status()
            result = _decision(response.json().get("content"), game, legal_actions)
    except (TimeoutError, httpx.HTTPError, ValueError, TypeError, AttributeError):
        _retry_after = time.monotonic() + 3
        return None
    if result:
        logging.getLogger("uvicorn.error").info("Trained solo bot: %s %s %s", game, stage, result[0])
    return result
