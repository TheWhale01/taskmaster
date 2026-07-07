import os
import sys
import json
import time
import shlex
import socket
import atexit
import readline
from Logger import Logger
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
        if self.socket is not None:
            self.socket.close()
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

    def cmd_help(self):
        print("Taskmaster client: list of commands:\n")
        print(f"{'Command':20}{'Argument':25}{'Description'}")
        print(f"{'status':20}{'[task_name, ...]':25}{'Display the status of all task or those in the argument.'}")
        print(f"{'start':20}{'[task_name, ...]':25}{'Start all task or those in the argument.'}")
        print(f"{'stop':20}{'[task_name, ...]':25}{'Stop all task or those in the argument.'}")
        print(f"{'restart':20}{'[task_name, ...]':25}{'Restart all task or those in the argument.'}")
        print(f"{'reload':20}{'':25}{'Reload the configuration file and apply the changes.'}")
        print(f"{'shutdown':20}{'':25}{'Shutdown the server.'}")
        print(f"{'quit | exit':20}{'':25}{'Disconnect the client.'}")

    def taskmaster_shell(self):
        COLOR = Logger.GREEN
        COMMANDS = {
            "help": 1, "quit": 1, "exit": 1, "shutdown": 1, "reload": 0,
            "status": 0, "start": 0, "stop": 0, "restart": 0
        }
        while True:
            try:
                shell_input = input(f"{COLOR}->{Logger.BLUE} taskmaster{Logger.RESET} ")
            except EOFError: #ctrl+D
                COLOR = Logger.RED
                print()
                self.close_client()
            except KeyboardInterrupt: #ctrl+C
                print()
                continue
            try:
                ligne = shlex.split(shell_input)
            except ValueError as e:
                COLOR = Logger.RED
                print(f"syntax error: {e}")
                continue
            if not ligne:
                continue
            cmd = ligne[0]
            args = ligne[1:]
            if cmd not in COMMANDS:
                COLOR = Logger.RED
                print(f"taskmaster: command not found: {cmd}")
                print("Try 'help' to see the list of commands.")
                continue
            if args and COMMANDS[cmd]:
                COLOR = Logger.RED
                print(f"{cmd}: too many arguments: {args}")
                continue
            COLOR = Logger.GREEN
            if cmd == "help":
                self.cmd_help()
            elif cmd in ("quit", "exit"):
                self.close_client()
            else:
                self.send_cmd(cmd, args)
