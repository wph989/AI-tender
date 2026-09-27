/**
 * 把 pdfjs-dist 的运行时资源复制到 public/pdfjs/。
 *
 * 为什么不直接用 `new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url)`：
 * 那条路依赖打包器对 `new URL(..., import.meta.url)` 的支持，换打包器（webpack ↔ Turbopack）
 * 就得重新验证一次；而 worker、cMaps 本来就是**运行时才取**的静态资源，
 * 放进 public/ 用固定 URL 取，行为与打包器无关。
 *
 * cMaps 不是可选项：样本与真实标书里的中文用的是 CID 字体，
 * 缺了 cMaps 中文会整页不显示（见 scripts/make_sample_pdf.py 的说明）。
 *
 * 本脚本由 dev / build 前置执行，产物在 public/pdfjs/，不进版本库。
 */
import { cp, mkdir, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const from = join(here, "..", "node_modules", "pdfjs-dist");
const to = join(here, "..", "public", "pdfjs");

const files = ["legacy/build/pdf.worker.min.mjs"];
const dirs = ["cmaps", "standard_fonts", "wasm", "iccs"];

await mkdir(to, { recursive: true });
for (const file of files) {
  await cp(join(from, file), join(to, file.split("/").pop()));
}
for (const dir of dirs) {
  // 目录不存在时直接跳过：pdfjs 的小版本之间这几个目录增删过，不该因此让 dev/build 挂掉
  try {
    await stat(join(from, dir));
  } catch {
    console.warn(`pdfjs-dist 里没有 ${dir}，跳过`);
    continue;
  }
  await cp(join(from, dir), join(to, dir), { recursive: true });
}
console.log(`pdfjs 资源已就位：public/pdfjs/（worker + ${dirs.join(" / ")}）`);