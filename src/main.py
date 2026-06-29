import yaml
import signal
import argparse
from Task import Task
from typing import Any
from functools import partial

def load_config(filename: str) -> dict[str, Task]:
    tasks: dict[str, Task] = {}
    with open(filename, 'r') as file:
        conf = yaml.safe_load(file)
        for (key, value) in conf['programs'].items():
            new_task: dict[str, Task] = {key: Task(**value)}
            tasks.update(new_task)
    return tasks

def spawn_task(tasks: dict[str, Task], task: dict[str, Task]):
    print("Spawning new task")
    tasks.update(task)

def despawn_task(tasks: dict[str, Task], name: str):
    print("De-_spawning old task")
    tasks.pop(name)

def change_numprocs(tasks: dict[str, Task], name: str):
    pass

def apply_update(tasks: dict[str, Task], name: str, key: str, value: Any):
    print("Applying update")
    setattr(tasks[name], key, value)
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
        change_numprocs(tasks, name)
    else:
        despawn_task(tasks, name)
        spawn_task(tasks, {name: tasks[name]})

def handle_sighup(old_tasks: dict[str, Task], config: str, signum, frame):
    new_tasks: dict[str, Task] = load_config(config)
    if new_tasks == old_tasks:
        return
    added = new_tasks.keys() - old_tasks.keys()
    removed = old_tasks.keys() - new_tasks.keys()
    updated = new_tasks.keys() & old_tasks.keys()
    for name in added:
        spawn_task(old_tasks, {name: new_tasks[name]})
    for name in removed:
        despawn_task(old_tasks, name)
    for name in updated:
        if old_tasks[name] == new_tasks[name]:
            continue
        old_field = old_tasks[name].model_dump()
        new_field = new_tasks[name].model_dump()
        for field in old_field:
            if old_field[field] != new_field[field]:
                apply_update(old_tasks, name, field, new_field[field])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()
    tasks: dict[str, Task] = load_config(args.config)
    handler = partial(handle_sighup, tasks, args.config)
    signal.signal(signal.SIGHUP, handler)

    while True:
        pass

if __name__ == '__main__':
    main()
