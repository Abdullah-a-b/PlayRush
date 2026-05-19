import time
import random
import socketio
from locust import User, task, between, events

HOST = 'http://127.0.0.1:8000'  # ← غيّره إلى https://api.playrush.com للإنتاج

# ✅ إصلاح المشكلة 1: الـ bots الآن تمر بـ join_global_lobby أو join_game_lobby
# حتى تُحسب صح في Redis وما تبقى كـ ghost connections
class PlayrushUser(User):
    wait_time = between(1, 3)

    def on_start(self):
        self.bot_name = f'LoadBot_{id(self)}_{random.randint(1000,9999)}'
        self.location = random.choice(['global', 'huroof'])
        self.sio = socketio.Client(request_timeout=60)
        self.connected = False

        # Track update_online_count events for debugging
        @self.sio.on('update_online_count')
        def on_count(data):
            pass  # يمكن طباعته لو أردت التتبع

        try:
            self.sio.connect(
                HOST,
                transports=['websocket'],
                wait_timeout=60,
            )
            self.connected = True

            # ✅ المهم: نبعث join event حتى يُضاف السيرفر للـ Redis
            # بدون هذا الـ bot يكون "متصل" لكن مو محسوب في العداد
            if self.location == 'global':
                self.sio.emit('join_global_lobby', {'name': self.bot_name})
            else:
                self.sio.emit('join_game_lobby', {
                    'name': self.bot_name,
                    'gameMode': 'huroof'
                })

        except Exception as e:
            events.request.fire(
                request_type="Socket.io",
                name="connect",
                response_time=0,
                response_length=0,
                exception=e,
            )

    def on_stop(self):
        # ✅ disconnect نظيف — السيرفر يستقبل disconnect event ويمسح اللاعب من Redis
        if self.connected and self.sio.connected:
            try:
                self.sio.disconnect()
            except Exception:
                pass

    @task(3)
    def stay_connected(self):
        """✅ معظم الوقت اللاعب فقط متصل (يحاكي الواقع)"""
        if not self.connected or not self.sio.connected:
            return
        time.sleep(random.uniform(0.5, 1.5))

    @task(1)
    def join_game(self):
        """✅ بعض الـ bots يجربون غرف اللعب"""
        if not self.connected or not self.sio.connected:
            return

        start_time = time.time()
        try:
            self.sio.emit('huroof_player_ready', {
                'roomId': f'LOAD_ROOM_{random.randint(1, 50)}',
                'playerName': self.bot_name
            })
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="Socket.io",
                name="huroof_player_ready",
                response_time=total_time,
                response_length=0,
                exception=None
            )
        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="Socket.io",
                name="huroof_player_ready",
                response_time=total_time,
                response_length=0,
                exception=e
            )
