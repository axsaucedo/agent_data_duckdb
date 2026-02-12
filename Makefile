.PHONY: clean clean_all

PROJ_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

EXTENSION_NAME=agent_data

# Unstable API required by duckdb-rs
USE_UNSTABLE_C_API=1

# Target DuckDB version
TARGET_DUCKDB_VERSION=v1.4.4

all: configure debug

# Include makefiles from DuckDB
include extension-ci-tools/makefiles/c_api_extensions/base.Makefile
include extension-ci-tools/makefiles/c_api_extensions/rust.Makefile

configure: venv platform extension_version

debug: build_extension_library_debug build_extension_with_metadata_debug
release: build_extension_library_release build_extension_with_metadata_release

test: test_debug
test_debug: debug
	$(PYTHON_VENV_BIN) -m duckdb_sqllogictest --test-dir test/sql --external-extension build/debug/$(EXTENSION_NAME).duckdb_extension
test_release: release
	$(PYTHON_VENV_BIN) -m duckdb_sqllogictest --test-dir test/sql --external-extension build/release/$(EXTENSION_NAME).duckdb_extension

clean: clean_build clean_rust
clean_all: clean_configure clean
