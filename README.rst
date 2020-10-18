CircUp
======

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

What?
-----

Each CircuitPython library on the device (``.py``, *NOT* ``.mpy`` at this time)
usually has a version number as metadata within the module.

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

First, plug in a device running CircuiPython. This should appear as a mounted
storage device called ``CIRCUITPYTHON``.

To get help, just type the command::

    $ circup
    Usage: circup [OPTIONS] COMMAND [ARGS]...

      A tool to manage and update libraries on a CircuitPython device.

    Options:
      --verbose         Comprehensive logging is sent to stdout.
      --version         Show the version and exit.
      --help            Show this message and exit.
      -r --requirement  Supports requirements.txt tracking of library
                        requirements with freeze and install commands.

    Commands:
      freeze     Output details of all the modules found on the connected...
      install    Install a named module onto the device.
      list       Lists all out of date modules found on the connected...
      show       Show a list of available modules in the bundle.
      uninstall  Uninstall a named module(s) from the connected device.
      update     Update modules on the device. Use --all to automatically update
                 all modules.


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

Install a module onto the connected device with::

    $ circup install adafruit_thermal_printer
    Installed 'adafruit_thermal_printer'.

You can also install a list of modules from a requirements.txt file in
the current working directory with::

    $ circup install -r requirements.txt
    Installed 'adafruit_bmp280'.
    Installed 'adafruit_lis3mdl'.
    Installed 'adafruit_lsm6ds'.
    Installed 'adafruit_sht31d'.
    Installed 'neopixel'.

Uninstall a module like this::

    $ circup uninstall adafruit_thermal_printer
    Uninstalled 'adafruit_thermal_printer'.

Use the ``--verbose`` flag to see the logs as the command is working::

    $ circup --verbose freeze
    Logging to /home/ntoll/.cache/circup/log/circup.log

    10/18/2020 00:54:43 INFO: ### Started Circup ###
    10/18/2020 00:54:43 INFO: Found device: /Volumes/CIRCUITPY
    Found device at /Volumes/CIRCUITPY, running CircuitPython 6.0.0-alpha.1-1352-gf0b37313c.
    10/18/2020 00:54:44 INFO: Freeze
    10/18/2020 00:54:44 INFO: Found device: /Volumes/CIRCUITPY
    ... etc ...

Finally, the ``--version`` flag will tell you the current version of the
``circup`` command itself::

    $ circup --version
    CircUp, A CircuitPython module updater. Version 0.0.1

That's it!

.. note::

    If you find a bug, or you want to suggest an enhancement or new feature
    feel free to create an issue or submit a pull request here:

    https://github.com/adafruit/circup

Developer Setup
---------------

.. note::

    Please try to use Python 3.6+ while developing CircUp. This is so we can
    use the
    `Black code formatter <https://black.readthedocs.io/en/stable/index.html>`_
    (which only works with Python 3.6+).

Clone the repository then make a virtualenv. From the root of the project,
install the requirements::

    pip install -e ".[dev]"

Run the test suite::

    make check

.. warning::

    Whenever you run ``make check``, to ensure the test suite starts from a
    known clean state, all auto-generated assets are deleted. This includes
    assets generated by running ``pip install -e ".[dev]"``, including the
    ``circup`` command itself. Simply re-run ``pip`` to re-generate the
    assets.

There is a Makefile that helps with most of the common workflows associated
with development. Typing "make" on its own will list the options thus::

    $ make

    There is no default Makefile target right now. Try:

    make clean - reset the project and remove auto-generated assets.
    make pyflakes - run the PyFlakes code checker.
    make pycodestyle - run the PEP8 style checker.
    make test - run the test suite.
    make coverage - view a report on test coverage.
    make tidy - tidy code with the 'black' formatter.
    make check - run all the checkers and tests.
    make dist - make a dist/wheel for the project.
    make publish-test - publish the project to PyPI test instance.
    make publish-live - publish the project to PyPI production.
    make docs - run sphinx to create project documentation.

