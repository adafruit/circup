"""
CircUp -- a utility to manage and update libraries on a CircuitPython device.

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
import github
import re
from serial.tools.list_ports import comports as list_serial_ports


# IMPORTANT
# ---------
# Keep these metadata assignments simple and single-line. They are parsed
# somewhat naively by setup.py.
__title__ = "circup"
__description__ = "A tool to manage/update libraries on CircuitPython devices."
__version__ = "0.0.1"
__license__ = "MIT"
__url__ = "https://github.com/adafruit/circup"
__author__ = "Adafruit Industries"
__email__ = "ntoll@ntoll.org"


#: The unique USB vendor ID for Adafruit boards.
VENDOR_ID = 9114
#: The regex used to extract __version__ and __repo__ assignments within code.
DUNDER_ASSIGN_RE = re.compile(r"""^__\w+__\s*=\s*['"].+['"]$""")


def find_device():
    """
    Returns a tuple containing the port's device and description for a
    connected Adafruit device. If no device is connected, the tuple will be
    (None, None).
    """
    ports = list_serial_ports()
    for port in ports:
        if port.vid == VENDOR_ID:
            return (port.device, port.description)
    return (None, None)


def get_repos_file(repository, filename):
    """
    Given a GitHub repository and a file contained therein, either returns the
    content of that file, or raises an exception.

    :param str repository: The full path to the GitHub repository.
    :param str filename: The name of the file within the GitHub repository.
    :return: The content of the file.
    :raises ValueError: if the repository or filename is unknown.
    """
    # Extract the repository's path for the GitHub API.
    owner, repos_name = repository.split("/")[-2:]
    repos_path = "{}/{}".format(owner, repos_name.replace(".git", ""))
    # Reference the remote repository.
    gh = github.Github()
    try:
        repos = gh.get_repo(repos_path)
    except github.GithubException.UnknownObjectException:
        raise ValueError("Unknown repository.")
    source = repos.get_contents(filename)
    return source.decoded_content


def extract_metadata(code):
    """
    Given some Adafruit library code, return a dictionary containing metadata
    extracted from dunder attributes found therein.

    Such metadata assignments should be simple and single-line. For example::

        __version__ = "1.1.4"
        __repo__ = "https://github.com/adafruit/SomeLibrary.git"

    :param str code: The source code containing the version details.
    :return: The dunder based metadata found in the code as a dictionary.
    """
    result = {}
    lines = code.split()
    for line in lines:
        if DUNDER_ASSIGN_RE.search(line):
            exec(line, result)
    return result


def check_version(path):
    """
    TODO: Finish this...
    """


def main():  # pragma: no cover
    """
    TODO: Finish this. Just checking things work.
    """
    print(find_device())
