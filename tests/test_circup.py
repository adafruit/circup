"""
Unit tests for the circup module.

Copyright (c) 2019 Adafruit Industries

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import circup
from unittest import mock


def test_find_device():
    """
    Ensure the find_device function returns the expected information about
    any Adafruit devices connected to the user's computer.
    """

    class FakePort:
        """
        Pretends to be a representation of a port in PySerial.
        """

        def __init__(self, vid, device, description):
            self.vid = vid
            self.device = device
            self.description = description

    device = "/dev/ttyACM3"
    description = "CircuitPlayground Express - CircuitPython CDC control"
    port = FakePort(circup.VENDOR_ID, device, description)
    ports = [port]
    with mock.patch("circup.list_serial_ports", return_value=ports):
        result = circup.find_device()
        assert result == (device, description)


def test_find_device_not_connected():
    """
    If no Adafruit device is connected to the user's computer, ensure the
    result is (None, None)
    """
    with mock.patch("circup.list_serial_ports", return_value=[]):
        result = circup.find_device()
        assert result == (None, None)
