/** Runtime context is captured by the generated program, never by translation. */
export function emitEnvironment(out: string[], excel = false): void {
  const source = String.raw`

def capture_environment(fig=None):
    if RUN_REPORT.get("environment") is not None:
        return RUN_REPORT["environment"]
    import importlib.metadata as package_metadata
    import platform
    unavailable = []
    def installed(name):
        try:
            return package_metadata.version(name)
        except package_metadata.PackageNotFoundError:
            return None
        except Exception:
            unavailable.append(name + ".version")
            return None
    def text(value):
        return str(value) if value else None
    core = {name: text(getattr(module, "__version__", None)) for name, module in
            (("numpy", np), ("pandas", pd), ("matplotlib", matplotlib), ("Pillow", sys.modules.get("PIL")))}
    core["freetype"] = text(getattr(getattr(matplotlib, "ft2font", None), "__freetype_version__", None))
    rc = None
    font = None
    if fig is not None:
        keys = ("font.family", "font.size", "font.style", "font.weight", "font.variant", "font.stretch", "mathtext.fontset",
                "text.usetex", "text.parse_math", "svg.fonttype", "pdf.fonttype", "ps.fonttype",
                "savefig.transparent", "savefig.facecolor", "figure.facecolor", "axes.facecolor",
                "path.simplify", "path.simplify_threshold", "agg.path.chunksize", "svg.hashsalt")
        rc = {key: matplotlib.rcParams.get(key) for key in keys}
        try:
            from matplotlib import font_manager
            path = Path(font_manager.findfont(font_manager.FontProperties()))
            font = {"family": font_manager.get_font(str(path)).family_name,
                    "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        except Exception:
            unavailable.append("default_font")
    snapshot = {
        "schema_version": 1,
        "capture_stage": "before_export" if fig is not None else "no_export_snapshot",
        "python": {"version": platform.python_version(), "implementation": platform.python_implementation(),
                   "optimize": sys.flags.optimize, "hash_randomization": bool(sys.flags.hash_randomization)},
        "platform": {"system": text(platform.system()), "machine": text(platform.machine())},
        "loaded_core_versions": core,
        "installed_optional_versions": {name: installed(name) for name in ("graphunslopify", "plotly", "scipy", "pypdf")},
        "rendering": {"backend": str(matplotlib.get_backend()),
                      "figure_inches": list(map(float, fig.get_size_inches())) if fig is not None else None,
                      "figure_dpi": float(fig.dpi) if fig is not None else None,
                      "export_dpi": DPI, "target_width_in": TARGET_WIDTH_IN,
                      "requested_formats": list(FORMATS),
                      "requested_interactive": RUN_REPORT["spec"]["output"]["interactive"],
                      "rc_parameters": rc, "default_font": font},
        "execution": dict(RUN_REPORT.get("_execution_policy", {"strict": None, "fail_on_warning": None, "source": "direct_call"})),
        "random_constants": {key: globals()[key] for key in ("BOOTSTRAP_SEED", "BOOTSTRAP_DRAWS", "POINT_JITTER_SEED", "PAIR_SEED") if key in globals()},
        "unavailable": unavailable,
    }
    # Detach mutable rc lists and normalize the stored snapshot to JSON types.
    snapshot = json.loads(json.dumps(snapshot, allow_nan=False))
    RUN_REPORT["environment"] = snapshot
    return snapshot
`;
  out.push(...(excel ? source.replace(
    '("graphunslopify", "plotly", "scipy", "pypdf")',
    '("graphunslopify", "plotly", "scipy", "pypdf", "python-calamine")',
  ) : source).split("\n"));
}
