.PHONY: clean clean_all

PROJ_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

EXTENSION_NAME=agent_data

# Unstable API required by duckdb-rs
USE_UNSTABLE_C_API=1

# Target DuckDB version
DEFAULT_TARGET_DUCKDB_VERSION := v1.5.3
TARGET_DUCKDB_VERSION ?= __AGENT_DATA_AUTO__

all: configure debug

# Include makefiles from DuckDB
include extension-ci-tools/makefiles/c_api_extensions/base.Makefile
include extension-ci-tools/makefiles/c_api_extensions/rust.Makefile

ifeq ($(TARGET_DUCKDB_VERSION),__AGENT_DATA_AUTO__)
  RESOLVE_DUCKDB_METADATA_VERSION = scripts/duckdb_metadata_version.py --duckdb-git-version "$(DUCKDB_GIT_VERSION)" --default "$(DEFAULT_TARGET_DUCKDB_VERSION)"
  override TARGET_DUCKDB_VERSION = $(shell $(PYTHON_VENV_BIN) $(RESOLVE_DUCKDB_METADATA_VERSION) 2>/dev/null || $(PYTHON_BIN) $(RESOLVE_DUCKDB_METADATA_VERSION))
endif
check_target_duckdb_version:
	@test -n "$(TARGET_DUCKDB_VERSION)" || (echo "Could not resolve TARGET_DUCKDB_VERSION" >&2; exit 1)

configure: venv platform extension_version

debug: build_extension_library_debug build_extension_with_metadata_debug

release: build_extension_library_release build_extension_with_metadata_release

build_extension_library_debug build_extension_library_release build_extension_with_metadata_debug build_extension_with_metadata_release: check_target_duckdb_version

test: test_debug
test_debug: test_extension_debug
test_release: test_extension_release

clean: clean_build clean_rust
clean_all: clean_configure clean
