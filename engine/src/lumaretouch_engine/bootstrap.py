"""Console entry point: restrict network capability before importing the engine."""
from .privacy import require_offline_or_exit


def main():
    require_offline_or_exit()
    from .server import main as server_main
    server_main()


if __name__=='__main__':
    main()
