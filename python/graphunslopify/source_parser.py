"""Static plotting-subset extraction. User imports/calls are never evaluated."""

from __future__ import annotations

import ast
import copy
import csv
import io
import itertools
import math
from types import SimpleNamespace

from .experiment_imports import _number

MAX_SOURCE = 256 * 1024
MAX_NODES = 50_000
MAX_ROWS = 100_000
MAX_PLOTS = 32


class Unsupported(ValueError):
    pass


def _literal(node):
    if isinstance(node, ast.Constant) and isinstance(
        node.value, (str, int, float, bool, type(None))
    ):
        if isinstance(node.value, float) and not math.isfinite(node.value):
            raise Unsupported("Nonfinite Python literal")
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        if len(node.elts) > MAX_ROWS:
            raise Unsupported("Literal vector exceeds the row limit")
        return [_literal(item) for item in node.elts]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _literal(node.operand)
        if type(value) not in (int, float):
            raise Unsupported("Unary sign requires a numeric literal")
        return -value if isinstance(node.op, ast.USub) else value
    raise Unsupported("Expression is outside the literal subset")


def _path(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _path(node.value) + "." + node.attr
    raise Unsupported("Dynamic call target")


class Parser:
    def __init__(self, source):
        self.source = source
        self.modules = {}
        self.values = {}
        self.axes = set()
        self.figures = set()
        self.plots = []
        self.issues = []
        self.references = []
        self.settings = {"legend": {"show": False}}

    def issue(self, node, message, category="unsupported"):
        self.issues.append(
            {
                "line": getattr(node, "lineno", 1),
                "end_line": getattr(node, "end_lineno", 1),
                "utf8_byte_column": getattr(node, "col_offset", 0),
                "category": category,
                "reason": message,
            }
        )

    def qualified(self, node):
        path = _path(node)
        for alias in sorted(self.modules, key=len, reverse=True):
            if path == alias or path.startswith(alias + "."):
                return self.modules[alias] + path[len(alias) :]
        if path.split(".")[0] in self.axes | self.figures:
            return path
        raise Unsupported("Call target has no supported, current import or axes binding")

    def unbind(self, name):
        self.modules.pop(name, None)
        self.values.pop(name, None)
        self.axes.discard(name)
        self.figures.discard(name)

    def expression(self, node):
        if isinstance(node, ast.Name) and node.id in self.values:
            return copy.deepcopy(self.values[node.id])
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            frame = self.values.get(node.value.id, {})
            column = _literal(node.slice)
            if frame.get("type") == "frame" and isinstance(column, str):
                return {"type": "column", "field": column, "reference": frame["reference"]}
        if isinstance(node, ast.Call) and self.qualified(node.func) == "numpy.array":
            if len(node.args) != 1 or node.keywords:
                raise Unsupported("Only a literal one-dimensional numpy.array is supported")
            node = node.args[0]
        value = _literal(node)
        if not isinstance(value, list) or any(isinstance(v, (list, dict)) for v in value):
            raise Unsupported("Plot vectors must be one-dimensional literals or mapped columns")
        return {"type": "vector", "values": value}

    def keywords(self, node):
        if any(k.arg is None for k in node.keywords):
            raise Unsupported("Expanded keyword dictionaries are dynamic")
        if len({k.arg for k in node.keywords}) != len(node.keywords):
            raise Unsupported("Repeated keyword arguments are invalid Python")
        return {k.arg: k.value for k in node.keywords}

    def assignment(self, node):
        if len(node.targets) != 1:
            raise Unsupported("Chained assignments are outside the subset")
        target = node.targets[0]
        value = node.value
        if isinstance(value, ast.Call):
            name = self.qualified(value.func)
            if name == "matplotlib.pyplot.subplots":
                options = self.keywords(value)
                if value.args or any(
                    k not in {"nrows", "ncols", "figsize", "dpi"} for k in options
                ):
                    raise Unsupported("Only a single independent axes is supported")
                if any(_literal(options[k]) != 1 for k in ("nrows", "ncols") if k in options):
                    raise Unsupported("Multiple subplot axes cannot be represented by one figure")
                if (
                    not isinstance(target, (ast.Tuple, ast.List))
                    or len(target.elts) != 2
                    or not all(isinstance(t, ast.Name) for t in target.elts)
                    or target.elts[0].id == target.elts[1].id
                ):
                    raise Unsupported("Use an explicit figure,axes assignment")
                if self.axes or self.figures:
                    raise Unsupported("Multiple figure/axes construction is unsupported")
                for item in target.elts:
                    self.unbind(item.id)
                self.figures.add(target.elts[0].id)
                self.axes.add(target.elts[1].id)
                if "figsize" in options:
                    self.issue(
                        node,
                        "Exact figsize is not a canonical paper size; review the new layout",
                        "presentation",
                    )
                if "dpi" in options:
                    self.settings["dpi"] = _literal(options["dpi"])
                return
            if name == "pandas.read_csv":
                if not isinstance(target, ast.Name) or len(value.args) != 1 or value.keywords:
                    raise Unsupported("CSV read options need explicit preprocessing/data binding")
                reference = _literal(value.args[0])
                if not isinstance(reference, str) or not reference or len(reference) > 4096:
                    raise Unsupported("CSV reference must be a bounded literal path")
                self.unbind(target.id)
                self.values[target.id] = {"type": "frame", "reference": reference}
                self.references.append(reference)
                return
        if not isinstance(target, ast.Name):
            raise Unsupported("Subscript/attribute assignment can mutate plotted data")
        try:
            parsed = self.expression(value)
            self.unbind(target.id)
            self.values[target.id] = parsed
        except Unsupported:
            # Scalar constants may be used for labels/settings, but never evaluated.
            self.values.pop(target.id, None)
            raise

    def call(self, node):
        name = self.qualified(node.func)
        options = self.keywords(node)
        owner, _, method = name.rpartition(".")
        mpl = owner == "matplotlib.pyplot" or owner in self.axes
        sns = owner == "seaborn"
        if (mpl and method in {"plot", "scatter", "bar"}) or (
            sns and method in {"lineplot", "scatterplot"}
        ):
            kind = {"plot": "line", "lineplot": "line", "scatterplot": "scatter"}.get(
                method, method
            )
            if len(self.plots) >= MAX_PLOTS:
                raise Unsupported("Source exceeds32 plot calls")
            allowed = {"label", "x", "y", "data"}
            if sns:
                allowed |= {"hue", "legend", "ax"}
                if kind == "line":
                    allowed |= {"estimator", "errorbar", "ci", "sort"}
                if node.args:
                    raise Unsupported("Use named Seaborn x,y,data arguments")
                if kind == "line":
                    if "estimator" not in options or _literal(options["estimator"]) is not None:
                        raise Unsupported(
                            "Seaborn aggregation/interval defaults require explicit author decisions; use estimator=None for raw lines"
                        )
                    if "errorbar" in options and _literal(options["errorbar"]) is not None:
                        raise Unsupported(
                            "Nonempty errorbar settings require an explicit interval mapping"
                        )
                    if "ci" in options and _literal(options["ci"]) is not None:
                        raise Unsupported(
                            "Nonempty ci settings require an explicit interval mapping"
                        )
                if "ax" in options and (
                    not isinstance(options["ax"], ast.Name) or options["ax"].id not in self.axes
                ):
                    raise Unsupported("Seaborn ax must be the selected single axes")
                if "legend" in options and _literal(options["legend"]) not in (
                    True,
                    False,
                    "auto",
                    "brief",
                    "full",
                ):
                    raise Unsupported("Unsupported Seaborn legend setting")
            unknown = set(options) - allowed
            if unknown:
                raise Unsupported(
                    "Unsupported plot encodings/settings: " + ", ".join(sorted(unknown))
                )
            if node.args and ({"x", "y", "data"} & set(options)):
                raise Unsupported("Positional and named plot vectors cannot be combined")
            if mpl and kind == "line" and not node.args:
                raise Unsupported("Matplotlib plot requires positional vectors")
            if "sort" in options and type(_literal(options["sort"])) is not bool:
                raise Unsupported("sort must be a literal boolean")
            if "data" in options:
                data = options["data"]
                frame = self.values.get(data.id, {}) if isinstance(data, ast.Name) else {}
                if frame.get("type") != "frame":
                    raise Unsupported("data must name an explicitly mapped CSV frame")

                def field(key):
                    value = _literal(options[key])
                    if not isinstance(value, str):
                        raise Unsupported("Mapped x/y/hue must name columns")
                    return {"type": "column", "field": value, "reference": frame["reference"]}

                x, y = field("x"), field("y")
                hue = field("hue") if "hue" in options else None
            elif sns or not node.args:
                if "x" not in options or "y" not in options:
                    raise Unsupported("Explicit x and y are required")
                x, y = self.expression(options["x"]), self.expression(options["y"])
                hue = None
                if "hue" in options:
                    raise Unsupported("Literal hue vectors need an explicit dataset/group mapping")
            else:
                if len(node.args) == 1 and kind == "line":
                    y = self.expression(node.args[0])
                    if y["type"] != "vector":
                        raise Unsupported("Implicit x requires a literal y vector")
                    x = {"type": "vector", "values": list(range(len(y["values"])))}
                elif len(node.args) == 2:
                    x, y = map(self.expression, node.args)
                else:
                    raise Unsupported("Only one x/y pair per plot call is supported")
                hue = None
            label = _literal(options["label"]) if "label" in options else None
            if label is not None and (not isinstance(label, str) or not label):
                raise Unsupported("Series label must be nonempty literal text")
            if sns:
                for key, expr in (("xlabel", x), ("ylabel", y)):
                    if expr["type"] == "column":
                        self.settings.setdefault(key, expr["field"])
                if hue:
                    self.settings["legend"].setdefault("title", hue["field"])
            self.plots.append(
                {
                    "kind": kind,
                    "x": x,
                    "y": y,
                    "hue": hue,
                    "label": label,
                    "line": node.lineno,
                    "seaborn": sns,
                    "sort": _literal(options["sort"]) if "sort" in options else True,
                }
            )
            if sns and hue and not ("legend" in options and _literal(options["legend"]) is False):
                self.settings["legend"]["show"] = True
            return
        if mpl:
            setters = {
                "xlabel": "xlabel",
                "ylabel": "ylabel",
                "title": "title",
                "set_xlabel": "xlabel",
                "set_ylabel": "ylabel",
                "set_title": "title",
                "xscale": "xscale",
                "yscale": "yscale",
                "set_xscale": "xscale",
                "set_yscale": "yscale",
            }
            if method in setters:
                if len(node.args) != 1 or options:
                    raise Unsupported("Axis/title setter options require manual review")
                value = _literal(node.args[0])
                if not isinstance(value, str) or not value:
                    raise Unsupported("Axis/title settings require literal text")
                if method.endswith("scale") and value not in {"linear", "log"}:
                    raise Unsupported("Only default linear/log scale semantics are supported")
                self.settings[setters[method]] = value
                return
            if method == "legend":
                if node.args or set(options) - {"loc", "title"}:
                    raise Unsupported("Legend handles/placement options need manual mapping")
                self.settings["legend"]["show"] = True
                if "loc" in options:
                    self.settings["legend"]["position"] = _literal(options["loc"]).replace(" ", "_")
                if "title" in options:
                    self.settings["legend"]["title"] = _literal(options["title"])
                return
            if method in {"show", "tight_layout"} and not node.args and not options:
                return
            if method == "savefig":
                self.issue(
                    node,
                    "Original export destination/layout is retained only in source; the new export is separate",
                    "presentation",
                )
                return
        if owner in self.figures and method == "savefig":
            self.issue(
                node, "Original export destination is not executed or reused", "presentation"
            )
            return
        raise Unsupported("Call is outside the supported plotting subset")

    def analyze(self):
        try:
            tree = ast.parse(self.source, feature_version=(3, 10))
        except (SyntaxError, ValueError, RecursionError) as problem:
            self.issue(
                SimpleNamespace(
                    lineno=getattr(problem, "lineno", 1), end_lineno=getattr(problem, "lineno", 1)
                ),
                "Source cannot be parsed as supported Python3.10 syntax",
                "syntax",
            )
            return self
        if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
            self.issue(tree, "Source exceeds the AST node limit", "resource")
            return self
        for statement in tree.body:
            try:
                if isinstance(statement, ast.Import):
                    for item in statement.names:
                        if item.name not in {"matplotlib.pyplot", "numpy", "pandas", "seaborn"}:
                            raise Unsupported(
                                "Import is not a supported plotting alias; it is not executed"
                            )
                        self.modules[item.asname or item.name] = item.name
                        self.values.pop(item.asname or item.name, None)
                        self.axes.discard(item.asname or item.name)
                        self.figures.discard(item.asname or item.name)
                elif isinstance(statement, ast.ImportFrom):
                    if (
                        statement.module != "matplotlib"
                        or len(statement.names) != 1
                        or statement.names[0].name != "pyplot"
                    ):
                        raise Unsupported("from-import is outside the supported alias subset")
                    item = statement.names[0]
                    self.unbind(item.asname or "pyplot")
                    self.modules[item.asname or "pyplot"] = "matplotlib.pyplot"
                elif isinstance(statement, ast.Assign):
                    self.assignment(statement)
                elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
                    self.call(statement.value)
                elif (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                ):
                    continue
                else:
                    raise Unsupported(
                        "Control flow,definitions and mutations are not executed or converted"
                    )
            except (Unsupported, KeyError, AttributeError, TypeError, ValueError) as problem:
                self.issue(
                    statement,
                    str(problem)
                    if isinstance(problem, Unsupported)
                    else "Unsupported or incomplete plotting arguments",
                )
                # A dynamic statement can mutate prior bindings. Do not borrow them
                # for later conversions; literal calls can still be reviewed separately.
                self.values.clear()
                self.modules.clear()
                self.axes.clear()
                self.figures.clear()
        return self


def convert(source, mapped_csv=None):
    if not isinstance(source, str) or len(source.encode()) > MAX_SOURCE:
        raise Unsupported("Source exceeds256KiB UTF8")
    parser = Parser(source).analyze()
    report = {
        "schema_version": 1,
        "parser_version": 1,
        "source_executed": False,
        "supported_plot_calls": len(parser.plots),
        "unsupported": parser.issues[:100],
        "unsupported_count": len(parser.issues),
        "unsupported_truncated": len(parser.issues) > 100,
        "dataset_references": sorted(set(parser.references)),
        "all_statements_supported": not parser.issues,
        "pixel_equivalence_claimed": False,
        "new_execution": False,
        "notice": "Static supported-subset extraction; canonical paper presentation is new. Review source, data binding, unsupported behavior and native checks.",
    }

    def refuse(reason):
        return {
            "report": {**report, "convertible": False, "reason": reason},
            "spec": None,
            "csv_text": None,
        }

    if not parser.plots:
        return refuse("No supported plot could be extracted")
    if len({p["kind"] for p in parser.plots}) != 1:
        return refuse("Mixed plot kinds need separate author-created figures")
    kind = parser.plots[0]["kind"]
    if kind == "bar" and len(parser.plots) != 1:
        return refuse("Multiple bar calls can overlap; grouped-bar conversion is not inferred")
    if len(set(parser.references)) > 1:
        return refuse("Multiple datasets require separate explicit mappings")
    data = None
    if mapped_csv is not None:
        reader = csv.DictReader(io.StringIO(mapped_csv))
        if (
            not reader.fieldnames
            or len(reader.fieldnames) > 128
            or len(set(reader.fieldnames)) != len(reader.fieldnames)
        ):
            return refuse("Mapped dataset needs unique bounded CSV columns")
        import pandas as pd

        try:
            frame = pd.read_csv(io.StringIO(mapped_csv), nrows=MAX_ROWS + 1)
        except (ValueError, pd.errors.ParserError):
            return refuse("Mapped dataset cannot be read with the supported default CSV settings")
        if len(frame) > MAX_ROWS:
            return refuse("Mapped dataset exceeds the row bound")
        data = frame.to_dict(orient="records")

    def vector(expr):
        if expr["type"] == "vector":
            return expr["values"]
        if data is None:
            raise Unsupported("Explicitly map the referenced CSV dataset before conversion")
        if data and expr["field"] not in data[0]:
            raise Unsupported("Mapped dataset does not contain a referenced column")
        return [row[expr["field"]] for row in data]

    rows = []
    labels = []
    identities = set()
    order = []
    try:
        for index, plot in enumerate(parser.plots):
            xs, ys = vector(plot["x"]), vector(plot["y"])
            hs = vector(plot["hue"]) if plot["hue"] else [None] * len(xs)
            if len(xs) != len(ys) or len(hs) != len(xs) or not xs:
                raise Unsupported("Vectors must have the same nonzero length")
            grouped = {}
            for record, (raw_x, raw_y, hue) in enumerate(zip(xs, ys, hs, strict=True)):
                x = raw_x
                y, issue = _number(raw_y)
                if kind != "bar":
                    x, xissue = _number(raw_x)
                    issue = issue or xissue
                elif not isinstance(x, str) or not x:
                    issue = "unsupported category"
                if issue:
                    raise Unsupported(
                        "Missing/nonfinite/unsupported plotted values require explicit cleaning; no rows were silently removed"
                    )
                if hue is not None and (
                    not isinstance(hue, str) or not hue or _number(hue)[1] is None
                ):
                    raise Unsupported(
                        "Numeric or missing hue has different color semantics; map it explicitly"
                    )
                label = hue if hue is not None else plot["label"] or f"Series {index + 1}"
                identity = f"plot-{index + 1}:" + label
                grouped.setdefault(identity, []).append(x)
                if identity not in identities:
                    if len(identities) >= 32:
                        raise Unsupported("Select at most32 plotted series")
                    identities.add(identity)
                    labels.append({"series": identity, "text": label})
                if kind == "bar" and x not in order:
                    order.append(x)
                rows.append(
                    {
                        "x": x,
                        "y": y,
                        "series": identity,
                        "source_line": plot["line"],
                        "source_record": record,
                    }
                )
                if len(rows) > MAX_ROWS:
                    raise Unsupported("Converted data exceeds100000 rows")
            if kind == "line" and any(
                any(b <= a for a, b in itertools.pairwise(values)) for values in grouped.values()
            ):
                raise Unsupported(
                    "Line steps must already increase strictly; duplicates/reordering are not silently changed"
                )
            if kind == "bar" and len(set(map(str, xs))) != len(xs):
                raise Unsupported(
                    "Duplicate bar categories overlap in Matplotlib; aggregation is not inferred"
                )
    except Unsupported as problem:
        return refuse(str(problem))
    text = io.StringIO(newline="")
    columns = ["x", "y", "series", "source_line", "source_record"]
    writer = csv.DictWriter(text, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    settings = parser.settings
    spec = {
        "kind": kind,
        "data": {"path": "imported-source.csv", "format": "csv", "columns": columns},
        "x": {
            "field": "x",
            "label": settings.get("xlabel", "x"),
            "scale": settings.get("xscale", "linear"),
        },
        "y": {
            "field": "y",
            "label": settings.get("ylabel", "y"),
            "scale": settings.get("yscale", "linear"),
        },
        "group": "series",
        "legend": {**settings["legend"], "labels": labels},
        "output": {"stem": "imported-source", "formats": ["png", "svg", "pdf"]},
    }
    if "title" in settings:
        spec["title"] = settings["title"]
    if "dpi" in settings:
        spec["output"]["dpi"] = settings["dpi"]
    if kind in {"line", "bar"}:
        spec["aggregation"] = "none"
    if kind == "line":
        spec["marker"] = True
    if kind == "bar":
        spec["order"] = list(map(str, order))
    return {
        "report": {
            **report,
            "convertible": True,
            "rows": len(rows),
            "series": len(labels),
            "requires_partial_review": bool(parser.issues),
            "dataset_binding_required": bool(parser.references),
        },
        "spec": spec,
        "csv_text": text.getvalue(),
    }
