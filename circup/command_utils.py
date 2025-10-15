# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, 2024 Tim Cocks, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
Functions called from commands in order to provide behaviors and return information.
"""

import ast
import ctypes
import glob
import os

from subprocess import check_output
import sys
import shutil
import zipfile
import json
import re
import toml
import requests
import click

from circup.shared import (
    PLATFORMS,
    REQUESTS_TIMEOUT,
    _get_modules_file,
    BUNDLE_CONFIG_OVERWRITE,
    BUNDLE_CONFIG_FILE,
    BUNDLE_CONFIG_LOCAL,
    BUNDLE_DATA,
    NOT_MCU_LIBRARIES,
    tags_data_load,
)
from circup.logging import logger
from circup.module import Module
from circup.bundle import Bundle

WARNING_IGNORE_MODULES = (
    "typing-extensions",
    "pyasn1",
    "circuitpython-typing",
)

CODE_FILES = [
    "code.txt",
    "code.py",
    "main.py",
    "main.txt",
    "code.txt.py",
    "code.py.txt",
    "code.txt.txt",
    "code.py.py",
    "main.txt.py",
    "main.py.txt",
    "main.txt.txt",
    "main.py.py",
]


class CodeParsingException(Exception):
    """Exception thrown when parsing code with ast fails"""


def clean_library_name(assumed_library_name):
    """
    Most CP repos and library names are look like this:

        repo: Adafruit_CircuitPython_LC709203F
        library: adafruit_lc709203f

    But some do not and this handles cleaning that up.
    Also cleans up if the pypi or reponame is passed in instead of the
    CP library name.

    :param str assumed_library_name: An assumed name of a library from user
        or requirements.txt entry
    :return: str proper library name
    """
    not_standard_names = {
        # Assumed Name : Actual Name
        "adafruit_adafruitio": "adafruit_io",
        "adafruit_asyncio": "asyncio",
        "adafruit_busdevice": "adafruit_bus_device",
        "adafruit_connectionmanager": "adafruit_connection_manager",
        "adafruit_display_button": "adafruit_button",
        "adafruit_neopixel": "neopixel",
        "adafruit_sd": "adafruit_sdcard",
        "adafruit_simpleio": "simpleio",
        "pimoroni_ltr559": "pimoroni_circuitpython_ltr559",
    }
    if "circuitpython" in assumed_library_name:
        # convert repo or pypi name to common library name
        assumed_library_name = (
            assumed_library_name.replace("-circuitpython-", "_")
            .replace("_circuitpython_", "_")
            .replace("-", "_")
        )
    if assumed_library_name in not_standard_names:
        return not_standard_names[assumed_library_name]
    return assumed_library_name


def completion_for_install(ctx, param, incomplete):
    """
    Returns the list of available modules for the command line tab-completion
    with the ``circup install`` command.
    """
    # pylint: disable=unused-argument
    available_modules = get_bundle_versions(get_bundles_list(), avoid_download=True)
    module_names = {m.replace(".py", "") for m in available_modules}
    if incomplete:
        module_names = [name for name in module_names if name.startswith(incomplete)]
        module_names.extend(glob.glob(f"{incomplete}*"))
    return sorted(module_names)


def completion_for_example(ctx, param, incomplete):
    """
    Returns the list of available modules for the command line tab-completion
    with the ``circup example`` command.
    """

    # pylint: disable=unused-argument, consider-iterating-dictionary
    available_examples = get_bundle_examples(get_bundles_list(), avoid_download=True)

    matching_examples = [
        example_path
        for example_path in available_examples.keys()
        if example_path.startswith(incomplete)
    ]

    return sorted(matching_examples)


def ensure_latest_bundle(bundle):
    """
    Ensure that there's a copy of the latest library bundle available so circup
    can check the metadata contained therein.

    :param Bundle bundle: the target Bundle object.
    """
    logger.info("Checking library updates for %s.", bundle.key)
    tag = bundle.latest_tag
    do_update = False
    if tag == bundle.current_tag:
        for platform in PLATFORMS:
            # missing directories (new platform added on an existing install
            # or side effect of pytest or network errors)
            do_update = do_update or not os.path.isdir(bundle.lib_dir(platform))
    else:
        do_update = True

    if do_update:
        logger.info("New version available (%s).", tag)
        try:
            get_bundle(bundle, tag)
            tags_data_save_tag(bundle.key, tag)
        except requests.exceptions.HTTPError as ex:
            # See #20 for reason for this
            click.secho(
                (
                    "There was a problem downloading that platform bundle. "
                    "Skipping and using existing download if available."
                ),
                fg="red",
            )
            logger.exception(ex)
    else:
        logger.info("Current bundle up to date %s.", tag)


def find_device():
    """
    Return the location on the filesystem for the connected CircuitPython device.
    This is based upon how Mu discovers this information.

    :return: The path to the device on the local filesystem.
    """
    device_dir = None
    # Attempt to find the path on the filesystem that represents the plugged in
    # CIRCUITPY board.
    if os.name == "posix":
        # Linux / OSX
        for mount_command in ["mount", "/sbin/mount"]:
            try:
                mount_output = check_output(mount_command).splitlines()
                mounted_volumes = [x.split()[2] for x in mount_output]
                for volume in mounted_volumes:
                    if volume.endswith(b"CIRCUITPY"):
                        device_dir = volume.decode("utf-8")
            except FileNotFoundError:
                continue
    elif os.name == "nt":
        # Windows

        def get_volume_name(disk_name):
            """
            Each disk or external device connected to windows has an attribute
            called "volume name". This function returns the volume name for the
            given disk/device.

            Based upon answer given here: http://stackoverflow.com/a/12056414
            """
            vol_name_buf = ctypes.create_unicode_buffer(1024)
            ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(disk_name),
                vol_name_buf,
                ctypes.sizeof(vol_name_buf),
                None,
                None,
                None,
                None,
                0,
            )
            return vol_name_buf.value

        #
        # In certain circumstances, volumes are allocated to USB
        # storage devices which cause a Windows popup to raise if their
        # volume contains no media. Wrapping the check in SetErrorMode
        # with SEM_FAILCRITICALERRORS (1) prevents this popup.
        #
        old_mode = ctypes.windll.kernel32.SetErrorMode(1)
        try:
            for disk in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                path = "{}:\\".format(disk)
                if os.path.exists(path) and get_volume_name(path) == "CIRCUITPY":
                    device_dir = path
                    # Report only the FIRST device found.
                    break
        finally:
            ctypes.windll.kernel32.SetErrorMode(old_mode)
    else:
        # No support for unknown operating systems.
        raise NotImplementedError('OS "{}" not supported.'.format(os.name))
    logger.info("Found device: %s", device_dir)
    return device_dir


def find_modules(backend, bundles_list):
    """
    Extracts metadata from the connected device and available bundles and
    returns this as a list of Module instances representing the modules on the
    device.

    :param Backend backend: Backend with the device connection.
    :param List[Bundle] bundles_list: List of supported bundles as Bundle objects.
    :return: A list of Module instances describing the current state of the
             modules on the connected device.
    """
    # pylint: disable=broad-except,too-many-locals
    try:
        device_modules = backend.get_device_versions()
        bundle_modules = get_bundle_versions(bundles_list)
        result = []
        for key, device_metadata in device_modules.items():

            if key in bundle_modules:
                path = device_metadata["path"]
                bundle_metadata = bundle_modules[key]
                repo = bundle_metadata.get("__repo__")
                bundle = bundle_metadata.get("bundle")
                device_version = device_metadata.get("__version__")
                bundle_version = bundle_metadata.get("__version__")
                mpy = device_metadata["mpy"]
                compatibility = device_metadata.get("compatibility", (None, None))
                module_name = (
                    path.split(os.sep)[-1]
                    if not path.endswith(os.sep)
                    else path[:-1].split(os.sep)[-1] + os.sep
                )

                m = Module(
                    module_name,
                    backend,
                    repo,
                    device_version,
                    bundle_version,
                    mpy,
                    bundle,
                    compatibility,
                )
                result.append(m)
        return result
    except Exception as ex:
        # If it's not possible to get the device and bundle metadata, bail out
        # with a friendly message and indication of what's gone wrong.
        logger.exception(ex)
        click.echo("There was a problem: {}".format(ex))
        sys.exit(1)
    # pylint: enable=broad-except,too-many-locals


def get_bundle(bundle, tag):
    """
    Downloads and extracts the version of the bundle with the referenced tag.
    The resulting zip file is saved on the local filesystem.

    :param Bundle bundle: the target Bundle object.
    :param str tag: The GIT tag to use to download the bundle.
    """
    click.echo(f"Downloading latest bundles for {bundle.key} ({tag}).")
    for platform, github_string in PLATFORMS.items():
        # Report the platform: "8.x-mpy", etc.
        click.echo(f"{github_string}:")
        url = bundle.url_format.format(platform=github_string, tag=tag)
        logger.info("Downloading bundle: %s", url)
        r = requests.get(url, stream=True, timeout=REQUESTS_TIMEOUT)
        # pylint: disable=no-member
        if r.status_code != requests.codes.ok:
            logger.warning("Unable to connect to %s", url)
            r.raise_for_status()
        # pylint: enable=no-member
        total_size = int(r.headers.get("Content-Length"))
        temp_zip = bundle.zip.format(platform=platform)
        with click.progressbar(
            r.iter_content(1024), label="Extracting:", length=total_size
        ) as pbar, open(temp_zip, "wb") as zip_fp:
            for chunk in pbar:
                zip_fp.write(chunk)
                pbar.update(len(chunk))
        logger.info("Saved to %s", temp_zip)
        temp_dir = bundle.dir.format(platform=platform)
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)
        with zipfile.ZipFile(temp_zip, "r") as zfile:
            zfile.extractall(temp_dir)
    bundle.current_tag = tag
    click.echo("\nOK\n")


def get_bundle_examples(bundles_list, avoid_download=False):
    """
    Return a dictionary of metadata from examples in the all of the bundles
    specified by bundles_list argument.

    :param List[Bundle] bundles_list: List of supported bundles as Bundle objects.
    :param bool avoid_download: if True, download the bundle only if missing.
    :return: A dictionary of metadata about the examples available in the
             library bundle.
    """
    # pylint: disable=too-many-nested-blocks,too-many-locals
    all_the_examples = dict()
    bundle_examples = dict()

    try:
        for bundle in bundles_list:
            if not avoid_download or not os.path.isdir(bundle.lib_dir("py")):
                ensure_latest_bundle(bundle)
            path = bundle.examples_dir("py")
            meta_saved = os.path.join(path, "../bundle_examples.json")
            if os.path.exists(meta_saved):
                with open(meta_saved, "r", encoding="utf-8") as f:
                    bundle_examples = json.load(f)
                all_the_examples.update(bundle_examples)
                bundle_examples.clear()
                continue
            path_examples = _get_modules_file(path, logger)
            for lib_name, lib_metadata in path_examples.items():
                for _dir_level in os.walk(lib_metadata["path"]):
                    for _file in _dir_level[2]:
                        _parts = _dir_level[0].split(os.path.sep)
                        _lib_name_index = _parts.index(lib_name)
                        _dirs = _parts[_lib_name_index:]
                        if _dirs[-1] == "":
                            _dirs.pop(-1)
                        slug = f"{os.path.sep}".join(_dirs + [_file.replace(".py", "")])
                        bundle_examples[slug] = os.path.join(_dir_level[0], _file)
                        all_the_examples[slug] = os.path.join(_dir_level[0], _file)

            with open(meta_saved, "w", encoding="utf-8") as f:
                json.dump(bundle_examples, f)
            bundle_examples.clear()

    except NotADirectoryError:
        # Bundle does not have new style examples directory
        # so we cannot include its examples.
        pass
    return all_the_examples


def get_bundle_versions(bundles_list, avoid_download=False):
    """
    Returns a dictionary of metadata from modules in the latest known release
    of the library bundle. Uses the Python version (rather than the compiled
    version) of the library modules.

    :param List[Bundle] bundles_list: List of supported bundles as Bundle objects.
    :param bool avoid_download: if True, download the bundle only if missing.
    :return: A dictionary of metadata about the modules available in the
             library bundle.
    """
    all_the_modules = dict()
    for bundle in bundles_list:
        if not avoid_download or not os.path.isdir(bundle.lib_dir("py")):
            ensure_latest_bundle(bundle)
        path = bundle.lib_dir("py")
        path_modules = _get_modules_file(path, logger)
        for name, module in path_modules.items():
            module["bundle"] = bundle
            if name not in all_the_modules:  # here we decide the order of priority
                all_the_modules[name] = module
    return all_the_modules


def get_bundles_dict():
    """
    Retrieve the dictionary from BUNDLE_CONFIG_FILE (JSON).
    Put the local dictionary in front, so it gets priority.
    It's a dictionary of bundle string identifiers.

    :return: Combined dictionaries from the config files.
    """
    bundle_dict = get_bundles_local_dict()
    try:
        with open(BUNDLE_CONFIG_OVERWRITE, "rb") as bundle_config_json:
            bundle_config = json.load(bundle_config_json)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        with open(BUNDLE_CONFIG_FILE, "rb") as bundle_config_json:
            bundle_config = json.load(bundle_config_json)
    for name, bundle in bundle_config.items():
        if bundle not in bundle_dict.values():
            bundle_dict[name] = bundle
    return bundle_dict


def get_bundles_local_dict():
    """
    Retrieve the local bundles from BUNDLE_CONFIG_LOCAL (JSON).

    :return: Raw dictionary from the config file(s).
    """
    try:
        with open(BUNDLE_CONFIG_LOCAL, "rb") as bundle_config_json:
            bundle_config = json.load(bundle_config_json)
        if not isinstance(bundle_config, dict) or not bundle_config:
            logger.error("Local bundle list invalid. Skipped.")
            raise FileNotFoundError("Bad local bundle list")
        return bundle_config
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        return dict()


def get_bundles_list():
    """
    Retrieve the list of bundles from the config dictionary.

    :return: List of supported bundles as Bundle objects.
    """
    bundle_config = get_bundles_dict()
    bundles_list = [Bundle(bundle_config[b]) for b in bundle_config]
    logger.info("Using bundles: %s", ", ".join(b.key for b in bundles_list))
    return bundles_list


def get_circup_version():
    """Return the version of circup that is running. If not available, return None.

    :return: Current version of circup, or None.
    """
    try:
        from importlib import metadata  # pylint: disable=import-outside-toplevel
    except ImportError:
        try:
            import importlib_metadata as metadata  # pylint: disable=import-outside-toplevel
        except ImportError:
            return None
    try:
        return metadata.version("circup")
    except metadata.PackageNotFoundError:
        return None


def get_dependencies(*requested_libraries, mod_names, to_install=()):
    """
    Return a list of other CircuitPython libraries required by the given list
    of libraries

    :param tuple requested_libraries: The libraries to search for dependencies
    :param object mod_names:  All the modules metadata from bundle
    :param list(str) to_install: Modules already selected for installation.
    :return: tuple of module names to install which we build
    """
    # pylint: disable=too-many-branches
    # Internal variables
    _to_install = to_install
    _requested_libraries = []
    _rl = requested_libraries[0]

    if not requested_libraries[0]:
        # If nothing is requested, we're done
        return _to_install

    for lib_name in _rl:
        lower_lib_name = lib_name.lower()
        if lower_lib_name in NOT_MCU_LIBRARIES:
            logger.info(
                "Skipping %s. It is not for microcontroller installs.", lib_name
            )
        else:
            # Canonicalize, with some exceptions:
            # adafruit-circuitpython-something => adafruit_something
            canonical_lib_name = clean_library_name(lower_lib_name)
            try:
                # Don't process any names we can't find in mod_names
                mod_names[canonical_lib_name]  # pylint: disable=pointless-statement
                _requested_libraries.append(canonical_lib_name)
            except KeyError:
                if canonical_lib_name not in WARNING_IGNORE_MODULES:
                    if os.path.exists(canonical_lib_name):
                        _requested_libraries.append(canonical_lib_name)
                    else:
                        click.secho(
                            f"WARNING:\n\t{canonical_lib_name} "
                            f"is not a known CircuitPython library.",
                            fg="yellow",
                        )

    if not _requested_libraries:
        # If nothing is requested, we're done
        return _to_install

    for library in list(_requested_libraries):
        if library not in _to_install:
            _to_install = _to_install + (library,)
            # get the requirements.txt from bundle
            try:
                bundle = mod_names[library]["bundle"]
                requirements_txt = bundle.requirements_for(library)
                if requirements_txt:
                    _requested_libraries.extend(
                        libraries_from_requirements(requirements_txt)
                    )

                circup_dependencies = get_circup_dependencies(bundle, library)
                for circup_dependency in circup_dependencies:
                    _requested_libraries.append(circup_dependency)
            except KeyError:
                # don't check local file for further dependencies
                pass

        # we've processed this library, remove it from the list
        _requested_libraries.remove(library)

        return get_dependencies(
            tuple(_requested_libraries), mod_names=mod_names, to_install=_to_install
        )


def get_circup_dependencies(bundle, library):
    """
    Get the list of circup dependencies from pyproject.toml
    e.g.
    [circup]
    circup_dependencies = ["dependency_name_here"]

    :param bundle: The Bundle to look within
    :param library: The Library to find pyproject.toml for and get dependencies from

    :return: The list of dependency libraries that were found
    """
    try:
        pyproj_toml = bundle.requirements_for(library, toml_file=True)
        if pyproj_toml:
            pyproj_toml_data = toml.loads(pyproj_toml)
            dependencies = pyproj_toml_data["circup"]["circup_dependencies"]
            if isinstance(dependencies, list):
                return dependencies

            if isinstance(dependencies, str):
                return (dependencies,)

        return tuple()

    except KeyError:
        # no circup_dependencies in pyproject.toml
        return tuple()


def libraries_from_requirements(requirements):
    """
    Clean up supplied requirements.txt and turn into tuple of CP libraries

    :param str requirements: A string version of a requirements.txt
    :return: tuple of library names
    """
    libraries = ()
    for line in requirements.split("\n"):
        line = line.lower().strip()
        if line.startswith("#") or line == "":
            # skip comments
            pass
        else:
            # Remove everything after any pip style version specifiers
            line = re.split("[<>=~[;]", line)[0].strip()
            libraries = libraries + (line,)
    return libraries


def save_local_bundles(bundles_data):
    """
    Save the list of local bundles to the settings.

    :param str key: The bundle's identifier/key.
    """
    if len(bundles_data) > 0:
        with open(BUNDLE_CONFIG_LOCAL, "w", encoding="utf-8") as data:
            json.dump(bundles_data, data)
    else:
        if os.path.isfile(BUNDLE_CONFIG_LOCAL):
            os.unlink(BUNDLE_CONFIG_LOCAL)


def tags_data_save_tag(key, tag):
    """
    Add or change the saved tag value for a bundle.

    :param str key: The bundle's identifier/key.
    :param str tag: The new tag for the bundle.
    """
    tags_data = tags_data_load(logger)
    tags_data[key] = tag
    with open(BUNDLE_DATA, "w", encoding="utf-8") as data:
        json.dump(tags_data, data)


def imports_from_code(full_content):
    """
    Parse the given code.py file and return the imported libraries
    Note that it's impossible at that level to differentiate between
    import module.property and import module.submodule, so we try both

    :param str full_content: Code to read imports from
    :param str module_name: Name of the module the code is from
    :return: sequence of library names
    """
    # pylint: disable=too-many-branches
    try:
        par = ast.parse(full_content)
    except (SyntaxError, ValueError) as err:
        raise CodeParsingException(err) from err

    imports = set()
    for thing in ast.walk(par):
        # import module and import module.submodule
        if isinstance(thing, ast.Import):
            for alias in thing.names:
                imports.add(alias.name)
        # from x import y
        if isinstance(thing, ast.ImportFrom):
            if thing.module:
                # from [.][.]module import names
                module = ("." * thing.level) + thing.module
                imports.add(module)
                for alias in thing.names:
                    imports.add(".".join([module, alias.name]))
            else:
                # from . import names
                for alias in thing.names:
                    imports.add(alias.name)

    # import parent modules (in practice it's the __init__.py)
    for name in list(imports):
        if "*" in name:
            imports.remove(name)
            continue
        names = name.split(".")
        for i in range(len(names)):
            module = ".".join(names[: i + 1])
            if module:
                imports.add(module)

    return sorted(imports)


def get_all_imports(  # pylint: disable=too-many-arguments,too-many-locals, too-many-branches
    backend, auto_file_content, auto_file_path, mod_names, current_module, visited=None
):
    """
    Recursively retrieve imports from files on the backend

    :param Backend backend: The current backend object
    :param str auto_file_content: Content of the python file to analyse
    :param str auto_file_path: Path to the python file to analyse
    :param list mod_names: Lits of supported bundle mod names
    :param str current_module: Name of the call context module if recursive call
    :param set visited: Modules previously visited
    :return: sequence of library names
    """
    if visited is None:
        visited = set()
    visited.add(current_module)

    requested_installs = []
    try:
        imports = imports_from_code(auto_file_content)
    except CodeParsingException as err:
        click.secho(f"Error parsing {current_module}:\n  {err}", fg="red")
        sys.exit(2)

    for install in imports:
        if install in visited:
            continue
        if install in mod_names:
            requested_installs.append(install)
        else:
            # relative module paths
            if install.startswith(".."):
                install_module = ".".join(current_module.split(".")[:-2])
                install_module = install_module + "." + install[2:]
            elif install.startswith("."):
                install_module = ".".join(current_module.split(".")[:-1])
                install_module = install_module + "." + install[1:]
            else:
                install_module = install
            # possible files for the module: .py or __init__.py (if directory)
            file_name = os.path.join(*install_module.split(".")) + ".py"
            try:
                file_location = os.path.join(
                    *auto_file_path.replace(str(backend.device_location), "").split(
                        "/"
                    )[:-1]
                )

                full_location = os.path.join(file_location, file_name)

            except TypeError:
                # file is in root of CIRCUITPY
                full_location = file_name

            exists = backend.file_exists(full_location)
            if not exists:
                file_name = os.path.join(*install_module.split("."), "__init__.py")
                full_location = file_name
                exists = backend.file_exists(full_location)
                if not exists:
                    continue
                install_module += ".__init__"
            # get the content and parse it recursively
            auto_file_content = backend.get_file_content(full_location)
            if auto_file_content:
                sub_imports = get_all_imports(
                    backend,
                    auto_file_content,
                    auto_file_path,
                    mod_names,
                    install_module,
                    visited,
                )
                requested_installs.extend(sub_imports)

    return sorted(requested_installs)
    # [r for r in requested_installs if r in mod_names]


def libraries_from_auto_file(backend, auto_file, mod_names):
    """
    Parse the input auto_file path and/or use the workflow to find the most
    appropriate code.py script. Then return the list of imports

    :param Backend backend: The current backend object
    :param str auto_file: Path of the candidate auto file or None
    :return: sequence of library names
    """
    # find the current main file based on Circuitpython's rules
    if auto_file is None:
        root_files = [
            file["name"] for file in backend.list_dir("") if not file["directory"]
        ]
        for main_file in CODE_FILES:
            if main_file in root_files:
                auto_file = main_file
                break
    # still no code file found
    if auto_file is None:
        click.secho(
            "No default code file found. See valid names:\n"
            "https://docs.circuitpython.org/en/latest/README.html#behavior",
            fg="red",
        )
        sys.exit(1)

    # pass a local file with "./" or "../"
    is_relative = auto_file.split(os.sep)[0] in [os.path.curdir, os.path.pardir]
    if os.path.isabs(auto_file) or is_relative:
        with open(auto_file, "r", encoding="UTF8") as fp:
            auto_file_content = fp.read()
    else:
        auto_file_content = backend.get_file_content(auto_file)

    if auto_file_content is None:
        click.secho(f"Auto file not found: {auto_file}", fg="red")
        sys.exit(1)

    # from file name to module name (in case it's in a subpackage)
    click.secho(f"Finding imports from: {auto_file}", fg="green")
    current_module = auto_file.rstrip(".py").replace(os.path.sep, ".")
    return get_all_imports(
        backend, auto_file_content, auto_file, mod_names, current_module
    )


def get_device_path(host, port, password, path):
    """
    :param host Hostname or IP address.
    :param password REST API password.
    :param path File system path.
    :return device URL or None if the device cannot be found.
    """
    if path:
        device_path = path
    elif host:
        # pylint: enable=no-member
        device_path = f"http://:{password}@{host}:{port}"
    else:
        device_path = find_device()
    return device_path


def sorted_by_directory_then_alpha(list_of_files):
    """
    Sort the list of files into alphabetical seperated
    with directories grouped together before files.
    """
    dirs = {}
    files = {}

    for cur_file in list_of_files:
        if cur_file["directory"]:
            dirs[cur_file["name"]] = cur_file
        else:
            files[cur_file["name"]] = cur_file

    sorted_dir_names = sorted(dirs.keys())
    sorted_file_names = sorted(files.keys())

    sorted_full_list = []
    for cur_name in sorted_dir_names:
        sorted_full_list.append(dirs[cur_name])
    for cur_name in sorted_file_names:
        sorted_full_list.append(files[cur_name])

    return sorted_full_list


def is_virtual_env_active():
    """
    Check if a virtual environment is currently active.

    We don't check the more commonly recommended way of checking if
    sys.prefix != sys.base_prefix as this will always be true if running circup
    from a pipx install. This way ensures the user manually activated a
    virtual environment, regardless how circup is installed.
    """
    return "VIRTUAL_ENV" in os.environ
