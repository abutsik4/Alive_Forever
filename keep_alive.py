"""Compatibility entrypoint for the Alive Forever application."""

import sys

from alive_forever.system.windows import setup_exception_logging


LOGGER = setup_exception_logging(supervisor=sys.argv[1:] == ["--autostart"])

def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments == ["--autostart"]:
        from alive_forever.system.startup import supervise_startup

        return supervise_startup(LOGGER)
    from alive_forever.app import main as app_main

    return app_main(arguments)


if __name__ == "__main__":
    sys.exit(main())