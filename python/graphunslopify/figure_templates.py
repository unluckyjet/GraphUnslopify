"""Portable canonical intent and reviewed export presets; never transfer a data binding."""

from __future__ import annotations

import copy
import json

from .errors import SpecError
from .project_changes import _differences
from .transport import local_request

KIND = "graphunslopify.figure-template"
MAX_TEMPLATE_BYTES = 1024 * 1024
PRESETS = [
    {
        "id": "paper-single",
        "name": "Paper · single column",
        "description": "Paper layout, 600 DPI, PNG/SVG/PDF. Check your venue requirements separately.",
        "settings": {
            "style": {"preset": "paper", "venue": "none"},
            "output": {"size": "single_column", "dpi": 600, "formats": ["png", "svg", "pdf"]},
        },
    },
    {
        "id": "paper-double",
        "name": "Paper · double column",
        "description": "Double-column paper layout, 600 DPI, PNG/SVG/PDF.",
        "settings": {
            "style": {"preset": "paper", "venue": "none"},
            "output": {"size": "double_column", "dpi": 600, "formats": ["png", "svg", "pdf"]},
        },
    },
    {
        "id": "review-png",
        "name": "Review copy · PNG",
        "description": "Single-column 144 DPI PNG; scientific checks still run.",
        "settings": {
            "output": {
                "size": "single_column",
                "dpi": 144,
                "formats": ["png"],
                "interactive": False,
                "latex": False,
            }
        },
    },
]


class TemplateError(ValueError):
    """A portable intent file or its current review cannot be established."""


def presets():
    return copy.deepcopy(PRESETS)


def _check(spec, validator):
    if not isinstance(spec, dict):
        raise TemplateError("Canonical figure intent must be a JSON object.")
    try:
        result = validator(copy.deepcopy(spec))
    except (SpecError, ValueError, TypeError) as error:
        raise TemplateError("Correct canonical figure intent: " + str(error)) from error
    if not isinstance(result.get("resolved"), dict):
        raise TemplateError("Canonical figure validation returned no resolved intent.")
    return result


def _size(value):
    if (
        len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf8"))
        > MAX_TEMPLATE_BYTES
    ):
        raise TemplateError("Figure templates are limited to 1 MiB.")


def create_template(spec, name, *, validator=None):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise TemplateError("Name the template using 1-100 characters.")
    check = _check(spec, validator or (lambda s: local_request("validate", s)))
    if not check["ok"]:
        raise TemplateError("Correct static errors before saving this template.")
    intent = copy.deepcopy(check["resolved"])
    intent.pop("data", None)
    intent.pop("palette_lock", None)
    intent["output"].pop("stem", None)
    value = {"kind": KIND, "schema_version": 1, "name": name.strip(), "intent": intent}
    _size(value)
    return value


def _read(value):
    _size(value)
    if (
        not isinstance(value, dict)
        or set(value) != {"kind", "schema_version", "name", "intent"}
        or value.get("kind") != KIND
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise TemplateError("Choose a version1 GraphUnslopify figure template.")
    if not isinstance(value["name"], str) or not 1 <= len(value["name"].strip()) <= 100:
        raise TemplateError("The template needs a name using 1-100 characters.")
    intent = value["intent"]
    if (
        not isinstance(intent, dict)
        or "data" in intent
        or "palette_lock" in intent
        or not isinstance(intent.get("output", {}), dict)
        or "stem" in intent.get("output", {})
    ):
        raise TemplateError("Templates must exclude dataset/palette paths and output stems.")
    checked = _check(
        {**intent, "data": {"path": "template-data.csv"}}, lambda s: local_request("validate", s)
    )

    def known(raw, resolved):
        if isinstance(raw, dict):
            if not isinstance(resolved, dict) or set(raw) - resolved.keys():
                raise TemplateError("Template contains unknown canonical settings.")
            for key, child in raw.items():
                known(child, resolved[key])
        elif isinstance(raw, list) and isinstance(resolved, list):
            for a, b in zip(raw, resolved, strict=True):
                known(a, b)

    known(intent, checked["resolved"])
    if not checked["ok"]:
        raise TemplateError("Correct static errors in the saved template.")
    return copy.deepcopy(intent)


def review_reuse(
    spec, *, template=None, preset=None, mapping=None, replace_claims=False, validator=None
):
    if type(replace_claims) is not bool or (template is None) == (preset is None):
        raise TemplateError("Review one template or one export preset.")
    validate = validator or (lambda s: local_request("validate", s))
    before = _check(spec, validate)
    fields = []
    if template is not None:
        intent = _read(template)
        portable = {**intent, "data": {"path": "template-data.csv"}}
        refs = local_request("template-fields", portable)
        fields = sorted({r["field"] for r in refs})
        candidate = local_request(
            "template-remap", {"spec": portable, "mapping": {} if mapping is None else mapping}
        )
        for key in ("data", "palette_lock"):
            candidate.pop(key, None)
            if key in spec:
                candidate[key] = copy.deepcopy(spec[key])
        candidate["output"].pop("stem", None)
        if "stem" in spec.get("output", {}):
            candidate["output"]["stem"] = spec["output"]["stem"]
        if not replace_claims:
            candidate.pop("claims", None)
            if "claims" in spec:
                candidate["claims"] = copy.deepcopy(spec["claims"])
        name = template["name"]
    else:
        if mapping or replace_claims:
            raise TemplateError("Export presets preserve fields and claims.")
        item = next((p for p in PRESETS if p["id"] == preset), None)
        if item is None:
            raise TemplateError("Choose an available export preset.")
        candidate = copy.deepcopy(spec)
        for key, settings in item["settings"].items():
            candidate[key] = {**candidate.get(key, {}), **settings}
        name = item["name"]
    after = _check(candidate, validate)
    changes = _differences(before["resolved"], after["resolved"])
    for key in ("data", "palette_lock"):
        assert (key in candidate, candidate.get(key)) == (key in spec, spec.get(key))
    result = {
        "name": name,
        "spec": candidate,
        "fields": fields,
        "changes": changes,
        "findings": after["findings"],
        "can_apply": bool(changes) and after["ok"],
        "execution": "not_run",
        "claims_policy": "template" if template is not None and replace_claims else "preserved",
        "preserved": ["dataset binding", "palette binding", "output stem"],
        "requires_verification": True,
    }
    _size(result)
    return result
