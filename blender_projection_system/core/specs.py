"""Projector & lens specification library (ADR 0001: pure Python, no bpy).

A local, versioned database of real projector models — lumens, contrast,
weight, and a lens lineup with per-lens throw-ratio ranges, lens-shift limits
and transmission factor — plus loaders for JSON and CSV so users can extend it
without touching code.

Every model row carries a ``source_url`` (where the numbers came from) and a
``verified`` flag (True means transcribed from that source, not measured).
Honest-claims discipline (ADR 0002): :meth:`SpecLibrary.validate_throw` reports
out-of-range choices as **warnings and never clamps**; loaders reject corrupt
data loudly with :class:`ProjectionError` rather than guessing.

Lens-shift convention matches :mod:`.throw`: shift limits are fractions of the
*full* image dimension (``0.5`` puts the optical axis on the image edge).
The bundled starter rows use conservative planning values for shift limits;
override per lens via CSV import when the datasheet number is known.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from .errors import ProjectionError, require_finite, require_positive

#: Schema version accepted by the JSON loader. Bump when fields change and
#: keep the loader accepting exactly one version so old files fail loudly.
SCHEMA_VERSION = 1

#: CSV columns of a user import. All must be present in the header; body-only
#: rows (no lens) leave the lens columns empty.
CSV_COLUMNS: tuple[str, ...] = (
    "manufacturer",
    "model",
    "lumens",
    "aspect_w",
    "aspect_h",
    "contrast",
    "weight",
    "lens_model",
    "tr_min",
    "tr_max",
    "shift_v",
    "shift_h",
    "transmission",
    "source_url",
    "verified",
)

_TRUTHY = {"true", "1", "yes", "on"}
_FALSY = {"false", "0", "no", "off", ""}


@dataclass(frozen=True)
class LensSpec:
    """One interchangeable lens: throw range, shift limits, transmission.

    A fixed lens has ``throw_ratio_min == throw_ratio_max``. Shift limits use
    the add-on's full-image-dimension convention (see module docstring).
    """

    model: str
    throw_ratio_min: float
    throw_ratio_max: float
    max_lens_shift_v: float
    max_lens_shift_h: float
    transmission_factor: float = 1.0
    source_url: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ProjectionError("lens model name must be a non-empty string")
        require_positive("minimum throw ratio", self.throw_ratio_min)
        require_positive("maximum throw ratio", self.throw_ratio_max)
        require_finite("vertical shift limit", self.max_lens_shift_v)
        require_finite("horizontal shift limit", self.max_lens_shift_h)
        require_finite("transmission factor", self.transmission_factor)
        if self.throw_ratio_min > self.throw_ratio_max:
            raise ProjectionError(
                f"lens '{self.model}': throw ratio minimum {self.throw_ratio_min} "
                f"exceeds maximum {self.throw_ratio_max}"
            )
        if self.max_lens_shift_v < 0 or self.max_lens_shift_h < 0:
            raise ProjectionError(f"lens '{self.model}': shift limits must not be negative")
        if not 0.0 < self.transmission_factor <= 1.0:
            raise ProjectionError(
                f"lens '{self.model}': transmission factor must be in (0, 1], "
                f"got {self.transmission_factor}"
            )

    @property
    def is_fixed(self) -> bool:
        return self.throw_ratio_min == self.throw_ratio_max


@dataclass(frozen=True)
class ProjectorModel:
    """One projector model with its lens lineup and cited provenance."""

    manufacturer: str
    model: str
    lumens: float
    aspect_w: int
    aspect_h: int
    native_contrast: float = 2000.0
    weight_kg: float = 0.0
    lenses: tuple[LensSpec, ...] = ()
    source_url: str = ""
    verified: bool = False

    def __post_init__(self) -> None:
        for name, value in (("manufacturer", self.manufacturer), ("model", self.model)):
            if not isinstance(value, str) or not value.strip():
                raise ProjectionError(f"projector {name} must be a non-empty string")
        require_positive("lumens", self.lumens)
        require_positive("aspect width", self.aspect_w)
        require_positive("aspect height", self.aspect_h)
        require_finite("native contrast", self.native_contrast)
        require_finite("weight", self.weight_kg)
        if self.native_contrast < 1.0:
            raise ProjectionError(
                f"native contrast must be at least 1:1, got {self.native_contrast}"
            )
        if self.weight_kg < 0.0:
            raise ProjectionError(f"weight must not be negative, got {self.weight_kg}")

    @property
    def full_name(self) -> str:
        return f"{self.manufacturer} {self.model}"


@dataclass
class SpecLibrary:
    """A set of projector models with lookup and range validation."""

    models: list[ProjectorModel] = field(default_factory=list)

    def get_model(self, manufacturer: str, model: str) -> ProjectorModel | None:
        """Case-insensitive exact lookup by manufacturer and model name."""
        want_mfr = manufacturer.strip().lower()
        want_model = model.strip().lower()
        for candidate in self.models:
            if candidate.manufacturer.lower() == want_mfr and candidate.model.lower() == want_model:
                return candidate
        return None

    def find_lens(self, projector: ProjectorModel, lens_name: str) -> LensSpec | None:
        """Case-insensitive lens lookup within one projector's lineup."""
        want = lens_name.strip().lower()
        for lens in projector.lenses:
            if lens.model.lower() == want:
                return lens
        return None

    def all_manufacturers(self) -> list[str]:
        """Manufacturer names in insertion order, de-duplicated."""
        seen: dict[str, str] = {}
        for model in self.models:
            seen.setdefault(model.manufacturer.lower(), model.manufacturer)
        return list(seen.values())

    def models_for_manufacturer(self, mfr: str) -> list[ProjectorModel]:
        """All models of one manufacturer, case-insensitive, insertion order."""
        want = mfr.strip().lower()
        return [m for m in self.models if m.manufacturer.lower() == want]

    def validate_throw(
        self,
        model: ProjectorModel,
        lens: LensSpec,
        throw_ratio: float,
        shift_v: float = 0.0,
        shift_h: float = 0.0,
    ) -> list[str]:
        """Range-check a chosen throw ratio and shift against one lens.

        Returns one warning string per violation; an empty list means every
        choice is inside the lens' documented range. **Never clamps** — the
        caller decides what an out-of-range entry means (ADR 0002).
        """
        warnings: list[str] = []
        require_finite("throw ratio", throw_ratio)
        require_finite("vertical shift", shift_v)
        require_finite("horizontal shift", shift_h)
        lo, hi = sorted((lens.throw_ratio_min, lens.throw_ratio_max))
        if throw_ratio < lo - 1e-9:
            warnings.append(f"Throw ratio {throw_ratio:.3f} is below lens minimum {lo:.3f}")
        elif throw_ratio > hi + 1e-9:
            warnings.append(f"Throw ratio {throw_ratio:.3f} is above lens maximum {hi:.3f}")
        if abs(shift_v) > lens.max_lens_shift_v + 1e-9:
            warnings.append(
                f"Vertical shift {abs(shift_v):.3f} exceeds lens limit "
                f"{lens.max_lens_shift_v:.3f} on '{lens.model}'"
            )
        if abs(shift_h) > lens.max_lens_shift_h + 1e-9:
            warnings.append(
                f"Horizontal shift {abs(shift_h):.3f} exceeds lens limit "
                f"{lens.max_lens_shift_h:.3f} on '{lens.model}'"
            )
        return warnings


