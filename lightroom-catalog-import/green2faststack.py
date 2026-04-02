#!/usr/bin/env python3
"""
green2faststack.py

Export Lightroom Classic green-labeled image paths from a .lrcat catalog,
and optionally update an existing FastStack faststack.json using the exported
paths file.

Design goals:
- Read the Lightroom catalog once and export all green-labeled paths to a text file.
- Later, read that text file as many times as desired to update FastStack JSON files.
- Match FastStack entries by lowercase stem only, so RAW/JPG pairs naturally align.
- Never create new JSON files implicitly.
- Be safe by default: dry-run support, automatic backups, verbose help, and summaries.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

PROGRAM_NAME = "green2faststack"
DEFAULT_UPLOADED_DATE = "1970-01-01"


@dataclass(frozen=True)
class GreenPathRecord:
    image_id: int
    full_path: str
    stem_key: str


class Logger:
    def __init__(self, verbose: bool = False, debug: bool = False) -> None:
        self.verbose_enabled = verbose or debug
        self.debug_enabled = debug

    def info(self, msg: str) -> None:
        print(msg)

    def verbose(self, msg: str) -> None:
        if self.verbose_enabled:
            print(msg)

    def debug(self, msg: str) -> None:
        if self.debug_enabled:
            print(f"[debug] {msg}")

    def warn(self, msg: str) -> None:
        print(f"[warn] {msg}", file=sys.stderr)

    def error(self, msg: str) -> None:
        print(f"[error] {msg}", file=sys.stderr)


def verbose_description() -> str:
    return f"""
{PROGRAM_NAME} bridges old Lightroom Classic "green label means uploaded"
workflows into FastStack's per-directory JSON tracking.

This tool has two modes:

1) Export mode
   Read a Lightroom Classic .lrcat catalog (a SQLite database), find all photos
   where Adobe_images.colorLabels = 'Green', reconstruct their full catalog paths,
   and write those paths to a plain text file, one path per line.

   Example:
     {PROGRAM_NAME} -i catalog.lrcat -o green.txt

2) JSON mode
   Read a previously exported text file of green-labeled paths and update one
   existing FastStack faststack.json file by matching entries on lowercase stem.
   This is intended for cases where Lightroom is no longer part of the workflow,
   and you want to apply the exported upload knowledge to FastStack as needed.

   Example:
     {PROGRAM_NAME} --paths green.txt --json /path/to/faststack.json

What this tool hopes to accomplish:
- Preserve historical "uploaded" decisions you made in Lightroom Classic.
- Let FastStack reflect those decisions without needing to reopen Lightroom.
- Work naturally with RAW/JPG pairs by matching same-stem entries.

Important limitations and behavior:
- Export mode reads the Lightroom catalog only; it does not require the image files
  to be mounted or present on disk.
- JSON mode reads only from the exported text file, not from the .lrcat.
- JSON mode updates only one existing faststack.json at a time.
- This tool does not create a new faststack.json unless that behavior is added in
  a future version. For now, the JSON must already exist.
- Matching is stem-based only. For example, IMG_0001.ORF and IMG_0001.JPG both map
  to the same FastStack key img_0001 if that is how FastStack tracks the entry.
- JSON mode sanity-checks whether the exported file paths currently exist on disk
  and includes those counts in the summary.
- If an entry is already uploaded in faststack.json, it is left unchanged and
  counted as already present.
- Existing uploaded_date values are preserved. If a matching entry is newly marked
  uploaded and has no uploaded_date, the default date is {DEFAULT_UPLOADED_DATE}
  unless overridden with --uploaded-date YYYY-MM-DD.
- Before any JSON write, an automatic rotating backup is created:
    faststack.json.bak
    faststack.json.bak1
    faststack.json.bak2
    ...
- Use --dry-run to preview changes without writing anything.
- Use --verbose for normal detailed progress.
- Use --debug for very chatty troubleshooting output.

Examples:
  Export green paths from a catalog:
    {PROGRAM_NAME} -i "Alan Rockefeller-v13-3.lrcat" -o green.txt

  Update an existing FastStack JSON from an exported paths file:
    {PROGRAM_NAME} --paths green.txt --json /mnt/c/.../faststack.json

  Preview JSON changes without writing:
    {PROGRAM_NAME} --paths green.txt --json /mnt/c/.../faststack.json --dry-run --verbose

  Use a specific uploaded date for newly marked entries:
    {PROGRAM_NAME} --paths green.txt --json /mnt/c/.../faststack.json --uploaded-date 2026-04-01
