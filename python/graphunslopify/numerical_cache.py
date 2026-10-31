"""Private bounded numerical reuse; current reports and verification are never cached."""

from __future__ import annotations

import copy
import dis
import functools
import hashlib
import json
import os
import pickle
import sys
import threading
from collections import OrderedDict
from contextvars import ContextVar
from pathlib import Path
from types import CodeType

VERSION = 1
HELPERS = ("summary_input", "bootstrap_interval", "summarise")
ACTIVE: ContextVar = ContextVar("graphunslopify_numerical_request", default=None)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _code(code):
    """Calculation bytecode without request filenames or source line positions."""

    def constant(value):
        if isinstance(value, CodeType):
            return _code(value)
        if isinstance(value, tuple):
            return ["tuple", [constant(v) for v in value]]
        return [type(value).__name__, repr(value)]

    return [
        code.co_code.hex(),
        code.co_names,
        code.co_varnames,
        code.co_freevars,
        code.co_cellvars,
        code.co_argcount,
        code.co_posonlyargcount,
        code.co_kwonlyargcount,
        code.co_flags,
        getattr(code, "co_exceptiontable", b"").hex(),
        [constant(v) for v in code.co_consts],
    ]


def calculation_intent(spec):
    result = copy.deepcopy(spec)
    for field in ("title", "legend", "style", "output", "palette_lock"):
        result.pop(field, None)
    for field in ("x", "y", "y2"):
        if isinstance(result.get(field), dict):
            result[field].pop("label", None)
    if isinstance(result.get("uncertainty"), dict):
        result["uncertainty"].pop("display", None)
    return result


class NumericalCache:
    """Only process-owned bytes created here can be deserialized; nothing is persisted."""

    def __init__(
        self, source, *, max_entries=64, max_bytes=32 * 1024 * 1024, max_entry_bytes=8 * 1024 * 1024
    ):
        if any(type(n) is not int or n < 1 for n in (max_entries, max_bytes, max_entry_bytes)):
            raise ValueError("Numerical cache bounds must be positive integers")
        self.source = source
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.max_entry_bytes = min(max_entry_bytes, max_bytes)
        self.entries = OrderedDict()
        self.sizes = {}
        self.bytes = 0
        self.lock = threading.RLock()

    def request(self):
        return NumericalRequest(self)

    def _drop(self, identity):
        self.entries.pop(identity, None)
        self.bytes -= self.sizes.pop(identity, 0)


