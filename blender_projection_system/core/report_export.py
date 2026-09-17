"""Structured export for coverage reports, photometry, and rigging schedules.

ADR 0001: Pure Python only, no bpy or mathutils.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from .coverage import CoverageReport
from .photometry import ISCR_CATEGORY_LABELS, ISCRCategory


@dataclass(frozen=True)
class RiggingItem:
    """Rigging, mounting, and optical schedule entry for one projector."""

    name: str
    manufacturer: str = ""
    model: str = ""
    lens_model: str = ""
    mount_x: float = 0.0
    mount_y: float = 0.0
    mount_z: float = 0.0
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    throw_distance: float = 0.0
    image_width: float = 0.0
    image_height: float = 0.0
    lens_shift_v_pct: float = 0.0
    lens_shift_h_pct: float = 0.0
    lumens: float = 0.0
    weight_kg: float = 0.0
    corners_world: tuple[tuple[float, float, float], ...] = ()


def report_to_dict(
    report: CoverageReport,
    rigging_items: Sequence[RiggingItem] = (),
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert a CoverageReport and optional rigging items into a structured dict."""
    data: dict[str, Any] = {
        "schema_version": 1,
        "metadata": extra_meta or {},
        "wall": {
            "name": report.wall_name,
            "arc_length_m": round(report.wall_arc_length, 4),
            "height_m": round(report.wall_height, 4),
            "area_m2": round(report.wall_arc_length * report.wall_height, 4),
        },
        "coverage": {
            "covered_cells": report.covered_cells,
            "total_cells": report.total_cells,
            "covered_fraction": round(report.covered_fraction, 4),
            "covered_area_m2": round(report.covered_area, 4),
            "gap_area_m2": round(report.gap_area, 4),
            "horizontal_coverage": round(report.horizontal_coverage, 4),
            "lit_band_z_min_m": round(report.covered_z_min, 4),
            "lit_band_z_max_m": round(report.covered_z_max, 4),
            "overlap_fraction": round(report.overlap_fraction, 4),
            "max_overlap_count": report.max_overlap_count,
            "gaps": [
                {
                    "start_m": round(g.start, 4),
                    "end_m": round(g.end, 4),
                    "length_m": round(g.length, 4),
                }
                for g in report.gaps
            ],
            "blend_zones": [
                {
                    "left_projector": z.left,
                    "right_projector": z.right,
                    "width_m": round(z.width, 4),
                    "overlap_fraction_left": round(z.overlap_fraction_left, 4),
                    "overlap_fraction_right": round(z.overlap_fraction_right, 4),
                    "mean_overlap_fraction": round(z.mean_overlap_fraction, 4),
                    "guidance": z.guidance,
                }
                for z in report.blend_zones
            ],
            "projector_spans": [
                {
                    "name": name,
                    "start_m": round(span.start, 4),
                    "end_m": round(span.end, 4),
                    "length_m": round(span.length, 4),
                }
                for name, span in report.projector_spans
            ],
        },
    }

    if report.brightness:
        b = report.brightness
        bright_dict: dict[str, Any] = {
            "sample_count": b.sample_count,
            "screen_gain": round(b.screen_gain, 4),
            "min_lux": round(b.min_lux, 2),
            "max_lux": round(b.max_lux, 2),
            "mean_lux": round(b.mean_lux, 2),
            "min_nits": round(b.min_nits, 2),
            "max_nits": round(b.max_nits, 2),
            "mean_nits": round(b.mean_nits, 2),
            "mean_foot_lamberts": round(b.mean_foot_lamberts, 2),
            "uniformity": round(b.uniformity, 4),
            "assumptions": list(b.assumptions),
        }
        if b.derate_chain:
            dc = b.derate_chain
            bright_dict["derate_chain"] = {
                "production_tolerance": round(dc.production_tolerance, 4),
                "picture_mode_factor": round(dc.picture_mode_factor, 4),
                "aging_factor": round(dc.aging_factor, 4),
                "lens_transmission": round(dc.lens_transmission, 4),
                "rated_multiplier": round(dc.rated_multiplier, 4),
                "typical_multiplier": round(dc.typical_multiplier, 4),
                "worst_case_multiplier": round(dc.worst_case_multiplier, 4),
            }
            if b.rated_band and b.typical_band and b.worst_case_band:
                bright_dict["bands"] = {
                    "rated": asdict(b.rated_band),
                    "typical": asdict(b.typical_band),
                    "worst_case": asdict(b.worst_case_band),
                }
        data["brightness"] = bright_dict

    if report.contrast:
        c = report.contrast
        data["contrast"] = {
            "ambient_lux": round(c.ambient_lux, 2),
            "screen_gain": round(c.screen_gain, 4),
            "veiling_nits": round(c.veiling_nits, 2),
            "min_contrast": round(c.min_contrast, 2),
            "max_contrast": round(c.max_contrast, 2),
            "mean_contrast": round(c.mean_contrast, 2),
            "target_category": c.target_category.value,
            "target_category_label": ISCR_CATEGORY_LABELS.get(c.target_category, ""),
            "user_target_ratio": round(c.user_target_ratio, 2),
            "meets_user_target": c.meets_user_target,
            "assumptions": list(c.assumptions),
            "disclaimer": c.disclaimer,
        }

    if report.nine_point:
        np = report.nine_point
        data["nine_point"] = {
            "average_lux": round(np.average_lux, 2),
            "average_nits": round(np.average_nits, 2),
            "average_foot_lamberts": round(np.average_foot_lamberts, 2),
            "center_lux": round(np.center_lux, 2),
            "center_nits": round(np.center_nits, 2),
            "center_foot_lamberts": round(np.center_foot_lamberts, 2),
            "lit_area_m2": round(np.lit_area, 4),
            "light_output_lumens": round(np.light_output_lumens, 1),
            "corner_to_center_ratio": round(np.corner_to_center_ratio, 4),
            "corner_average_to_center_ratio": round(np.corner_average_to_center_ratio, 4),
            "nine_point_uniformity": round(np.nine_point_uniformity, 4),
            "disclaimer": np.disclaimer,
            "points": [
                {
                    "label": p.position_label,
                    "normalized_u": round(p.normalized_u, 4),
                    "normalized_v": round(p.normalized_v, 4),
                    "s_m": round(p.s, 4),
                    "z_m": round(p.z, 4),
                    "lux": round(p.lux, 2),
                    "nits": round(p.nits, 2),
                    "foot_lamberts": round(p.foot_lamberts, 2),
                }
                for p in np.points
            ],
        }

    if rigging_items:
        data["rigging_schedule"] = [asdict(item) for item in rigging_items]

    data["warnings"] = list(report.warnings)
    return data


