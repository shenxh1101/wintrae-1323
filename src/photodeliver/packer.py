"""多版本打包模块"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image

from .models import ClientContext, FileType, FILE_TYPE_LABELS, PackVersion, PhotoFile, ScanResult


VERSION_LABELS = {
    PackVersion.FULL: "完整版",
    PackVersion.WEB: "网页版",
    PackVersion.PREVIEW: "预览版",
    PackVersion.SOCIAL: "社交版",
}


VERSION_MAX_SIZE = {
    PackVersion.FULL: None,
    PackVersion.WEB: (1920, 1080),
    PackVersion.PREVIEW: (1024, 768),
    PackVersion.SOCIAL: (1080, 1080),
}


VERSION_QUALITY = {
    PackVersion.FULL: 100,
    PackVersion.WEB: 85,
    PackVersion.PREVIEW: 75,
    PackVersion.SOCIAL: 80,
}


def _resize_image(src: Path, max_size: tuple[int, int], quality: int, target_ext: str = "jpg") -> bytes:
    with Image.open(src) as img:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        w, h = img.size
        max_w, max_h = max_size
        if w > max_w or h > max_h:
            ratio = min(max_w / w, max_h / h)
            new_w, new_h = int(w * ratio), int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        fmt = "JPEG" if target_ext in ("jpg", "jpeg") else target_ext.upper()
        save_kwargs = {"format": fmt, "quality": quality, "optimize": True}
        if fmt == "JPEG":
            save_kwargs["progressive"] = True
        img.save(buf, **save_kwargs)
        return buf.getvalue()


class Packer:
    """多版本打包器"""

    def __init__(self, context: ClientContext, result: ScanResult):
        self.context = context
        self.result = result

    def _collect_files(self) -> list[PhotoFile]:
        return [f for f in self.result.files if f.selected and f.file_type != FileType.UNKNOWN]

    def _archive_name(self, version: PackVersion) -> str:
        client = self.context.client_name.replace(" ", "_")
        date = self.context.shoot_date.replace(" ", "_")
        label = VERSION_LABELS.get(version, version.value)
        return f"{client}_{date}_{label}.zip"

    def _write_full_version(self, zipf: zipfile.ZipFile, files: list[PhotoFile]):
        for photo in files:
            if not photo.new_filename:
                name = photo.filename
            else:
                name = photo.new_filename
            arcname = f"{FILE_TYPE_LABELS[photo.file_type]}/{name}"
            zipf.write(str(photo.path), arcname=arcname)

    def _write_resized_version(
        self,
        zipf: zipfile.ZipFile,
        files: list[PhotoFile],
        max_size: tuple[int, int],
        quality: int,
    ):
        for photo in files:
            name = photo.new_filename if photo.new_filename else photo.filename
            stem = Path(name).stem
            ext = Path(name).suffix.lower()
            arcname = f"{FILE_TYPE_LABELS[photo.file_type]}/{stem}.jpg"
            if photo.file_type == FileType.VIDEO:
                zipf.write(str(photo.path), arcname=f"{FILE_TYPE_LABELS[photo.file_type]}/{name}")
                continue
            if photo.file_type == FileType.ORIGINAL:
                continue
            try:
                data = _resize_image(photo.path, max_size, quality, "jpg")
                zipf.writestr(arcname, data)
            except Exception:
                zipf.write(str(photo.path), arcname=f"{FILE_TYPE_LABELS[photo.file_type]}/{name}")

    def pack_version(self, version: PackVersion, output_dir: Optional[Path] = None, dry_run: bool = False) -> Optional[Path]:
        out_dir = output_dir or self.context.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        archive_path = out_dir / self._archive_name(version)

        files = self._collect_files()
        if not files:
            return None

        if dry_run:
            return archive_path

        max_size = VERSION_MAX_SIZE.get(version)
        quality = VERSION_QUALITY.get(version, 85)

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
            if version == PackVersion.FULL or max_size is None:
                self._write_full_version(zipf, files)
            else:
                self._write_resized_version(zipf, files, max_size, quality)
        return archive_path

    def pack_all(
        self,
        versions: Optional[Iterable[PackVersion]] = None,
        dry_run: bool = False,
    ) -> dict[PackVersion, Optional[Path]]:
        vers = list(versions) if versions else self.context.rules.pack_versions
        results: dict[PackVersion, Optional[Path]] = {}
        for v in vers:
            results[v] = self.pack_version(v, dry_run=dry_run)
        return results
