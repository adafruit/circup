# SPDX-FileCopyrightText: 2019 Nicholas Tollervey, 2024 Tim Cocks, written for Adafruit Industries
#
# SPDX-License-Identifier: MIT
"""
# ----------- CLI command definitions  ----------- #

The following functions have IO side effects (for instance they emit to
stdout). Ergo, these are not checked with unit tests. Most of the
functionality they provide is provided by the functions from util_functions.py,
and the respective Backends which *are* tested. Most of the logic of the following
functions is to prepare things for presentation to / interaction with the user.
"""
import os
import subprocess
import time
import sys
import re
import logging
import update_checker
from semver import VersionInfo
import click
import requests


from circup.backends import WebBackend, DiskBackend
from circup.logging import logger, log_formatter, LOGFILE
from circup.shared import BOARDLESS_COMMANDS, get_latest_release_from_url
from circup.bundle import Bundle
from circup.command_utils import (
    get_device_path,
    get_circup_version,
    find_modules,
    get_bundles_list,
    completion_for_install,
    get_bundle_versions,
    libraries_from_requirements,
    libraries_from_auto_file,
    get_dependencies,
    get_bundles_local_dict,
    save_local_bundles,
    get_bundles_dict,
    completion_for_example,
    get_bundle_examples,
    is_virtual_env_active,
)


@click.group()
@click.option(
    "--verbose", is_flag=True, help="Comprehensive logging is sent to stdout."
)
@click.option(
    "--path",
    type=click.Path(exists=True, file_okay=False),
    help="Path to CircuitPython directory. Overrides automatic path detection.",
)
@click.option(
    "--host",
    help="Hostname or IP address of a device. Overrides automatic path detection.",
)
@click.option(
    "--port", help="Port to contact. Overrides automatic path detection.", default=80
)
@click.option(
    "--password",
    help="Password to use for authentication when --host is used."
    " You can optionally set an environment variable CIRCUP_WEBWORKFLOW_PASSWORD"
    " instead of passing this argument. If both exist the CLI arg takes precedent.",
)
@click.option(
    "--timeout",
    default=30,
    help="Specify the timeout in seconds for any network operations.",
)
@click.option(
    "--board-id",
    default=None,
    help="Manual Board ID of the CircuitPython device. If provided in combination "
    "with --cpy-version, it overrides the detected board ID.",
)
@click.option(
    "--cpy-version",
    default=None,
    help="Manual CircuitPython version. If provided in combination "
    "with --board-id, it overrides the detected CPy version.",
)
@click.version_option(
    prog_name="Circup",
    message="%(prog)s, A CircuitPython module updater. Version %(version)s",
)
@click.pass_context
def main(  # pylint: disable=too-many-locals
    ctx, verbose, path, host, port, password, timeout, board_id, cpy_version
):  # pragma: no cover
    """
    A tool to manage and update libraries on a CircuitPython device.
    """
    # pylint: disable=too-many-arguments,too-many-branches,too-many-statements,too-many-locals, R0801
    ctx.ensure_object(dict)
    ctx.obj["TIMEOUT"] = timeout

    if password is None:
        password = os.getenv("CIRCUP_WEBWORKFLOW_PASSWORD")

    device_path = get_device_path(host, port, password, path)

    using_webworkflow = "host" in ctx.params.keys() and ctx.params["host"] is not None

    if using_webworkflow:
        if host == "circuitpython.local":
            click.echo("Checking versions.json on circuitpython.local to find hostname")
            versions_resp = requests.get(
                "http://circuitpython.local/cp/version.json", timeout=timeout
            )
            host = f'{versions_resp.json()["hostname"]}.local'
            click.echo(f"Using hostname: {host}")
            device_path = device_path.replace("circuitpython.local", host)
        try:
            ctx.obj["backend"] = WebBackend(
                host=host,
                port=port,
                password=password,
                logger=logger,
                timeout=timeout,
                version_override=cpy_version,
            )
        except ValueError as e:
            click.secho(e, fg="red")
            time.sleep(0.3)
            sys.exit(1)
        except RuntimeError as e:
            click.secho(e, fg="red")
            sys.exit(1)
    else:
        try:
            ctx.obj["backend"] = DiskBackend(
                device_path,
                logger,
                version_override=cpy_version,
            )
        except ValueError as e:
            print(e)

    if verbose:
        # Configure additional logging to stdout.
        ctx.obj["verbose"] = True
        verbose_handler = logging.StreamHandler(sys.stdout)
        verbose_handler.setLevel(logging.INFO)
        verbose_handler.setFormatter(log_formatter)
        logger.addHandler(verbose_handler)
        click.echo("Logging to {}\n".format(LOGFILE))
    else:
        ctx.obj["verbose"] = False

    logger.info("### Started Circup ###")

    # If a newer version of circup is available, print a message.
    logger.info("Checking for a newer version of circup")
    version = get_circup_version()
    if version:
        update_checker.update_check("circup", version)

    # stop early if the command is boardless
    if ctx.invoked_subcommand in BOARDLESS_COMMANDS or "--help" in sys.argv:
        return

    ctx.obj["DEVICE_PATH"] = device_path
    latest_version = get_latest_release_from_url(
        "https://github.com/adafruit/circuitpython/releases/latest", logger
    )

    if device_path is None or not ctx.obj["backend"].is_device_present():
        click.secho("Could not find a connected CircuitPython device.", fg="red")
        sys.exit(1)
    else:
        cpy_version, board_id = (
            ctx.obj["backend"].get_circuitpython_version()
            if board_id is None or cpy_version is None
            else (cpy_version, board_id)
        )
        click.echo(
            "Found device {} at {}, running CircuitPython {}.".format(
                board_id, device_path, cpy_version
            )
        )
    try:
        if VersionInfo.parse(cpy_version) < VersionInfo.parse(latest_version):
            click.secho(
                "A newer version of CircuitPython ({}) is available.".format(
                    latest_version
                ),
                fg="green",
            )
            if board_id:
                url_download = f"https://circuitpython.org/board/{board_id}"
            else:
                url_download = "https://circuitpython.org/downloads"
            click.secho("Get it here: {}".format(url_download), fg="green")
    except ValueError as ex:
        logger.warning("CircuitPython has incorrect semver value.")
        logger.warning(ex)


