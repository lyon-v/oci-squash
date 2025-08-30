# Variables
ENTRY := oci_squash/__main__.py
NAME  := oci-squash
OUT   := dist
PYI   := pyinstaller
PYI_FLAGS := --onefile --name $(NAME) -p .

# Default
.PHONY: help
help:
	@echo "Targets:"
	@echo "  deps        Install Python dependencies"
	@echo "  build       Build single-file binary with PyInstaller"
	@echo "  rebuild     Clean then build"
	@echo "  run         Run CLI via Python"
	@echo "  verify      Run a sample squash and hint docker load"
	@echo "  clean       Remove build artifacts"
	@echo "  distclean   Remove all build artifacts and temp dirs"
	@echo "  install     Install binary to /usr/local/bin"
	@echo "  uninstall   Remove installed binary"

.PHONY: deps
deps:
	pip install -r oci_squash/requirements.txt

.PHONY: build
build: deps
	$(PYI) $(PYI_FLAGS) $(ENTRY)

.PHONY: rebuild
rebuild: clean build

.PHONY: run
run:
	python -m oci_squash.cli -h

# Example verification: adjust paths as needed
SAMPLE_TAR ?= testtar/redis.tar
OUTPUT_TAR ?= test.tar
TAG        ?= newimage

.PHONY: verify
verify:
	./dist/$(NAME) -f 3 -m "test" --output-path $(OUTPUT_TAR) -t $(TAG) $(SAMPLE_TAR) || python -m oci_squash.cli -f 3 -m "test" --output-path $(OUTPUT_TAR) -t $(TAG) $(SAMPLE_TAR)
	@echo "Hint: docker load -i $(OUTPUT_TAR)"

.PHONY: clean
clean:
	rm -rf build $(OUT) *.spec **/__pycache__/ **/*.pyc **/*.pyo

.PHONY: distclean
distclean: clean
	rm -rf .oci-squash-work .pytest_cache .mypy_cache

PREFIX ?= /usr/local
.PHONY: install
install:
	install -d $(PREFIX)/bin
	install -m 0755 dist/$(NAME) $(PREFIX)/bin/$(NAME)

.PHONY: uninstall
uninstall:
	rm -f $(PREFIX)/bin/$(NAME)