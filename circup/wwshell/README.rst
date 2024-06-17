
wwshell
=======

.. image:: https://readthedocs.org/projects/circup/badge/?version=latest
    :target: https://circuitpython.readthedocs.io/projects/circup/en/latest/
    :alt: Documentation Status

.. image:: https://img.shields.io/discord/327254708534116352.svg
    :target: https://adafru.it/discord
    :alt: Discord


.. image:: https://github.com/adafruit/circup/workflows/Build%20CI/badge.svg
    :target: https://github.com/adafruit/circup/actions
    :alt: Build Status


.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
    :alt: Code Style: Black


A tool to manage files on a CircuitPython device via wireless workflows.
Currently supports Web Workflow.

.. contents::

Installation
------------

wwshell is bundled along with Circup. When you install Circup you'll get wwshell automatically.

Circup requires Python 3.5 or higher.

In a `virtualenv <https://virtualenv.pypa.io/en/latest/>`_,
``pip install circup`` should do the trick. This is the simplest way to make it
work.

If you have no idea what a virtualenv is, try the following command,
``pip3 install --user circup``.

.. note::

    If you use the ``pip3`` command to install CircUp you must make sure that
    your path contains the directory into which the script will be installed.
    To discover this path,

    * On Unix-like systems, type ``python3 -m site --user-base`` and append
      ``bin`` to the resulting path.
    * On Windows, type the same command, but append ``Scripts`` to the
      resulting path.

What does wwshell do?
---------------------

It lets you view, delete, upload, and download files from your Circuitpython device
via wireless workflows. Similar to ampy, but operates over wireless workflow rather
than USB serial.

Usage
-----

To use web workflow you need to enable it by putting WIFI credentials and a web workflow
password into your settings.toml file. `See here <https://learn.adafruit.com/getting-started-with-web-workflow-using-the-code-editor/device-setup>`_,

To get help, just type the command::

    $ wwshell
    Usage: wwshell [OPTIONS] COMMAND [ARGS]...

      A tool to manage files CircuitPython device over web workflow.

    Options:
      --verbose          Comprehensive logging is sent to stdout.
      --path DIRECTORY   Path to CircuitPython directory. Overrides automatic path
                         detection.
      --host TEXT        Hostname or IP address of a device. Overrides automatic
                         path detection.
      --password TEXT    Password to use for authentication when --host is used.
                         You can optionally set an environment variable
                         CIRCUP_WEBWORKFLOW_PASSWORD instead of passing this
                         argument. If both exist the CLI arg takes precedent.
      --timeout INTEGER  Specify the timeout in seconds for any network
                         operations.
      --version          Show the version and exit.
      --help             Show this message and exit.

    Commands:
      get  Download a copy of a file or directory from the device to the...
      ls   Lists the contents of a directory.
      put  Upload a copy of a file or directory from the local computer to...
      rm   Delete a file on the device.


.. note::

    If you find a bug, or you want to suggest an enhancement or new feature
    feel free to create an issue or submit a pull request here:

    https://github.com/adafruit/circup


Discussion of this tool happens on the Adafruit CircuitPython
`Discord channel <https://discord.gg/rqrKDjU>`_.
