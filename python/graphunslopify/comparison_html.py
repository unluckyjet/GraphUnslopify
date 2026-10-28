"""A portable, passive-artifact review surface; untrusted text stays text."""

from __future__ import annotations

import base64
import hashlib
import html
import json
from pathlib import Path

_SCRIPT = """document.querySelectorAll('[data-blend]').forEach(input => {
  const image = input.closest('.blend').querySelector('.upper');
  const update = () => { image.style.opacity = input.value / 100; };
  input.addEventListener('input', update); update();
});"""
_STYLE = """*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#192734;font:16px/1.55 system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:32px 24px}h1{font-size:2.4rem;line-height:1.15;letter-spacing:-.04em;margin:8px 0 16px}h2{margin:0;font-size:1.5rem}h3{font-size:1rem;margin:0 0 8px}.eyebrow{color:#236a60;font-size:.8rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase}.muted,figcaption{color:#536171;font-size:.88rem}.notice{border-left:4px solid #ba7400;background:#fff7e7;padding:14px 18px}.summary{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}.badge{display:inline-block;background:#e4ebf1;border-radius:6px;padding:3px 9px;font-size:.85rem}.badge.failed,.badge.incomplete{background:#ffe5df;color:#8b2615}nav{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}a{color:#145b85;overflow-wrap:anywhere}nav a{background:white;border:1px solid #d4dce4;border-radius:6px;padding:6px 12px}section{background:white;border:1px solid #d4dce4;border-radius:12px;padding:24px;margin:24px 0;scroll-margin:20px}.heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:22px 0}figure{margin:0;min-width:0}figure img{display:block;width:100%;height:auto;max-height:650px;object-fit:contain;background:white;border:1px solid #e1e6eb}figcaption{padding:8px 0;overflow-wrap:anywhere}.missing{background:#f4f6f8;padding:30px 18px;min-height:120px;border:1px dashed #b1bdc9}.details{border-top:1px solid #e1e6eb;margin-top:16px;padding-top:12px}summary{cursor:pointer;font-weight:600}pre{font:13px/1.5 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;border-radius:6px;padding:14px;max-height:440px;overflow:auto}.metrics{display:flex;gap:18px;flex-wrap:wrap;background:#edf4f2;padding:14px;margin:16px 0}.metric strong{display:block;font-size:1.2rem}.metric span{font-size:.85rem;color:#435c58}.difference{max-width:620px}.blend{margin:20px 0;max-width:620px}.stack{position:relative}.stack img{display:block;width:100%;height:auto}.stack .upper{position:absolute;inset:0}.blend label{display:block;margin-top:8px}.blend input{width:100%;min-height:32px}.explanation{padding:10px 0;border-bottom:1px solid #edf0f3}.explanation p{margin:4px 0}.verdicts{overflow-wrap:anywhere}.scope{font-size:.9rem;color:#536171}footer{margin:30px 0;font-size:.9rem;color:#536171}@media(max-width:650px){main{padding:20px 12px}h1{font-size:2rem}section{padding:16px}.pair{grid-template-columns:1fr}.heading{align-items:flex-start}}"""


def _text(value) -> str:
    return html.escape(str(value), quote=True)


def _json(value) -> str:
    return _text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def _uri(preview: dict, folder: Path) -> str:
    payload = (folder / preview["path"]).read_bytes()
    return f"data:{preview['mime']};base64,{base64.b64encode(payload).decode()}"


def _image(side: dict, folder: Path, label: str) -> str:
    if side["status"] != "available":
        return f'<div class="missing">{_text(side["reason"])}</div>'
    dimensions = (
        " x ".join(map(str, side["dimensions"])) + " px"
        if side["dimensions"]
        else "browser SVG preview; pixel metrics unknown"
    )
    return (
        f'<img src="{_uri(side["preview"], folder)}" alt="{_text(label)}">'
        f"<figcaption>{_text(side['format'].upper())} · {_text(dimensions)} · verified saved bytes</figcaption>"
    )


