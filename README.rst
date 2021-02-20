
CircUp
======

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


A tool to manage and update libraries (modules) on a CircuitPython device.

.. contents::

Installation
------------

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

What does Circup Do?
--------------------

Each CircuitPython library on the device usually has a version number as
metadata within the module.

This utility looks at all the libraries on the device and checks if they are
the most recent (compared to the versions found in the most recent version of
the Adafruit CircuitPython Bundle). If the libraries are out of date, the
utility helps you update them.

The Adafruit CircuitPython Bundle can be found here:

https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/latest

Full details of these libraries, what they're for and how to get them, can be
found here:

https://circuitpython.org/libraries

Usage
-----

If you need more detailed help using Circup see the Learn Guide article
`"Use CircUp to easily keep your CircuitPython libraries up to date" <https://learn.adafruit.com/keep-your-circuitpython-libraries-on-devices-up-to-date-with-circup/>`_.

First, plug in a device running CircuiPython. This should appear as a mounted
storage device called ``CIRCUITPY``.

To get help, just type the command::

    $ circup
    Usage: circup [OPTIONS] COMMAND [ARGS]...

      A tool to manage and update libraries on a CircuitPython device.

    Options:
      --verbose         Comprehensive logging is sent to stdout.
      --version         Show the version and exit.
      --path DIRECTORY  Path to CircuitPython directory. Overrides automatic
                        path detection.
      --help            Show this message and exit.
      -r --requirement  Supports requirements.txt tracking of library
                        requirements with freeze and install commands.

    Commands:
      freeze        Output details of all the modules found on the connected...
      install       Install a named module(s) onto the device.
      list          Lists all out of date modules found on the connected...
      show          Show the long list of all available modules in the bundle.
      show <query>  Search the names in the modules in the bundle for a match.
      uninstall     Uninstall a named module(s) from the connected device.
      update        Update modules on the device. Use --all to automatically update
                    all modules.


To search for a specific module containing the name bme:
:code:`$ circup show bme`::

    $ circup show bme
    Found device at /Volumes/CIRCUITPY, running CircuitPython 6.1.0-beta.2.
    adafruit_bme280
    adafruit_bme680
    2 shown of 257 packages.

To show version information for all the modules currently on a connected
CIRCUITPYTHON device::

    $ circup freeze
    adafruit_binascii==v1.0
    adafruit_bme280==2.3.1
    adafruit_ble==1.0.2

With :code:`$ circup freeze -r`, Circup will save, in the current working directory,
a requirements.txt file with a list of all modules currently installed on the
connected device.

To list all the modules that require an update::

    $ circup list
    The following modules are out of date or probably need an update.

    Module             Version  Latest
    ------------------ -------- --------
    adafruit_binascii  v1.0     1.0.1
    adafruit_ble       1.0.2    4.0

To interactively update the out-of-date modules::

    $ circup update
    Found 3 module[s] needing update.
    Please indicate which modules you wish to update:

    Update 'adafruit_binascii'? [y/N]: Y
    OK
    Update 'adafruit_ble'? [y/N]: Y
    OK

Install a module or modules onto the connected device with::

    $ circup install adafruit_thermal_printer
    Installed 'adafruit_thermal_printer'.

    $ circup install adafruit_thermal_printer adafruit_bus_io
    Installed 'adafruit_thermal_printer'.
    Installed 'adafruit_bus_io'.

You can also install a list of modules from a requirements.txt file in
the current working directory with::

    $ circup install -r requirements.txt
    Installed 'adafruit_bmp280'.
    Installed 'adafruit_lis3mdl'.
    Installed 'adafruit_lsm6ds'.
    Installed 'adafruit_sht31d'.
    Installed 'neopixel'.

Uninstall a module or modules like this::

    $ circup uninstall adafruit_thermal_printer
    Uninstalled 'adafruit_thermal_printer'.

    $ circup uninstall adafruit_thermal_printer adafruit_bus_io
    Uninstalled 'adafruit_thermal_printer'.
    Uninstalled 'adafruit_bus_io'.

Use the ``--verbose`` flag to see the logs as the command is working::

    $ circup --verbose freeze
    Logging to /home/ntoll/.cache/circup/log/circup.log

    10/18/2020 00:54:43 INFO: ### Started Circup ###
    10/18/2020 00:54:43 INFO: Found device: /Volumes/CIRCUITPY
    Found device at /Volumes/CIRCUITPY, running CircuitPython 6.0.0-alpha.1-1352-gf0b37313c.
    10/18/2020 00:54:44 INFO: Freeze
    10/18/2020 00:54:44 INFO: Found device: /Volumes/CIRCUITPY
    ... etc ...

The ``--path`` flag let's you pass in a different path to the CircuitPython
mounted volume. This is helpful when you have renamed or have more than one
CircuitPython devices attached::

    $ circup --path /run/media/user/CIRCUITPY1 list

The ``--version`` flag will tell you the current version of the
``circup`` command itself::

    $ circup --version
    CircUp, A CircuitPython module updater. Version 0.0.1

That's it!

.. note::

    If you find a bug, or you want to suggest an enhancement or new feature
    feel free to create an issue or submit a pull request here:

    https://github.com/adafruit/circup


Discussion of this tool happens on the Adafruit CircuitPython
`Discord channel <https://discord.gg/rqrKDjU>`_.
