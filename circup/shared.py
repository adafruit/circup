# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, written for Adafruit Industries
# SPDX-FileCopyrightText: 2023 Tim Cocks, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
Utilities that are shared and used by both click CLI command functions
and Backend class functions.
"""
import glob
import os
import re
import json
import importlib.resources
import appdirs
import requests

from circup.lazy_metadata import LazyMetadata

#: Version identifier for a bad MPY file format
BAD_FILE_FORMAT = "Invalid"

#: The location of data files used by circup (following OS conventions).
DATA_DIR = appdirs.user_data_dir(appname="circup", appauthor="adafruit")

#: Module formats list (and the other form used in github files)
PLATFORMS = {"py": "py", "9mpy": "9.x-mpy", "10mpy": "10.x-mpy"}

#: Timeout for requests calls like get()
REQUESTS_TIMEOUT = 30

#: The path to the JSON file containing the metadata about the bundles.
BUNDLE_CONFIG_FILE = importlib.resources.files("circup") / "config/bundle_config.json"

#: Overwrite the bundles list with this file (only done manually)
BUNDLE_CONFIG_OVERWRITE = os.path.join(DATA_DIR, "bundle_config.json")
#: The path to the JSON file containing the local list of bundles.
BUNDLE_CONFIG_LOCAL = os.path.join(DATA_DIR, "bundle_config_local.json")
#: The path to the JSON file containing the metadata about the bundles.
BUNDLE_DATA = os.path.join(DATA_DIR, "circup.json")

#:  The libraries (and blank lines) which don't go on devices
NOT_MCU_LIBRARIES = [
    "",
    "adafruit-blinka",
    "adafruit-blinka-bleio",
    "adafruit-blinka-displayio",
    "adafruit-circuitpython-typing",
    "circuitpython_typing",
    "pyserial",
]

#: Commands that do not require an attached board
BOARDLESS_COMMANDS = ["show", "bundle-add", "bundle-remove", "bundle-show"]


def _get_modules_file(path, logger):  # pylint: disable=too-many-locals
    """
    Get a dictionary containing metadata about all the Python modules found in
    the referenced file system path.

    :param str path: The directory in which to find modules.
    :return: A dictionary containing metadata about the found modules.
    """
    result = {}
    if not path:
        return result
    single_file_py_mods = glob.glob(os.path.join(path, "*.py"))
    single_file_mpy_mods = glob.glob(os.path.join(path, "*.mpy"))
    package_dir_mods = [
        d
        for d in glob.glob(os.path.join(path, "*", ""))
        if not os.path.basename(os.path.normpath(d)).startswith(".")
    ]
    single_file_mods = single_file_py_mods + single_file_mpy_mods
    for sfm in [f for f in single_file_mods if not os.path.basename(f).startswith(".")]:
        default_metadata = {"path": sfm, "mpy": sfm.endswith(".mpy")}
        metadata = LazyMetadata(
            lambda sfm=sfm: extract_metadata(sfm, logger), default_metadata
        )
        result[os.path.basename(sfm).replace(".py", "").replace(".mpy", "")] = metadata
    for package_path in package_dir_mods:
        name = os.path.basename(os.path.dirname(package_path))
        py_files = glob.glob(os.path.join(package_path, "**/*.py"), recursive=True)
        mpy_files = glob.glob(os.path.join(package_path, "**/*.mpy"), recursive=True)
        all_files = py_files + mpy_files
        # put __init__ first if any, assumed to have the version number
        all_files.sort()

        def get_metadata(all_files=all_files):  # capture all_files
            selected_metadata = {}
            # explore all the submodules to detect bad ones
            for source in [
                f for f in all_files if not os.path.basename(f).startswith(".")
            ]:
                metadata = extract_metadata(source, logger)
                if "__version__" in metadata:
                    # don't replace metadata if already found
                    if "__version__" not in selected_metadata:
                        selected_metadata = metadata
                    # break now if any of the submodules has a bad format
                    if metadata["__version__"] == BAD_FILE_FORMAT:
                        break
            return selected_metadata

        # default value
        default_metadata = {"path": package_path, "mpy": bool(mpy_files)}
        metadata = LazyMetadata(get_metadata, default_metadata)
        result[name] = metadata
    return result


def extract_metadata(path, logger):
    # pylint: disable=too-many-locals,too-many-branches
    """
    Given a file path, return a dictionary containing metadata extracted from
    dunder attributes found therein. Works with both .py and .mpy files.

    For Python source files, such metadata assignments should be simple and
    single-line. For example::

        __version__ = "1.1.4"
        __repo__ = "https://github.com/adafruit/SomeLibrary.git"

    For byte compiled .mpy files, a brute force / backtrack approach is used
    to find the __version__ number in the file -- see comments in the
    code for the implementation details.

    :param str path: The path to the file containing the metadata.
    :return: The dunder based metadata found in the file, as a dictionary.
    """
    result = {}
    logger.info("%s", path)
    if path.endswith(".py"):
        result["mpy"] = False
        with open(path, "r", encoding="utf-8") as source_file:
            content = source_file.read()
        #: The regex used to extract ``__version__`` and ``__repo__`` assignments.
        dunder_key_val = r"""(__\w+__)(?:\s*:\s*\w+)?\s*=\s*(?:['"]|\(\s)(.+)['"]"""
        for match in re.findall(dunder_key_val, content):
            result[match[0]] = str(match[1])
        if result:
            logger.info("Extracted metadata: %s", result)
    elif path.endswith(".mpy"):
        find_by_regexp_match = False
        result["mpy"] = True
        with open(path, "rb") as mpy_file:
            content = mpy_file.read()
        # Track the MPY version number
        mpy_version = content[0:2]
        compatibility = None
        loc = -1
        # Find the start location of the __version__
        if mpy_version == b"M\x03":
            # One byte for the length of "__version__"
            loc = content.find(b"__version__") - 1
            compatibility = (None, "7.0.0-alpha.1")
        elif mpy_version == b"C\x05":
            # Two bytes for the length of "__version__" in mpy version 5
            loc = content.find(b"__version__") - 2
            compatibility = ("7.0.0-alpha.1", "8.99.99")
        elif mpy_version == b"C\x06":
            # Two bytes in mpy version 6
            find_by_regexp_match = True
            compatibility = ("9.0.0-alpha.1", None)
        if find_by_regexp_match:
            # Too hard to find the version positionally.
            # Find the first thing that looks like an x.y.z version number.
            match = re.search(rb"([\d]+\.[\d]+\.[\d]+)\x00", content)
            if match:
                result["__version__"] = match.group(1).decode("utf-8")
        elif loc > -1:
            # Backtrack until a byte value of the offset is reached.
            offset = 1
            while offset < loc:
                val = int(content[loc - offset])
                if mpy_version == b"C\x05":
                    val = val // 2
                if val == offset - 1:  # Off by one..!
                    # Found version, extract the number given boundaries.
                    start = loc - offset + 1  # No need for prepended length.
                    end = loc  # Up to the start of the __version__.
                    version = content[start:end]  # Slice the version number.
                    # Create a string version as metadata in the result.
                    result["__version__"] = version.decode("utf-8")
                    break  # Nothing more to do.
                offset += 1  # ...and again but backtrack by one.
        if compatibility:
            result["compatibility"] = compatibility
        else:
            # not a valid MPY file
            result["__version__"] = BAD_FILE_FORMAT
    return result


def tags_data_load(logger):
    """
    Load the list of the version tags of the bundles on disk.

    :return: a dict() of tags indexed by Bundle identifiers/keys.
    """
    tags_data = None
    try:
        with open(BUNDLE_DATA, encoding="utf-8") as data:
            try:
                tags_data = json.load(data)
            except json.decoder.JSONDecodeError as ex:
                # Sometimes (why?) the JSON file becomes corrupt. In which case
                # log it and carry on as if setting up for first time.
                logger.error("Could not parse %s", BUNDLE_DATA)
                logger.exception(ex)
    except FileNotFoundError:
        pass
    if not isinstance(tags_data, dict):
        tags_data = {}
    return tags_data


def get_latest_release_from_url(url, logger):
    """
    Find the tag name of the latest release by using HTTP HEAD and decoding the redirect.

    :param str url: URL to the latest release page on a git repository.
    :return: The most recent tag value for the release.
    """

    logger.info("Requesting redirect information: %s", url)
    response = requests.head(url, timeout=REQUESTS_TIMEOUT)
    responseurl = response.url
    if response.is_redirect:
        responseurl = response.headers["Location"]
    tag = responseurl.rsplit("/", 1)[-1]
    logger.info("Tag: '%s'", tag)
    return tag
