"""数据模型定义"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class FileType(str, Enum):
    ORIGINAL = "original"
    RETOUCHED = "retouched"
    BEHIND = "behind"
    VIDEO = "video"
    UNKNOWN = "unknown"


class PackVersion(str, Enum):
    FULL = "full"
    WEB = "web"
    PREVIEW = "preview"
    SOCIAL = "social"


FILE_TYPE_LABELS = {
    FileType.ORIGINAL: "原片",
    FileType.RETOUCHED: "精修片",
    FileType.BEHIND: "花絮",
    FileType.VIDEO: "视频",
    FileType.UNKNOWN: "未知",
}


@dataclass
class PhotoFile:
    """单个照片/视频文件"""
    path: Path
    file_type: FileType
    filename: str = ""
    extension: str = ""
    size: int = 0
    width: int = 0
    height: int = 0
    rating: int = 0
    sequence: Optional[int] = None
    hash_md5: str = ""
    new_filename: str = ""
    new_path: Optional[Path] = None
    selected: bool = True
    issues: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.filename:
            self.filename = self.path.name
        if not self.extension:
            self.extension = self.path.suffix.lower().lstrip(".")

    @property
    def aspect_ratio(self) -> Optional[float]:
        if self.width and self.height:
            return self.width / self.height
        return None

    @property
    def megapixels(self) -> Optional[float]:
        if self.width and self.height:
            return round((self.width * self.height) / 1_000_000, 2)
        return None

    @property
    def size_mb(self) -> float:
        return round(self.size / (1024 * 1024), 2)


@dataclass
class ScanResult:
    """扫描结果汇总"""
    directory: Path
    files: list[PhotoFile] = field(default_factory=list)
    total_count: int = 0
    total_size: int = 0
    by_type: dict[FileType, list[PhotoFile]] = field(default_factory=dict)

    def count_by_type(self, file_type: FileType) -> int:
        return len(self.by_type.get(file_type, []))

    def size_by_type_mb(self, file_type: FileType) -> float:
        files = self.by_type.get(file_type, [])
        return round(sum(f.size for f in files) / (1024 * 1024), 2)


@dataclass
class DeliveryRules:
    """交付规则配置"""
    name_template: str = "{client}_{date}_{type}_{seq:04d}"
    folder_structure: str = "{client}_{date}/"
    min_rating: int = 0
    exclude_types: list[FileType] = field(default_factory=list)
    pack_versions: list[PackVersion] = field(
        default_factory=lambda: [PackVersion.FULL, PackVersion.WEB]
    )
    expected_ranges: dict[FileType, tuple[int, int]] = field(default_factory=dict)
    min_dimensions: dict[FileType, tuple[int, int]] = field(default_factory=dict)
    max_dimensions: dict[FileType, tuple[int, int]] = field(default_factory=dict)


@dataclass
class ClientContext:
    """客户与项目上下文"""
    client_name: str
    shoot_date: str
    output_dir: Path
    rules: DeliveryRules = field(default_factory=DeliveryRules)


@dataclass
class CheckIssue:
    """检查发现的问题"""
    level: str
    category: str
    message: str
    files: list[PhotoFile] = field(default_factory=list)


@dataclass
class QualityReport:
    """质量检查报告"""
    issues: list[CheckIssue] = field(default_factory=list)
    missing_sequences: dict[FileType, list[int]] = field(default_factory=dict)
    duplicate_files: list[list[PhotoFile]] = field(default_factory=list)
    abnormal_sizes: list[PhotoFile] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "warning")
