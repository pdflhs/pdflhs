import argparse
import io
from pathlib import Path

from PIL import Image


def save_png_to_bytes(image, colors=None):
    """将图片保存到内存，方便反复比较压缩后的大小。"""
    output = io.BytesIO()

    # 优先使用调色板压缩，适合截图、收据这类颜色不太复杂的 PNG。
    if colors:
        source = image.convert("RGBA")
        image_to_save = source.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
    else:
        image_to_save = image

    image_to_save.save(output, format="PNG", optimize=True, compress_level=9)
    return output.getvalue()


def compress_one_png(input_path, output_path, max_bytes):
    """压缩单张 PNG，目标是小于 max_bytes。"""
    with Image.open(input_path) as image:
        image.load()

        # 先尝试不同颜色数量的调色板压缩，尽量不改变图片尺寸。
        attempts = []
        for colors in (256, 192, 128, 96, 64, 48, 32, 24, 16):
            data = save_png_to_bytes(image, colors=colors)
            attempts.append((data, image.size, colors))
            if len(data) <= max_bytes:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(data)
                return len(data), image.size, colors, False

        # 如果仅调色板压缩仍超过目标大小，就逐步缩小尺寸。
        width, height = image.size
        resized = image.convert("RGBA")
        scale = 0.92

        while width > 320 and height > 320:
            width = max(1, int(width * scale))
            height = max(1, int(height * scale))
            resized = resized.resize((width, height), Image.Resampling.LANCZOS)

            for colors in (128, 96, 64, 48, 32, 24, 16, 12, 8):
                data = save_png_to_bytes(resized, colors=colors)
                attempts.append((data, resized.size, colors))
                if len(data) <= max_bytes:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(data)
                    return len(data), resized.size, colors, True

        # 极端情况下仍未达标，就保存目前最小的版本，并标记未达标。
        best_data, best_size, best_colors = min(attempts, key=lambda item: len(item[0]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(best_data)
        return len(best_data), best_size, best_colors, True


def build_output_path(input_path, input_root, output_root, overwrite):
    """根据输入目录结构生成输出路径；覆盖模式下直接返回原路径。"""
    if overwrite:
        return input_path
    return output_root / input_path.relative_to(input_root)


def main():
    parser = argparse.ArgumentParser(description="批量压缩 PNG 图片到指定大小以内。")
    parser.add_argument("directory", help="需要压缩 PNG 的目录，例如 screenshots3")
    parser.add_argument("--max-kb", type=int, default=100, help="目标大小，默认 100KB")
    parser.add_argument("--output", help="输出目录；不传则生成 directory_compressed")
    parser.add_argument("--overwrite", action="store_true", help="直接覆盖原图片")
    parser.add_argument("--recursive", action="store_true", help="递归处理子目录")
    args = parser.parse_args()

    input_root = Path(args.directory).resolve()
    if not input_root.exists() or not input_root.is_dir():
        raise SystemExit(f"目录不存在: {input_root}")

    max_bytes = args.max_kb * 1024
    output_root = Path(args.output).resolve() if args.output else input_root.with_name(f"{input_root.name}_compressed")
    pattern = "**/*.png" if args.recursive else "*.png"
    png_files = sorted(input_root.glob(pattern))

    if not png_files:
        raise SystemExit(f"目录中没有 PNG 文件: {input_root}")

    ok_count = 0
    over_count = 0
    total_before = 0
    total_after = 0

    print(f"输入目录: {input_root}")
    print(f"输出目录: {'覆盖原图' if args.overwrite else output_root}")
    print(f"目标大小: {args.max_kb}KB")
    print(f"图片数量: {len(png_files)}")

    for index, input_path in enumerate(png_files, start=1):
        output_path = build_output_path(input_path, input_root, output_root, args.overwrite)
        before_size = input_path.stat().st_size
        after_size, final_dimensions, colors, resized = compress_one_png(input_path, output_path, max_bytes)

        total_before += before_size
        total_after += after_size
        is_ok = after_size <= max_bytes
        ok_count += 1 if is_ok else 0
        over_count += 0 if is_ok else 1

        status = "OK" if is_ok else "超过目标"
        resize_text = "缩小尺寸" if resized else "原尺寸"
        print(
            f"[{index}/{len(png_files)}] {status} {input_path.name} "
            f"{before_size / 1024:.1f}KB -> {after_size / 1024:.1f}KB "
            f"{final_dimensions[0]}x{final_dimensions[1]} {colors}色 {resize_text}"
        )

    print()
    print(f"完成: 达标 {ok_count} 张，未达标 {over_count} 张")
    print(f"总体大小: {total_before / 1024 / 1024:.1f}MB -> {total_after / 1024 / 1024:.1f}MB")


if __name__ == "__main__":
    main()

