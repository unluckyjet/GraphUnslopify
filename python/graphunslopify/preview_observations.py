"""Local observation inspection for one completed, owned editor render."""

from __future__ import annotations

import hashlib
import json

from .observation_geometry import (
    resolve_matrix_cell,
    resolve_summary_estimate,
    resolve_summary_interval,
)
from .observation_provenance import _load_observation_selection
from .preview_reviews import _file
from .project import _execution_source, _inside

MATRIX_KINDS = frozenset({"heatmap", "confusion_matrix"})
_PAGE_SIZE = 50
_DETAIL_BYTES = 65536
_PROGRAM_BYTES = 20 * 1024 * 1024


def can_trace_observations(spec):
    kind = spec.get("kind")
    if kind in MATRIX_KINDS or kind == "forest":
        return True
    aggregation = spec.get("aggregation")
    if kind == "bar":
        return aggregation in ("mean", "median", "sum", "count") and not spec.get("stacked", False)
    uncertainty = spec.get("uncertainty")
    return (
        kind == "line"
        and aggregation in ("mean", "median")
        and isinstance(uncertainty, dict)
        and uncertainty.get("display", "band") in ("bar", "band")
    )


class PreviewObservations:
    """Share the editor's existing render owner without exposing the graph to reviewers."""

    def __init__(self, state):
        self.state = state

    def _load(self, record):
        evidence = record["review_evidence"]
        if not evidence["available"]:
            raise ValueError(evidence.get("error") or "No completed render evidence is available")
        folder = record["folder"]
        if folder.resolve() != folder or folder.parent != self.state.root / "runs":
            raise ValueError("The observation render folder changed")
        report = evidence["report"]
        reference = report.get("observation_selection") or {}
        keys = (
            ("matrix_geometry",)
            if report["spec"]["kind"] in MATRIX_KINDS
            else ("summary_interval_geometry", "summary_estimate_geometry")
        )
        references = [reference[f"{key}_node_id"] for key in keys if f"{key}_node_id" in reference]
        if not references:
            gaps = (reference[f"{key}_gap"] for key in keys if f"{key}_gap" in reference)
            raise ValueError(next(gaps, "This run has no supported PNG observation geometry"))
        _, graph = _load_observation_selection(
            folder,
            report,
            run_id=reference["run_id"],
            program_sha256=evidence["files"][evidence["script"]]["sha256"],
            require_contained_png=True,
        )
        if graph._source["snapshot_sha256"] != evidence["data_sha256"]:
            raise ValueError("The observation graph belongs to a different input snapshot")
        geometry = {}
        for identity in references:
            geometry.update(graph._nodes[identity]["metadata"])
        if "grids" in geometry:
            if geometry["gaps"]:
                raise ValueError("Matrix placement is unavailable. " + geometry["gaps"][0])
            if not geometry["grids"]:
                raise ValueError("The final PNG contains no matrix panels")
        return graph, geometry, reference

    def bind(self, record):
        """Publish geometry and scope handles only, keeping raw records on the server."""
        try:
            _, geometry, reference = self._load(record)
            interval_ids = self._interval_ids(geometry)
            return {
                "available": True,
                "image": geometry["image"],
                "grids": [
                    {"rows": len(grid["y_edges"]) - 1, "columns": len(grid["x_edges"]) - 1}
                    for grid in geometry.get("grids", ())
                ],
                "intervals": len(interval_ids),
                "estimates": len(self._estimate_ids(geometry)),
                "band": bool(geometry.get("bands")),
                "filters": reference["node_id"],
                "preparation": reference.get("preparation_node_id"),
            }
        except (OSError, KeyError, ValueError, TypeError) as problem:
            return {"available": False, "error": str(problem)}

    def _check_owner(self, owner, record):
        source = self.state.review_sources
        source._root()
        if source._selected(owner) is not record:
            raise ValueError("The observation render is stale")
        evidence = record["review_evidence"]
        if _execution_source() != evidence["execution_source"]:
            raise ValueError("The renderer source changed; render again")
        folder = record["folder"].relative_to(self.state.root)
        stem = evidence["report"]["spec"]["output"]["stem"]
        inputs = {
            evidence["script"],
            (folder / record["data"]).as_posix(),
            (folder / f"{stem}.figure.json").as_posix(),
            (folder / f"{stem}.report.json").as_posix(),
        }
        if evidence["palette_run"] is not None:
            inputs.add(evidence["palette_run"])
        inputs.update(name for name in evidence["files"] if name.startswith("uploads/"))
        for name in inputs:
            if _file(self.state.root, name) != evidence["files"][name]:
                raise ValueError("The rendered input, program or report changed; render again")
        if source._selected(owner) is not record:
            raise ValueError("The observation render is stale")

    def _owned(self, payload, allowed):
        source = self.state.review_sources
        fields = source.selection_fields | {"image_sha256"}
        if not fields <= payload.keys() or payload.keys() - fields - allowed:
            raise ValueError("Choose a current observation render and a supported operation")
        owner = {key: payload[key] for key in source.selection_fields}
        record = source._selected(owner)
        binding = record.get("observations", {})
        if not binding.get("available") or payload["image_sha256"] != binding["image"]["sha256"]:
            raise ValueError("Observation evidence does not match the current PNG")
        self._check_owner(owner, record)
        graph, geometry, reference = self._load(record)
        if geometry["image"] != binding["image"]:
            raise ValueError("The observation image changed; render again")
        return owner, record, graph, geometry, reference

    def _finish(self, owner, record, geometry, reference):
        folder = record["folder"].relative_to(self.state.root)
        image = geometry["image"]
        image_file = _file(self.state.root, (folder / image["path"]).as_posix())
        graph_file = _file(self.state.root, (folder / reference["path"]).as_posix())
        if image_file != {key: image[key] for key in ("sha256", "bytes")}:
            raise ValueError("The observation PNG changed; render again")
        if graph_file["sha256"] != reference["sha256"]:
            raise ValueError("The observation graph changed; render again")
        self._check_owner(owner, record)

    @staticmethod
    def _interval_ids(geometry):
        identities = [stroke["node_id"] for stroke in geometry.get("strokes", ())]
        identities.extend(
            identity for strip in geometry.get("bands", ()) for identity in strip["interval_ids"]
        )
        return tuple(dict.fromkeys(identities))

    @staticmethod
    def _estimate_ids(geometry):
        return tuple(dict.fromkeys(mark["node_id"] for mark in geometry.get("estimates", ())))

    @staticmethod
    def _cell_center(geometry, cell):
        if not isinstance(cell, list) or len(cell) != 3:
            raise ValueError("Choose a matrix panel, row and column")
        if any(type(index) is not int or index < 0 for index in cell):
            raise ValueError("Matrix selection indices must be nonnegative integers")
        panel, row, column = cell
        if panel >= len(geometry["grids"]):
            raise ValueError("Unknown matrix panel")
        grid = geometry["grids"][panel]
        if row >= len(grid["y_edges"]) - 1 or column >= len(grid["x_edges"]) - 1:
            raise ValueError("Unknown matrix cell")
        left, top, right, bottom = grid["clip"]
        x0, x1 = sorted(grid["x_edges"][column : column + 2])
        y0, y1 = sorted(grid["y_edges"][row : row + 2])
        x0, x1 = max(left, x0), min(right, x1)
        y0, y1 = max(top, y0), min(bottom, y1)
        if x0 >= x1 or y0 >= y1:
            raise ValueError("The selected cell is outside the rendered image")
        return (x0 + x1) / 2, (y0 + y1) / 2

    def query(self, payload):
        selectors = {"position", "cell", "interval_index", "estimate_index", "node_id"}
        selected = selectors & payload.keys()
        offset = payload.get("offset", 0)
        if len(selected) != 1 or type(offset) is not int or not 0 <= offset <= 200_000:
            raise ValueError("Choose one observation target and a valid page")
        owner, record, graph, geometry, reference = self._owned(
            payload, selectors | {"offset", "tolerance", "position_kind"}
        )
        estimate = payload.get("position_kind") == "estimate" or (
            "estimates" in geometry and "strokes" not in geometry
        )
        if "position_kind" in payload and (
            "position" not in payload
            or payload["position_kind"] != "estimate"
            or "estimates" not in geometry
        ):
            raise ValueError("Choose a position on the estimate PNG")
        if "tolerance" in payload and (
            "position" not in payload or ("strokes" not in geometry and not estimate)
        ):
            raise ValueError("Pick tolerance only applies to a summary mark position")
        if "node_id" in payload:
            node_id = payload["node_id"]
            if not isinstance(node_id, str) or node_id not in graph._nodes:
                raise ValueError("Unknown observation graph node")
        elif "interval_index" in payload or "estimate_index" in payload:
            interval = "interval_index" in payload
            key = "interval_index" if interval else "estimate_index"
            index = payload[key]
            ids = self._interval_ids(geometry) if interval else self._estimate_ids(geometry)
            if type(index) is not int or not 0 <= index < len(ids):
                raise ValueError(
                    "Choose a visible interval" if interval else "Choose a visible estimate"
                )
            node_id = ids[index]
        else:
            if "cell" in payload and "grids" not in geometry:
                raise ValueError("This PNG has summary marks. Choose a summary mark or a pixel.")
            point = (
                self._cell_center(geometry, payload["cell"])
                if "cell" in payload
                else payload["position"]
            )
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError("Use two natural image coordinates")
            if estimate:
                node_id = resolve_summary_estimate(
                    geometry, *point, tolerance=payload.get("tolerance", 0)
                )
            elif "strokes" in geometry:
                node_id = resolve_summary_interval(
                    geometry, *point, tolerance=payload.get("tolerance", 2)
                )
            else:
                node_id = resolve_matrix_cell(geometry, graph._nodes, *point)
        answer = None if node_id is None else self._page(graph, node_id, offset)
        self._finish(owner, record, geometry, reference)
        return {"selection": answer, "page_size": _PAGE_SIZE}

    @staticmethod
    def _page(graph, node_id, offset):
        node = graph._nodes[node_id]
        explained = graph.explain(node_id)
        end = offset + _PAGE_SIZE
        detail = {key: item for key, item in node.items() if key not in {"inputs", "excluded"}}
        if len(json.dumps(detail).encode()) > _DETAIL_BYTES:
            detail = {
                "id": node_id,
                "kind": node["kind"],
                "operation": node.get("operation"),
                "detail_in_download": True,
            }
        result = {"node": detail, "offset": offset}
        for key in ("contributing_records", "excluded_records"):
            rows = explained[key]
            result[key] = {"total": len(rows), "items": rows[offset:end]}
        for key in ("inputs", "excluded"):
            edges = node.get(key, [])
            items = [
                {
                    "id": item["id"],
                    "label": item.get("operation") or item.get("reason") or "Source record",
                    "record_ordinal": item.get("record_ordinal"),
                }
                for item in (graph._nodes[identity] for identity in edges[offset:end])
            ]
            result[key] = {"total": len(edges), "items": items}
        return result

    def download(self, payload):
        choice = payload.get("document")
        if choice not in ("program", "graph"):
            raise ValueError("Choose the observation graph or generated program")
        owner, record, graph, geometry, reference = self._owned(payload, {"document"})
        if choice == "graph":
            raw = graph.to_json()
            if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
                raise ValueError("Observation graph bytes changed")
            content_type, filename = "application/json; charset=utf-8", reference["path"]
        else:
            evidence = record["review_evidence"]
            program = _inside(self.state.root, evidence["script"])
            with program.open("rb") as source:
                raw = source.read(_PROGRAM_BYTES + 1)
            if (
                len(raw) > _PROGRAM_BYTES
                or hashlib.sha256(raw).hexdigest()
                != evidence["files"][evidence["script"]]["sha256"]
            ):
                raise ValueError("The generated program changed; render again")
            content_type, filename = "text/plain; charset=utf-8", None
        self._finish(owner, record, geometry, reference)
        return raw, content_type, filename
