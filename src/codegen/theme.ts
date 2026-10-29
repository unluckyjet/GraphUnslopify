/**
 * Every presentation decision in one place.
 *
 * The spec never carries a colour, a line width, or a font size, so this file
 * is the only thing that decides how a figure looks. Two figures built from two
 * specs agree with each other because they both come through here.
 */

/** Okabe-Ito, minus the yellow, which is unreadable on white. */
export const PALETTE = [
  "#0072B2",
  "#D55E00",
  "#009E73",
  "#CC79A7",
  "#E69F00",
  "#56B4E9",
  "#8C564B",
  "#000000",
];

/** Blue to red through white, for a scale centred on zero. */
export const DIVERGING = ["#2166AC", "#67A9CF", "#D1E5F0", "#F7F7F7", "#FDDBC7", "#EF8A62", "#B2182B"];
/** Perceptually ordered, for magnitudes. */
export const SEQUENTIAL = "viridis";

export const RECEDED_ALPHA = 0.4;
export const BAND_ALPHA = 0.18;
export const RAW_ALPHA = 0.22;

/**
 * Any chart with more than this many series carries a second visual channel.
 *
 * One, so it always applies. Okabe-Ito is colourblind-safe but not
 * greyscale-safe, and reordering cannot fix that. Searching every permutation,
 * the best ordering still leaves four series only 0.094 apart in relative
 * luminance, under the 0.10 a reader needs. Luminance runs out, a second
 * channel does not. The first entry in each cycle is the plain form, so a
 * single-series chart looks untouched.
 */
export const SECOND_CHANNEL_THRESHOLD = 1;
export const LINE_STYLES = ["-", "--", "-.", ":"];
export const MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"];
export const HATCHES = ["", "///", "...", "xxx", "\\\\\\", "+++", "ooo", "**"];

export const FIGURE_SIZES = {
  single_column: [3.4, 2.6],
  double_column: [7.0, 4.2],
} as const;

/**
 * Column widths and font floors from each venue's submission guide. A figure
 * measured against the wrong width passes a check it should have failed.
 */
export const VENUE_RULES = {
  none: { single: 3.4, double: 7.0, min_pt: 5.0 },
  neurips: { single: 3.25, double: 5.5, min_pt: 6.0 },
  icml: { single: 3.25, double: 6.75, min_pt: 6.0 },
  iclr: { single: 3.25, double: 5.5, min_pt: 6.0 },
  nature: { single: 3.5, double: 7.2, min_pt: 5.0 },
  ieee: { single: 3.5, double: 7.16, min_pt: 6.0 },
} as const;

export const PRESETS = {
  paper: {
    rc: {
      "pdf.fonttype": 42,
      "ps.fonttype": 42,
      "font.size": 9,
      "axes.labelsize": 9,
      "axes.titlesize": 9,
      "xtick.labelsize": 8,
      "ytick.labelsize": 8,
      "legend.fontsize": 8,
      "axes.linewidth": 0.8,
      "xtick.major.width": 0.8,
      "ytick.major.width": 0.8,
    },
    line: { base: 1.4, emphasis: 2.2, muted: 1.0 },
    marker: { base: 18, emphasis: 30, muted: 12 },
    annotation_pt: 8,
    panel_letter_pt: 10,
  },
  paper_compact: {
    rc: {
      "pdf.fonttype": 42,
      "ps.fonttype": 42,
      "font.size": 8,
      "axes.labelsize": 8,
      "axes.titlesize": 8,
      "xtick.labelsize": 7,
      "ytick.labelsize": 7,
      "legend.fontsize": 7,
      "axes.linewidth": 0.7,
      "xtick.major.width": 0.7,
      "ytick.major.width": 0.7,
    },
    line: { base: 1.2, emphasis: 1.9, muted: 0.9 },
    marker: { base: 14, emphasis: 24, muted: 10 },
    annotation_pt: 7,
    panel_letter_pt: 9,
  },
} as const;

export const LEGEND_LOCATIONS = {
  best: 'loc="best"',
  upper_left: 'loc="upper left"',
  upper_right: 'loc="upper right"',
  lower_left: 'loc="lower left"',
  lower_right: 'loc="lower right"',
  outside_right: 'loc="center left", bbox_to_anchor=(1.02, 0.5)',
  outside_bottom: 'loc="upper center", bbox_to_anchor=(0.5, -0.18)',
} as const;

/** How each kind of reference line is drawn, so the spec only says what it means. */
export const REFERENCE_STYLES = {
  chance: { style: '":"', width: 1.0, colour: '"#767676"' },
  human: { style: '"--"', width: 1.2, colour: '"#404040"' },
  threshold: { style: '"--"', width: 1.0, colour: '"#767676"' },
  baseline: { style: '"-"', width: 1.0, colour: '"#a0a0a0"' },
  target: { style: '"-."', width: 1.2, colour: '"#404040"' },
  other: { style: '":"', width: 1.0, colour: '"#767676"' },
} as const;

export const READERS = {
  csv: "read_csv",
  parquet: "read_parquet",
  json: "read_json",
  excel: "read_excel",
} as const;

export const TOOL_VERSION = "0.8.0";

/**
 * Kinds whose second channel is a dash pattern rather than a hatch or a marker.
 *
 * Anything that draws a line belongs here. Adding a kind to the emitter and
 * forgetting this list produces a NameError on HATCHES at render time, which
 * has happened twice.
 */
export const DASHED_KINDS = new Set([
  "line",
  "ecdf",
  "slope",
  "calibration",
  "kaplan_meier",
]);

/** Kinds whose second channel is the marker shape, because they draw points. */
export const MARKER_KINDS = new Set(["scatter", "qq", "scaling_fit"]);
