"""质量检查模块"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from .models import CheckIssue, ClientContext, FileType, PhotoFile, QualityReport, ScanResult


class QualityChecker:
    """质量检查器"""

    def __init__(self, result: ScanResult, context: Optional[ClientContext] = None):
        self.result = result
        self.context = context

    def check_missing_sequences(self) -> dict[FileType, list[int]]:
        missing: dict[FileType, list[int]] = {}
        for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
            files = [f for f in self.result.by_type.get(ftype, []) if f.selected and f.sequence is not None]
            if not files:
                continue
            seqs = sorted({f.sequence for f in files})
            if not seqs:
                continue
            expected = set(range(seqs[0], seqs[-1] + 1))
            actual = set(seqs)
            miss = sorted(expected - actual)
            if miss:
                missing[ftype] = miss
        return missing

    def check_duplicates(self) -> list[list[PhotoFile]]:
        duplicates: list[list[PhotoFile]] = []
        groups: dict[str, list[PhotoFile]] = defaultdict(list)
        for photo in self.result.files:
            if not photo.selected:
                continue
            if photo.hash_md5:
                key = f"md5:{photo.hash_md5}"
                groups[key].append(photo)
        duplicates.extend([g for g in groups.values() if len(g) > 1])

        name_groups: dict[str, list[PhotoFile]] = defaultdict(list)
        for photo in self.result.files:
            if not photo.selected:
                continue
            key = (photo.filename.lower(), photo.size)
            name_groups[f"{key[0]}|{key[1]}"].append(photo)
        for g in name_groups.values():
            if len(g) > 1:
                dup_paths = {p.path.resolve() for p in g}
                if len(dup_paths) <= 1:
                    continue
                already = False
                for d in duplicates:
                    if {p.path.resolve() for p in d} == dup_paths:
                        already = True
                        break
                if not already:
                    duplicates.append(g)
        return duplicates

    def check_abnormal_dimensions(self) -> list[PhotoFile]:
        abnormal: list[PhotoFile] = []
        rules = self.context.rules if self.context else None
        for photo in self.result.files:
            if not photo.selected:
                continue
            if not (photo.width and photo.height):
                continue
            min_dim = rules.min_dimensions.get(photo.file_type) if rules else None
            max_dim = rules.max_dimensions.get(photo.file_type) if rules else None
            if min_dim:
                if photo.width < min_dim[0] or photo.height < min_dim[1]:
                    if photo not in abnormal:
                        abnormal.append(photo)
                        photo.issues.append(f"尺寸小于最小要求 {min_dim[0]}x{min_dim[1]}")
            if max_dim:
                if photo.width > max_dim[0] or photo.height > max_dim[1]:
                    if photo not in abnormal:
                        abnormal.append(photo)
                        photo.issues.append(f"尺寸大于最大要求 {max_dim[0]}x{max_dim[1]}")
        return abnormal

    def check_expected_ranges(self) -> list[CheckIssue]:
        issues: list[CheckIssue] = []
        rules = self.context.rules if self.context else None
        if not rules:
            return issues
        for ftype, (min_count, max_count) in rules.expected_ranges.items():
            actual = sum(1 for f in self.result.by_type.get(ftype, []) if f.selected)
            if actual < min_count:
                issues.append(CheckIssue(
                    level="warning",
                    category="数量不足",
                    message=f"{ftype.value} 数量 {actual} 少于预期最小值 {min_count}",
                    files=self.result.by_type.get(ftype, []),
                ))
            if actual > max_count:
                issues.append(CheckIssue(
                    level="warning",
                    category="数量过多",
                    message=f"{ftype.value} 数量 {actual} 多于预期最大值 {max_count}",
                    files=self.result.by_type.get(ftype, []),
                ))
        return issues

    def run(self) -> QualityReport:
        report = QualityReport()
        report.missing_sequences = self.check_missing_sequences()
        report.duplicate_files = self.check_duplicates()
        report.abnormal_sizes = self.check_abnormal_dimensions()

        for ftype, missing in report.missing_sequences.items():
            sample = missing[:10]
            extra = f"...(+{len(missing)-10})" if len(missing) > 10 else ""
            report.issues.append(CheckIssue(
                level="warning",
                category="缺失序号",
                message=f"{ftype.value} 缺失序号: {sample}{extra}",
            ))

        for dup_group in report.duplicate_files:
            names = [f.filename for f in dup_group]
            report.issues.append(CheckIssue(
                level="error",
                category="重复文件",
                message=f"检测到 {len(dup_group)} 个重复文件: {', '.join(names)}",
                files=dup_group,
            ))

        for photo in report.abnormal_sizes:
            report.issues.append(CheckIssue(
                level="warning",
                category="异常尺寸",
                message=f"{photo.filename} 尺寸 {photo.width}x{photo.height} 不符合要求",
                files=[photo],
            ))

        report.issues.extend(self.check_expected_ranges())

        for photo in self.result.files:
            if photo.selected and photo.file_type == FileType.UNKNOWN:
                report.issues.append(CheckIssue(
                    level="warning",
                    category="未知类型",
                    message=f"无法识别文件类型: {photo.filename}",
                    files=[photo],
                ))

        return report
