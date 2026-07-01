import json
import yaml
import socket
import argparse
from Task import Task

class Client:
    def __init__(self, host: str = '127.0.0.1', port: int = 8080):
        parser = argparse.ArgumentParser()
        parser.add_argument("config")
        args = parser.parse_args()
        self.filename = args.config
        self.host = host
        self.port = port
        self.socket: socket.socket

    def __del__(self):
        try:
            self.socket.close()
        except Exception:
            pass

    @staticmethod
    def get_socket(host: str, port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((host, port))
        except Exception as e:
            print(f"Failed to connect to server: {e}")
        return sock

    def launch(self):
        self.socket = Client.get_socket(self.host, self.port)
        tasks: dict = self.load_config()
        self.send_config(tasks)

    def load_config(self) -> dict:
        tasks: dict = {}
        with open(self.filename, 'r') as file:
            conf = yaml.safe_load(file)
            for key, value in conf['programs'].items():
                new_task = Task(**value)
                tasks[key] = new_task.model_dump(mode='json')
        return tasks

    def send_config(self, config: dict):
        payload: bytes = json.dumps(config).encode()
        self.socket.sendall(payload)

    def send_cmd(self, cmd: str, args: list[str]):
        payload: bytes = json.dumps({'cmd': cmd, 'args': args}).encode()
        self.socket.sendall(payload)
