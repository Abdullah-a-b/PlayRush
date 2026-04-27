import time
import random
import socketio
from locust import User, task, between, events

HOST = 'http://127.0.0.1:8000'  # ← غيّره إلى https://api.playrush.com للإنتاج

class PlayrushUser(User):
    wait_time = between(1, 3)

    def on_start(self):
        self.sio = socketio.Client(request_timeout=60)
        self.connected = False
        try:
            self.sio.connect(
                HOST,
                transports=['websocket'],
                wait_timeout=60,
            )
            self.connected = True
        except Exception as e:
            events.request.fire(
                request_type="Socket.io",
                name="connect",
                response_time=0,
                response_length=0,
                exception=e,
            )

    def on_stop(self):
        if self.connected and self.sio.connected:
            try:
                self.sio.disconnect()
            except Exception:
                pass

    @task
    def join_game(self):
        if not self.connected or not self.sio.connected:
            return

        start_time = time.time()
        try:
            self.sio.emit('huroof_player_ready', {
                'roomId': f'LOAD_ROOM_{random.randint(1, 50)}',
                'playerName': f'Bot_{id(self)}'
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