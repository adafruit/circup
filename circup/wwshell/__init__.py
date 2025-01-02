# SPDX-FileCopyrightText: 2024 Tim Cocks, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
wwshell is a CLI utility for managing files on CircuitPython devices via wireless workflows.
It currently supports Web Workflow.
"""
from .commands import main


# Allows execution via `python -m circup ...`
# pylint: disable=no-value-for-parameter
if __name__ == "__main__":
    main()
