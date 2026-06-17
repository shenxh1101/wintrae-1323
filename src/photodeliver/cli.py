"""命令行入口"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from .checker import QualityChecker
from .models import (
    ClientContext,
    DeliveryRules,
    FileType,
    FILE_TYPE_LABELS,
    PackVersion,
)
from .namer import NamingEngine
from .packer import Packer, VERSION_LABELS
from .reporter import ReportGenerator
from .scanner import FileScanner
from .selector import FileSelector

console = Console()

FILE_TYPE_CHOICES = ["original", "retouched", "behind", "video"]
PACK_VERSION_CHOICES = ["full", "web", "preview", "social"]


def _parse_file_type(value: str) -> FileType:
    return FileType(value.lower())


def _parse_pack_version(value: str) -> PackVersion:
    return PackVersion(value.lower())


def _build_context(
    directory: str,
    client: str,
    date: str,
    output: Optional[str],
    template: Optional[str],
    min_rating: int,
    exclude: tuple,
    versions: tuple,
) -> ClientContext:
    rules = DeliveryRules()
    if template:
        rules.name_template = template
    if min_rating is not None:
        rules.min_rating = min_rating
    if exclude:
        rules.exclude_types = [_parse_file_type(v) for v in exclude]
    if versions:
        rules.pack_versions = [_parse_pack_version(v) for v in versions]

    out_dir = Path(output) if output else (Path(directory).parent / "交付")
    ctx = ClientContext(
        client_name=client,
        shoot_date=date,
        output_dir=out_dir,
        rules=rules,
    )
    return ctx


def _print_scan_summary(result):
    table = Table(title="扫描结果汇总", show_lines=False)
    table.add_column("类型", style="cyan", justify="left")
    table.add_column("数量", style="magenta", justify="right")
    table.add_column("大小 (MB)", style="green", justify="right")
    total = 0
    total_size = 0.0
    for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO, FileType.UNKNOWN):
        count = result.count_by_type(ftype)
        size = result.size_by_type_mb(ftype)
        if count > 0:
            table.add_row(FILE_TYPE_LABELS[ftype], str(count), f"{size:.2f}")
            total += count
            total_size += size
    table.add_section()
    table.add_row("合计", str(total), f"{total_size:.2f}", style="bold")
    console.print(table)


def _print_dry_run_banner():
    console.print(
        Panel.fit(
            "[yellow bold]⚠ DRY RUN 模式 - 不会实际执行文件操作[/yellow bold]",
            border_style="yellow",
        )
    )


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(version="0.1.0", prog_name="photodeliver")
def main():
    """摄影交付文件批量整理工具

    \b
    常用命令:
      scan     扫描目录并识别文件
      rename   按模板重命名并复制文件
      select   按条件筛选文件
      pack     打包多版本交付
      report   生成整理报告
    """


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--recursive/--no-recursive", default=True, help="递归扫描子目录")
@click.option("--hash/--no-hash", default=False, help="计算MD5（较慢）")
@click.option("--verbose", "-v", is_flag=True, help="显示详细列表")
def scan(directory, recursive, hash, verbose):
    """扫描目录，识别原片、精修片、花絮和视频"""
    scanner = FileScanner(compute_hash=hash, read_exif=True)
    with console.status(f"[cyan]正在扫描目录: {directory}"):
        result = scanner.scan(directory, recursive=recursive)

    console.print(f"[green]扫描完成[/green] 共发现 [bold]{result.total_count}[/bold] 个文件")
    _print_scan_summary(result)

    if verbose:
        for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
            files = result.by_type.get(ftype, [])
            if not files:
                continue
            t = Table(title=f"{FILE_TYPE_LABELS[ftype]} ({len(files)} 个)")
            t.add_column("#", style="dim")
            t.add_column("文件名", style="cyan")
            t.add_column("序号", justify="right")
            t.add_column("尺寸", justify="right")
            t.add_column("大小", justify="right", style="green")
            t.add_column("星级", justify="center")
            for i, f in enumerate(files[:50], 1):
                dim = f"{f.width}x{f.height}" if f.width else "-"
                stars = "★" * f.rating if f.rating else "-"
                t.add_row(str(i), f.filename, str(f.sequence or "-"), dim, f"{f.size_mb:.1f}MB", stars)
            if len(files) > 50:
                t.add_row("...", f"还有 {len(files) - 50} 个文件", "", "", "", "")
            console.print(t)


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--client", "-c", required=True, help="客户名称")
@click.option("--date", "-d", required=True, help="拍摄日期 (如 20250618)")
@click.option("--output", "-o", default=None, help="输出目录（默认：扫描目录/../交付）")
@click.option("--template", "-t", default=None, help="命名模板，默认 {client}_{date}_{type}_{seq:04d}")
@click.option("--min-rating", default=0, type=int, help="最低星级筛选 (0-5)")
@click.option("--exclude", multiple=True, type=click.Choice(FILE_TYPE_CHOICES), help="排除文件类型")
@click.option("--version", "versions", multiple=True, type=click.Choice(PACK_VERSION_CHOICES), help="打包版本 (可多次)")
@click.option("--move/--copy", default=False, help="移动文件而非复制")
@click.option("--dry-run", "-n", is_flag=True, help="预览模式，不实际操作")
def rename(directory, client, date, output, template, min_rating, exclude, versions, move, dry_run):
    """按命名模板重命名并整理文件"""
    if dry_run:
        _print_dry_run_banner()

    ctx = _build_context(directory, client, date, output, template, min_rating, exclude, versions)
    scanner = FileScanner(compute_hash=True, read_exif=True)
    with console.status("[cyan]扫描文件..."):
        result = scanner.scan(directory, recursive=True)

    selector = FileSelector(result)
    selector.filter_by_rating(min_rating)
    if exclude:
        selector.filter_by_exclude_types([_parse_file_type(v) for v in exclude])

    console.print(f"筛选后保留 [bold]{selector.selected_count}[/bold] 个文件")

    with console.status("[cyan]规划重命名..."):
        engine = NamingEngine(ctx)
        engine.apply_renames(result)

    plan = engine.plan_renames(result)
    table = Table(title="重命名预览 (前15项)")
    table.add_column("类型", style="cyan")
    table.add_column("原文件名", style="dim")
    table.add_column("→")
    table.add_column("新文件名", style="green bold")
    count = 0
    for ftype, entries in plan.items():
        for photo, new_name, seq in entries[:15]:
            if count >= 15:
                break
            table.add_row(
                FILE_TYPE_LABELS[ftype],
                photo.filename,
                "→",
                f"{new_name}.{photo.extension}",
            )
            count += 1
        if count >= 15:
            break
    console.print(table)

    with console.status("[cyan]执行文件操作..." if not dry_run else "[cyan]预览操作..."):
        ops = engine.execute_copy(result, dry_run=dry_run, move=move)

    console.print(f"[green]完成[/green] 共处理 [bold]{len(ops)}[/bold] 个文件")
    if not dry_run:
        console.print(f"输出目录: [link=file://{ctx.output_dir}]{ctx.output_dir}[/link]")


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--client", "-c", required=True, help="客户名称")
@click.option("--date", "-d", required=True, help="拍摄日期")
@click.option("--output", "-o", default=None, help="输出目录")
@click.option("--min-rating", default=0, type=int, help="最低星级 (0-5)")
@click.option("--list-file", "list_file", type=click.Path(exists=True, dir_okay=False), help="选择清单文件 (每行一个文件名)")
@click.option("--exclude", multiple=True, type=click.Choice(FILE_TYPE_CHOICES), help="排除类型")
@click.option("--dry-run", "-n", is_flag=True, help="预览模式")
def select(directory, client, date, output, min_rating, list_file, exclude, dry_run):
    """按星级或文件清单筛选成片"""
    if dry_run:
        _print_dry_run_banner()

    ctx = _build_context(directory, client, date, output, None, min_rating, exclude, ())
    scanner = FileScanner(compute_hash=False, read_exif=True)
    with console.status("[cyan]扫描文件..."):
        result = scanner.scan(directory, recursive=True)

    selector = FileSelector(result)
    before = selector.selected_count

    if min_rating:
        selector.filter_by_rating(min_rating)
        console.print(f"[cyan]星级筛选:[/cyan] ≥ {min_rating} 星")

    if list_file:
        selector.filter_by_selection_list(list_file)
        console.print(f"[cyan]清单筛选:[/cyan] {list_file}")

    if exclude:
        selector.filter_by_exclude_types([_parse_file_type(v) for v in exclude])

    after = selector.selected_count
    console.print(f"[green]筛选结果[/green] 保留 [bold]{after}[/bold] / {before} 个文件 (排除 {before - after} 个)")

    t = Table(title="筛选后文件统计")
    t.add_column("类型", style="cyan")
    t.add_column("保留", justify="right", style="green")
    t.add_column("排除", justify="right", style="red")
    t.add_column("总数", justify="right")
    for ftype in (FileType.ORIGINAL, FileType.RETOUCHED, FileType.BEHIND, FileType.VIDEO):
        all_files = result.by_type.get(ftype, [])
        sel = [f for f in all_files if f.selected]
        t.add_row(
            FILE_TYPE_LABELS[ftype],
            str(len(sel)),
            str(len(all_files) - len(sel)),
            str(len(all_files)),
        )
    console.print(t)


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--client", "-c", required=True, help="客户名称")
@click.option("--date", "-d", required=True, help="拍摄日期")
@click.option("--output", "-o", default=None, help="输出目录")
@click.option("--template", default=None, help="命名模板")
@click.option("--min-rating", default=0, type=int, help="最低星级")
@click.option("--version", "versions", multiple=True, type=click.Choice(PACK_VERSION_CHOICES), help="打包版本 (可多次，默认 full+web)")
@click.option("--exclude", multiple=True, type=click.Choice(FILE_TYPE_CHOICES), help="排除类型")
@click.option("--dry-run", "-n", is_flag=True, help="预览模式")
def pack(directory, client, date, output, template, min_rating, versions, exclude, dry_run):
    """打包不同用途版本（完整版/网页版/预览版/社交版）"""
    if dry_run:
        _print_dry_run_banner()

    if not versions:
        versions = ("full", "web")

    ctx = _build_context(directory, client, date, output, template, min_rating, exclude, versions)
    scanner = FileScanner(compute_hash=False, read_exif=True)
    with console.status("[cyan]扫描文件..."):
        result = scanner.scan(directory, recursive=True)

    selector = FileSelector(result)
    selector.filter_by_rating(min_rating)
    if exclude:
        selector.filter_by_exclude_types([_parse_file_type(v) for v in exclude])

    with console.status("[cyan]规划重命名..."):
        engine = NamingEngine(ctx)
        engine.apply_renames(result)

    packer = Packer(ctx, result)
    vers = [_parse_pack_version(v) for v in versions]
    results = {}
    for v in vers:
        with console.status(f"[cyan]打包 {VERSION_LABELS[v]}..."):
            results[v] = packer.pack_version(v, dry_run=dry_run)

    t = Table(title="打包结果")
    t.add_column("版本", style="cyan")
    t.add_column("输出文件", style="green")
    t.add_column("状态")
    for v, path in results.items():
        status = "[yellow]预览[/yellow]" if dry_run else "[green]完成[/green]"
        t.add_row(VERSION_LABELS[v], str(path) if path else "—", status)
    console.print(t)


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--client", "-c", required=True, help="客户名称")
@click.option("--date", "-d", required=True, help="拍摄日期")
@click.option("--output", "-o", default=None, help="输出目录")
@click.option("--template", default=None, help="命名模板")
@click.option("--min-rating", default=0, type=int, help="最低星级")
@click.option("--exclude", multiple=True, type=click.Choice(FILE_TYPE_CHOICES), help="排除类型")
@click.option("--format", "formats", multiple=True, type=click.Choice(["text", "json", "csv"]), help="报告格式 (默认全部)")
@click.option("--dry-run", "-n", is_flag=True, help="预览模式")
def report(directory, client, date, output, template, min_rating, exclude, formats, dry_run):
    """生成整理报告：统计、检查、预览清单"""
    if dry_run:
        _print_dry_run_banner()

    ctx = _build_context(directory, client, date, output, template, min_rating, exclude, ())
    scanner = FileScanner(compute_hash=True, read_exif=True)
    with console.status("[cyan]扫描文件..."):
        result = scanner.scan(directory, recursive=True)

    selector = FileSelector(result)
    selector.filter_by_rating(min_rating)
    if exclude:
        selector.filter_by_exclude_types([_parse_file_type(v) for v in exclude])

    with console.status("[cyan]质量检查..."):
        checker = QualityChecker(result, ctx)
        quality = checker.run()

    engine = NamingEngine(ctx)
    engine.apply_renames(result)

    _print_scan_summary(result)

    if quality.issues:
        t = Table(title=f"质量检查 ({quality.error_count} 错误, {quality.warning_count} 警告)")
        t.add_column("级别", style="bold")
        t.add_column("类别", style="cyan")
        t.add_column("说明")
        for issue in quality.issues[:30]:
            style = "red" if issue.level == "error" else "yellow"
            t.add_row(f"[{style}]{issue.level.upper()}[/{style}]", issue.category, issue.message)
        console.print(t)
    else:
        console.print("[green]✓[/green] 质量检查通过，未发现问题")

    if dry_run:
        console.print("[yellow]DRY RUN: 不生成文件[/yellow]")
        return

    with console.status("[cyan]生成报告文件..."):
        generator = ReportGenerator(ctx, result, quality)
        fmt_set = set(formats) if formats else {"text", "json", "csv"}
        out_paths = {}
        if "csv" in fmt_set:
            out_paths["预览清单"] = generator.generate_preview_list()
        if "text" in fmt_set:
            out_paths["文本报告"] = generator.generate_text_report()
        if "json" in fmt_set:
            out_paths["JSON报告"] = generator.generate_json_report()

    t = Table(title="报告文件")
    t.add_column("类型", style="cyan")
    t.add_column("路径", style="green")
    for name, path in out_paths.items():
        t.add_row(name, str(path))
    console.print(t)


if __name__ == "__main__":
    main()
