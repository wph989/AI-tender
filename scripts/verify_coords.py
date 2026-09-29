"""对照 MiddleJson bbox 与 PDF 页面，输出原点和旋转候选调试图。"""

from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium


def _bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if any(not isinstance(item, (int, float)) or isinstance(item, bool) for item in value):
        return None
    x0, y0, x1, y1 = (float(item) for item in value)
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        return None
    return x0, y0, x1, y1


def _block_with_bbox(page: object) -> tuple[dict[str, Any], tuple[float, float, float, float]]:
    blocks = page.get("blocks") if isinstance(page, dict) else None
    if not isinstance(blocks, list):
        raise ValueError("所选 MiddleJson 页面没有 blocks 数组")
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bbox = _bbox(block.get("bbox"))
        if bbox is not None:
            return block, bbox
    raise ValueError("所选页面没有有效 bbox 的块")


# 用标准库处理 PNG，避免为一次性坐标检查增加生产图像依赖。
def _bitmap_rgb(bitmap: Any) -> bytearray:
    mode = bitmap.mode
    channels = bitmap.n_channels
    source = bytes(bitmap.buffer)
    pixels = bytearray(bitmap.width * bitmap.height * 3)
    for y in range(bitmap.height):
        source_row = y * bitmap.stride
        target_row = y * bitmap.width * 3
        for x in range(bitmap.width):
            source_index = source_row + x * channels
            target_index = target_row + x * 3
            if mode == "L":
                gray = source[source_index]
                pixels[target_index : target_index + 3] = bytes((gray, gray, gray))
            elif mode.startswith("BGR"):
                pixels[target_index : target_index + 3] = bytes(
                    (source[source_index + 2], source[source_index + 1], source[source_index])
                )
            elif mode.startswith("RGB"):
                pixels[target_index : target_index + 3] = source[source_index : source_index + 3]
            else:
                raise ValueError(f"不支持的 PDFium bitmap 格式：{mode}")
    return pixels


def _draw_outline(
    pixels: bytearray,
    width: int,
    height: int,
    bbox: tuple[float, float, float, float],
    color: tuple[int, int, int],
) -> None:
    x0, y0, x1, y1 = bbox
    left = max(0, min(width - 1, round(x0 * width)))
    top = max(0, min(height - 1, round(y0 * height)))
    right = max(left + 1, min(width, round(x1 * width)))
    bottom = max(top + 1, min(height, round(y1 * height)))

    def paint(x: int, y: int) -> None:
        offset = (y * width + x) * 3
        pixels[offset : offset + 3] = bytes(color)

    thickness = max(2, round(min(width, height) / 300))
    for inset in range(thickness):
        upper = min(bottom - 1, top + inset)
        lower = max(top, bottom - 1 - inset)
        left_edge = min(right - 1, left + inset)
        right_edge = max(left, right - 1 - inset)
        for x in range(left, right):
            paint(x, upper)
            paint(x, lower)
        for y in range(top, bottom):
            paint(left_edge, y)
            paint(right_edge, y)


def _rotate_bbox(
    bbox: tuple[float, float, float, float], rotation: int
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    if rotation == 90:
        return 1 - y1, x0, 1 - y0, x1
    if rotation == 180:
        return 1 - x1, 1 - y1, 1 - x0, 1 - y0
    if rotation == 270:
        return y0, 1 - x1, y1, 1 - x0
    return bbox


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    content = kind + data
    return struct.pack(">I", len(data)) + content + struct.pack(">I", zlib.crc32(content))


def _write_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    scanlines = bytearray()
    stride = width * 3
    for y in range(height):
        scanlines.append(0)
        scanlines.extend(pixels[y * stride : (y + 1) * stride])
    image = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes(scanlines)))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(image)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="MinerU 解析时使用的 PDF 基座")
    parser.add_argument("middle_json", type=Path, help="MinerU 导出的 MiddleJson 2.0")
    parser.add_argument("--page", type=int, default=1, help="要对照的 1-based 页面，默认 1")
    parser.add_argument("--scale", type=float, default=2.0, help="调试图缩放比例，默认 2")
    parser.add_argument("--output-dir", type=Path, default=Path("coord-check"))
    args = parser.parse_args()
    if args.page < 1 or args.scale <= 0:
        parser.error("--page 必须大于 0，--scale 必须大于 0")

    middle = json.loads(args.middle_json.read_text(encoding="utf-8"))
    pages = middle.get("pages") if isinstance(middle, dict) else None
    if not isinstance(pages, list) or args.page > len(pages):
        raise ValueError("MiddleJson 不含所选页面")
    block, bbox = _block_with_bbox(pages[args.page - 1])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with pdfium.PdfDocument(str(args.pdf)) as document:
        if args.page > len(document):
            raise ValueError("PDF 页数少于所选页面")
        page = document[args.page - 1]
        try:
            rotation = int(page.get_rotation())
            bitmap = page.render(scale=args.scale, rotation=rotation)
            try:
                base = _bitmap_rgb(bitmap)
                width, height = bitmap.width, bitmap.height
                flipped_bbox = (bbox[0], 1 - bbox[3], bbox[2], 1 - bbox[1])
                candidates = [
                    ("top-left-visual", bbox, (0, 180, 70)),
                    ("bottom-left-visual", flipped_bbox, (220, 35, 35)),
                ]
                if rotation:
                    candidates.extend(
                        [
                            ("top-left-unrotated", _rotate_bbox(bbox, rotation), (35, 95, 220)),
                            (
                                "bottom-left-unrotated",
                                _rotate_bbox(flipped_bbox, rotation),
                                (180, 45, 185),
                            ),
                        ]
                    )
                outputs = []
                for label, candidate_bbox, color in candidates:
                    pixels = bytearray(base)
                    _draw_outline(pixels, width, height, candidate_bbox, color)
                    output_path = args.output_dir / f"page-{args.page:03d}-{label}.png"
                    _write_png(output_path, width, height, pixels)
                    outputs.append((label, output_path))
            finally:
                bitmap.close()
        finally:
            page.close()

    print(f"page={args.page} rotation={rotation} bbox={list(bbox)} type={block.get('type')!r}")
    for label, output_path in outputs:
        print(f"{label}: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
