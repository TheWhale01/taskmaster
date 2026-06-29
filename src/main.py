import yaml
import signal
import argparse
from Task import Task
from functools import partial

def load_config(filename: str) -> dict[str, Task]:
    tasks: dict[str, Task] = {}
    with open(filename, 'r') as file:
        conf = yaml.safe_load(file)
        for (key, value) in conf['programs'].items():
            new_task: dict[str, Task] = {key: Task(**value)}
            tasks.update(new_task)
    return tasks

def handle_sighup(old_tasks: dict[str, Task], config: str, signum, frame):
    new_tasks: dict[str, Task] = load_config(config)
    if new_tasks == old_tasks:
        return
    added = new_tasks.keys() - old_tasks.keys()
    removed = old_tasks.keys() - new_tasks.keys()
    updated = new_tasks.keys() & old_tasks.keys()
    for name in added:
        print(f"Added {name} task")
        # Will need to actually run the new task
    for name in removed:
        print(f"Removed {name} task")
        # Will need to actually kill the old task
    for name in updated:
        if old_tasks[name] == new_tasks[name]:
            continue
        old_field = old_tasks[name].model_dump()
        new_field = new_tasks[name].model_dump()
        for field in old_field:
            if old_field[field] != new_field[field]:
                print(f"Key: {field} changed in task: {name}")

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