@main.command()
@click.option("-r", "--requirement", is_flag=True)
@click.pass_context
def freeze(ctx, requirement):  # pragma: no cover
    """
    Output details of all the modules found on the connected CIRCUITPYTHON
    device. Option -r saves output to requirements.txt file
    """
    logger.info("Freeze")
    modules = find_modules(ctx.obj["backend"], get_bundles_list())
    if modules:
        output = []
        for module in modules:
            output.append("{}=={}".format(module.name, module.device_version))
        for module in output:
            click.echo(module)
            logger.info(module)
        if requirement:
            cwd = os.path.abspath(os.getcwd())
            for i, module in enumerate(output):
                output[i] += "\n"

            overwrite = None
            if os.path.exists(os.path.join(cwd, "requirements.txt")):
                overwrite = click.confirm(
                    click.style(
                        "\nrequirements.txt file already exists in this location.\n"
                        "Do you want to overwrite it?",
                        fg="red",
                    ),
                    default=False,
                )
            else:
                overwrite = True

            if overwrite:
                with open(
                    cwd + "/" + "requirements.txt", "w", newline="\n", encoding="utf-8"
                ) as file:
                    file.truncate(0)
                    file.writelines(output)
    else:
        click.echo("No modules found on the device.")


@main.command("list")
@click.pass_context
def list_cli(ctx):  # pragma: no cover
    """
    Lists all out of date modules found on the connected CIRCUITPYTHON device.
    """
    logger.info("List")
    # Grab out of date modules.
    data = [("Module", "Version", "Latest", "Update Reason")]

    modules = [
        m.row
        for m in find_modules(ctx.obj["backend"], get_bundles_list())
        if m.outofdate
    ]
    if modules:
        data += modules
        # Nice tabular display.
        col_width = [0, 0, 0, 0]
        for row in data:
            for i, word in enumerate(row):
                col_width[i] = max(len(word) + 2, col_width[i])
        dashes = tuple(("-" * (width - 1) for width in col_width))
        data.insert(1, dashes)
        click.echo(
            "The following modules are out of date or probably need an update.\n"
            "Major Updates may include breaking changes. Review before updating.\n"
            "MPY Format changes from Circuitpython 8 to 9 require an update.\n"
        )
        for row in data:
            output = ""
            for index, cell in enumerate(row):
                output += cell.ljust(col_width[index])
            if "--verbose" not in sys.argv:
                click.echo(output)
            logger.info(output)
    else:
        click.echo("All modules found on the device are up to date.")


