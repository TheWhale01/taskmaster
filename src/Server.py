import os
import sys
import time
import yaml
import json
import shlex
import string
import select
import socket
import signal
import logging
import argparse
import subprocess
from Task import Task
from typing import Any
from pathlib import Path
from Logger import Logger
from typing import Optional
from subprocess import Popen
from logging.handlers import RotatingFileHandler

class Server:
    def __init__(self, host: str = '127.0.0.1', port: int = 8080):
        signal.signal(signal.SIGHUP, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        parser = argparse.ArgumentParser()
        parser.add_argument("config")
        args = parser.parse_args()
        self.filename = args.config
        self.host = host
        self.port = port
        self.logger = logging.Logger("TaskmasterServer")
        self.setup_logger(logging.DEBUG)
        self.tasks: dict[str, Task] = {}
        self.socket: Optional[socket.socket] = self.get_socket()
        self.active_processes: dict[str, list[Popen]] = {}
        self.pending_spawns: list = []
        self.reload_file()
        self.commands = {
            "status":   self.cmd_status,
            "start":    self.cmd_start,
            "stop":     self.cmd_stop,
            "restart":  self.cmd_restart,
            "reload":   self.cmd_reload,
            "shutdown": self.cmd_shutdown,
        }

    def get_socket(self) -> Optional[socket.socket]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.setblocking(False)
        except Exception as e:
            self.logger.error(f"Failed to establish connection to client. {e}")
            return None
        return sock

    def shutdown_server(self):
        try:
            if self.socket is not None:
                self.socket.close()
        except Exception:
            pass
        self.stop_all_task()
        self.logger.info("The server has been successfully shutdown.")
        sys.exit(0)

    def signal_handler(self, sig, context):
        if sig == signal.SIGHUP:
            self.reload_file()
        elif sig in (signal.SIGINT, signal.SIGTERM):
            self.shutdown_server()

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

    def create_process(self, name: str, task: Task):
        env: dict[str, str] = self.get_env(task)
        logfiles: tuple = self.get_logfiles(task)
        proc = Popen(
            self.get_cmd(task, env),
            cwd=task.workingdir,
            env=env,
            stdout=logfiles[0],
            stderr=logfiles[1],
            # Setting the umask inside the child process
            preexec_fn=lambda: os.umask(task.umask)
        )
        self.active_processes[name].append(proc)

    def schedule_spawn(self, name: str, task: Task):
        target_time = time.time() + task.starttime
        self.pending_spawns.append({
            'launch_time': target_time,
            'name': name,
            'task': task
        })
        if task.starttime != 0:
            self.logger.info(f"Scheduled task {name} to start in {task.starttime} seconds.")

    def spawn_task(self, name: str, task: Task, nb_procs: int = -1, flush_processes: bool = True):
        if flush_processes or name not in self.active_processes:
            self.active_processes[name] = []
        if nb_procs == -1:
            nb_procs = task.numprocs
        for _ in range(nb_procs):
            try:
                self.create_process(name, task)
            except Exception as e:
                if task.retry_count < task.startretries:
                    self.schedule_spawn(name, task)
                    self.logger.warning(f"Failed to spawn process {name}. {e}. Retrying")
                    task.retry_count += 1
                else:
                    self.logger.error(f"Failed to spawn process {name}. {e}")
        self.logger.info(f"Successfully spawned task {name}")

    def stop_all_task(self):
        for name in self.tasks.keys():
            self.despawn_task(name, self.tasks[name])

    def get_signal(self, sig_name: str):
        full_name = "SIG" + sig_name
        try:
            return getattr(signal, full_name)
        except AttributeError:
            self.logger.error(f"Signal inconnu : '{sig_name}'. SIGTERM used by default.")
            return signal.SIGTERM

    def despawn_task(self, name: str, task: Task, nb_procs: int = -1):
        if name not in self.active_processes.keys():
            return
        procs = self.active_processes[name]
        if nb_procs == -1:
            nb_procs = task.numprocs
        for _ in range(nb_procs):
            if not procs:
                break
            proc = procs.pop()
            proc.send_signal(self.get_signal(task.stopsignal))
            try:
                proc.wait(timeout=task.stoptime)
            except (subprocess.TimeoutExpired):
                proc.kill()
                proc.wait()
        del self.active_processes[name]
        self.logger.info(f"Despawned {nb_procs} process(es) of {name}")

    def update_numprocs(self, name: str, task: Task):
        nb_processes: int = len(self.active_processes[name])
        if nb_processes > task.numprocs:
            self.spawn_task(name, task, (nb_processes - task.numprocs), flush_processes=False)
        elif nb_processes < task.numprocs:
            self.despawn_task(name, task, (task.numprocs - nb_processes))

    def apply_update(self, name: str, key: str, value: Any):
        self.logger.info("Update signal received")
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
        self.logger.info("Processing configuration...")
        if new_tasks == self.tasks:
            return
        added = new_tasks.keys() - self.tasks.keys()
        removed = self.tasks.keys() - new_tasks.keys()
        updated = new_tasks.keys() & self.tasks.keys()
        for name in added:
            self.tasks[name] = new_tasks[name]
            if self.tasks[name].autostart:
                self.schedule_spawn(name, new_tasks[name])
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

    def reload_file(self):
        with open(self.filename, 'r') as file:
            conf = yaml.safe_load(file)
            new_tasks: dict[str, Task] = {}
            for key, value in conf['programs'].items():
                new_tasks[key] = Task(**value)
            self.process_new_config(new_tasks)

    def cmd_status(self, args):
        status: str = ''
        if len(args) == 0:
            args = [name for name in self.tasks.keys()]
        for taskname in args:
            status += f'{taskname:20}\t'
            if taskname in self.active_processes.keys():
                status += "RUNNING"
            elif any(taskname == name for task in self.pending_spawns for name in task.values()):
                status += "PENDING"
            elif taskname not in self.tasks.keys():
                status += "UNKNOWN TASK"
            else:
                status += "STOPPED"
            status += '\n'
        status = status[:-1]
        return status

    def cmd_start(self, args):
        started = []
        failed = []
        success = []
        for taskname in args:
            if taskname not in self.tasks.keys():
                failed.append(taskname)
                continue
            if taskname not in self.active_processes.keys():
                success.append(taskname)
                self.tasks[taskname].retry_count = 1
                self.schedule_spawn(taskname, self.tasks[taskname])
            else:
                started.append(taskname)
        started = ' '.join(started)
        failed = ' '.join(failed)
        success = ' '.join(success)
        return (f"Started programs: {success}\nFailed to start: {failed}\nAlready running: {started}")

    def cmd_stop(self, args):
        for taskname in args:
            if taskname in self.active_processes.keys():
                self.despawn_task(taskname, self.tasks[taskname])
        return(f"Stopped programs: {' '.join(args)}")

    def cmd_restart(self, args):
        self.cmd_stop(args)
        msg: str = self.cmd_start(args)
        return(msg)

    def cmd_reload(self, args):
        self.reload_file()
        return(f"File: {self.filename} reloaded")

    def cmd_shutdown(self, args):
        self.shutdown_server()

    def handle_cmd(self, cmd, arg):
        function = self.commands[cmd]
        return function(arg)

    def handle_proc_exit(self, name: str, task: Task, proc: Popen, exit_code: int):
        is_expected: bool = False
        if isinstance(task.exitcodes, list):
            is_expected = exit_code in task.exitcodes
        else:
            is_expected = exit_code == task.exitcodes
        if is_expected:
            self.logger.info(f"Process {name} (PID: {proc.pid}) gracefully exited with code {exit_code}")
        else:
            self.logger.warning(f"Process {name} (PID: {proc.pid}) exited unexpectedly with code {exit_code}")
        needs_restart: bool = task.autorestart == 'always' or (task.autorestart == 'unexpected' and not is_expected)
        if needs_restart:
            if task.retry_count < task.startretries:
                self.schedule_spawn(name, task)
                task.retry_count += 1
                self.logger.warning(f"Restarting process {name} based on policy {task.autorestart}")
            elif task.retry_count == task.startretries:
                self.logger.error(f"Failed to start process {name} due to repeated crashes.")

    def monitor_processes(self):
        current_time = time.time()
        for i in range(len(self.pending_spawns) - 1, -1, -1):
            pending = self.pending_spawns[i]
            if current_time >= pending['launch_time']:
                self.spawn_task(pending['name'], pending['task'], 1, flush_processes=False)
                self.pending_spawns.pop(i)
        for name, task in self.tasks.items():
            alive_processes: list[Popen] = []
            if name not in self.active_processes.keys():
                continue
            for proc in self.active_processes[name]:
                exit_code = proc.poll()
                if exit_code is None:
                    alive_processes.append(proc)
                else:
                    self.handle_proc_exit(name, task, proc, exit_code)
            self.active_processes[name] = alive_processes
            if (len(alive_processes) == 0):
                del self.active_processes[name]

    def launch(self):
        if self.socket is None:
            self.logger.error("Socket not initialized. Exiting server.")
            exit(1)
        self.socket.listen()
        self.logger.info(f"Server successfully started on {self.host}:{self.port}")
        input_sockets: list[socket.socket] = [self.socket]
        input_buffers: dict[socket.socket, bytes] = {}
        while True:
            self.monitor_processes()
            readable_sockets, _, _ = select.select(input_sockets, [], [], 0.1)
            for sock in readable_sockets:
                if sock is self.socket:
                    conn, addr = sock.accept()
                    conn.setblocking(False)
                    input_sockets.append(conn)
                    input_buffers[conn] = b''
                    self.logger.info(f"Connection received from {addr[0]}")
                else:
                    try:
                        chunk = sock.recv(2048)
                        if not chunk:
                            self.logger.info("Client disconnected.")
                            input_sockets.remove(sock)
                            del input_buffers[sock]
                            sock.close()
                            continue
                        input_buffers[sock] += chunk
                        while b'\n' in input_buffers[sock]:
                            message, input_buffers[sock] = input_buffers[sock].split(b'\n', 1)
                            message = json.loads(message.decode())
                            response = self.handle_cmd(message["cmd"], message["args"])
                            sock.sendall(response.encode())
                    except ConnectionResetError:
                        input_sockets.remove(sock)
                        if sock in input_buffers.keys():
                            del input_buffers[sock]
                        sock.close()
                        self.logger.info("Client unexpectedly closed the connection from server.")
