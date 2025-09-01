# Variables
OUT   := dist
PYTHON ?= python

# Default
.PHONY: help
help:
	@echo "Targets:"
	@echo "  build         Build wheel and sdist (pyproject)"
	@echo "  publish       Upload to PyPI (twine)"
	@echo "  publish-test  Upload to TestPyPI (twine)"
	@echo "  run           Show CLI help via python -m"
	@echo "  verify        Run a sample squash and hint docker load"
	@echo "  clean         Remove build artifacts"
	@echo "  distclean     Remove all build artifacts and temp dirs"

.PHONY: build
build:
	$(PYTHON) -m pip install -U build
	$(PYTHON) -m build

.PHONY: publish
publish:
	$(PYTHON) -m pip install -U twine
	$(PYTHON) -m twine upload $(OUT)/*

.PHONY: publish-test
publish-test:
	$(PYTHON) -m pip install -U twine
	$(PYTHON) -m twine upload -r testpypi $(OUT)/*

.PHONY: run
run:
	PYTHONPATH=src $(PYTHON) -m oci_squash.cli -h

# Example verification: adjust paths as needed
SAMPLE_TAR ?= testtar/redis.tar
OUTPUT_TAR ?= test.tar
TAG        ?= newimage


.PHONY: verify
verify:
	oci-squash -f 3 -m "test" --output-path $(OUTPUT_TAR) -t $(TAG) $(SAMPLE_TAR) || PYTHONPATH=src $(PYTHON) -m oci_squash.cli -f 3 -m "test" --output-path $(OUTPUT_TAR) -t $(TAG) $(SAMPLE_TAR)
	@echo "Hint: docker load -i $(OUTPUT_TAR)"

.PHONY: clean
clean:
	rm -rf build $(OUT) *.spec **/__pycache__/ **/*.pyc **/*.pyo

.PHONY: distclean
distclean: clean
	rm -rf .oci-squash-work .pytest_cache .mypy_cache