# pylint: disable=too-many-arguments,too-many-locals
@main.command()
@click.argument(
    "modules", required=False, nargs=-1, shell_complete=completion_for_install
)
@click.option(
    "pyext",
    "--py",
    is_flag=True,
    help="Install the .py version of the module(s) instead of the mpy version.",
)
@click.option(
    "-r",
    "--requirement",
    type=click.Path(exists=True, dir_okay=False),
    help="specify a text file to install all modules listed in the text file."
    " Typically requirements.txt.",
)
@click.option(
    "--auto", "-a", is_flag=True, help="Install the modules imported in code.py."
)
@click.option(
    "--upgrade", "-U", is_flag=True, help="Upgrade modules that are already installed."
)
@click.option(
    "--stubs",
    "-s",
    is_flag=True,
    help="Install stubs module from PyPi for context in IDE.",
)
@click.option(
    "--auto-file",
    default=None,
    help="Specify the name of a file on the board to read for auto install."
    " Also accepts an absolute path or a local ./ path.",
)
@click.pass_context
def install(
    ctx, modules, pyext, requirement, auto, auto_file, upgrade=False, stubs=False
):  # pragma: no cover
    """
    Install a named module(s) onto the device. Multiple modules
    can be installed at once by providing more than one module name, each
    separated by a space. Modules can be from a Bundle or local filepaths.
    """

    # pylint: disable=too-many-branches
    # TODO: Ensure there's enough space on the device
    available_modules = get_bundle_versions(get_bundles_list())
    mod_names = {}
    for module, metadata in available_modules.items():
        mod_names[module.replace(".py", "").lower()] = metadata
    if requirement:
        with open(requirement, "r", encoding="utf-8") as rfile:
            requirements_txt = rfile.read()
        requested_installs = libraries_from_requirements(requirements_txt)
    elif auto or auto_file:
        requested_installs = libraries_from_auto_file(
            ctx.obj["backend"], auto_file, mod_names
        )
    else:
        requested_installs = modules

    requested_installs = sorted(set(requested_installs))
    click.echo(f"Searching for dependencies for: {requested_installs}")
    to_install = get_dependencies(requested_installs, mod_names=mod_names)
    device_modules = ctx.obj["backend"].get_device_versions()
    if to_install is not None:
        to_install = sorted(to_install)
        is_global_install_ok = None
        click.echo(f"Ready to install: {to_install}\n")
        for library in to_install:
            ctx.obj["backend"].install_module(
                ctx.obj["DEVICE_PATH"],
                device_modules,
                library,
                pyext,
                mod_names,
                upgrade,
            )

            if stubs:
                # Check we are in a virtual environment
                if not is_virtual_env_active():
                    if is_global_install_ok is None:
                        click.secho(
                            (
                                "No virtual environment detected.\n"
                                "It is recommended to run circup inside a virtual environment "
                                "when installing stubs. Without a virtual environment, the stubs "
                                "will be installed to the global python."
                            ),
                            fg="yellow",
                        )
                        is_global_install_ok = click.confirm(
                            click.style(
                                "Would you still like to install stubs (to the global python)?",
                                fg="yellow",
                            )
                        )
                    if not is_global_install_ok:
                        continue
                library_stubs = "adafruit-circuitpython-{}".format(
                    library.replace("adafruit_", "")
                )
                try:
                    output = subprocess.check_output(["pip", "install", library_stubs])
                    if (
                        f"Requirement already satisfied: {library_stubs}"
                        in output.decode()
                    ):
                        click.echo(f"'{library}' stubs already installed.")
                    else:
                        click.echo(f"Installed '{library}' stubs.")
                except subprocess.CalledProcessError:
                    click.secho(
                        f"Could not install stubs module {library_stubs}", fg="yellow"
                    )


