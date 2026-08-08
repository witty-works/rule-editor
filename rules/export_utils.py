"""Small helpers for consistent export JSON writing and summary formatting.

These utilities avoid duplication across management commands and standalone scripts.
"""

from pathlib import Path
import json
import gzip
import os
from typing import Dict, Iterable, Optional, Union


def dump_json(
    data: Iterable,
    output_path: Union[str, Path],
    indent: Optional[int] = 2,
    compress: Optional[bool] = None,
) -> Path:
    """Write JSON to file with optional gzip compression.

    Args:
        data: JSON-serializable object
        output_path: File path to write
        indent: JSON indentation (None for compact)
        compress: Force compression (True/False), or auto-detect from extension (None)

    Returns:
        Path to the written file

    Examples:
        # Auto-detect from extension
        dump_json(data, "output.json.gz")  # Compressed
        dump_json(data, "output.json")     # Uncompressed

        # Force compression
        dump_json(data, "output.json", compress=True)  # Creates output.json.gz
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Auto-detect compression from extension if not explicitly set
    if compress is None:
        compress = out.suffix.lower() == ".gz"

    # Adjust filename if compression is forced but extension isn't .gz
    if compress and not str(output_path).endswith(".gz"):
        out = out.with_suffix(out.suffix + ".gz")

    # Write to temp file and replace atomically
    tmp = out.with_suffix(out.suffix + ".tmp")

    try:
        if compress:
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
        else:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)

        os.replace(tmp, out)
        return out
    finally:
        # Clean up temp file if something went wrong
        if tmp.exists():
            tmp.unlink()


def load_json(input_path: Union[str, Path]) -> list:
    """Load JSON from file with automatic decompression.

    Args:
        input_path: Path to JSON or JSON.gz file

    Returns:
        Loaded JSON data

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If JSON is invalid
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    # Auto-detect compression
    is_compressed = input_path.suffix.lower() == ".gz"

    if is_compressed:
        with gzip.open(input_path, "rt", encoding="utf-8") as f:
            return json.load(f)
    else:
        with open(input_path, "r", encoding="utf-8") as f:
            return json.load(f)


def validate_foreign_keys_exist(obj) -> None:
    """Raise ValueError when a to-be-saved object references a pk that does
    not exist.

    SQLite defers foreign key enforcement to the COMMIT of the outermost
    transaction, so a dangling reference sails through its per-item savepoint
    and blows up the whole import at the very end, far from the record that
    caused it. Checking here turns that into a per-record error with a
    message naming the culprit.
    """
    for field in obj._meta.concrete_fields:
        if not field.is_relation:
            continue
        value = getattr(obj, field.attname)
        if value is None:
            continue
        if not field.related_model._default_manager.filter(pk=value).exists():
            raise ValueError(
                f"{obj._meta.label} references {field.name}={value} "
                f"({field.related_model._meta.label}) which does not exist"
            )


def format_file_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def format_export_summary(
    counts: Dict[str, int],
    total: int,
    header: str = "Export summary:",
    output_file: Optional[Path] = None,
) -> str:
    """Return a multi-line export summary string with deterministic ordering.

    Args:
        counts: Mapping of name -> count
        total: Total objects exported
        header: Header line
        output_file: Optional path to output file for size info
    """
    lines = [header]
    for name in sorted(counts):
        lines.append(f"  - {name}: {counts[name]}")
    lines.append(f"\nTotal objects: {total}")

    if output_file and output_file.exists():
        size = output_file.stat().st_size
        lines.append(f"File size: {format_file_size(size)}")

        # Show compression info if it's a .gz file
        if output_file.suffix.lower() == ".gz":
            lines.append("Format: gzip compressed")

    return "\n".join(lines)
