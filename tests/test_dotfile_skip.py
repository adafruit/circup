# SPDX-FileCopyrightText: 2024 circup contributors
#
# SPDX-License-Identifier: MIT
# pylint: disable=missing-docstring,protected-access
"""The web-workflow backend must skip dotfiles (e.g. macOS ._ AppleDouble
metadata) during module enumeration, matching the disk backend, and must never
fetch their contents."""
import logging
import types

from circup.backends import WebBackend

LOGGER = logging.getLogger("test")


def _mpy(version):
    return b"C\x06\x00\x00m\x00\x00" + version.encode() + b"\x00"


# A device /lib whose root and one package are littered with macOS ._ files
# (binary AppleDouble content that fails UTF-8 decoding), plus a hidden dir.
ROOT = {
    "files": [
        {"name": "neopixel.mpy", "directory": False},
        {"name": "._neopixel.mpy", "directory": False},  # AppleDouble ghost
        {"name": "._breadcrumb.py", "directory": False},  # ghost of a .py
        {"name": ".Trashes", "directory": True},  # hidden dir
        {"name": "adafruit_bus_device", "directory": True},
    ]
}
PKG = {
    "files": [
        {"name": "__init__.mpy", "directory": False},
        {"name": "._: __init__.mpy", "directory": False},  # ghost inside package
    ]
}
CONTENT = {
    "neopixel.mpy": _mpy("6.5.0"),
    "adafruit_bus_device/__init__.mpy": _mpy("1.2.3"),
}
# AppleDouble ghosts contain a 0xb0 byte at offset 37 -> would crash on decode
# if they were ever fetched and read as a .py file.
_GHOST = b"# macos appledouble header padding padding5" + b"\xb0" + b"junk"


class FakeDevice:
    def __init__(self):
        self.gets = []

    def session_get(self, url, *_a, **_k):
        self.gets.append(url)

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def json(self):
                if url.endswith("/fs/lib/"):
                    return ROOT
                if url.endswith("/adafruit_bus_device/"):
                    return PKG
                raise ValueError(url)

            @property
            def content(self):
                rel = url.split("/fs/lib/", 1)[1]
                if rel in CONTENT:
                    return CONTENT[rel]
                # Any dotfile fetch returns undecodable ghost content.
                return _GHOST

        return Resp()


def _backend(device):
    wb = WebBackend.__new__(WebBackend)  # bypass __init__ (no real device)
    wb.session = types.SimpleNamespace(get=device.session_get)
    wb.timeout = 5
    wb.logger = LOGGER
    return wb


def test_dotfiles_are_skipped_and_never_fetched():
    dev = FakeDevice()
    result = _backend(dev)._get_modules_http("http://:pw@dev:80/fs/lib/")

    # Only the real modules are discovered.
    assert set(result) == {"neopixel", "adafruit_bus_device"}
    assert result["neopixel"]["__version__"] == "6.5.0"
    assert result["adafruit_bus_device"]["__version__"] == "1.2.3"

    # No request was ever made for a dotfile (which would have crashed on
    # decode). Every fetched path's final segment must not start with ".".
    for url in dev.gets:
        last = url.rstrip("/").rsplit("/", 1)[-1]
        assert not last.startswith("."), f"dotfile was fetched: {url}"
