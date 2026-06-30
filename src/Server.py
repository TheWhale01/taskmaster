import json
import socket
from typing import Any
from Task import Task

class Server:
    def __init__(self, host: str = '127.0.0.1', port: int = 8080):
        self.host = host
        self.port = port
        self.tasks: dict[str, Task] = {}

    def spawn_task(self, task: dict[str, Task]):
        pass

    def despawn_task(self, name: str):
        pass

    def change_numprocs(self, name):
        pass

    def apply_update(self, name: str, key: str, value: Any):
        print("Applying update")
        setattr(self.tasks[name], key, value)
        non_rebooting_fields: list[str] = [
            'autostart',
            'autorestart',
            'exitcodes',
            'startretries',
            'starttime',
            'stopsignal',
            'stoptime'
        ]
        if key in non_rebooting_fields:
            return
        if key == 'numprocs':
            self.change_numprocs(name)
        else:
            self.despawn_task(name)
            self.spawn_task({name: self.tasks[name]})

    def process_new_config(self, new_tasks: dict[str, Task]):
        if new_tasks == self.tasks:
            return
        added = new_tasks.keys() - self.tasks.keys()
        removed = self.tasks.keys() - new_tasks.keys()
        updated = new_tasks.keys() & self.tasks.keys()
        for name in added:
            self.spawn_task({name: new_tasks[name]})
        for name in removed:
            self.despawn_task(name)
        for name in updated:
            if self.tasks[name] == new_tasks[name]:
                continue
            old_field = self.tasks[name].model_dump()
            new_field = new_tasks[name].model_dump()
            for field in old_field:
                if old_field[field] != new_field[field]:
                    self.apply_update(name, field, new_field[field])

    def launch(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen()
            while True:
                conn, addr = sock.accept()
                with conn:
                    print(f"Connection receved from {addr}.")
                    payload: bytes = b''
                    while True:
                        chunk = conn.recv(2048)
                        if not chunk:
                            break
                        payload += chunk
                    new_tasks: dict[str, Task] = {}
                    for key, value in json.loads(payload.decode()).items():
                        new_tasks[key] = Task(**value)
                    print(f"DEBUG: {new_tasks}")
                    self.process_new_config(new_tasks)
