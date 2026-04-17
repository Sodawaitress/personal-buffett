#!/usr/bin/env python3
"""New development entrypoint for the refactor branch."""

from radar_app import create_app, run_dev_server

app = create_app()


if __name__ == "__main__":
    run_dev_server(app)
