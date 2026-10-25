import type { FigureSpec } from "../schema.ts";
import { pyStr } from "./py.ts";

/**
 * Manim-style animation, built on matplotlib rather than on manim.
 *
 * Manim itself wants cairo, ffmpeg and often a LaTeX install, and it draws its
 * own axes rather than the ones the rest of this emitter spent so long getting
 * right. What actually makes a manim animation read well is two things: rate
 * functions that ease instead of running at constant speed, and construction
 * staged so the eye is led through the figure. Both are a few lines on top of
 * matplotlib's FuncAnimation, and the result is the same publication figure in
 * motion rather than a second, differently styled one.
 *
 * The rate functions below are ports of manim's, and keep its names.
 */

export function emitEasing(out: string[]): void {
  out.push(
    "",
    "def smooth_rate(t, inflection=10.0):",
    "    # manim's default. Sigmoid, rescaled so it starts at 0 and ends at 1.",
    "    error = 1 / (1 + math.exp(inflection / 2))",
    "    value = 1 / (1 + math.exp(-inflection * (t - 0.5)))",
    "    return min(max((value - error) / (1 - 2 * error), 0.0), 1.0)",
    "",
    "",
    "def smoothstep(t):",
    "    t = min(max(t, 0.0), 1.0)",
    "    return t * t * (3 - 2 * t)",
    "",
    "",
    "def rush_into(t):",
    "    return 2 * smooth_rate(min(max(t, 0.0), 1.0) / 2.0)",
    "",
    "",
    "def rush_from(t):",
    "    return 2 * smooth_rate(0.5 + min(max(t, 0.0), 1.0) / 2.0) - 1",
    "",
    "",
    "RATE_FUNCTIONS = {",
    '    "linear": lambda t: min(max(t, 0.0), 1.0),',
    '    "smooth": smooth_rate,',
    '    "smoothstep": smoothstep,',
    '    "rush_into": rush_into,',
    '    "rush_from": rush_from,',
    "}",
    "",
  );
}

/** Reveal fractions per series, staggered so the eye follows one at a time. */
function emitProgress(out: string[]): void {
  out.push(
    "",
    "def series_progress(elapsed, index, count):",
    '    """How far series `index` has come in, from 0 to 1."""',
    "    start = index * ANIMATE_STAGGER",
    "    span = max(ANIMATE_DURATION - (count - 1) * ANIMATE_STAGGER, 0.1)",
    "    return RATE_FUNCTIONS[ANIMATE_EASING]((elapsed - start) / span)",
    "",
  );
}

function emitLineFrames(spec: FigureSpec & { kind: "line" }, out: string[]): void {
  const trace = true;
  out.push(
    "",
    "def build_animation(fig, ax, frame):",
    "    artists = [a for a in ax.get_lines()]",
    "    if not artists:",
    "        return None",
    "    full = [line.get_xydata().copy() for line in artists]",
    "    bands = [c for c in ax.collections]",
    "    for band in bands:",
    "        band.set_alpha(0.0)",
    "",
    "    def render(frame_index):",
    "        elapsed = frame_index / ANIMATE_FPS",
    "        for index, line in enumerate(artists):",
    "            data = full[index]",
    "            share = series_progress(elapsed, index, len(artists))",
    trace
      ? "            upto = max(int(round(share * len(data))), 0)"
      : "            upto = len(data)",
    "            line.set_data(data[:upto, 0], data[:upto, 1])",
    "        for band in bands:",
    "            band.set_alpha(BAND_ALPHA * series_progress(elapsed, 0, 1))",
    "        return artists + bands",
    "",
    "    return render, artists + bands",
    "",
  );
  void spec;
}

function emitBarFrames(out: string[]): void {
  out.push(
    "",
    "def build_animation(fig, ax, frame):",
    "    from matplotlib.patches import Rectangle",
    "",
    "    bars = [p for p in ax.patches if isinstance(p, Rectangle)]",
    "    if not bars:",
    "        return None",
    "    vertical = all(bar.get_width() < bar.get_height() or bar.get_height() == 0 for bar in bars)",
    "    targets = [(bar.get_width(), bar.get_height()) for bar in bars]",
    "",
    "    def render(frame_index):",
    "        elapsed = frame_index / ANIMATE_FPS",
    "        for index, bar in enumerate(bars):",
    "            width, height = targets[index]",
    "            share = series_progress(elapsed, index % max(SERIES_COUNT, 1), max(SERIES_COUNT, 1))",
    "            if vertical:",
    "                bar.set_height(height * share)",
    "            else:",
    "                bar.set_width(width * share)",
    "        return bars",
    "",
    "    return render, bars",
    "",
  );
}

function emitRevealFrames(out: string[]): void {
  out.push(
    "",
    "def build_animation(fig, ax, frame):",
    "    drawn = list(ax.get_lines()) + list(ax.collections) + list(ax.patches)",
    "    if not drawn:",
    "        return None",
    "    opacity = [a.get_alpha() if a.get_alpha() is not None else 1.0 for a in drawn]",
    "",
    "    def render(frame_index):",
    "        elapsed = frame_index / ANIMATE_FPS",
    "        for index, artist in enumerate(drawn):",
    "            share = series_progress(elapsed, index, len(drawn))",
    "            artist.set_alpha(opacity[index] * share)",
    "        return drawn",
    "",
    "    return render, drawn",
    "",
  );
}

export function emitAnimation(spec: FigureSpec, out: string[]): void {
  if (!spec.animate) return;

  emitEasing(out);
  emitProgress(out);

  const style = spec.animate.style;
  if (style === "grow" && spec.kind === "bar") emitBarFrames(out);
  else if ((style === "draw" || style === "trace") && spec.kind === "line") emitLineFrames(spec, out);
  else emitRevealFrames(out);

  out.push(
    "",
    "def write_animation(fig, ax, frame):",
    "    built = build_animation(fig, ax, frame)",
    "    if built is None:",
    '        print("nothing on the axes to animate")',
    "        return",
    "    render, artists = built",
    "",
    "    total = int(round((ANIMATE_DURATION + ANIMATE_HOLD) * ANIMATE_FPS))",
    "",
    "    def step(index):",
    "        return render(min(index, int(ANIMATE_DURATION * ANIMATE_FPS)))",
    "",
    "    animation = FuncAnimation(",
    "        fig,",
    "        step,",
    "        frames=total,",
    "        interval=1000 / ANIMATE_FPS,",
    "        blit=False,",
    "        repeat=False,",
    "    )",
    "",
    `    path = f"{STEM}.${spec.animate.format}"`,
    "    try:",
    spec.animate.format === "mp4"
      ? '        animation.save(path, writer=FFMpegWriter(fps=ANIMATE_FPS, bitrate=2400), dpi=ANIMATION_DPI)'
      : '        animation.save(path, writer=PillowWriter(fps=ANIMATE_FPS), dpi=ANIMATION_DPI)',
    "    except Exception as problem:",
    `        print(f"could not write {path}: {problem}")`,
    spec.animate.format === "mp4"
      ? '        print("mp4 needs ffmpeg on PATH. Set animate.format to \\"gif\\" to avoid it.")'
      : '        print("gif output needs pillow, which ships with matplotlib")',
    '        skip_output("animation", str(problem))',
    "        return",
    "    record_output(path)",
    '    print(f"wrote {path}")',
    "",
  );
  void pyStr;
}
