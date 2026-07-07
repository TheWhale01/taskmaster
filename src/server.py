import os
from Server import Server

def main():
    if os.geteuid() == 0:
        print("Taskmaster Server started as root detected.")
        os.setgid(1000)
        os.setuid(1000)
        print("Privilege de-escalation done.")
    with open("taskmaster.pid", "w") as f:
        f.write(str(os.getpid()))
    server = Server()
    server.launch()

if __name__ == '__main__':
    main()
