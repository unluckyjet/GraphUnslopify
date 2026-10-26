"""Each test builds a figure with one specific defect and checks it is caught.

The point of these is that the checks fire on real matplotlib output rather than
on a mock, because every bug this package exists to catch survived both a unit
test and a successful render.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from graphunslopify import inspect_figure
from graphunslopify.colour import distance, simulate, worst_case_distance


def codes(figure, **kwargs) -> set[str]:
    return {finding.code for finding in inspect_figure(figure, **kwargs).findings}


@pytest.fixture
def close_figures():
    yield
    plt.close("all")


pytestmark = pytest.mark.usefixtures("close_figures")


def test_offscreen_minor_log_labels_do_not_create_false_collisions():
    fig, ax = plt.subplots(figsize=(3.3, 2.5))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.plot([1, 2], [3, 6])
    # Make hidden labels deliberately collide; keep actual tick labels short
    # independently of the installed Matplotlib version's default log formatter.
    from matplotlib.ticker import FuncFormatter

    for axis, limits in ((ax.xaxis, ax.get_xlim()), (ax.yaxis, ax.get_ylim())):

        def format_tick(value, position, limits=limits):
            return (
                f"undrawn overlapping minor label {value:g}"
                if not limits[0] <= value <= limits[1]
                else f"{value:g}"
            )

        axis.set_major_formatter(FuncFormatter(format_tick))
        axis.set_minor_formatter(FuncFormatter(format_tick))
    fig.tight_layout()
    assert not {"labels_collide", "tick_labels_collide"} & codes(fig)


def test_visible_minor_tick_collisions_are_still_reported():
    from matplotlib.ticker import FixedFormatter, FixedLocator

    fig, ax = plt.subplots(figsize=(3.3, 2.5))
    ax.set_xscale("log")
    ax.set_xlim(1, 2)
    ax.xaxis.set_major_locator(FixedLocator([1]))
    ax.xaxis.set_minor_locator(FixedLocator([1.49, 1.5]))
    ax.xaxis.set_minor_formatter(FixedFormatter(["crowded minor alpha", "crowded minor beta"]))
    assert "tick_labels_collide" in codes(fig)


# --- colour science -------------------------------------------------------


def test_white_against_black_is_the_reference_maximum():
    assert distance((1, 1, 1), (0, 0, 0)) == pytest.approx(100.0, abs=0.5)


def test_a_colour_is_identical_to_itself():
    assert distance((0.2, 0.6, 0.9), (0.2, 0.6, 0.9)) == pytest.approx(0.0)


def test_red_against_green_collapses_for_a_deuteranope():
    gap, condition = worst_case_distance((0.8, 0.1, 0.1), (0.1, 0.6, 0.2))
    assert gap < 11.0
    assert condition == "deuteranopia"


def test_okabe_ito_blue_and_vermillion_survive_every_deficiency():
    gap, _ = worst_case_distance((0.0, 0.447, 0.698), (0.835, 0.369, 0.0))
    assert gap > 11.0


def test_simulation_leaves_greys_alone():
    grey = (0.5, 0.5, 0.5)
    for deficiency in ("protanopia", "deuteranopia", "tritanopia"):
        assert distance(grey, simulate(grey, deficiency)) < 2.0


# --- the bug that shipped this morning ------------------------------------


def test_series_muted_to_the_same_grey_are_caught():
    fig, ax = plt.subplots()
    for name in ("baseline", "+augment", "+distill"):
        ax.plot([1, 2, 3], [1, 2, 3], color="#bdbdbd", label=name)
    ax.plot([1, 2, 3], [2, 3, 4], color="#CC79A7", label="ours")
    ax.legend()
    assert "series_indistinguishable" in codes(fig)


def test_the_okabe_ito_palette_passes():
    fig, ax = plt.subplots()
    for index, colour in enumerate(["#0072B2", "#D55E00", "#009E73", "#CC79A7"]):
        ax.plot([1, 2, 3], [index, index + 1, index + 2], color=colour, label=f"s{index}")
    ax.legend(loc="upper left")
    assert "series_indistinguishable" not in codes(fig)


def test_red_against_green_is_flagged_on_a_real_figure():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3], color="#cc1a1a", label="control")
    ax.plot([1, 2, 3], [2, 3, 4], color="#1a9933", label="treatment")
    ax.legend(loc="upper left")
    assert "series_indistinguishable" in codes(fig)


def test_a_second_channel_excuses_a_colour_vision_clash():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3], color="#cc1a1a", linestyle="-", label="control")
    ax.plot([1, 2, 3], [2, 3, 4], color="#1a9933", linestyle="--", label="treatment")
    ax.legend(loc="upper left")
    assert "series_indistinguishable" not in codes(fig)


def test_bar_series_are_examined_at_all():
    """A bar legend hands back a BarContainer, not a patch.

    The colour check silently skipped every bar chart until this was noticed,
    because the container carries no colour of its own and the extractor found
    nothing to measure.
    """
    from graphunslopify.inspect import _series_appearance

    _fig, ax = plt.subplots()
    ax.bar([0, 1], [1, 2], color="#0072B2", label="Kids")
    ax.bar([0.4, 1.4], [2, 1], color="#D55E00", label="Adults")
    ax.legend()
    assert len(_series_appearance(ax)) == 2


def test_bars_in_the_same_colour_are_caught():
    fig, ax = plt.subplots()
    ax.bar([0, 1], [1, 2], color="#0072B2", label="Kids")
    ax.bar([0.4, 1.4], [2, 1], color="#0072B2", label="Adults")
    ax.legend()
    assert "series_indistinguishable" in codes(fig)


def test_hatching_rescues_bars_that_merge_in_greyscale():
    """Okabe-Ito blue and vermillion sit 0.07 apart in luminance."""
    fig, ax = plt.subplots()
    ax.bar([0, 1], [1, 2], color="#0072B2", label="Kids")
    ax.bar([0.4, 1.4], [2, 1], color="#D55E00", label="Adults")
    ax.legend()
    assert "greyscale_collision" in codes(fig)

    fig2, ax2 = plt.subplots()
    ax2.bar([0, 1], [1, 2], color="#0072B2", hatch="", edgecolor="white", label="Kids")
    ax2.bar([0.4, 1.4], [2, 1], color="#D55E00", hatch="///", edgecolor="white", label="Adults")
    ax2.legend()
    assert "greyscale_collision" not in codes(fig2)


def test_scatter_markers_count_as_a_second_channel():
    """A PathCollection has no get_marker, so the shape has to come from the path."""
    from graphunslopify.inspect import _series_appearance

    fig, ax = plt.subplots()
    ax.scatter([1, 2], [1, 2], marker="o", color="#0072B2", label="A")
    ax.scatter([1, 2], [2, 3], marker="s", color="#D55E00", label="B")
    ax.legend(loc="upper left")

    channels = {channel for _, _, channel in _series_appearance(ax)}
    assert len(channels) == 2
    assert "greyscale_collision" not in codes(fig)


def test_matching_scatter_markers_do_not_excuse_a_clash():
    fig, ax = plt.subplots()
    ax.scatter([1, 2], [1, 2], marker="o", color="#0072B2", label="A")
    ax.scatter([1, 2], [2, 3], marker="o", color="#D55E00", label="B")
    ax.legend(loc="upper left")
    assert "greyscale_collision" in codes(fig)


def test_a_colourbar_is_not_a_second_panel():
    fig, ax = plt.subplots()
    image = ax.imshow([[1, 2], [3, 4]])
    fig.colorbar(image, ax=ax)
    found = codes(fig)
    assert "panels_disagree_on_x" not in found
    assert "panels_disagree_on_y" not in found


# --- readability ----------------------------------------------------------


def test_text_below_five_points_is_an_error():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.set_xlabel("Epoch", fontsize=4)
    assert "text_too_small" in codes(fig)


def test_scaling_a_wide_figure_into_a_column_shrinks_its_text():
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.set_xlabel("Epoch", fontsize=12)
    ax.tick_params(labelsize=12)
    assert "text_too_small" not in codes(fig)
    assert "text_too_small" in codes(fig, target_width_in=3.4)


def test_crowded_tick_labels_are_caught():
    fig, ax = plt.subplots(figsize=(2.0, 2.0))
    values = list(range(40))
    ax.plot(values, values)
    ax.set_xticks(values)
    ax.set_xticklabels([f"category-{v}" for v in values])
    assert "tick_labels_collide" in codes(fig)


def test_room_to_breathe_produces_no_collision():
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([1, 2, 3], [1, 2, 3])
    assert "tick_labels_collide" not in codes(fig)


def test_a_label_landing_on_the_title_is_caught():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.set_title("A fairly long chart title")
    # Deliberately placed where the title sits.
    ax.annotate(
        "A fairly long chart title",
        xy=(0.5, 1.02),
        xycoords="axes fraction",
        ha="center",
    )
    assert "labels_collide" in codes(fig)


def test_an_inset_crowding_its_parent_axis_is_caught():
    """Two axes, so neither the tick check nor the old text check saw it."""
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot(range(20), range(20))
    # Placed low enough that its tick labels sit on the parent's.
    zoom = ax.inset_axes([0.55, -0.02, 0.4, 0.3])
    zoom.plot(range(20), range(20))
    zoom.set_xlim(10, 15)
    assert "labels_collide" in codes(fig)


def test_an_inset_with_clearance_is_fine():
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(range(20), range(20))
    zoom = ax.inset_axes([0.55, 0.16, 0.35, 0.35])
    zoom.plot(range(20), range(20))
    zoom.set_xlim(10, 15)
    assert "labels_collide" not in codes(fig)


def test_well_spaced_labels_do_not_collide():
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.set_title("Title")
    ax.annotate("note", xy=(1, 1), xytext=(4, 4), textcoords="offset points")
    assert "labels_collide" not in codes(fig)


# --- occlusion ------------------------------------------------------------


def test_a_legend_sitting_on_the_data_is_caught():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2, 3, 4], [0, 1, 2, 3, 4], label="a series with a fairly long name")
    ax.legend(loc="center")
    assert "legend_covers_data" in codes(fig)


def test_a_legend_outside_the_axes_is_fine():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2, 3, 4], [0, 1, 2, 3, 4], label="series")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    assert "legend_covers_data" not in codes(fig)


# --- integrity ------------------------------------------------------------


def test_a_truncated_bar_axis_is_an_error():
    fig, ax = plt.subplots()
    ax.bar([0, 1, 2], [98, 99, 100])
    ax.set_ylim(97, 101)
    assert "truncated_bar_axis" in codes(fig)


def test_a_bar_axis_reaching_zero_is_fine():
    fig, ax = plt.subplots()
    ax.bar([0, 1, 2], [98, 99, 100])
    ax.set_ylim(bottom=0)
    assert "truncated_bar_axis" not in codes(fig)


def test_a_heavily_zoomed_line_axis_warns_about_exaggeration():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [99.90, 99.93, 99.95])
    ax.set_ylim(99.89, 99.96)
    assert "axis_exaggeration" in codes(fig)


def test_a_line_chart_is_not_held_to_the_bar_baseline_rule():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [70, 75, 80])
    ax.set_ylim(65, 85)
    found = codes(fig)
    assert "truncated_bar_axis" not in found
    assert "axis_exaggeration" not in found


# --- overplotting ---------------------------------------------------------


def test_a_dense_scatter_warns():
    fig, ax = plt.subplots(figsize=(3, 3))
    xs = [i % 40 for i in range(3000)]
    ys = [i // 40 for i in range(3000)]
    ax.scatter(xs, ys, s=400)
    assert "overplotting" in codes(fig)


def test_a_sparse_scatter_does_not_warn():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.scatter([1, 2, 3, 4], [1, 2, 3, 4], s=18)
    assert "overplotting" not in codes(fig)


# --- the report object ----------------------------------------------------


def test_a_clean_figure_reports_nothing():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([1, 2, 3], [1, 2, 3], color="#0072B2", label="only series")
    ax.legend(loc="upper left")
    report = inspect_figure(fig)
    assert report.findings == []
    assert report.ok
    assert "no problems found" in str(report)


def test_warnings_alone_leave_the_report_ok():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [99.90, 99.93, 99.95])
    ax.set_ylim(99.89, 99.96)
    report = inspect_figure(fig)
    assert report.findings
    assert report.ok


def test_a_tick_the_locator_kept_offscreen_is_not_a_collision():
    """The locator lays ticks on a round grid and keeps the ones past the limits.

    They report get_visible() as True and carry a real bounding box, so the
    collision checks used to measure a "60" that no reader can see and report it
    landing on the title.
    """
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    ax.plot(range(1, 253), [42 + (i % 20) for i in range(252)])
    ax.set_ylim(28, 57)
    ax.set_title("The average follows the price, it does not predict it")

    offscreen = [t.get_text() for t in ax.get_yticklabels() if t.get_position()[1] > 57]
    assert offscreen, "this figure no longer reproduces the offscreen tick"
    assert "labels_collide" not in codes(fig)


def test_an_inverted_axis_still_reports_its_drawn_ticks():
    """Limits come back high to low when the axis is inverted, so they get sorted."""
    from graphunslopify.inspect import _drawn_tick_labels

    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    ax.plot([1, 2, 3], [10, 20, 30])
    ax.set_ylim(35, 5)
    fig.canvas.draw()

    drawn = [t.get_text() for t in _drawn_tick_labels(ax, "y")]
    assert drawn, "an inverted axis reported no drawn ticks at all"


def test_axis_break_halves_are_excluded_only_from_range_comparisons():
    figure, axes = plt.subplots(2, 1)
    for ax in axes:
        ax.plot([1, 2], [10, 90], label="method")
        ax.set_label("<axis-break>")
    axes[0].set_ylim(60, 100)
    axes[1].set_ylim(0, 30)
    assert "panels_disagree_on_y" not in codes(figure)


def test_unmarked_panels_still_report_different_ranges():
    figure, axes = plt.subplots(2, 1)
    for ax in axes:
        ax.plot([1, 2], [10, 90], label="method")
    axes[0].set_ylim(60, 100)
    axes[1].set_ylim(0, 30)
    assert "panels_disagree_on_y" in codes(figure)


def test_axis_break_halves_still_report_series_colour_drift():
    figure, axes = plt.subplots(2, 1)
    for ax, colour in zip(axes, ["#0072B2", "#D55E00"], strict=True):
        ax.plot([1, 2], [10, 90], label="method", color=colour)
        ax.set_label("<axis-break>")
    assert "series_colour_drifts_between_panels" in codes(figure)


def test_axis_break_halves_still_check_small_text():
    figure, axes = plt.subplots(2, 1)
    for ax in axes:
        ax.plot([1, 2], [10, 90])
        ax.set_label("<axis-break>")
        ax.set_xlabel("Too small", fontsize=2)
    assert "text_too_small" in codes(figure)
