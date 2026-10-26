"""Cell annotation colours shared with standalone generated programs.

Sample normalized image colours at the annotation anchor, composite in drawing
order, and compare declared sRGB colours (not antialiased glyph pixels). Fully
transparent canvas backgrounds are assessed on white paper. This is a cell-text
check, not a certificate for every mark, background, or accessibility criterion.
Keep this module standalone: build:translator embeds it without a package import.
"""

import matplotlib.colors as mcolors
import numpy as np


def _cell_over(rgba, background):
    return np.asarray(rgba[:3]) * rgba[3] + np.asarray(background) * (1 - rgba[3])


def cell_contrast_ratio(a, b):
    """WCAG relative-luminance ratio; compare the unrounded result to 4.5."""
    luminances = []
    for colour in (a, b):
        rgb = np.asarray(colour, dtype=float)
        linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        luminances.append(float(linear @ np.array([0.2126, 0.7152, 0.0722])))
    low, high = sorted(luminances)
    return (high + 0.05) / (low + 0.05)


def _cell_paper(ax):
    background = np.ones(3)
    figures = []
    figure = ax.figure
    while figure is not None and figure not in figures:
        figures.append(figure)
        figure = figure.get_figure()
    for figure in reversed(figures):
        if figure.patch.get_visible():
            background = _cell_over(figure.get_facecolor(), background)
    if ax.axison and ax.get_frame_on() and ax.patch.get_visible():
        background = _cell_over(ax.get_facecolor(), background)
    return background


def _cell_image_layers(ax, display):
    layers = []
    for index, artist in enumerate(ax.get_children()):
        if artist not in ax.images or not artist.get_visible():
            continue
        if artist.get_clip_on():
            box = artist.get_clip_box()
            if box is not None and not box.contains(*display):
                continue
            clip = artist.get_clip_path()
            if clip is not None:
                path, transform = clip.get_transformed_path_and_affine()
                if not path.contains_point(display, transform=transform):
                    continue
        x, y = artist.get_transform().inverted().transform(display)
        left, right, bottom, top = artist.get_extent()
        fx = (x - left) / (right - left)
        fy = (
            (y - top) / (bottom - top)
            if artist.origin == "upper"
            else (y - bottom) / (top - bottom)
        )
        if not (0 <= fx < 1 and 0 <= fy < 1):
            continue
        array = artist.get_array()
        row, column = int(fy * array.shape[0]), int(fx * array.shape[1])
        rgba = artist.to_rgba(array[row : row + 1, column : column + 1], norm=array.ndim == 2)[
            0, 0
        ].copy()
        alpha = artist.get_alpha()
        if alpha is not None:
            rgba[3] *= float(alpha if np.ndim(alpha) == 0 else alpha[row, column])
        layers.append(((artist.get_zorder(), index), rgba))
    return sorted(layers, key=lambda layer: layer[0])


def cell_colour_for_rgb(background):
    """Pure black or white, whichever has greater unrounded contrast."""
    return (
        "black"
        if cell_contrast_ratio((0, 0, 0), background) >= cell_contrast_ratio((1, 1, 1), background)
        else "white"
    )


def cell_text_colour(ax, x, y):
    """Choose pure black/white against the actual image/axes background."""
    layers = _cell_image_layers(ax, ax.transData.transform((x, y)))
    if not layers:
        raise ValueError("Cell text requires a visible image at its anchor")
    background = _cell_paper(ax)
    for _, rgba in layers:
        background = _cell_over(rgba, background)
    return cell_colour_for_rgb(background)


def cell_text_contrast(ax, text):
    """Effective foreground/background ratio, or None outside cell images.

    Handles image alpha, masks, extent/origin, text transforms/alpha/bboxes and
    image drawing order. Outlined text needs a separate geometric assessment.
    """
    display = text.get_transform().transform(text.get_unitless_position())
    layers = _cell_image_layers(ax, display)
    if not layers:
        return None
    if text.get_path_effects():
        raise NotImplementedError("Outlined cell text needs a separate contrast assessment")
    key = (text.get_zorder(), list(ax.get_children()).index(text))
    background = _cell_paper(ax)
    above = []
    for order, rgba in layers:
        if order < key:
            background = _cell_over(rgba, background)
        else:
            above.append(rgba)
    bbox = text.get_bbox_patch()
    if bbox is not None and bbox.get_visible() and bbox.get_fill() and bbox.contains_point(display):
        background = _cell_over(bbox.get_facecolor(), background)
    foreground = _cell_over(mcolors.to_rgba(text.get_color(), alpha=text.get_alpha()), background)
    for rgba in above:
        background = _cell_over(rgba, background)
        foreground = _cell_over(rgba, foreground)
    return cell_contrast_ratio(foreground, background)
