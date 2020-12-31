XARGS := xargs -0 $(shell test $$(uname) = Linux && echo -r)
GREP_T_FLAG := $(shell test $$(uname) = Linux && echo -T)

all:
	@echo "\nThere is no default Makefile target right now. Try:\n"
	@echo "make clean - reset the project and remove auto-generated assets."
	@echo "make pyflakes - run the PyFlakes code checker."
	@echo "make pycodestyle - run the PEP8 style checker."
	@echo "make test - run the test suite."
	@echo "make coverage - view a report on test coverage."
	@echo "make tidy - tidy code with the 'black' formatter."
	@echo "make check - run all the checkers and tests."
	@echo "make dist - make a dist/wheel for the project."
	@echo "make publish-test - publish the project to PyPI test instance."
	@echo "make publish-live - publish the project to PyPI production."
	@echo "make docs - run sphinx to create project documentation.\n"

clean:
	rm -rf build
	rm -rf dist
	rm -rf .coverage
	rm -rf .eggs
	rm -rf .pytest_cache
	rm -rf .tox
	rm -rf docs/_build
	find . \( -name '*.py[co]' -o -name dropin.cache \) -delete
	find . \( -name '*.bak' -o -name dropin.cache \) -delete
	find . \( -name '*.tgz' -o -name dropin.cache \) -delete
	find . | grep -E "(__pycache__)" | xargs rm -rf

pyflakes:
        # search the current directory tree for .py files, skipping docs and  _build, var directories, feeding them to pyflakes
	find . \( -name _build -o -name var -o -path ./docs -o -name .env \) -type d -prune -o -name '*.py' -print0 | $(XARGS) pyflakes

pycodestyle:
        # search the current directory tree for .py files, skipping _build and var directories, feeding them to pycodestyle
	find . \( -name _build -o -name var -o -name .env \) -type d -prune -o -name '*.py' -print0 | $(XARGS) -n 1 pycodestyle --repeat --exclude=docs/*,.vscode/* --ignore=E731,E402,W504,W503

test: clean
	pytest --random-order

coverage: clean
	pytest --random-order --cov-config .coveragerc --cov-report term-missing --cov=circup tests/

tidy: clean
	@echo "\nTidying code with black..."
	black --target-version=py35 .

check: clean tidy pycodestyle pyflakes coverage

dist: check
	@echo "\nChecks pass, good to package..."
	python setup.py sdist bdist_wheel

publish-test: dist
	@echo "\nPackaging complete... Uploading to PyPi..."
	twine upload -r test --sign dist/*

publish-live: dist
	@echo "\nPackaging complete... Uploading to PyPi..."
	twine upload --sign dist/*

docs: clean
	$(MAKE) -C docs html
	@echo "\nDocumentation can be found here:"
	@echo file://`pwd`/docs/_build/html/index.html
	@echo "\n"
