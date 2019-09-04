CircUp
======

A tool to manage and update libraries on a CircuitPython device.

How
---

Each CircuitPython library on the device (``.py``, *NOT* ``.mpy`` at this time)
has a version number and a github repo URL.

This utility looks at all the libraries on the device and checks if they are
the most recet (compared to what is in the referenced GitHub repository). If
the libraries are out of date, the utility downloads them to the local device
and/or local system in a zip file.

Example libraries:

https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/download/20190830/adafruit-circuitpython-bundle-py-20190830.zip

Usage
-----

Example usage::

    circup list

    Package     Version Latest
    ----------- ------- ------  
    foo         1.0.1   1.1.0
    bar         19.3    19.4
    baz         0.3.1   0.9

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
