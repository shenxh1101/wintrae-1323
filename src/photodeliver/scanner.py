"""文件扫描与识别模块"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ExifTags

from .models import FileType, PhotoFile, ScanResult


RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".raf", ".rw2", ".orf", ".dng", ".pef", ".3fr", ".raw",
    ".rwl", ".iiq",
}

RETOUCHED_EXTENSIONS = {".jpg", ".jpeg", ".tif", ".tiff", ".png", ".heic", ".heif"}
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp",
}

RETOUCH_KEYWORDS = ["精修", "修", "retouch", "final", "ps", "output", "成品", "交付", "修片"]
BEHIND_KEYWORDS = ["花絮", "behind", "bts", "现场", "日常", "侧拍", "工作照"]
ORIGINAL_KEYWORDS = ["原片", "原图", "original", "raw", "未修", "直出"]

RATING_EXIF_TAG = None
for tag_id, tag_name in ExifTags.TAGS.items():
    if tag_name == "Rating":
        RATING_EXIF_TAG = tag_id
        break


def _classify_by_extension(ext: str) -> FileType:
    ext_lower = ext.lower()
    if ext_lower in RAW_EXTENSIONS:
        return FileType.ORIGINAL
    if ext_lower in VIDEO_EXTENSIONS:
        return FileType.VIDEO
    if ext_lower in RETOUCHED_EXTENSIONS:
        return FileType.RETOUCHED
    return FileType.UNKNOWN


def _classify_by_name(name: str, current_type: FileType) -> FileType:
    name_lower = name.lower()
    if current_type == FileType.RETOUCHED:
        for kw in BEHIND_KEYWORDS:
            if kw.lower() in name_lower:
                return FileType.BEHIND
        for kw in ORIGINAL_KEYWORDS:
            if kw.lower() in name_lower:
                return FileType.ORIGINAL
    return current_type


def _classify_by_path(path: Path, current_type: FileType) -> FileType:
    parts_lower = [p.lower() for p in path.parts]
    full_path = str(path).lower()
    for kw in BEHIND_KEYWORDS:
        if kw.lower() in full_path:
            if current_type in (FileType.RETOUCHED, FileType.UNKNOWN):
                return FileType.BEHIND
    for kw in ORIGINAL_KEYWORDS + ["raw"]:
        if kw.lower() in full_path:
            if current_type in (FileType.RETOUCHED, FileType.UNKNOWN):
                return FileType.ORIGINAL
    for kw in RETOUCH_KEYWORDS:
        if kw.lower() in full_path:
            if current_type == FileType.UNKNOWN:
                return FileType.RETOUCHED
    return current_type


def extract_sequence(name: str) -> Optional[int]:
    patterns = [
        r"(\d{3,6})",
        r"[-_](\d+)[-_]",
        r"IMG[_-]?(\d+)",
        r"DSC[_-]?(\d+)",
        r"DJI[_-]?(\d+)",
        r"[-_](\d+)\.",
    ]
    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def compute_md5(path: Path, chunk_size: int = 8192) -> str:
    md5 = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            md5.update(chunk)
    return md5.hexdigest()


def get_image_info(path: Path) -> tuple[int, int, int]:
    try:
        with Image.open(path) as img:
            width, height = img.size
            rating = 0
            try:
                exif = img.getexif()
                if exif and RATING_EXIF_TAG is not None:
                    rating_val = exif.get(RATING_EXIF_TAG)
                    if rating_val is not None:
                        rating = int(rating_val)
            except Exception:
                pass
            return width, height, rating
    except Exception:
        return 0, 0, 0


def _iter_files(directory: Path, recursive: bool = True) -> Iterable[Path]:
    pattern = "**/*" if recursive else "*"
    for p in directory.glob(pattern):
        if p.is_file() and not p.name.startswith("."):
            yield p


class FileScanner:
    """文件扫描器"""

    def __init__(self, compute_hash: bool = False, read_exif: bool = True):
        self.compute_hash = compute_hash
        self.read_exif = read_exif

    def classify_file(self, path: Path) -> FileType:
        ext = path.suffix
        ftype = _classify_by_extension(ext)
        ftype = _classify_by_name(path.name, ftype)
        ftype = _classify_by_path(path, ftype)
        return ftype

    def create_photo_file(self, path: Path) -> PhotoFile:
        ftype = self.classify_file(path)
        stat = path.stat()
        photo = PhotoFile(
            path=path,
            file_type=ftype,
            filename=path.name,
            extension=path.suffix.lower().lstrip("."),
            size=stat.st_size,
            sequence=extract_sequence(path.name),
        )
        if ftype in (FileType.RETOUCHED, FileType.BEHIND, FileType.ORIGINAL) and self.read_exif:
            photo.width, photo.height, photo.rating = get_image_info(path)
        if self.compute_hash:
            photo.hash_md5 = compute_md5(path)
        return photo

    def scan(self, directory: str | Path, recursive: bool = True) -> ScanResult:
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"目录不存在: {dir_path}")
        if not dir_path.is_dir():
            raise NotADirectoryError(f"不是目录: {dir_path}")

        result = ScanResult(directory=dir_path)

        for file_path in _iter_files(dir_path, recursive=recursive):
            try:
                photo = self.create_photo_file(file_path)
                result.files.append(photo)
                result.by_type.setdefault(photo.file_type, []).append(photo)
            except Exception as e:
                pass

        result.total_count = len(result.files)
        result.total_size = sum(f.size for f in result.files)

        for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
            files = result.by_type.get(ftype, [])
            files.sort(key=lambda f: (f.sequence if f.sequence else 999999, f.filename))

        return result
