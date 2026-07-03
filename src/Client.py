import os
import sys
import json
import time
import shlex
import socket
import atexit
import readline
from typing import Optional

class Client:
    def __init__(self, host: str = '127.0.0.1', port: int = 8080):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket]

    @staticmethod
    def get_socket(host: str, port: int) -> Optional[socket.socket]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((host, port))
        except Exception as e:
            print(f"Failed to connect to server: {e}")
            print("Retrying connection in 3 seconds...")
            time.sleep(3)
            return None
        return sock

    def close_client(self, message: Optional[str] = None):
        if message:
            print(message)
        try:
            if self.socket is not None:
                self.socket.close()
        except Exception:
            pass
        print("The client was successfully disconnected.")
        sys.exit(0)

    def launch(self):
        self.connect()
        self.set_history()
        self.taskmaster_shell()

    def connect(self):
        try:
            self.socket = None
            while not self.socket:
              self.socket = self.get_socket(self.host, self.port)
        except KeyboardInterrupt:
            self.close_client("\nKeyboard Interrupt while trying to connect.")
        print(f"The client is now connected to the server. host: {self.host} port: {self.port}")

    def set_history(self):
        HISTORY_FILE = os.path.expanduser("~/.taskmaster_history")
        try:
            readline.read_history_file(HISTORY_FILE)
        except FileNotFoundError:
            pass
        atexit.register(readline.write_history_file, HISTORY_FILE)

    def send_cmd(self, cmd: str, args: list[str]):
        if self.socket is None:
            print("Client is not connected to server.")
            return
        payload: bytes = json.dumps({'cmd': cmd, 'args': args}).encode()
        try:
            self.socket.sendall(payload + b'\n')
        except (BrokenPipeError, ConnectionResetError) as e:
            print(f"Connection to server lost: {e}")
            self.connect()
        response = self.socket.recv(2084)
        if not response: 
            print("Server is unreachable.")
            self.connect()
        else:
            print(response.decode())

    def taskmaster_shell(self):
        RED = "\033[31;20m"
        BLUE = "\033[36m"
        GREEN = "\033[32;20m"
        RESET = "\033[0m"
        COLOR = GREEN
        COMMANDS = {
            "help": 1, "quit": 1, "exit": 1, "shutdown": 1,
            "status": 0, "start": 0, "stop": 0, "restart": 0, "reload": 0
        }
        while True:
            try:
                shell_input = input(f"{COLOR}->{BLUE} taskmaster{RESET} ")
            except EOFError: #ctrl+D
                COLOR = RED
                print()
                self.close_client()
            except KeyboardInterrupt: #ctrl+C
                print()
                continue
            try:
                ligne = shlex.split(shell_input)
            except ValueError as e:
                COLOR = RED
                print(f"syntax error: {e}")
                continue
            if not ligne:
                continue
            cmd = ligne[0]
            args = ligne[1:]
            if cmd not in COMMANDS:
                COLOR = RED
                print(f"taskmaster: command not found: {cmd}")
                print("Try 'help' to see the list of commands.")
                continue
            if args and COMMANDS[cmd]:
                COLOR = RED
                print(f"{cmd}: too many arguments: {args}")
                continue
            COLOR = GREEN
            if cmd == "help":
                self.cmd_help()
            elif cmd in ("quit", "exit"):
                self.close_client()
            else:
                self.send_cmd(cmd, args)
