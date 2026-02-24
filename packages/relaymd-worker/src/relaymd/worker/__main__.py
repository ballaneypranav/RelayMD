from relaymd.worker.bootstrap import run_bootstrap
from relaymd.worker.logging import configure_logging
from relaymd.worker.main import run_worker


def main() -> None:
    configure_logging()
    config = run_bootstrap()
    run_worker(config)


if __name__ == "__main__":
    main()
