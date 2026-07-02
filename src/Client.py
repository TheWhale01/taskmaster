import os
import json
import time
import shlex
import socket
import atexit
import readline

class Client:
    def __init__(self, host: str = '127.0.0.1', port: int = 8080):
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
            print("Retrying connection in 3 secondes...")
            time.sleep(3)
            return None
        return sock

    def launch(self):
        self.socket = None
        while not self.socket:
            self.socket = self.get_socket(self.host, self.port)
        self.set_history()
        self.taskmaster_shell()

    def set_history(self):
        HISTORY_FILE = os.path.expanduser("~/.taskmaster_history")
        try:
            readline.read_history_file(HISTORY_FILE)
        except FileNotFoundError:
            pass
        atexit.register(readline.write_history_file, HISTORY_FILE)

    def send_cmd(self, cmd: str, args: list[str]):
        payload: bytes = json.dumps({'cmd': cmd, 'args': args}).encode()
        payload += b'\n'
        self.socket.sendall(payload)

    def taskmaster_shell(self):
        RED = "\033[31;20m"
        BLUE = "\033[36m"
        GREEN = "\033[32;20m"
        RESET = "\033[0m"
        COLOR = GREEN
        ARGS_MAX = {
            "help": 0, "quit": 0, "exit": 0, "shutdown": 0,
            "status": 1, "start": 1, "stop": 1, "restart": 1, "reload": 1
        }
        while True:
            try:
                shell_input = input(f"{COLOR}->{BLUE} taskmaster{RESET} ")
            except EOFError: #ctrl+D
                COLOR = RED
                print()
                break
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
            if cmd not in ARGS_MAX:
                COLOR = RED
                print(f"taskmaster: command not found: {cmd}")
                print("Try 'help' to see the list of commands.")
                continue
            if len(args) > ARGS_MAX[cmd]:
                COLOR = RED
                print(f"{cmd}: too many arguments: {args}")
                continue
            COLOR = GREEN
            if cmd == "help":
                print("help")
            elif cmd in ("quit", "exit"):
                break
            else:
                self.send_cmd(cmd, args)
