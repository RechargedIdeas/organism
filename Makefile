.PHONY: all proto python rust test lint clean fmt

PYTHON ?= python3.11
PROTOC ?= protoc
CARGO ?= cargo

# ---- Proto generation ----

PROTO_DIR := proto
PROTO_FILES := $(wildcard $(PROTO_DIR)/organism/v1/*.proto)
PY_OUT := sdk/python/organism_sdk/_proto
RS_OUT := sdk/rust/organism-proto/src/gen

proto: proto-python proto-rust

proto-python:
	@mkdir -p $(PY_OUT)
	$(PYTHON) -m grpc_tools.protoc \
		-I $(PROTO_DIR) \
		--python_out=$(PY_OUT) \
		--grpc_python_out=$(PY_OUT) \
		--pyi_out=$(PY_OUT) \
		$(PROTO_FILES)

proto-rust:
	@mkdir -p $(RS_OUT)
	$(CARGO) build -p organism-proto

# ---- Python ----

python-install:
	$(PYTHON) -m pip install -e ".[dev]"

python-test:
	$(PYTHON) -m pytest -x -v

python-lint:
	$(PYTHON) -m ruff check sdk/python modules
	$(PYTHON) -m mypy sdk/python

# ---- Rust ----

rust-build:
	$(CARGO) build --workspace

rust-test:
	$(CARGO) test --workspace

rust-lint:
	$(CARGO) clippy --workspace -- -D warnings

# ---- Combined ----

test: python-test rust-test
lint: python-lint rust-lint
fmt:
	$(PYTHON) -m black sdk/python modules
	$(CARGO) fmt --all

all: proto python-install rust-build test lint

clean:
	rm -rf $(PY_OUT) $(RS_OUT) target build dist *.egg-info
	find . -name __pycache__ -exec rm -rf {} +
	find . -name '*.pyc' -delete