class NumericalRequest:
    def __init__(self, owner):
        self.owner = owner
        self.counts = {
            "hits": 0,
            "misses": 0,
            "stores": 0,
            "evictions": 0,
            "bypassed": 0,
            "invalid": 0,
        }
        self.functions = {}

    def trace(self):
        with self.owner.lock:
            return {
                "enabled": True,
                "version": VERSION,
                "pid": os.getpid(),
                "runtime_source_sha256": self.owner.source,
                **self.counts,
                "functions": copy.deepcopy(self.functions),
                "entries": len(self.owner.entries),
                "serialized_bytes": self.owner.bytes,
                "max_entries": self.owner.max_entries,
                "max_bytes": self.owner.max_bytes,
                "max_entry_bytes": self.owner.max_entry_bytes,
            }

    def _count(self, name, field):
        self.counts[field] += 1
        values = self.functions.setdefault(name, {})
        values[field] = values.get(field, 0) + 1

    def install(self, context):
        def identity_only(function):
            instructions = [
                i
                for i in dis.get_instructions(function)
                if i.opname not in {"RESUME", "CACHE", "NOP"}
            ]
            return (
                len(instructions) == 2
                and instructions[0].opname == "LOAD_FAST"
                and instructions[0].arg == 0
                and instructions[1].opname == "RETURN_VALUE"
            )

        functions = {
            name: context[name]
            for name in HELPERS
            if callable(context.get(name)) and not identity_only(context[name])
        }
        if not functions:
            return
        # These hooks must not acquire effects merely because the generator evolves.
        forbidden = {"ROW_COUNTS", "MISSING_INTERVALS", "RUN_REPORT", "DATA_HASH"}
        if any(
            forbidden.intersection(fn.__code__.co_names) or fn.__closure__
            for fn in functions.values()
        ):
            return
        identities = {
            name: [_code(fn.__code__), fn.__defaults__, fn.__kwdefaults__]
            for name, fn in functions.items()
        }
        names = sorted(
            {
                key
                for fn in functions.values()
                for key in fn.__code__.co_names
                if key.isupper() and key in context
            }
        )
        intent = calculation_intent(context["RUN_REPORT"]["spec"])
        input_hash = None

        def key(name, args, kwargs):
            nonlocal input_hash
            if input_hash is None:
                digest = hashlib.sha256()
                with Path(context["DATA_PATH"]).open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                input_hash = digest.hexdigest()
            import pandas as pd

            def argument(value):
                if isinstance(value, (pd.DataFrame, pd.Series)):
                    memory = value.memory_usage(index=True, deep=True)
                    size = int(memory.sum()) if isinstance(value, pd.DataFrame) else int(memory)
                    if size > self.owner.max_entry_bytes:
                        raise ValueError("Numerical input exceeds key budget")
                    value = value.copy(deep=True)
                payload = pickle.dumps(value, protocol=5)
                if len(payload) > self.owner.max_entry_bytes:
                    raise ValueError("Numerical input exceeds key budget")
                return _sha(payload)

            versions = {
                name: getattr(sys.modules.get(name), "__version__", None)
                for name in ("numpy", "pandas", "scipy", "pyarrow")
            }
            description = [
                VERSION,
                self.owner.source,
                sys.version_info[:3],
                versions,
                input_hash,
                intent,
                identities,
                {n: context[n] for n in names},
                name,
                [argument(v) for v in args],
                {n: argument(v) for n, v in sorted(kwargs.items())},
            ]
            return _sha(
                json.dumps(
                    description, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            )

        for name, function in functions.items():
            context[name] = self._wrap(name, function, key)

    def _wrap(self, name, function, key):
        @functools.wraps(function)
        def call(*args, **kwargs):
            try:
                identity = key(name, args, kwargs)
            except (OSError, ValueError, TypeError, AttributeError, pickle.PickleError):
                self._count(name, "bypassed")
                return function(*args, **kwargs)
            with self.owner.lock:
                cached = self.owner.entries.get(identity)
                if cached is not None:
                    try:
                        if not isinstance(cached, tuple) or len(cached) != 2:
                            raise ValueError("Numerical cache entry changed shape")
                        payload, checksum = cached
                        if type(payload) is not bytes or not isinstance(checksum, str):
                            raise ValueError("Numerical cache entry changed type")
                        if _sha(payload) != checksum:
                            raise ValueError("Numerical cache checksum changed")
                        result = pickle.loads(payload)
                    except (
                        ValueError,
                        TypeError,
                        EOFError,
                        AttributeError,
                        ImportError,
                        pickle.PickleError,
                    ):
                        self.owner._drop(identity)
                        self._count(name, "invalid")
                    else:
                        self.owner.entries.move_to_end(identity)
                        self._count(name, "hits")
                        return result
            self._count(name, "misses")
            # Never catch a real calculation error or substitute an older success.
            result = function(*args, **kwargs)
            try:
                payload = pickle.dumps(result, protocol=5)
            except (ValueError, TypeError, pickle.PickleError):
                self._count(name, "bypassed")
                return result
            if len(payload) > self.owner.max_entry_bytes:
                self._count(name, "bypassed")
                return result
            with self.owner.lock:
                self.owner._drop(identity)
                while self.owner.entries and (
                    len(self.owner.entries) >= self.owner.max_entries
                    or self.owner.bytes + len(payload) > self.owner.max_bytes
                ):
                    self.owner._drop(next(iter(self.owner.entries)))
                    self._count(name, "evictions")
                self.owner.entries[identity] = payload, _sha(payload)
                self.owner.sizes[identity] = len(payload)
                self.owner.bytes += len(payload)
                self._count(name, "stores")
            return result

        return call
