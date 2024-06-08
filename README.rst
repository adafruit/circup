
Circup
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

Circup requires Python 3.9 or higher.

In a `virtualenv <https://virtualenv.pypa.io/en/latest/>`_,
``pip install circup`` should do the trick. This is the simplest way to make it
work.

If you have no idea what a virtualenv is, try the following command,
``pip3 install --user circup``.

.. note::

    If you use the ``pip3`` command to install Circup you must make sure that
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
the Adafruit CircuitPython Bundle and Circuitpython Community Bundle). If the libraries are out of date, the
utility helps you update them.

The Adafruit CircuitPython Bundle can be found here:

https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/latest

Full details of these libraries, what they're for and how to get them, can be
found here:

https://circuitpython.org/libraries

The Circuitpython Community Bundle can be found here:

https://github.com/adafruit/CircuitPython_Community_Bundle/releases/latest

Usage
-----

If you need more detailed help using Circup see the Learn Guide article
`"Use Circup to easily keep your CircuitPython libraries up to date" <https://learn.adafruit.com/keep-your-circuitpython-libraries-on-devices-up-to-date-with-circup/>`_.

First, plug in a device running CircuiPython. This should appear as a mounted
storage device called ``CIRCUITPY``.

To get help, just type the command::

    $ circup
    Usage: circup [OPTIONS] COMMAND [ARGS]...

      A tool to manage and update libraries on a CircuitPython device.

    Options:
      --verbose           Comprehensive logging is sent to stdout.
      --path DIRECTORY    Path to CircuitPython directory. Overrides automatic
                          path detection.
      --host TEXT         Hostname or IP address of a device. Overrides automatic
                          path detection.
      --password TEXT     Password to use for authentication when --host is used.
      --timeout INTEGER   Specify the timeout in seconds for any network
                          operations.
      --board-id TEXT     Manual Board ID of the CircuitPython device. If provided
                          in combination with --cpy-version, it overrides the
                          detected board ID.
      --cpy-version TEXT  Manual CircuitPython version. If provided in combination
                          with --board-id, it overrides the detected CPy version.
      --version           Show the version and exit.
      --help              Show this message and exit.

    Commands:
      bundle-add     Add bundles to the local bundles list, by "user/repo"...
      bundle-remove  Remove one or more bundles from the local bundles list.
      bundle-show    Show the list of bundles, default and local, with URL,...
      example        Copy named example(s) from a bundle onto the device.
      freeze         Output details of all the modules found on the connected...
      install        Install a named module(s) onto the device.
      list           Lists all out of date modules found on the connected...
      show           Show a list of available modules in the bundle.
      uninstall      Uninstall a named module(s) from the connected device.
      update         Update modules on the device. Use --all to automatically
                     update all modules without Major Version warnings.



To automatically install all modules imported by ``code.py``,
:code:`$ circup install --auto`::

    $ circup install --auto
    Found device at /Volumes/CIRCUITPY, running CircuitPython 7.0.0-alpha.5.
    Searching for dependencies for: ['adafruit_bmp280']
    Ready to install: ['adafruit_bmp280', 'adafruit_bus_device', 'adafruit_register']

    Installed 'adafruit_bmp280'.
    Installed 'adafruit_bus_device'.
    Installed 'adafruit_register'.

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

If you need to work with the original .py version of a module, use the --py
flag.

    $ circup install --py adafruit_thermal_printer
    Installed 'adafruit_thermal_printer'.

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
    Circup, A CircuitPython module updater. Version 0.0.1


To use circup via the `Web Workflow <https://learn.adafruit.com/getting-started-with-web-workflow-using-the-code-editor>`_. on devices that support it. Use the ``--host`` and ``--password`` arguments before your circup command.::

    $ circup --host 192.168.1.119 --password s3cr3t install adafruit_hid
    $ circup --host cpy-9573b2.local --password s3cr3t install adafruit_hid

That's it!


Library Name Autocomplete
-------------------------

When enabled, circup will autocomplete library names, simliar to other command line tools.

For example:

  ``circup install n`` + tab -``circup install neopixel`` (+tab: offers ``neopixel`` and ``neopixel_spi`` completions)

  ``circup install a`` + tab -``circup install adafruit\_`` + m a g + tab -``circup install adafruit_magtag``

How to Activate Library Name Autocomplete
-----------------------------------------

In order to activate shell completion, you need to inform your shell that completion is available for your script. Any Click application automatically provides support for that.

For Bash, add this to ~/.bashrc::

    eval "$(_CIRCUP_COMPLETE=bash_source circup)"

For Zsh, add this to ~/.zshrc::

    autoload -U compinit; compinit
    eval "$(_CIRCUP_COMPLETE=zsh_source circup)"

For Fish, add this to ~/.config/fish/completions/foo-bar.fish::

    eval (env _CIRCUP_COMPLETE=fish_source circup)

Open a new shell to enable completion. Or run the eval command directly in your current shell to enable it temporarily.
### Activation Script

The above eval examples will invoke your application every time a shell is started. This may slow down shell startup time significantly.

Alternatively, export the generated completion code as a static script to be executed. You can ship this file with your builds; tools like Git do this. At least Zsh will also cache the results of completion files, but not eval scripts.

For Bash::

    _CIRCUP_COMPLETE=bash_source circup circup-complete.sh

For Zsh::

    _CIRCUP_COMPLETE=zsh_source circup circup-complete.sh

For Fish::

    _CIRCUP_COMPLETE=fish_source circup circup-complete.sh

In .bashrc or .zshrc, source the script instead of the eval command::

    . /path/to/circup-complete.sh

For Fish, add the file to the completions directory::

    _CIRCUP_COMPLETE=fish_source circup ~/.config/fish/completions/circup-complete.fish


.. note::

    If you find a bug, or you want to suggest an enhancement or new feature
    feel free to create an issue or submit a pull request here:

    https://github.com/adafruit/circup


Discussion of this tool happens on the Adafruit CircuitPython
`Discord channel <https://discord.gg/rqrKDjU>`_.