def export_analysis_to_json(
    report: CoverageReport,
    rigging_items: Sequence[RiggingItem] = (),
    extra_meta: dict[str, Any] | None = None,
    indent: int = 2,
) -> str:
    """Serialize the coverage analysis and rigging schedule to formatted JSON."""
    d = report_to_dict(report, rigging_items, extra_meta)
    return json.dumps(d, indent=indent)


def export_rigging_schedule_to_csv(rigging_items: Sequence[RiggingItem]) -> str:
    """Export the projector mounting and rigging table to CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    headers = [
        "Unit",
        "Manufacturer",
        "Model",
        "Lens",
        "Mount_X_m",
        "Mount_Y_m",
        "Mount_Z_m",
        "Yaw_deg",
        "Pitch_deg",
        "Roll_deg",
        "Throw_m",
        "Image_Width_m",
        "Image_Height_m",
        "Shift_V_pct",
        "Shift_H_pct",
        "Rated_Lumens",
        "Weight_kg",
    ]
    writer.writerow(headers)
    for r in rigging_items:
        writer.writerow(
            [
                r.name,
                r.manufacturer,
                r.model,
                r.lens_model,
                f"{r.mount_x:+.3f}",
                f"{r.mount_y:+.3f}",
                f"{r.mount_z:+.3f}",
                f"{r.yaw_deg:.1f}",
                f"{r.pitch_deg:.1f}",
                f"{r.roll_deg:.1f}",
                f"{r.throw_distance:.3f}",
                f"{r.image_width:.3f}",
                f"{r.image_height:.3f}",
                f"{r.lens_shift_v_pct:+.1f}",
                f"{r.lens_shift_h_pct:+.1f}",
                f"{r.lumens:.0f}",
                f"{r.weight_kg:.1f}",
            ]
        )
    return buf.getvalue()


def export_coverage_summary_to_csv(
    report: CoverageReport,
    rigging_items: Sequence[RiggingItem] = (),
) -> str:
    """Export coverage summary and rigging schedule combined in a CSV format."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")

    # Section 1: Summary Key-Value
    writer.writerow(["Section", "Metric", "Value", "Unit"])
    writer.writerow(["Wall", "Name", report.wall_name, ""])
    writer.writerow(["Wall", "Arc Length", f"{report.wall_arc_length:.3f}", "m"])
    writer.writerow(["Wall", "Height", f"{report.wall_height:.3f}", "m"])
    writer.writerow(["Wall", "Area", f"{report.wall_arc_length * report.wall_height:.3f}", "m2"])
    writer.writerow(["Coverage", "Covered Area", f"{report.covered_area:.3f}", "m2"])
    writer.writerow(["Coverage", "Covered Fraction", f"{report.covered_fraction * 100:.1f}", "%"])
    writer.writerow(
        ["Coverage", "Horizontal Coverage", f"{report.horizontal_coverage * 100:.1f}", "%"]
    )
    writer.writerow(["Coverage", "Overlap Fraction", f"{report.overlap_fraction * 100:.1f}", "%"])
    writer.writerow(["Coverage", "Max Overlap Count", str(report.max_overlap_count), "units"])

    if report.brightness:
        b = report.brightness
        writer.writerow(["Brightness", "Mean Illuminance", f"{b.mean_lux:.1f}", "lux"])
        writer.writerow(["Brightness", "Mean Luminance", f"{b.mean_nits:.1f}", "nits"])
        writer.writerow(["Brightness", "Mean Foot-Lamberts", f"{b.mean_foot_lamberts:.1f}", "fL"])
        writer.writerow(["Brightness", "Uniformity (Min/Max)", f"{b.uniformity:.3f}", "ratio"])
        if b.typical_band and b.worst_case_band:
            writer.writerow(
                ["Brightness", "Typical Luminance", f"{b.typical_band.mean_nits:.1f}", "nits"]
            )
            writer.writerow(
                [
                    "Brightness",
                    "Worst-Case Luminance",
                    f"{b.worst_case_band.mean_nits:.1f}",
                    "nits",
                ]
            )

    if report.contrast:
        c = report.contrast
        writer.writerow(["Contrast", "Ambient Illuminance", f"{c.ambient_lux:.1f}", "lux"])
        writer.writerow(["Contrast", "Veiling Luminance", f"{c.veiling_nits:.1f}", "nits"])
        writer.writerow(["Contrast", "Mean Effective Ratio", f"{c.mean_contrast:.1f}:1", "ratio"])
        writer.writerow(["Contrast", "Min Effective Ratio", f"{c.min_contrast:.1f}:1", "ratio"])
        if c.target_category is not ISCRCategory.NONE:
            writer.writerow(
                [
                    "Contrast",
                    "ISCR Target",
                    ISCR_CATEGORY_LABELS.get(c.target_category, ""),
                    "",
                ]
            )

    if report.nine_point:
        np = report.nine_point
        writer.writerow(
            ["ANSI_9Point", "Light Output", f"{np.light_output_lumens:.0f}", "lumens"]
        )
        writer.writerow(["ANSI_9Point", "Average Luminance", f"{np.average_nits:.1f}", "nits"])
        writer.writerow(["ANSI_9Point", "Center Luminance", f"{np.center_nits:.1f}", "nits"])
        writer.writerow(
            ["ANSI_9Point", "Corner-to-Center", f"{np.corner_to_center_ratio * 100:.1f}", "%"]
        )

    if rigging_items:
        writer.writerow([])
        writer.writerow(["--- RIGGING SCHEDULE ---"])
        headers = [
            "Unit",
            "Manufacturer",
            "Model",
            "Lens",
            "Mount_X_m",
            "Mount_Y_m",
            "Mount_Z_m",
            "Yaw_deg",
            "Pitch_deg",
            "Roll_deg",
            "Throw_m",
            "Image_Width_m",
            "Image_Height_m",
            "Shift_V_pct",
            "Shift_H_pct",
            "Rated_Lumens",
            "Weight_kg",
        ]
        writer.writerow(headers)
        for r in rigging_items:
            writer.writerow(
                [
                    r.name,
                    r.manufacturer,
                    r.model,
                    r.lens_model,
                    f"{r.mount_x:+.3f}",
                    f"{r.mount_y:+.3f}",
                    f"{r.mount_z:+.3f}",
                    f"{r.yaw_deg:.1f}",
                    f"{r.pitch_deg:.1f}",
                    f"{r.roll_deg:.1f}",
                    f"{r.throw_distance:.3f}",
                    f"{r.image_width:.3f}",
                    f"{r.image_height:.3f}",
                    f"{r.lens_shift_v_pct:+.1f}",
                    f"{r.lens_shift_h_pct:+.1f}",
                    f"{r.lumens:.0f}",
                    f"{r.weight_kg:.1f}",
                ]
            )

    return buf.getvalue()


export_analysis_summary_to_csv = export_coverage_summary_to_csv
