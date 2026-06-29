import yaml
import signal
import argparse
from Task import Task
from functools import partial

def load_config(filename: str):
    tasks: list[tuple[str, Task]] = []
    with open(filename, 'r') as file:
        conf = yaml.safe_load(file)
        for (key, value) in conf['programs'].items():
            new_task = (key, Task(**value))
            tasks.append(new_task)

def handle_sighup(config, signum, frame):
    load_config(config)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()
    load_config(args.config)
    handler = partial(handle_sighup, args.config)
    signal.signal(signal.SIGHUP, handler)

    # while True:
    #     pass

if __name__ == '__main__':
    main()