@main.command()
@click.option("--overwrite", is_flag=True, help="Overwrite the file if it exists.")
@click.option("--list", "-ls", "op_list", is_flag=True, help="List available examples.")
@click.option("--rename", is_flag=True, help="Install the example as code.py.")
@click.argument(
    "examples", required=False, nargs=-1, shell_complete=completion_for_example
)
@click.pass_context
def example(ctx, examples, op_list, rename, overwrite):
    """
    Copy named example(s) from a bundle onto the device. Multiple examples
    can be installed at once by providing more than one example name, each
    separated by a space.
    """

    if op_list:
        if examples:
            click.echo("\n".join(completion_for_example(ctx, "", examples)))
        else:
            click.echo("Available example libraries:")
            available_examples = get_bundle_examples(
                get_bundles_list(), avoid_download=True
            )
            lib_names = {
                str(key.split(os.path.sep)[0]): value
                for key, value in available_examples.items()
            }
            click.echo("\n".join(sorted(lib_names.keys())))
        return

    for example_arg in examples:
        available_examples = get_bundle_examples(
            get_bundles_list(), avoid_download=True
        )
        if example_arg in available_examples:
            filename = available_examples[example_arg].split(os.path.sep)[-1]
            install_metadata = {"path": available_examples[example_arg]}

            filename = available_examples[example_arg].split(os.path.sep)[-1]
            if rename:
                if os.path.isfile(available_examples[example_arg]):
                    filename = "code.py"
                    install_metadata["target_name"] = filename

            if overwrite or not ctx.obj["backend"].file_exists(filename):
                click.echo(
                    f"{'Copying' if not overwrite else 'Overwriting'}: {filename}"
                )
                ctx.obj["backend"].install_module_py(install_metadata, location="")
            else:
                click.secho(
                    f"File: {filename} already exists. Use --overwrite if you wish to replace it.",
                    fg="red",
                )
        else:
            click.secho(
                f"Error: {example_arg} was not found in any local bundle examples.",
                fg="red",
            )


# pylint: enable=too-many-arguments,too-many-locals


@main.command()
@click.argument("match", required=False, nargs=1)
def show(match):  # pragma: no cover
    """
    Show a list of available modules in the bundle. These are modules which
    *could* be installed on the device.

    If MATCH is specified only matching modules will be listed.
    """
    available_modules = get_bundle_versions(get_bundles_list())
    module_names = sorted([m.replace(".py", "") for m in available_modules])
    if match is not None:
        match = match.lower()
        module_names = [m for m in module_names if match in m]
    click.echo("\n".join(module_names))

    click.echo(
        "{} shown of {} packages.".format(len(module_names), len(available_modules))
    )


@main.command()
@click.argument("module", nargs=-1)
@click.pass_context
def uninstall(ctx, module):  # pragma: no cover
    """
    Uninstall a named module(s) from the connected device. Multiple modules
    can be uninstalled at once by providing more than one module name, each
    separated by a space.
    """
    device_path = ctx.obj["DEVICE_PATH"]
    print(f"Uninstalling {module} from {device_path}")
    for name in module:
        device_modules = ctx.obj["backend"].get_device_versions()
        name = name.lower()
        mod_names = {}
        for module_item, metadata in device_modules.items():
            mod_names[module_item.replace(".py", "").lower()] = metadata
        if name in mod_names:
            metadata = mod_names[name]
            module_path = metadata["path"]
            ctx.obj["backend"].uninstall(device_path, module_path)
            click.echo("Uninstalled '{}'.".format(name))
        else:
            click.echo("Module '{}' not found on device.".format(name))
        continue


# pylint: disable=too-many-branches


