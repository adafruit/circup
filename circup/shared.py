import glob
import os
import re

import appdirs

#: Version identifier for a bad MPY file format
BAD_FILE_FORMAT = "Invalid"

#: The location of data files used by circup (following OS conventions).
DATA_DIR = appdirs.user_data_dir(appname="circup", appauthor="adafruit")


def _get_modules_file(path, logger):
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
        metadata = extract_metadata(sfm, logger)
        metadata["path"] = sfm
        result[os.path.basename(sfm).replace(".py", "").replace(".mpy", "")] = metadata
    for package_path in package_dir_mods:
        name = os.path.basename(os.path.dirname(package_path))
        py_files = glob.glob(os.path.join(package_path, "**/*.py"), recursive=True)
        mpy_files = glob.glob(os.path.join(package_path, "**/*.mpy"), recursive=True)
        all_files = py_files + mpy_files
        # default value
        result[name] = {"path": package_path, "mpy": bool(mpy_files)}
        # explore all the submodules to detect bad ones
        for source in [f for f in all_files if not os.path.basename(f).startswith(".")]:
            metadata = extract_metadata(source, logger)
            if "__version__" in metadata:
                metadata["path"] = package_path
                result[name] = metadata
                # break now if any of the submodules has a bad format
                if metadata["__version__"] == BAD_FILE_FORMAT:
                    break
    return result


def extract_metadata(path, logger):
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
    elif path.endswith(".mpy"):
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
            # Two bytes in mpy version 5
            loc = content.find(b"__version__") - 2
            compatibility = ("7.0.0-alpha.1", None)
        if loc > -1:
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

    if result:
        logger.info("Extracted metadata: %s", result)
    return result