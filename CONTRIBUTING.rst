Contributing
============

Please note that this project is released with a Contributor Code of Conduct.
By participating in this project you agree to abide by its terms. Participation
covers any forum used to converse about CircuitPython including unofficial and
official spaces. Failure to do so will result in corrective actions such as
time out or ban from the project.

Licensing
---------

By contributing to this repository you are certifying that you have all
necessary permissions to license the code under an MIT License. You still
retain the copyright but are granting many permissions under the MIT License.

If you have an employment contract with your employer please make sure that
they don't automatically own your work product. Make sure to get any necessary
approvals before contributing. Another term for this contribution off-hours is
moonlighting.


Developer Setup
---------------

.. note::

    Please try to use Python 3.9+ while developing Circup. This is so we can
    use the
    `Black code formatter <https://black.readthedocs.io/en/stable/index.html>`_
    and so that we're supporting versions which still receive security updates.


Clone the repository and from the root of the project,


If you'd like you can setup a virtual environment and activate it.::

    python3 -m venv .env
    source .env/bin/activate

install the development requirements::

    pip install -r optional_requirements.txt


Run the test suite::

    pytest --random-order --cov-config .coveragerc --cov-report term-missing --cov=circup


How Does Circup Work?
#####################

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

Unit tests can be found in the ``tests`` directory. Circup uses
`pytest <http://www.pytest.org/en/latest/>`_ style testing conventions. Test
functions should include a comment to describe its *intention*. We currently
have 100% unit test coverage for all the core functionality (excluding
functions used to define the CLI commands).

To run the full test suite, type::

    pytest --random-order --cov-config .coveragerc --cov-report term-missing --cov=circup

All code is formatted using the stylistic conventions enforced by
`black <https://black.readthedocs.io/en/stable/>`_. Python coding standard are
enforced by Pylint and verification of licensing is handled by REUSE. All of these
are run using pre-commit, which you can run by using::

    pip install pre-commit
    pre-commit run --all-files

Please see the output from ``pre-commit`` for more information about the various
available options to help you work with the code base.

Before submitting a PR, please remember to ``pre-commit run --all-files``.
But if  you forget the CI process in Github will run it for you. ;-)

Circup uses the `Click <https://click.palletsprojects.com>`_ module to
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
