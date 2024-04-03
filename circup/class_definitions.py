import os
from urllib.parse import urljoin, urlparse

import click
import requests
from semver import VersionInfo

from circup.shared import DATA_DIR, PLATFORMS, REQUESTS_TIMEOUT, BAD_FILE_FORMAT, tags_data_load, \
    get_latest_release_from_url
from circup.backends import WebBackend
from circup.logging import logger



#: The version of CircuitPython found on the connected device.
CPY_VERSION = ""





