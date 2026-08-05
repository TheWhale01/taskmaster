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
import requests
import argparse
import subprocess
from Task import Task
from pathlib import Path
from Logger import Logger
from subprocess import Popen
from NotificationItem import NotificationItem
from TaskmasterSession import TaskmasterSession
from logging.handlers import RotatingFileHandler

class Server:
    def __init__(self, host: str = '127.0.0.1', port: int = 8080, pid_filepath: str = './taskmaster.pid'):
        args = self.parse_args(host, port, pid_filepath)
        self.setup_signals()
        self.filename = args.config
        self.host = args.host
        self.port = args.port
        self.pidfile = args.pidfile
        self.tasks: dict[str, Task] = {}
        self.active_processes: dict[str, list[Popen]] = {}
        self.wait_success_start: dict = {}
        self.daemonize(args.daemon)
        self.logger = logging.getLogger("TaskmasterServer")
        self.setup_logger(logging.DEBUG)
        self.descalate()
        self.check_pid()
        self.socket: socket.socket | None = self.get_socket()
        self.webhook_session: TaskmasterSession | None = self.get_webhook_session(args.webhook)
        self.commands = {
            "status":   self.cmd_status,
            "start":    self.cmd_start,
            "stop":     self.cmd_stop,
            "restart":  self.cmd_restart,
            "reload":   self.cmd_reload,
            "shutdown": self.cmd_shutdown,
        }

    def send_webhook_notif(self, body: NotificationItem):
        if self.webhook_session is None:
            return
        response: requests.Response = self.webhook_session.post('taskmaster', json=body.model_dump(mode='json'))
        if not response.ok:
            self.logger.warning(f"Could not notify webhook. {response.text}")

    def get_webhook_session(self, webhook_url: str | None) -> TaskmasterSession | None:
        if webhook_url is None:
            return None
        session = TaskmasterSession(webhook_url)
        return session

    def setup_signals(self):
        signal.signal(signal.SIGHUP, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def parse_args(self, host: str, port: int, pid_filepath: str):
        parser = argparse.ArgumentParser()
        parser.add_argument("config", help="Specifies the programs to run")
        parser.add_argument("-d", "--daemon", action='store_true', help='Run server in the background')
        parser.add_argument("-H", "--host", default=host, action='store', help='host on which the server should run')
        parser.add_argument("-p", "--port", default=port, action='store', help='port on which the server should run')
        parser.add_argument("-P", "--pidfile", default=pid_filepath, action='store', help='Path to the file where the pid of the server should be written')
        parser.add_argument('-w', '--webhook', default=None, action='store', help='Url to webhook service')
        return parser.parse_args()

    def get_socket(self) -> socket.socket | None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.setblocking(False)
        except Exception as e:
            self.logger.error(f"Failed to establish connection to client. {e}")
            return None
        return sock

    def check_pid(self):
        if os.path.exists(self.pidfile):
            with open(self.pidfile, 'r') as file:
                pid: int = int(file.readline().strip())
            try:
                os.kill(pid, 0)
                self.logger.error(f"Could not start taskmaster. Another instance is already running (PID: {pid}).")
                sys.exit(1)
            except PermissionError:
                self.logger.error(f"Taskmaster is already running (PID: {pid}) under a different user. Exiting.")
                sys.exit(1)
            except (ProcessLookupError, ValueError) as e:
                self.logger.info(f"No previous taskmaster server found with pid: {pid}. {e}")
        with open(self.pidfile, "w") as file:
            file.write(str(os.getpid()))

    def descalate(self):
        if os.geteuid() != 0:
            return
        self.logger.info("Taskmaster Server started as root detected.")
        sudo_uid: int = int(os.environ.get("SUDO_UID") or 1000)
        sudo_gid: int = int(os.environ.get("SUDO_GID") or 1000)
        try:
            os.setgroups([])
            os.setgid(sudo_gid)
            os.setuid(sudo_uid)
            self.logger.info("Privilege de-escalation done.")
        except OSError as e:
            self.logger.critical(f"Failed to drop privileges: {e}. Exiting.")
            sys.exit(1)

    def daemonize(self, daemon_mode: bool):
        if not daemon_mode:
            return
        try:
            if os.fork() > 0:
                sys.exit(0)
            os.setsid()
            os.umask(0)
            if os.fork() > 0:
                sys.exit(0)
        except OSError as e:
            print(f"Failed to daemonize the server. {e}. Exiting", file=sys.stderr)
            sys.exit(1)
        sys.stdout.flush()
        sys.stderr.flush()
        with open(os.devnull, 'r') as file:
            os.dup2(file.fileno(), sys.stdin.fileno())
        with open(os.devnull, 'a+') as file:
            os.dup2(file.fileno(), sys.stdout.fileno())
            os.dup2(file.fileno(), sys.stderr.fileno())

    def shutdown_server(self):
        self.stop_all_task()
        try:
            if self.socket is not None:
                self.socket.close()
        except Exception as e:
            self.logger.error(f"Failed to close socket connection: {e}")
        if os.path.exists(self.pidfile):
            os.unlink(self.pidfile)
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
        file_handler = RotatingFileHandler(logs_path, maxBytes=5*1024*1024, mode='w')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(fmt=Logger.CLEAN_FORMAT, datefmt=Logger.DATE_FORMAT))
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)

    def get_cmd(self, task: Task, env: dict) -> list[str]:
        cmd: str = string.Template(task.cmd).safe_substitute(env)
        return shlex.split(cmd)

    def get_logfiles(self, task: Task) -> tuple:
        mode: str = 'a'
        return (open(task.stdout, mode) if task.stdout else None, open(task.stderr, mode) if task.stderr else None)

    def get_env(self, task: Task) -> dict[str, str]:
        env: dict[str, str] = os.environ.copy()
        env.update(task.env)
        return env

    def create_process(self, name: str, task: Task) -> Popen:
        env: dict[str, str] = self.get_env(task)
        logfiles: tuple = self.get_logfiles(task)
        return Popen(
            self.get_cmd(task, env),
            cwd=task.workingdir,
            env=env,
            stdout=logfiles[0],
            stderr=logfiles[1],
            preexec_fn=lambda: os.umask(task.umask)
        )

    def apply_restart_policy(self, name: str, task: Task, ex: Exception | None = None, is_expected: bool = False):
        if ex is not None:
            self.logger.error(f"Failed to start process: {ex}")
        if task.autorestart == 'never':
            return
        if task.retry_count < task.startretries:
            self.logger.warning(f"Restarting process {name} based on policy {task.autorestart}")
            task.retry_count += 1
            self.spawn_task(name, task)
        elif (not is_expected or ex is not None) and task.retry_count == task.startretries:
            self.logger.error(f"Failed to start process {name} due to repeated crashes.")

    def spawn_task(self, name: str, task: Task, nb_procs: int = -1, flush_processes: bool = True):
        if flush_processes or name not in self.active_processes:
            self.active_processes[name] = []
        if nb_procs == -1:
            nb_procs = task.numprocs
        try:
            for _ in range(nb_procs):
                proc: Popen = self.create_process(name, task)
                if task.starttime != 0:
                    self.wait_success_start.setdefault(name, {}).setdefault('procs', []).append(proc)
                else:
                    self.active_processes.setdefault(name, []).append(proc)
            if task.starttime != 0:
                self.wait_success_start[name].update({
                    'task': task,
                    'starttime': time.time() + task.starttime
                })
                self.logger.info(f"Started task {name}. Waiting {task.starttime} seconds for service to be healthy.")
                self.send_webhook_notif(NotificationItem(taskname=name, task=task, status='started', retries=task.retry_count))
            else:
                self.logger.info(f"Started task {name}. Task {name} healthy.")
                self.send_webhook_notif(NotificationItem(taskname=name, task=task, status='healthy', retries=task.retry_count))
        except Exception as e:
            self.send_webhook_notif(NotificationItem(taskname=name, task=task, status='crashed', retries=task.retry_count))
            self.apply_restart_policy(name, task, e)
            self.wait_success_start.pop(name, None)

    def stop_all_task(self):
        for name in self.tasks:
            self.despawn_task(name, self.tasks[name])

    def get_signal(self, sig_name: str):
        full_name = "SIG" + sig_name
        try:
            return getattr(signal, full_name)
        except AttributeError:
            self.logger.error(f"Signal inconnu : '{sig_name}'. SIGTERM used by default.")
            return signal.SIGTERM

    def despawn_task(self, name: str, task: Task, nb_procs: int = -1):
        if name not in self.active_processes:
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
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self.active_processes.pop(name)
        self.logger.info(f"Despawned {nb_procs} process(es) of {name}")

    def update_numprocs(self, name: str, task: Task):
        nb_processes: int = len(self.active_processes[name])
        if nb_processes > task.numprocs:
            self.spawn_task(name, task, (nb_processes - task.numprocs), flush_processes=False)
        elif nb_processes < task.numprocs:
            self.despawn_task(name, task, (task.numprocs - nb_processes))

    def respawn_task(self, name: str):
        self.tasks[name].retry_count = 1
        self.despawn_task(name, self.tasks[name])
        if self.tasks[name].autostart:
            self.spawn_task(name, self.tasks[name])

    def process_new_config(self, new_tasks: dict[str, Task]):
        self.logger.info("Processing configuration...")
        if new_tasks == self.tasks:
            return
        added = new_tasks.keys() - self.tasks.keys()
        removed = self.tasks.keys() - new_tasks.keys()
        tasks = new_tasks.keys() & self.tasks.keys()
        for name in added:
            self.tasks[name] = new_tasks[name]
            if self.tasks[name].autostart:
                self.spawn_task(name, new_tasks[name])
        for name in removed:
            self.despawn_task(name, self.tasks[name])
            self.tasks.pop(name)
        for name in tasks:
            respawn_task: bool = False
            old_field = self.tasks[name].model_dump()
            new_field = new_tasks[name].model_dump()
            for field in old_field:
                if old_field[field] != new_field[field]:
                    respawn_task = True
                    self.logger.debug(f"{field}: {new_field[field]}")
                    setattr(self.tasks[name], field, new_field[field])
            if respawn_task:
                self.respawn_task(name)

    def reload_file(self):
        with open(self.filename, 'r') as file:
            conf = yaml.safe_load(file)
            new_tasks: dict[str, Task] = {}
            try:
                for key, value in conf['programs'].items():
                    new_tasks.update({key: Task(**value)})
            except Exception as e:
                self.logger.error(f"Failed to parse {self.filename}: {e}")
        self.process_new_config(new_tasks)

    def cmd_status(self, args):
        status: str = ''
        if len(args) == 0:
            args = [name for name in self.tasks]
        for taskname in args:
            status += f'{taskname:20}\t'
            if taskname in self.active_processes:
                status += "HEALTHY"
            elif taskname in self.wait_success_start:
                status += "STARTED"
            elif taskname not in self.tasks:
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
        msg: str = ""
        if len(args) == 0:
            args = [name for name in self.tasks]
        for taskname in args:
            if taskname not in self.tasks:
                failed.append(taskname)
                continue
            if taskname not in self.active_processes:
                success.append(taskname)
                self.tasks[taskname].retry_count = 1
                self.spawn_task(taskname, self.tasks[taskname])
            else:
                started.append(taskname)
        if len(success) != 0:
            msg += f"Started: {' '.join(success)}\n"
        if len(failed) != 0:
            msg += f"Failed to start: {' '.join(failed)}\n"
        if len(started) != 0:
            msg += f"Already running: {' '.join(started)}\n"
        return msg

    def cmd_stop(self, args):
        if len(args) == 0:
            args = [name for name in self.tasks]
        for taskname in args:
            if taskname in self.active_processes:
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
            self.send_webhook_notif(NotificationItem(taskname=name, task=task, status='stopped', retries=task.retry_count))
        else:
            self.logger.warning(f"Process {name} (PID: {proc.pid}) exited unexpectedly with code {exit_code}")
            self.send_webhook_notif(NotificationItem(taskname=name, task=task, status='crashed', retries=task.retry_count))
        needs_restart: bool = task.autorestart == 'always' or (task.autorestart == 'unexpected' and not is_expected)
        if needs_restart:
            self.apply_restart_policy(name, task, None, is_expected)

    def monitor_processes(self):
        for taskname in list(self.wait_success_start.keys()):
            task = self.wait_success_start[taskname]
            if time.time() >= task['starttime']:
                self.active_processes.update({taskname: task['procs']})
                self.logger.info(f"Task {taskname} healthy.")
                self.send_webhook_notif(NotificationItem(taskname=taskname, task=task['task'], retries=task['task'].retry_count, status='healthy'))
                self.wait_success_start.pop(taskname)
        for name, task in self.tasks.items():
            if name not in self.active_processes:
                continue
            for proc in self.active_processes[name]:
                exit_code = proc.poll()
                if exit_code is not None:
                    self.active_processes[name].remove(proc)
                    self.handle_proc_exit(name, task, proc, exit_code)
            if len(self.active_processes[name]) == 0:
                self.active_processes.pop(name)

    def launch(self):
        if self.socket is None:
            self.logger.error("Socket not initialized. Exiting server.")
            sys.exit(1)
        self.socket.listen()
        self.logger.info(f"Server successfully started on {self.host}:{self.port}")
        self.reload_file()
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
                        if sock in input_buffers:
                            input_buffers.pop(sock)
                        sock.close()
                        self.logger.info("Client unexpectedly closed the connection from server.")
