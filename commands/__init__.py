from .CreateThread import entry as create_thread

commands = [create_thread]


def start():
    for command in commands:
        command.start()


def stop():
    for command in commands:
        command.stop()
