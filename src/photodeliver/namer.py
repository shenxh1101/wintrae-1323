"""命名模板与重命名引擎"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

from .models import ClientContext, FileType, FILE_TYPE_LABELS, PhotoFile, ScanResult


TYPE_SHORT = {
    FileType.ORIGINAL: "RAW",
    FileType.RETOUCHED: "RET",
    FileType.BEHIND: "BTS",
    FileType.VIDEO: "VID",
    FileType.UNKNOWN: "MIX",
}


def sanitize_name(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name


class NamingEngine:
    """命名引擎"""

    def __init__(self, context: ClientContext):
        self.context = context

    def render_name(self, photo: PhotoFile, sequence: int) -> str:
        template = self.context.rules.name_template
        type_short = TYPE_SHORT.get(photo.file_type, "MIX")
        type_label = FILE_TYPE_LABELS.get(photo.file_type, "未知")
        client = sanitize_name(self.context.client_name)
        date = sanitize_name(self.context.shoot_date)
        values = {
            "client": client,
            "date": date,
            "type": type_short,
            "type_label": type_label,
            "seq": sequence,
            "sequence": sequence,
            "ext": photo.extension,
            "orig_name": photo.filename,
        }
        try:
            name = template.format(**values)
        except (KeyError, IndexError, ValueError):
            name = f"{client}_{date}_{type_short}_{sequence:04d}"
        return sanitize_name(name)

    def plan_renames(self, result: ScanResult) -> dict[FileType, list[tuple[PhotoFile, str, int]]]:
        plan: dict[FileType, list[tuple[PhotoFile, str, int]]] = {}
        for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
            files = [f for f in result.by_type.get(ftype, []) if f.selected]
            if not files:
                continue
            files.sort(key=lambda f: (f.sequence if f.sequence else 999999, f.filename))
            plan[ftype] = []
            for idx, photo in enumerate(files, start=1):
                new_name = self.render_name(photo, idx)
                plan[ftype].append((photo, new_name, idx))
        return plan

    def apply_renames(self, result: ScanResult) -> None:
        plan = self.plan_renames(result)
        for ftype, entries in plan.items():
            for photo, new_name, seq in entries:
                ext = photo.extension
                if not new_name.lower().endswith(f".{ext}"):
                    new_name_full = f"{new_name}.{ext}"
                else:
                    new_name_full = new_name
                photo.new_filename = new_name_full
                photo.sequence = seq

    def build_output_structure(self, result: ScanResult) -> Path:
        folder = self.context.rules.folder_structure.format(
            client=sanitize_name(self.context.client_name),
            date=sanitize_name(self.context.shoot_date),
        )
        output_root = self.context.output_dir / folder
        output_root.mkdir(parents=True, exist_ok=True)
        for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
            if result.count_by_type(ftype) > 0:
                sub = output_root / FILE_TYPE_LABELS[ftype]
                sub.mkdir(parents=True, exist_ok=True)
        return output_root

    def execute_copy(
        self,
        result: ScanResult,
        dry_run: bool = False,
        move: bool = False,
    ) -> list[tuple[Path, Path]]:
        if not dry_run:
            output_root = self.build_output_structure(result)
        else:
            folder = self.context.rules.folder_structure.format(
                client=sanitize_name(self.context.client_name),
                date=sanitize_name(self.context.shoot_date),
            )
            output_root = self.context.output_dir / folder

        operations: list[tuple[Path, Path]] = []
        for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
            files = [f for f in result.by_type.get(ftype, []) if f.selected and f.new_filename]
            for photo in files:
                sub_dir = output_root / FILE_TYPE_LABELS[ftype]
                dest = sub_dir / photo.new_filename
                photo.new_path = dest
                operations.append((photo.path, dest))
                if not dry_run:
                    sub_dir.mkdir(parents=True, exist_ok=True)
                    if move:
                        shutil.move(str(photo.path), str(dest))
                    else:
                        shutil.copy2(str(photo.path), str(dest))
        return operations
