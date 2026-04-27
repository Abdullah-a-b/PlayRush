# loadtest.py
import gevent.monkey
gevent.monkey.patch_all()

from locust import HttpUser, task, between
import socketio
import random
import time

class PlayrushUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        self.sio = socketio.Client()
        self.sio = socketio.Client(request_timeout=60, logger=False, engineio_logger=False)
        self.sio.connect('http://127.0.0.1:8000', transports=['websocket'], wait_timeout=60)

    @task
    def find_match(self):
        self.sio.emit('find_match', {'gameMode': 'huroof'})
        time.sleep(random.uniform(2, 8))

    def on_stop(self):
        try: self.sio.disconnect()
        except: pass