# ---------------------------------------------------------------------------
# Primitive field parsing shared by both loaders
# ---------------------------------------------------------------------------


def _require_text(row_label: str, key: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectionError(f"{row_label}: '{key}' must be a non-empty string")
    return value.strip()


def _require_number(row_label: str, key: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectionError(f"{row_label}: '{key}' must be a number, got {value!r}")
    require_finite(key, value)
    return float(value)


def _parse_aspect(row_label: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectionError(f"{row_label}: aspect components must be integers, got {value!r}")
    require_positive("aspect component", value)
    return value


def _parse_verified(value: Any, row_label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUTHY:
            return True
        if text in _FALSY:
            return False
    raise ProjectionError(f"{row_label}: 'verified' must be a boolean (true/false), got {value!r}")


def _lens_from_mapping(entry: Any, row_label: str) -> LensSpec:
    if not isinstance(entry, dict):
        raise ProjectionError(f"{row_label}: each lens must be an object")
    lens_label = f"{row_label} lens '{entry.get('model', '?')}'"
    return LensSpec(
        model=_require_text(lens_label, "model", entry.get("model")),
        throw_ratio_min=_require_number(
            lens_label, "throw_ratio_min", entry.get("throw_ratio_min")
        ),
        throw_ratio_max=_require_number(
            lens_label, "throw_ratio_max", entry.get("throw_ratio_max")
        ),
        max_lens_shift_v=_require_number(
            lens_label, "max_lens_shift_v", entry.get("max_lens_shift_v", 0.0)
        ),
        max_lens_shift_h=_require_number(
            lens_label, "max_lens_shift_h", entry.get("max_lens_shift_h", 0.0)
        ),
        transmission_factor=_require_number(
            lens_label, "transmission_factor", entry.get("transmission_factor", 1.0)
        ),
        source_url=entry.get("source_url", "") or "",
    )


def _model_from_mapping(entry: Any) -> ProjectorModel:
    if not isinstance(entry, dict):
        raise ProjectionError("each model must be an object")
    label = f"model '{entry.get('model', '?')}'"
    lenses_raw = entry.get("lenses", [])
    if not isinstance(lenses_raw, Sequence) or isinstance(lenses_raw, (str, bytes)):
        raise ProjectionError(f"{label}: 'lenses' must be a list of lens objects")
    return ProjectorModel(
        manufacturer=_require_text(label, "manufacturer", entry.get("manufacturer")),
        model=_require_text(label, "model", entry.get("model")),
        lumens=_require_number(label, "lumens", entry.get("lumens")),
        aspect_w=_parse_aspect(label, entry.get("aspect_w")),
        aspect_h=_parse_aspect(label, entry.get("aspect_h")),
        native_contrast=_require_number(
            label, "native_contrast", entry.get("native_contrast", 2000.0)
        ),
        weight_kg=_require_number(label, "weight_kg", entry.get("weight_kg", 0.0)),
        lenses=tuple(_lens_from_mapping(lens_entry, label) for lens_entry in lenses_raw),
        source_url=entry.get("source_url", "") or "",
        verified=_parse_verified(entry.get("verified", False), label),
    )


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------


def load_library_from_json(content_or_path: Any) -> SpecLibrary:
    """Build a :class:`SpecLibrary` from parsed/raw JSON.

    Accepts an already-parsed ``dict``, a ``Path``, or a ``str`` that is either
    a path to a JSON file or literal JSON text. Corrupt or unknown-version
    content raises :class:`ProjectionError` naming the problem (ADR 0002).
    """
    data = _resolve_content(content_or_path, "JSON")
    if not isinstance(data, dict):
        raise ProjectionError("spec library JSON must be an object at the top level")
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ProjectionError(
            f"unsupported spec library schema_version {version!r} "
            f"(this build reads version {SCHEMA_VERSION})"
        )
    models_raw = data.get("models", [])
    if not isinstance(models_raw, list):
        raise ProjectionError("'models' must be a list")
    return SpecLibrary(models=[_model_from_mapping(entry) for entry in models_raw])


def load_builtin_library() -> SpecLibrary:
    """The curated starter library bundled with the add-on.

    Loaded relative to this module so the lookup works both from a source
    checkout and inside an installed Blender extension archive.
    """
    path = Path(__file__).resolve().parent / "data" / "projector_library.json"
    if not path.is_file():
        raise ProjectionError(f"bundled projector library is missing: {path}")
    return load_library_from_json(path)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


def _csv_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(text, newline=""))
    header = reader.fieldnames or []
    missing = [column for column in CSV_COLUMNS if column not in header]
    if missing:
        raise ProjectionError("CSV header is missing required column(s): " + ", ".join(missing))
    return list(reader)


def _csv_number(row: dict[str, str], column: str, row_label: str, default: float) -> float:
    raw = (row.get(column) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ProjectionError(f"{row_label}: '{column}' must be a number, got {raw!r}") from None
    return require_finite(column, value)


def load_library_from_csv(content_or_path: Any) -> SpecLibrary:
    """Build a :class:`SpecLibrary` from user CSV content or a file path.

    One row per lens; consecutive rows sharing manufacturer and model merge
    into one projector. Lens columns may be left empty for body-only rows.
    See :data:`CSV_COLUMNS` for the required header.
    """
    text = _resolve_text(content_or_path, "CSV")
    models: list[ProjectorModel] = []
    index_of: dict[tuple[str, str], int] = {}

    for line_number, row in enumerate(_csv_rows(text), start=2):
        row_label = f"CSV line {line_number}"
        manufacturer = _require_text(row_label, "manufacturer", row.get("manufacturer"))
        model_name = _require_text(row_label, "model", row.get("model"))
        key = (manufacturer.lower(), model_name.lower())

        lens_model = (row.get("lens_model") or "").strip()
        tr_min_raw = (row.get("tr_min") or "").strip()
        tr_max_raw = (row.get("tr_max") or "").strip()
        if lens_model or tr_min_raw or tr_max_raw:
            if not lens_model or not tr_min_raw or not tr_max_raw:
                raise ProjectionError(
                    f"{row_label}: lens rows need lens_model, tr_min and tr_max together"
                )
            lens = LensSpec(
                model=lens_model,
                throw_ratio_min=_csv_number(row, "tr_min", row_label, 0.0),
                throw_ratio_max=_csv_number(row, "tr_max", row_label, 0.0),
                max_lens_shift_v=_csv_number(row, "shift_v", row_label, 0.0),
                max_lens_shift_h=_csv_number(row, "shift_h", row_label, 0.0),
                transmission_factor=_csv_number(row, "transmission", row_label, 1.0),
                source_url=(row.get("source_url") or "").strip(),
            )
            # LensSpec.__post_init__ rejects tr_min > tr_max and non-positive
            # ranges itself, naming the lens; no duplicate check needed here.
        else:
            lens = None

        verified_raw = (row.get("verified") or "false").strip()
        if key in index_of:
            existing = models[index_of[key]]
            if lens is not None:
                models[index_of[key]] = ProjectorModel(
                    manufacturer=existing.manufacturer,
                    model=existing.model,
                    lumens=existing.lumens,
                    aspect_w=existing.aspect_w,
                    aspect_h=existing.aspect_h,
                    native_contrast=existing.native_contrast,
                    weight_kg=existing.weight_kg,
                    lenses=existing.lenses + (lens,),
                    source_url=existing.source_url,
                    verified=existing.verified,
                )
            continue

        model = ProjectorModel(
            manufacturer=manufacturer,
            model=model_name,
            lumens=_csv_number(row, "lumens", row_label, 0.0),
            aspect_w=int(_csv_number(row, "aspect_w", row_label, 0.0)),
            aspect_h=int(_csv_number(row, "aspect_h", row_label, 0.0)),
            native_contrast=_csv_number(row, "contrast", row_label, 2000.0),
            weight_kg=_csv_number(row, "weight", row_label, 0.0),
            lenses=(lens,) if lens is not None else (),
            source_url=(row.get("source_url") or "").strip(),
            verified=_parse_verified(verified_raw, row_label),
        )
        index_of[key] = len(models)
        models.append(model)

    return SpecLibrary(models=models)


# ---------------------------------------------------------------------------
# Shared input resolution
# ---------------------------------------------------------------------------


def _resolve_text(source: Any, kind: str) -> str:
    """Normalise ``content_or_path`` into file text for a text loader."""
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8-sig")
    if isinstance(source, str):
        # A string is either literal content or a path to an existing file.
        # Literal content always wins when both could match, so the file
        # branch requires the path to exist and to be a file.
        candidate = Path(source)
        if "\n" not in source and "," not in source and candidate.is_file():
            return candidate.read_text(encoding="utf-8-sig")
        return source
    raise ProjectionError(f"{kind} loader accepts text, a path, or parsed content")


def _resolve_content(source: Any, kind: str) -> Any:
    """Normalise ``content_or_path`` into parsed JSON data."""
    if isinstance(source, dict):
        return source
    text = _resolve_text(source, kind)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectionError(f"corrupt {kind} content: {exc}") from None