@main.command(
    short_help=(
        "Update modules on the device. "
        "Use --all to automatically update all modules without Major Version warnings."
    )
)
@click.option(
    "update_all",
    "--all",
    is_flag=True,
    help="Update all modules without Major Version warnings.",
)
@click.pass_context
# pylint: disable=too-many-locals
def update(ctx, update_all):  # pragma: no cover
    """
    Checks for out-of-date modules on the connected CIRCUITPYTHON device, and
    prompts the user to confirm updating such modules.
    """
    logger.info("Update")
    # Grab current modules.
    bundles_list = get_bundles_list()
    installed_modules = find_modules(ctx.obj["backend"], bundles_list)
    modules_to_update = [m for m in installed_modules if m.outofdate]

    if not modules_to_update:
        click.echo("None of the module[s] found on the device need an update.")
        return

    # Process out of date modules
    updated_modules = []
    click.echo("Found {} module[s] needing update.".format(len(modules_to_update)))
    if not update_all:
        click.echo("Please indicate which module[s] you wish to update:\n")
    for module in modules_to_update:
        update_flag = update_all
        if "--verbose" in sys.argv:
            click.echo(
                "Device version: {}, Bundle version: {}".format(
                    module.device_version, module.bundle_version
                )
            )
        if isinstance(module.bundle_version, str) and not VersionInfo.is_valid(
            module.bundle_version
        ):
            click.secho(
                f"WARNING: Library {module.name} repo has incorrect __version__"
                "\n\tmetadata. Circup will assume it needs updating."
                "\n\tPlease file an issue in the library repo.",
                fg="yellow",
            )
            if module.repo:
                click.secho(f"\t{module.repo}", fg="yellow")
        if not update_flag:
            if module.bad_format:
                click.secho(
                    f"WARNING: '{module.name}': module corrupted or in an"
                    " unknown mpy format. Updating is required.",
                    fg="yellow",
                )
                update_flag = click.confirm("Do you want to update?")
            elif module.mpy_mismatch:
                click.secho(
                    f"WARNING: '{module.name}': mpy format doesn't match the"
                    " device's Circuitpython version. Updating is required.",
                    fg="yellow",
                )
                update_flag = click.confirm("Do you want to update?")
            elif module.major_update:
                update_flag = click.confirm(
                    (
                        "'{}' is a Major Version update and may contain breaking "
                        "changes. Do you want to update?".format(module.name)
                    )
                )
            else:
                update_flag = click.confirm("Update '{}'?".format(module.name))
        if update_flag:
            # pylint: disable=broad-except
            try:
                ctx.obj["backend"].update(module)
                updated_modules.append(module.name)
                click.echo("Updated {}".format(module.name))
            except Exception as ex:
                logger.exception(ex)
                click.echo("Something went wrong, {} (check the logs)".format(str(ex)))
            # pylint: enable=broad-except

    if not updated_modules:
        return

    # We updated modules, look to see if any requirements are missing
    click.echo(
        "Checking {} updated module[s] for missing requirements.".format(
            len(updated_modules)
        )
    )
    available_modules = get_bundle_versions(bundles_list)
    mod_names = {}
    for module, metadata in available_modules.items():
        mod_names[module.replace(".py", "").lower()] = metadata
    missing_modules = get_dependencies(updated_modules, mod_names=mod_names)
    device_modules = ctx.obj["backend"].get_device_versions()
    # Process newly needed modules
    if missing_modules is not None:
        installed_module_names = [m.name for m in installed_modules]
        missing_modules = set(missing_modules) - set(installed_module_names)
        missing_modules = sorted(list(missing_modules))
        click.echo(f"Ready to install: {missing_modules}\n")
        for library in missing_modules:
            ctx.obj["backend"].install_module(
                ctx.obj["DEVICE_PATH"], device_modules, library, False, mod_names
            )


# pylint: enable=too-many-branches


@main.command("bundle-show")
@click.option("--modules", is_flag=True, help="List all the modules per bundle.")
def bundle_show(modules):
    """
    Show the list of bundles, default and local, with URL, current version
    and latest version retrieved from the web.
    """
    local_bundles = get_bundles_local_dict().values()
    bundles = get_bundles_list()
    available_modules = get_bundle_versions(bundles)

    for bundle in bundles:
        if bundle.key in local_bundles:
            click.secho(bundle.key, fg="yellow")
        else:
            click.secho(bundle.key, fg="green")
        click.echo("    " + bundle.url)
        click.echo("    version = " + bundle.current_tag)
        if modules:
            click.echo("Modules:")
            for name, mod in sorted(available_modules.items()):
                if mod["bundle"] == bundle:
                    click.echo(f"   {name} ({mod.get('__version__', '-')})")


