import yaml
import signal
import argparse
from Task import Task
from typing import Any

class Taskmaster:
    filename: str
    tasks: dict[str, Task] = {}

    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("config")
        args = parser.parse_args()
        self.filename = args.config

    def load_config(self) -> dict[str, Task]:
        tasks: dict[str, Task] = {}
        with open(self.filename, 'r') as file:
            conf = yaml.safe_load(file)
            for (key, value) in conf['programs'].items():
                tasks[key] = Task(**value)
        print(f"DEBUG: {tasks}")
        return tasks

    def spawn_task(self, task: dict[str, Task]):
        print("Spawning new task")
        self.tasks.update(task)

    def despawn_task(self, name: str):
        print("De-_spawning old task")
        self.tasks.pop(name)

    def change_numprocs(self, name: str):
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

    def handler(self, signum, frame):
        new_tasks: dict[str, Task] = self.load_config()
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
        self.load_config()
        signal.signal(signal.SIGHUP, self.handler)
        while True:
            pass
