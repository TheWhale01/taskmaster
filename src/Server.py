import os
import time
import json
import shlex
import string
import socket
import logging
from Task import Task
from typing import Any
from pathlib import Path
from Logger import Logger
from subprocess import Popen
from logging.handlers import RotatingFileHandler

class Server:
    def __init__(self, host: str = '127.0.0.1', port: int = 8080):
        self.host = host
        self.port = port
        self.logger = logging.Logger("TaskmasterServer")
        self.setup_logger(logging.DEBUG)
        self.tasks: dict[str, Task] = {}
        self.active_processes: dict[str, list[Popen]] = {}

    def setup_logger(self, log_level: int):
        self.logger.setLevel(log_level)
        logs_path: Path = Path("logs/")
        logs_path.mkdir(parents=True, exist_ok=True)
        logs_path = logs_path / "server.log"
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(Logger())
        file_handler = RotatingFileHandler(
            # Creates files of 5MB max
            logs_path, maxBytes=5*1024*1024
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(Logger())
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)

    def get_cmd(self, task: Task, env: dict) -> list[str]:
        cmd: str = string.Template(task.cmd).safe_substitute(env)
        return shlex.split(cmd)

    def get_logfiles(self, task: Task) -> tuple:
        mode: str = 'a'
        return (open(task.stdout, mode), open(task.stderr, mode))

    def get_env(self, task: Task) -> dict[str, str]:
        env: dict[str, str] = os.environ.copy()
        env.update(task.env)
        return env

    def create_process(self, task: Task, env: dict[str, str], logfiles: tuple) -> Popen:
        proc = Popen(
            self.get_cmd(task, env),
            cwd=task.workingdir,
            env=env,
            stdout=logfiles[0],
            stderr=logfiles[1],
            # Setting the umask inside the child process
            preexec_fn=lambda: os.umask(task.umask)
        )
        return proc

    def spawn_task(self, name: str, task: Task, nb_procs: int = -1):
        self.active_processes[name] = []
        time.sleep(task.starttime)
        if nb_procs == -1:
            nb_procs = task.numprocs
        for i in range(task.startretries, 0, -1):
            try:
                env: dict[str, str] = self.get_env(task)
                logfiles: tuple = self.get_logfiles(task)
                for i in range(nb_procs):
                    proc: Popen = self.create_process(task, env, logfiles)
                    self.active_processes[name].append(proc)
                self.logger.info(f"Successfully spawned task {name}")
                break
            except Exception as e:
                self.logger.error(f"Failed to spawn process {name}. {e}. Retrying")

    def despawn_task(self, name: str, task: Task, nb_procs: int = -1):
        time.sleep(task.stoptime)
        if nb_procs == -1:
            nb_procs = task.numprocs

    def update_numprocs(self, name: str, task: Task):
        nb_processes: int = len(self.active_processes[name])
        if nb_processes > task.numprocs:
            self.spawn_task(name, task, (nb_processes - task.numprocs))
        elif nb_processes < task.numprocs:
            self.despawn_task(name, task, (task.numprocs - nb_processes))

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
            self.update_numprocs(name, self.tasks[name])
        else:
            self.despawn_task(name, self.tasks[name])
            self.spawn_task(name, self.tasks[name])

    def process_new_config(self, new_tasks: dict[str, Task]):
        self.logger.info("Processing configuration.")
        if new_tasks == self.tasks:
            return
        added = new_tasks.keys() - self.tasks.keys()
        removed = self.tasks.keys() - new_tasks.keys()
        updated = new_tasks.keys() & self.tasks.keys()
        for name in added:
            self.tasks[name] = new_tasks[name]
            if self.tasks[name].autostart:
                self.spawn_task(name, new_tasks[name])
        for name in removed:
            self.despawn_task(name, self.tasks[name])
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
            self.logger.info(f"Server successfully started on {self.host}:{self.port}")
            while True:
                conn, addr = sock.accept()
                with conn:
                    self.logger.info(f"Connection received from {addr[0]}")
                    payload: bytes = b''
                    while True:
                        chunk = conn.recv(2048)
                        if not chunk:
                            break
                        payload += chunk
                    new_tasks: dict[str, Task] = {}
                    for key, value in json.loads(payload.decode()).items():
                        new_tasks[key] = Task(**value)
                    self.process_new_config(new_tasks)
