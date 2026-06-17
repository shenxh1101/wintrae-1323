"""生成测试数据"""
import os
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent / "test_data"
RAW_DIR = ROOT / "原片"
RET_DIR = ROOT / "精修片"
BTS_DIR = ROOT / "花絮"
VID_DIR = ROOT / "视频"


def make_image(path: Path, size: tuple, color: tuple):
    img = Image.new("RGB", size, color)
    img.save(path, "JPEG", quality=90)


def main():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    for d in (RAW_DIR, RET_DIR, BTS_DIR, VID_DIR):
        d.mkdir(parents=True, exist_ok=True)

    for i in range(1, 21):
        make_image(RAW_DIR / f"IMG_{i:04d}.CR2.jpg", (6000, 4000), (100 + i*5, 50 + i*3, 80 + i*2))

    for i in range(1, 16):
        make_image(RET_DIR / f"客户A_精修_{i:03d}.jpg", (6000, 4000), (200 + i, 180 - i, 150 + i*2))
    make_image(RET_DIR / f"客户A_精修_020.jpg", (6000, 4000), (210, 165, 185))

    for i in range(1, 8):
        make_image(BTS_DIR / f"behind_the_scene_{i:02d}.jpg", (4000, 3000), (90 + i*8, 120 + i*4, 200 - i*6))

    for i in range(1, 4):
        v = VID_DIR / f"clip_{i:02d}.mp4"
        v.write_bytes(os.urandom(1024 * 500 + i * 10000))

    dup = RET_DIR / "客户A_精修_010_副本.jpg"
    shutil.copy(RET_DIR / "客户A_精修_010.jpg", dup)

    small = RET_DIR / "客户A_精修_小图_001.jpg"
    make_image(small, (800, 600), (120, 120, 120))

    list_file = ROOT / "select_list.txt"
    lines = [f"客户A_精修_{i:03d}.jpg" for i in (1, 2, 3, 5, 7, 9, 10, 12, 15)]
    list_file.write_text("\n".join(lines), encoding="utf-8")

    print(f"测试数据已生成: {ROOT}")
    print(f"  原片: 20 张")
    print(f"  精修: 17 张 (含1个重复, 1张小图, 缺失16-19序号)")
    print(f"  花絮: 7 张")
    print(f"  视频: 3 个")
    print(f"  选择清单: {list_file}")


if __name__ == "__main__":
    main()
