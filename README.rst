CircUp
======

A tool to manage and update libraries (modules) on a CircuitPython device.

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

    * On unix-like systems, type ``python3 -m site --user-base`` and append
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
      --verbose  Comprehensive logging is sent to stdout.
      --version  Show the version and exit.
      --help     Show this message and exit.

    Commands:
      freeze  Output details of all the modules found on the connected...
      list    Lists all out of date modules found on the connected
              CIRCUITPYTHON...
      update  Checks for out-of-date modules on the connected CIRCUITPYTHON...

To show version information for all the modules currently on a connected
CIRCUITPYTHON device::

    $ circup freeze
    Logging to /home/ntoll/.cache/circup/log/circup.log

    adafruit_binascii==v1.0
    adafruit_bme280==2.3.1
    adafruit_ble==1.0.2

To list all the modules that require an update::

    $ circup list
    Logging to /home/ntoll/.cache/circup/log/circup.log

    The following modules are out of date or probably need an update.

    Module             Version  Latest   
    ------------------ -------- -------- 
    adafruit_binascii  v1.0     1.0.1    
    adafruit_ble       1.0.2    4.0

To interactively update the out-of-date modules::

    $ circup update
    Logging to /home/ntoll/.cache/circup/log/circup.log

    Found 3 module[s] needing update.
    Please indicate which modules you wish to update:

    Update 'adafruit_binascii'? [y/N]: Y
    OK
    Update 'adafruit_ble'? [y/N]: Y
    OK

Use the ``--verbose`` flag to see the logs as the command is working::

    $ circup --verbose freeze



    Started 2019-09-05 13:13:41.031822
    INFO: Freeze
    INFO: Found device: /media/ntoll/CIRCUITPY
    ... etc ...

Finally, the ``--version`` flag will tell you the current version of the
``circup`` command itself::

    $ circup --version
    CircUp, A CircuitPython module updater. Version 0.0.1

That's it!

.. note::

    If you find a bug, or you want to suggest an enhancement or new feature
    feel free to submit a bug report or pull request here:

    https://github.com/adafruit/circup

Developer Setup
---------------

Clone the repository then make a virtualenv. From the root of the project,
install the requirements::

    pip install -r ".[dev]"

Run the test suite::

    make check

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
