# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
Circup -- a utility to manage and update libraries on a CircuitPython device.
"""


from circup.shared import DATA_DIR, BAD_FILE_FORMAT, extract_metadata, _get_modules_file
from circup.backends import WebBackend, DiskBackend
from circup.logging import logger


# Useful constants.


__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/circup.git"


from circup.commands import *

# Allows execution via `python -m circup ...`
# pylint: disable=no-value-for-parameter
if __name__ == "__main__":  # pragma: no cover
    main()
