Release History
===============

0.0.8
-----

* Added requirements.txt support to both freeze and install commands. Many thanks to Steven Abadie for this really useful feature.

0.0.7
-----

Two new features contributed from the community:

* Run circup via ``python -m circup``. Thank you to Joe DeVivo for this contribution.
* Add an uninstall command. Thank you to Steven Abadie for this new feature.

0.0.6
-----

This release includes a security fix


0.0.5
-----

Fixed error message when Bundle Unavailable

* Error message when bundle unavailable is better
* Fixed a couple types


0.0.4
-----

Added install and show commands

* Circup now has an install command to install a CircuitPython library onto your device.
* It also has a show command to show you what is available.

0.0.3
-----

Automated Release Deployment Bug Fix

* Fix missing PyPI egg dependency

0.0.2
-----

Initial PyPI Release Automation w/ TravisCI

* Add Continuous Integration with TravisCI
* Deploy ``circup`` releases to PyPI automatically with TravisCI

0.0.1
-----

Initial release.

* Core project scaffolding.
* ``circup freeze`` - lists version details for all modules found on the
  connected CIRCUITPYTHON device.
* ``circup list`` - lists all modules requiring an update found on the the
  connected CIRCUITPYTHON device.
* ``circup update`` - interactively update out-of-date modules found on the
  connected CIRCUITPYTHON device.
* 100% test coverage.
* Documentation.
