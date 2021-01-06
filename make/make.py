#!python3
"""
A "pretend" make command written in Python for Windows users. :-)
"""
import os
import sys
import fnmatch
import shutil
import subprocess

PYTEST = "pytest"
BLACK = "black"
PYLINT = "pylint"

INCLUDE_PATTERNS = {"*.py"}
EXCLUDE_PATTERNS = {"build/*", "docs/*"}
_exported = {}


def _walk(start_from=".", include_patterns=None, exclude_patterns=None, recurse=True):
    if include_patterns:
        _include_patterns = set(os.path.normpath(p) for p in include_patterns)
    else:
        _include_patterns = set()
    if exclude_patterns:
        _exclude_patterns = set(os.path.normpath(p) for p in exclude_patterns)
    else:
        _exclude_patterns = set()

    for dirpath, dirnames, filenames in os.walk(start_from):
        for filename in filenames:
            filepath = os.path.normpath(os.path.join(dirpath, filename))

            if not any(
                fnmatch.fnmatch(filepath, pattern) for pattern in _include_patterns
            ):
                continue

            if any(fnmatch.fnmatch(filepath, pattern) for pattern in _exclude_patterns):
                continue

            yield filepath

        if not recurse:
            break


def _process_code(executable, use_python, *args):
    """
    Perform some action (check, translate etc.) across the .py files
    in the codebase, skipping docs and build artefacts.
    """
    if use_python:
        execution = ["python", executable]
    else:
        execution = [executable]
    returncodes = set()
    for filepath in _walk(".", INCLUDE_PATTERNS, EXCLUDE_PATTERNS, False):
        p = subprocess.run(execution + [filepath] + list(args))
        returncodes.add(p.returncode)
    for filepath in _walk("tests", INCLUDE_PATTERNS, EXCLUDE_PATTERNS):
        p = subprocess.run(execution + [filepath] + list(args))
        returncodes.add(p.returncode)
    return max(returncodes)


def _rmtree(dirpath, cascade_errors=False):
    """
    Remove a directory and its contents, including subdirectories.
    """
    try:
        shutil.rmtree(dirpath)
    except OSError:
        if cascade_errors:
            raise


def _rmfiles(start_from, pattern):
    """
    Remove files from a directory and its descendants.

    Starting from `start_from` directory and working downwards,
    remove all files which match `pattern`, eg *.pyc.
    """
    for filepath in _walk(start_from, {pattern}):
        os.remove(filepath)


def export(function):
    """
    Decorator to tag certain functions as exported, meaning
    that they show up as a command, with arguments, when this
    file is run.
    """
    _exported[function.__name__] = function
    return function


@export
def test(*pytest_args):
    """
    Run the test suite.

    Call py.test to run the test suite with additional args.
    The subprocess runner will raise an exception if py.test exits
    with a failure value. This forces things to stop if tests fail.
    """
    print("\ntest")
    return subprocess.run([PYTEST] + list(pytest_args)).returncode


@export
def coverage():
    """
    View a report on test coverage.

    Call py.test with coverage turned on.
    """
    print("\ncoverage")
    return subprocess.run(
        [
            PYTEST,
            "--cov-config",
            ".coveragerc",
            "--cov-report",
            "term-missing",
            "--cov=circup",
            "tests/",
        ]
    ).returncode


@export
def black(*black_args):
    """
    Run Black in check mode
    """
    args = (BLACK, "--check", "--target-version", "py35", ".") + black_args
    result = subprocess.run(args).returncode
    if result > 0:
        return result


@export
def pylint():
    """
    Run python Linter
    """
    # args = ("circup.py",)
    # return _process_code(PYLINT, False, *args)
    args = (PYLINT, "circup.py")
    result = subprocess.run(args).returncode
    if result > 0:
        return result


@export
def tidy(*tidy_args):
    """
    Run black against the code and tests.
    """
    print("\nTidy code")
    args = (BLACK, "--target-version", "py35", ".")
    result = subprocess.run(args).returncode
    if result > 0:
        return result


@export
def check():
    """
    Run all the checkers and tests.
    """
    print("\nCheck")
    funcs = [clean, tidy, black, pylint, coverage]
    for func in funcs:
        return_code = func()
        if return_code != 0:
            return return_code
    return 0


@export
def clean():
    """
    Reset the project and remove auto-generated assets.
    """
    print("\nClean")
    _rmtree("build")
    _rmtree("dist")
    _rmtree("circup.egg-info")
    _rmtree("coverage")
    _rmtree("docs/build")
    _rmfiles(".", "*.pyc")
    return 0


@export
def dist():
    """
    Generate a source distribution and a binary wheel.
    """
    check()
    print("Checks pass; good to package")
    return subprocess.run(["python", "setup.py", "sdist", "bdist_wheel"]).returncode


@export
def publish_test():
    """
    Upload to a test PyPI.
    """
    dist()
    print("Packaging complete; upload to PyPI")
    return subprocess.run(
        ["twine", "upload", "-r", "test", "--sign", "dist/*"]
    ).returncode


@export
def publish_live():
    """
    Upload to PyPI.
    """
    dist()
    print("Packaging complete; upload to PyPI")
    return subprocess.run(["twine", "upload", "--sign", "dist/*"]).returncode


@export
def docs():
    """
    Build the docs.
    """
    cwd = os.getcwd()
    os.chdir("docs")
    try:
        return subprocess.run(["cmd", "/c", "make.bat", "html"]).returncode
    except Exception:
        return 1
    finally:
        os.chdir(cwd)


@export
def help():
    """
    Display all commands with their description in alphabetical order.
    """
    module_doc = sys.modules["__main__"].__doc__ or "check"
    print(module_doc + "\n" + "=" * len(module_doc) + "\n")

    for command, function in sorted(_exported.items()):
        doc = function.__doc__
        print("make {}{}".format(command, doc))


def main(command="help", *args):
    """
    Dispatch on command name, passing all remaining parameters to the
    module-level function.
    """
    try:
        function = _exported[command]
    except KeyError:
        raise RuntimeError("No such command: %s" % command)
    else:
        return function(*args)


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
