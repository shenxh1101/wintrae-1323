"""报告生成模块"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    CheckIssue,
    ClientContext,
    FileType,
    FILE_TYPE_LABELS,
    PackVersion,
    PhotoFile,
    QualityReport,
    ScanResult,
)


class ReportGenerator:
    """报告生成器"""

    def __init__(
        self,
        context: ClientContext,
        result: ScanResult,
        quality: Optional[QualityReport] = None,
    ):
        self.context = context
        self.result = result
        self.quality = quality

    def _files_by_type_selected(self) -> dict[FileType, list[PhotoFile]]:
        out: dict[FileType, list[PhotoFile]] = {}
        for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
            out[ftype] = [f for f in self.result.by_type.get(ftype, []) if f.selected]
        return out

    def generate_preview_list(self, output_path: Optional[Path] = None) -> Path:
        out_path = output_path or self.context.output_dir / f"{self.context.client_name}_{self.context.shoot_date}_预览清单.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        selected = self._files_by_type_selected()
        with open(out_path, "w", encoding="utf-8-sig") as f:
            f.write("序号,分类,原文件名,新文件名,尺寸,大小(MB),星级,备注\n")
            for ftype, files in selected.items():
                for idx, photo in enumerate(files, start=1):
                    dim = f"{photo.width}x{photo.height}" if photo.width else "-"
                    new_name = photo.new_filename if photo.new_filename else "-"
                    issues = "; ".join(photo.issues) if photo.issues else ""
                    line = (
                        f"{idx},{FILE_TYPE_LABELS[ftype]},"
                        f"{photo.filename},{new_name},"
                        f"{dim},{photo.size_mb},{photo.rating},{issues}\n"
                    )
                    f.write(line)
        return out_path

    def generate_text_report(self, output_path: Optional[Path] = None) -> Path:
        out_path = output_path or self.context.output_dir / f"{self.context.client_name}_{self.context.shoot_date}_整理报告.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("        摄影交付整理报告")
        lines.append("=" * 60)
        lines.append(f"客户名称: {self.context.client_name}")
        lines.append(f"拍摄日期: {self.context.shoot_date}")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"扫描目录: {self.result.directory}")
        lines.append(f"输出目录: {self.context.output_dir}")
        lines.append("")

        lines.append("-" * 60)
        lines.append("文件统计")
        lines.append("-" * 60)
        lines.append(f"{'类型':<10} {'总数':>6} {'选中':>6} {'总大小(MB)':>12}")
        lines.append("-" * 60)
        sel_by_type = self._files_by_type_selected()
        for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
            total = self.result.count_by_type(ftype)
            selected = len(sel_by_type.get(ftype, []))
            size = self.result.size_by_type_mb(ftype)
            lines.append(f"{FILE_TYPE_LABELS[ftype]:<10} {total:>6} {selected:>6} {size:>12.2f}")
        lines.append("-" * 60)
        lines.append(
            f"{'合计':<10} {self.result.total_count:>6} "
            f"{sum(len(v) for v in sel_by_type.values()):>6} "
            f"{round(self.result.total_size / 1024 / 1024, 2):>12.2f}"
        )
        lines.append("")

        if self.quality:
            lines.append("-" * 60)
            lines.append("质量检查")
            lines.append("-" * 60)
            lines.append(f"错误数: {self.quality.error_count}")
            lines.append(f"警告数: {self.quality.warning_count}")
            if self.quality.issues:
                lines.append("")
                for issue in self.quality.issues:
                    marker = "✗" if issue.level == "error" else "!"
                    lines.append(f"[{issue.level.upper()}] {marker} {issue.category} - {issue.message}")
            lines.append("")

        lines.append("-" * 60)
        lines.append("交付清单预览 (前20项)")
        lines.append("-" * 60)
        preview_count = 0
        for ftype, files in sel_by_type.items():
            for photo in files[:20 - preview_count]:
                if preview_count >= 20:
                    break
                new_name = photo.new_filename if photo.new_filename else photo.filename
                rating = "★" * photo.rating if photo.rating else "-"
                lines.append(f"  [{FILE_TYPE_LABELS[ftype]:<3}] {new_name:<50} {rating}")
                preview_count += 1
            if preview_count >= 20:
                break
        lines.append("")
        lines.append("=" * 60)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return out_path

    def generate_json_report(self, output_path: Optional[Path] = None) -> Path:
        out_path = output_path or self.context.output_dir / f"{self.context.client_name}_{self.context.shoot_date}_整理报告.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "client": self.context.client_name,
            "shoot_date": self.context.shoot_date,
            "generated_at": datetime.now().isoformat(),
            "source_dir": str(self.result.directory),
            "output_dir": str(self.context.output_dir),
            "totals": {
                "total_count": self.result.total_count,
                "total_size_mb": round(self.result.total_size / 1024 / 1024, 2),
            },
            "by_type": {},
        }
        sel_by_type = self._files_by_type_selected()
        for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
            files_all = self.result.by_type.get(ftype, [])
            files_sel = sel_by_type.get(ftype, [])
            data["by_type"][ftype.value] = {
                "label": FILE_TYPE_LABELS[ftype],
                "total_count": len(files_all),
                "selected_count": len(files_sel),
                "total_size_mb": self.result.size_by_type_mb(ftype),
                "files": [
                    {
                        "filename": p.new_filename if p.new_filename else p.filename,
                        "original": p.filename,
                        "size_mb": p.size_mb,
                        "dimensions": f"{p.width}x{p.height}" if p.width else None,
                        "rating": p.rating,
                        "issues": p.issues,
                    }
                    for p in files_sel
                ],
            }
        if self.quality:
            data["quality"] = {
                "error_count": self.quality.error_count,
                "warning_count": self.quality.warning_count,
                "issues": [
                    {
                        "level": i.level,
                        "category": i.category,
                        "message": i.message,
                        "files": [p.filename for p in i.files],
                    }
                    for i in self.quality.issues
                ],
                "missing_sequences": {k.value: v for k, v in self.quality.missing_sequences.items()},
                "duplicate_count": len(self.quality.duplicate_files),
                "abnormal_size_count": len(self.quality.abnormal_sizes),
            }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return out_path

    def generate_all(self) -> dict[str, Path]:
        return {
            "preview_csv": self.generate_preview_list(),
            "text_report": self.generate_text_report(),
            "json_report": self.generate_json_report(),
        }
