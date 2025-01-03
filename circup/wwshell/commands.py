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
import time
import sys
import logging
import update_checker
import click
import requests


from circup.backends import WebBackend
from circup.logging import logger, log_formatter, LOGFILE
from circup.shared import BOARDLESS_COMMANDS

from circup.command_utils import (
    get_device_path,
    get_circup_version,
    sorted_by_directory_then_alpha,
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
    default="circuitpython.local",
)
@click.option(
    "--port",
    help="HTTP port that the web workflow is listening on.",
    default=80,
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
@click.version_option(
    prog_name="CircFile",
    message="%(prog)s, A CircuitPython web workflow file managemenr. Version %(version)s",
)
@click.pass_context
def main(  # pylint: disable=too-many-locals
    ctx,
    verbose,
    path,
    host,
    port,
    password,
    timeout,
):  # pragma: no cover
    """
    A tool to manage files CircuitPython device over web workflow.
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
                host=host, port=port, password=password, logger=logger, timeout=timeout
            )
        except ValueError as e:
            click.secho(e, fg="red")
            time.sleep(0.3)
            sys.exit(1)
        except RuntimeError as e:
            click.secho(e, fg="red")
            sys.exit(1)

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

    logger.info("### Started Circfile ###")

    # If a newer version of circfile is available, print a message.
    logger.info("Checking for a newer version of circfile")
    version = get_circup_version()
    if version:
        update_checker.update_check("circfile", version)

    # stop early if the command is boardless
    if ctx.invoked_subcommand in BOARDLESS_COMMANDS or "--help" in sys.argv:
        return

    ctx.obj["DEVICE_PATH"] = device_path

    if device_path is None or not ctx.obj["backend"].is_device_present():
        click.secho("Could not find a connected CircuitPython device.", fg="red")
        sys.exit(1)
    else:
        click.echo("Found device at {}.".format(device_path))


@main.command("ls")
@click.argument("file", required=True, nargs=1, default="/")
@click.pass_context
def ls_cli(ctx, file):  # pragma: no cover
    """
    Lists the contents of a directory. Defaults to root directory
    if not supplied.
    """
    logger.info("ls")
    if not file.endswith("/"):
        file += "/"
    click.echo(f"running: ls {file}")

    files = ctx.obj["backend"].list_dir(file)
    click.echo("Size\tName")
    for cur_file in sorted_by_directory_then_alpha(files):
        click.echo(
            f"{cur_file['file_size']}\t{cur_file['name']}{'/' if cur_file['directory'] else ''}"
        )


@main.command("put")
@click.argument("file", required=True, nargs=1)
@click.argument("location", required=False, nargs=1, default="")
@click.option("--overwrite", is_flag=True, help="Overwrite the file if it exists.")
@click.pass_context
def put_cli(ctx, file, location, overwrite):
    """
    Upload a copy of a file or directory from the local computer
    to the device
    """
    click.echo(f"Attempting PUT: {file} at {location} overwrite? {overwrite}")
    if not ctx.obj["backend"].file_exists(f"{location}{file}"):
        ctx.obj["backend"].upload_file(file, location)
        click.echo(f"Successfully PUT {location}{file}")
    else:
        if overwrite:
            click.secho(
                f"{location}{file} already exists. Overwriting it.", fg="yellow"
            )
            ctx.obj["backend"].upload_file(file, location)
            click.echo(f"Successfully PUT {location}{file}")
        else:
            click.secho(
                f"{location}{file} already exists. Pass --overwrite if you wish to replace it.",
                fg="red",
            )


# pylint: enable=too-many-arguments,too-many-locals


@main.command("get")
@click.argument("file", required=True, nargs=1)
@click.argument("location", required=False, nargs=1)
@click.pass_context
def get_cli(ctx, file, location):  # pragma: no cover
    """
    Download a copy of a file or directory from the device to the local computer.
    """

    click.echo(f"running: get {file} {location}")
    ctx.obj["backend"].download_file(file, location)


@main.command("rm")
@click.argument("file", nargs=1)
@click.pass_context
def rm_cli(ctx, file):  # pragma: no cover
    """
    Delete a file on the device.
    """
    click.echo(f"running: rm {file}")
    ctx.obj["backend"].uninstall(
        ctx.obj["backend"].device_location, ctx.obj["backend"].get_file_path(file)
    )


@main.command("mkdir")
@click.argument("directory", nargs=1)
@click.pass_context
def mkdir_cli(ctx, directory):  # pragma: no cover
    """
    Create
    """
    click.echo(f"running: mkdir {directory}")
    ctx.obj["backend"].create_directory(
        ctx.obj["backend"].device_location, ctx.obj["backend"].get_file_path(directory)
    )
