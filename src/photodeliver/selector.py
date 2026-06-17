"""文件筛选模块"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from .models import FileType, PhotoFile, ScanResult


class FileSelector:
    """文件筛选器"""

    def __init__(self, result: ScanResult):
        self.result = result

    def filter_by_rating(self, min_rating: int, file_types: Optional[Iterable[FileType]] = None):
        target_types = set(file_types) if file_types else {
            FileType.RETOUCHED, FileType.BEHIND
        }
        for photo in self.result.files:
            if photo.file_type in target_types and photo.selected:
                if photo.rating < min_rating:
                    photo.selected = False
                    photo.issues.append(f"星级低于阈值 {min_rating}")

    def filter_by_exclude_types(self, exclude_types: Iterable[FileType]):
        excludes = set(exclude_types)
        for photo in self.result.files:
            if photo.file_type in excludes:
                photo.selected = False
                photo.issues.append(f"文件类型被排除")

    def filter_by_whitelist(self, whitelist: set[str]):
        for photo in self.result.files:
            if not whitelist:
                continue
            if photo.filename not in whitelist and str(photo.path) not in whitelist:
                photo.selected = False
                photo.issues.append("不在白名单内")

    def filter_by_selection_list(self, list_path: str | Path):
        path = Path(list_path)
        if not path.exists():
            raise FileNotFoundError(f"选择清单不存在: {path}")

        selected_names: set[str] = set()
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                name = Path(line).name
                selected_names.add(name)
                selected_names.add(line)

        for photo in self.result.files:
            if photo.filename not in selected_names and str(photo.path) not in selected_names:
                photo.selected = False
                photo.issues.append("不在选择清单中")

    def keep_only(self, indices: Iterable[int]):
        idx_set = set(indices)
        for i, photo in enumerate(self.result.files):
            if i not in idx_set:
                photo.selected = False

    def reset(self):
        for photo in self.result.files:
            photo.selected = True
            photo.issues = [i for i in photo.issues if not i.startswith("星级") and not i.startswith("文件类型") and not i.startswith("不在")]

    @property
    def selected_count(self) -> int:
        return sum(1 for f in self.result.files if f.selected)

    @property
    def selected_files(self) -> list[PhotoFile]:
        return [f for f in self.result.files if f.selected]

    def selected_by_type(self, file_type: FileType) -> list[PhotoFile]:
        return [f for f in self.result.by_type.get(file_type, []) if f.selected]