def render_html(report: dict, folder: Path) -> str:
    count = len(report["figures"])
    count_label = f"{count} figure" + ("s" if count != 1 else "")
    change_label = "Changes detected" if report["changed"] else "No recorded changes"
    script_hash = base64.b64encode(hashlib.sha256(_SCRIPT.encode()).digest()).decode()
    csp = f"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'; base-uri 'none'; form-action 'none'"
    content = [
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{html.escape(csp, quote=True)}"><title>GraphUnslopify · Figure comparison</title><style>{_STYLE}</style></head><body><main>',
        '<div class="eyebrow">GraphUnslopify · saved evidence</div><h1>See what changed.</h1>',
        "<p>Compare figure versions alongside the data, settings and validation evidence that changed.</p>",
        f'<div class="summary"><span class="badge">{count_label}</span><span class="badge">{change_label}</span><span class="badge">Previews: {_text(report["preview_status"])}</span></div>',
        f'<p class="verdicts">Before validation: <strong>{_text(report["before_status"])}</strong> (exit {report["before_exit_code"]}) · After validation: <strong>{_text(report["after_status"])}</strong> (exit {report["after_exit_code"]})</p>',
        '<p class="notice">A matching picture does not establish scientific validity. Observed changes do not identify their cause. Failed or incomplete source audits retain that status here.</p>',
        '<nav aria-label="Figures">',
    ]
    content.extend(
        f'<a href="#figure-{i}">{_text(f["id"])}</a>' for i, f in enumerate(report["figures"])
    )
    content.append("</nav>")
    content.append(
        f"<details><summary>Source acceptance settings</summary><pre>{_json({'before': report['before_policy'], 'after': report['after_policy']})}</pre></details>"
    )
    for index, figure in enumerate(report["figures"]):
        name = _text(figure["id"])
        a, b = figure["before"], figure["after"]
        content += [
            f'<section id="figure-{index}"><div class="heading"><h2>{name}</h2><span class="badge">{_text(figure["kind"])}</span></div>',
            f'<p class="scope">Before: {_text(figure["before_status"] or "not present")} · After: {_text(figure["after_status"] or "not present")}</p>',
            f'<div class="pair"><figure><h3>Before</h3>{_image(a, folder, "Before figure " + figure["id"])}</figure><figure><h3>After</h3>{_image(b, folder, "After figure " + figure["id"])}</figure></div>',
        ]
        metrics = figure["metrics"]
        if metrics:
            content += [
                f'<div class="metrics"><div class="metric"><strong>{metrics["visible_pixels_changed"]:,}</strong><span>visible pixels changed ({metrics["visible_changed_fraction"]:.2%})</span></div><div class="metric"><strong>{metrics["rgba_pixels_changed"]:,}</strong><span>RGBA pixels changed</span></div><div class="metric"><strong>{metrics["mean_absolute_rgb_channel_difference"]:.4f}</strong><span>mean RGB channel delta (0-255)</span></div></div>',
                '<p class="scope">Exact native pixel grid; no resizing. Visible differences use a white background. Invisible RGB changes under transparency can affect the RGBA count without changing the visible picture.</p>',
                f'<figure class="difference"><h3>Visible difference map</h3><img src="{_uri(figure["difference"], folder)}" alt="Visible pixel difference map for {name}"><figcaption>Magenta marks changed visible pixels. Grey marks identical pixels. The map shows location, not scientific importance or error magnitude.</figcaption></figure>',
                f'<details><summary>Blend before and after</summary><div class="blend"><div class="stack"><img src="{_uri(a["preview"], folder)}" alt="Before layer for {name}"><img class="upper" src="{_uri(b["preview"], folder)}" alt="After layer for {name}"></div><label>After opacity<input data-blend type="range" min="0" max="100" value="50" aria-label="After opacity for {name}"></label></div></details>',
            ]
        else:
            reason = {
                "dimensions_changed": "Canvas dimensions changed. No pixel score or resized difference is computed.",
                "preview_only": "Preview only. SVG or differing preview formats have no server-side pixel score.",
                "unavailable": "Visual comparison is unavailable. Restore verified files or export a supported static format.",
                "added": "A new figure has no before image to compare.",
                "removed": "A removed figure has no after image to compare.",
            }[figure["visual_status"]]
            content.append(f'<p class="notice">{reason}</p>')
        content.append("<h3>What changed and why to review it</h3>")
        if not figure["explanations"]:
            content.append(
                "<p>No data, settings, claims, validation or environment change was recorded. Check exported-byte changes below; metadata can change without a visible change.</p>"
            )
        for explanation in figure["explanations"]:
            content.append(
                f'<div class="explanation"><strong>{_text(explanation["field"].replace("_", " ").capitalize())}</strong><p>{_text(explanation["message"])}</p>'
            )
            if "before" in explanation:
                detail = explanation.get("details") or {
                    "before": explanation["before"],
                    "after": explanation["after"],
                }
                content.append(
                    f"<details><summary>Before/after evidence</summary><pre>{_json(detail)}</pre></details>"
                )
            content.append("</div>")
        content.append(
            f'<details class="details"><summary>Exported-byte changes across formats</summary><pre>{_json({"changes": figure["output_changes"], "before": figure["outputs_before"], "after": figure["outputs_after"]})}</pre></details></section>'
        )
    content += ["<footer><strong>Scope and limits</strong><ul>"]
    content.extend(f"<li>{_text(item)}</li>" for item in report["limitations"])
    content += [
        "</ul><p>This self-contained report needs no network connection. Saved source files and datasets are not executed.</p></footer>",
        f"</main><script>{_SCRIPT}</script></body></html>",
    ]
    return "\n".join(content)
