from Server import Server
import os

def main():
    if os.geteuid() == 0:
        print("Taskmaster Server started as root detected.")
        os.setgid(1000)
        os.setuid(1000)
        print("Privilege de-escalation done.")
    server = Server()

    server.launch()

if __name__ == '__main__':
    main()