.. note::

    On Windows there is a ``make.cmd`` file that calls ``make.py``: a script
    that works in a similar way to the ``make`` command on Unix-like operating
    systems. Typing ``make`` will display help for the various commands it
    provides that are equivalent of those in the Unix Makefile.

How?
####

The ``circup`` tool checks for a connected CircuitPython device by
interrogating the local filesystem to find a path to a directory which ends
with ``"CIRCUITPYTHON"`` (the name under which a CircuitPython device is
mounted by the host operating system). This is handled in the ``find_device``
function.

A Python module on a connected device is represented by an instance of the
``Module`` class. This class provides useful methods for discerning if the
module is out of date, returning useful representations of it in order to
display information to the user, or updating the module on the connected
device with whatever the version is in the latest Adafruit CircuitPython
Bundle.

All of the libraries included in the Adafruit CircuitPython Bundle contain,
somewhere within their code, two metadata objects called ``__version__`` and
``__repo__``.

The ``__repo__`` object is a string containing the GitHub repository URL, as
used to clone the project.

The ``__version__`` object is interesting because *within the source code in
Git* the value is **always** the string ``"0.0.0-auto.0"``. When a new release
is made of the bundle, this value is automatically replaced by the build
scripts to the correct version information, which will always conform to the
`semver standard <https://semver.org/>`_.

Given this context, the ``circup`` tool will check a configuration file
to discern what *it* thinks is the latest version of the bundle. If there is
no configuration file (for example, on first run), then the bundle version is
assumed to be ``"0"``.

Next, it checks GitHub for the tag value (denoting the version) of the very
latest bundle release. Bundle versions are based upon the date of release, for
instance ``"20190904"``. If the latest version on GitHub is later than the
version ``circup`` currently has, then the latest version of the bundle
is automatically downloaded and cached away somewhere.

In this way, the ``circup`` tool is able to have available to it both a path
to a connected CIRCUITPYTHON devce and a copy of the latest version, including
the all important version information, of the Adafruit CircuitPython Bundle.

Exactly the same function (``get_modules``) is used to extract the metadata
from the modules on both the connected device and in the bundle cache. This
metadata is used to instantiate instances of the ``Module`` class which is
subsequently used to facilitate the various commands the tool makes available.

These commands are defined at the very end of the ``circup.py`` code.

Unit tests can be found in the ``tests`` directory. CircUp uses
`pytest <http://www.pytest.org/en/latest/>`_ style testing conventions. Test
functions should include a comment to describe its *intention*. We currently
have 100% unit test coverage for all the core functionality (excluding
functions used to define the CLI commands).

To run the full test suite, type::

    make check

All code is formatted using the stylistic conventions enforced by
`black <https://black.readthedocs.io/en/stable/>`_. The tidying of code
formatting is part of the ``make check`` process, but you can also just use::

    make tidy

Please see the output from ``make`` for more information about the various
available options to help you work with the code base. TL;DR ``make check``
runs everything.

Before submitting a PR, please remember to ``make check``. ;-)

CircUp uses the `Click <https://click.palletsprojects.com/en/7.x/>`_ module to
run command-line interaction. The
`AppDirs <https://pypi.org/project/appdirs/>`_ module is used to determine
where to store user-specific assets created by the tool in such a way that
meets the host operating system's usual conventions. The
`python-semver <https://github.com/k-bx/python-semver>`_ package is used to
validate and compare the semver values associated with modules. The ubiquitous
`requests <http://python-requests.org/>`_ module is used for HTTP activity.

Documentation, generated by `Sphinx <http://www.sphinx-doc.org/en/master/>`_,
is based on this README and assembled by assets in the ``doc`` subdirectory.
The latest version of the docs will be found on
`Read the Docs <https://circup.readthedocs.io/>`_.

Discussion of this tool happens on the Adafruit CircuitPython
`Discord channel <https://discord.gg/rqrKDjU>`_.