""".strip()


class RichHelpFormatter(argparse.RawDescriptionHelpFormatter):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=verbose_description(),
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--input",
        help="Path to Lightroom Classic .lrcat file for export mode.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output text file for export mode; one green-labeled path per line.",
    )
    parser.add_argument(
        "--paths",
        help="Previously exported text file of green-labeled paths for JSON mode.",
    )
    parser.add_argument(
        "--json",
        help="Path to an existing FastStack faststack.json to update in JSON mode.",
    )
    parser.add_argument(
        "--uploaded-date",
        default=DEFAULT_UPLOADED_DATE,
        help=f"Date to use for newly marked uploaded entries with no date (default: {DEFAULT_UPLOADED_DATE}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview JSON changes without writing any file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print normal detailed progress information.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print very verbose debugging information.",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> str:
    export_selected = bool(args.input or args.output)
    json_selected = bool(args.paths or args.json)

    if not export_selected and not json_selected:
        parser.print_help()
        raise SystemExit(1)

    if export_selected and json_selected:
        parser.error("Choose either export mode (-i/-o) or JSON mode (--paths/--json), not both.")

    if export_selected:
        if not args.input or not args.output:
            parser.error("Export mode requires both -i/--input and -o/--output.")
        return "export"

    if not args.paths or not args.json:
        parser.error("JSON mode requires both --paths and --json.")
    return "json"


def connect_ro_sqlite(path: str) -> sqlite3.Connection:
    uri = f"file:{os.path.abspath(path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_catalog_path(root: str, subdir: str, base_name: str, extension: str) -> str:
    filename = f"{base_name}.{extension}" if extension else base_name
    return os.path.normpath((root or "") + (subdir or "") + filename)


def stem_key_from_path(path_str: str) -> str:
    return Path(path_str).stem.lower()


def export_green_paths(catalog_path: str, output_path: str, logger: Logger) -> int:
    if not os.path.exists(catalog_path):
        raise FileNotFoundError(f"Catalog not found: {catalog_path}")

    logger.verbose(f"Opening Lightroom catalog read-only: {catalog_path}")
    conn = connect_ro_sqlite(catalog_path)
    try:
        sql = """
        SELECT
            i.id_local AS image_id,
            r.absolutePath,
            d.pathFromRoot,
            f.baseName,
            f.extension
        FROM Adobe_images i
        JOIN AgLibraryFile f
            ON i.rootFile = f.id_local
        JOIN AgLibraryFolder d
            ON f.folder = d.id_local
        JOIN AgLibraryRootFolder r
            ON d.rootFolder = r.id_local
        WHERE i.colorLabels = 'Green'
        ORDER BY r.absolutePath, d.pathFromRoot, f.baseName
        """
        rows = conn.execute(sql).fetchall()
        logger.verbose(f"Found {len(rows)} Lightroom rows where colorLabels = 'Green'.")

        output_records: list[GreenPathRecord] = []
        for row in rows:
            full_path = normalize_catalog_path(
                row["absolutePath"] or "",
                row["pathFromRoot"] or "",
                row["baseName"] or "",
                row["extension"] or "",
            )
            record = GreenPathRecord(
                image_id=int(row["image_id"]),
                full_path=full_path,
                stem_key=stem_key_from_path(full_path),
            )
            output_records.append(record)
            logger.debug(f"Export row image_id={record.image_id} path={record.full_path}")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as handle:
            for record in output_records:
                handle.write(record.full_path)
                handle.write("\n")

        logger.info(f"Wrote {len(output_records)} green-labeled paths to {out_path}")
        return len(output_records)
    finally:
        conn.close()


@dataclass
class JsonUpdateSummary:
    paths_read: int = 0
    unique_stems_in_paths: int = 0
    existing_files: int = 0
    missing_files: int = 0
    json_entries_total: int = 0
    matching_entries_found: int = 0
    newly_marked_uploaded: int = 0
    already_uploaded: int = 0
    stems_not_present_in_json: int = 0
    backup_path: str | None = None
    json_written: bool = False


DEFAULT_FASTSTACK_ENTRY_SHAPE = {
    "stack_id": None,
    "stacked": False,
    "stacked_date": None,
    "uploaded": False,
    "uploaded_date": None,
    "edited": False,
    "edited_date": None,
    "restacked": False,
    "restacked_date": None,
    "favorite": False,
    "todo": False,
    "todo_date": None,
}


def load_paths_file(paths_path: str, logger: Logger) -> list[str]:
    if not os.path.exists(paths_path):
        raise FileNotFoundError(f"Paths file not found: {paths_path}")

    result: list[str] = []
    with open(paths_path, "r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                logger.debug(f"Skipping empty line {line_number} in paths file.")
                continue
            result.append(line)
    logger.verbose(f"Loaded {len(result)} non-empty paths from {paths_path}")
    return result


def next_backup_path(json_path: Path) -> Path:
    first = json_path.with_name(json_path.name + ".bak")
    if not first.exists():
        return first

    index = 1
    while True:
        candidate = json_path.with_name(json_path.name + f".bak{index}")
        if not candidate.exists():
            return candidate
        index += 1


def ensure_faststack_entry_shape(entry: dict) -> dict:
    for key, value in DEFAULT_FASTSTACK_ENTRY_SHAPE.items():
        entry.setdefault(key, value)
    return entry


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    tmp_path.replace(path)


def human_summary(summary: JsonUpdateSummary, json_path: str) -> str:
    lines = [
        f"Summary for {json_path}",
        f"  Paths read: {summary.paths_read}",
        f"  Unique stems in paths file: {summary.unique_stems_in_paths}",
        f"  Exported image paths that currently exist on disk: {summary.existing_files}",
        f"  Exported image paths missing on disk: {summary.missing_files}",
        f"  FastStack entries present in JSON: {summary.json_entries_total}",
        f"  Matching FastStack entries found: {summary.matching_entries_found}",
        f"  Newly marked uploaded: {summary.newly_marked_uploaded}",
        f"  Already uploaded: {summary.already_uploaded}",
        f"  Exported stems not present in this JSON: {summary.stems_not_present_in_json}",
    ]
    if summary.backup_path:
        lines.append(f"  Backup created: {summary.backup_path}")
    if summary.json_written:
        lines.append("  JSON file written: yes")
    else:
        lines.append("  JSON file written: no")
    return "\n".join(lines)


def update_faststack_json(
    paths_file: str,
    json_path_str: str,
    uploaded_date: str,
    dry_run: bool,
    logger: Logger,
) -> JsonUpdateSummary:
    json_path = Path(json_path_str)
    if not json_path.exists():
        raise FileNotFoundError(
            f"FastStack JSON not found: {json_path}. This tool does not create new JSON files."
        )

    path_lines = load_paths_file(paths_file, logger)
    summary = JsonUpdateSummary(paths_read=len(path_lines))

    stem_to_paths: dict[str, list[str]] = {}
    for path_str in path_lines:
        stem = stem_key_from_path(path_str)
        stem_to_paths.setdefault(stem, []).append(path_str)
        if os.path.exists(path_str):
            summary.existing_files += 1
            logger.debug(f"File exists on disk: {path_str}")
        else:
            summary.missing_files += 1
            logger.debug(f"File missing on disk: {path_str}")

    summary.unique_stems_in_paths = len(stem_to_paths)

    logger.verbose(f"Opening FastStack JSON: {json_path}")
    data = load_json(json_path)
    entries = data.get("entries")
    if not isinstance(entries, dict):
        raise ValueError(f"FastStack JSON missing an 'entries' dictionary: {json_path}")

    summary.json_entries_total = len(entries)
    changed = False

    json_stems = set(entries.keys())
    exported_stems = set(stem_to_paths.keys())
    summary.stems_not_present_in_json = len(exported_stems - json_stems)

    for stem in sorted(exported_stems & json_stems):
        summary.matching_entries_found += 1
        entry = entries[stem]
        if not isinstance(entry, dict):
            logger.warn(f"Skipping malformed FastStack entry for stem {stem!r}: not an object")
            continue

        ensure_faststack_entry_shape(entry)
        source_paths = stem_to_paths[stem]
        logger.debug(f"Matching stem {stem!r} with source paths: {source_paths}")

        if entry.get("uploaded") is True:
            summary.already_uploaded += 1
            logger.verbose(f"Already uploaded: {stem}")
            continue

        entry["uploaded"] = True
        if not entry.get("uploaded_date"):
            entry["uploaded_date"] = uploaded_date
        summary.newly_marked_uploaded += 1
        changed = True
        logger.verbose(f"Marking uploaded: {stem}")

    if changed and not dry_run:
        backup_path = next_backup_path(json_path)
        shutil.copy2(json_path, backup_path)
        summary.backup_path = str(backup_path)
        save_json(json_path, data)
        summary.json_written = True
    elif changed and dry_run:
        logger.info("[dry-run] Changes detected; JSON was not written.")
    else:
        logger.info("No JSON changes were needed.")

    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    mode = validate_args(parser, args)
    logger = Logger(verbose=args.verbose, debug=args.debug)

    try:
        if mode == "export":
            count = export_green_paths(args.input, args.output, logger)
            logger.info(f"Export complete. {count} paths written.")
            return 0

        summary = update_faststack_json(
            paths_file=args.paths,
            json_path_str=args.json,
            uploaded_date=args.uploaded_date,
            dry_run=args.dry_run,
            logger=logger,
        )
        logger.info("")
        logger.info(human_summary(summary, args.json))
        return 0
    except (FileNotFoundError, ValueError, sqlite3.DatabaseError, json.JSONDecodeError) as exc:
        logger.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