@main.command("bundle-add")
@click.argument("bundle", nargs=-1)
@click.pass_context
def bundle_add(ctx, bundle):
    """
    Add bundles to the local bundles list, by "user/repo" github string.
    A series of tests to validate that the bundle exists and at least looks
    like a bundle are done before validating it. There might still be errors
    when the bundle is downloaded for the first time.
    """

    if len(bundle) == 0:
        click.secho(
            "Must pass bundle argument, expecting github URL or `user/repository` string.",
            fg="red",
        )
        return

    bundles_dict = get_bundles_local_dict()
    modified = False
    for bundle_repo in bundle:
        # cleanup in case seombody pastes the URL to the repo/releases
        bundle_repo = re.sub(
            r"https?://github.com/([^/]+/[^/]+)(/.*)?", r"\1", bundle_repo
        )
        if bundle_repo in bundles_dict.values():
            click.secho("Bundle already in list.", fg="yellow")
            click.secho("    " + bundle_repo, fg="yellow")
            continue
        try:
            bundle_added = Bundle(bundle_repo)
        except ValueError:
            click.secho(
                "Bundle string invalid, expecting github URL or `user/repository` string.",
                fg="red",
            )
            click.secho("    " + bundle_repo, fg="red")
            continue
        result = requests.get(
            "https://github.com/" + bundle_repo, timeout=ctx.obj["TIMEOUT"]
        )
        # pylint: disable=no-member
        if result.status_code == requests.codes.NOT_FOUND:
            click.secho("Bundle invalid, the repository doesn't exist (404).", fg="red")
            click.secho("    " + bundle_repo, fg="red")
            continue
        # pylint: enable=no-member
        if not bundle_added.validate():
            click.secho(
                "Bundle invalid, is the repository a valid circup bundle ?", fg="red"
            )
            click.secho("    " + bundle_repo, fg="red")
            continue
        # note: use bun as the dictionary key for uniqueness
        bundles_dict[bundle_repo] = bundle_repo
        modified = True
        click.echo("Added " + bundle_repo)
        click.echo("    " + bundle_added.url)
    if modified:
        # save the bundles list
        save_local_bundles(bundles_dict)
        # update and get the new bundles for the first time
        get_bundle_versions(get_bundles_list())


@main.command("bundle-remove")
@click.argument("bundle", nargs=-1)
@click.option("--reset", is_flag=True, help="Remove all local bundles.")
def bundle_remove(bundle, reset):
    """
    Remove one or more bundles from the local bundles list.
    """
    if reset:
        save_local_bundles({})
        return

    if len(bundle) == 0:
        click.secho(
            "Must pass bundle argument or --reset, expecting github URL or "
            "`user/repository` string. Run circup bundle-show to see a list of bundles.",
            fg="red",
        )
        return
    bundle_config = list(get_bundles_dict().values())
    bundles_local_dict = get_bundles_local_dict()
    modified = False
    for bun in bundle:
        # cleanup in case somebody pastes the URL to the repo/releases
        bun = re.sub(r"https?://github.com/([^/]+/[^/]+)(/.*)?", r"\1", bun)
        found = False
        for name, repo in list(bundles_local_dict.items()):
            if bun in (name, repo):
                found = True
                click.secho(f"Bundle {repo}")
                do_it = click.confirm("Do you want to remove that bundle ?")
                if do_it:
                    click.secho("Removing the bundle from the local list", fg="yellow")
                    click.secho(f"    {bun}", fg="yellow")
                    modified = True
                    del bundles_local_dict[name]
        if not found:
            if bun in bundle_config:
                click.secho("Cannot remove built-in module:" "\n    " + bun, fg="red")
            else:
                click.secho(
                    "Bundle not found in the local list, nothing removed:"
                    "\n    " + bun,
                    fg="red",
                )
    if modified:
        save_local_bundles(bundles_local_dict)
