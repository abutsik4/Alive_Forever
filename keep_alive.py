"""Compatibility entrypoint for the Alive Forever application."""

import sys

from alive_forever.app import main


if __name__ == "__main__":
    sys.exit(main())