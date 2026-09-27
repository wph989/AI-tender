/**
 * 校验合成样本的坐标契约。
 *
 * 跑法（apps/web 下）：pnpm verify:sample
 *
 * 为什么要单独校一次：样本里的 bbox 是生成器「按自己理解的页面坐标系」算出来的，
 * 而渲染出来对不对只有渲染器说了算。第 4 页是 /Rotate 90 的横版扫描件形状——
 * 生成器一旦把「视觉尺寸」当成「未旋转尺寸」写进 width_pt/height_pt，就会出现
 * **渲染出来是横版、契约算出来是竖版**的双重自洽：单测（前后端共享向量）全绿，
 * 高亮却整体落在错误位置。这类 bug 只能靠「拿真实渲染器的读数和契约对账」发现。
 *
 * 校验三件事：
 *   1. 页面几何：JSON 的 width_pt/height_pt/rotation 换算出的视觉尺寸 == pdf.js 的视口尺寸；
 *   2. 块坐标：JSON 的 bbox 必须框住该块文本的真实基线（起点与终点都落在框内），
 *      且框的面积不能比「文字长度 × 字高」大出太多（防止「位置大致对但尺度离谱」）；
 *   3. 证据锚点必须指向真实存在的块。
 *
 * 注意文本层是**按 run 拼行**后再比对的：内嵌 TTF 子集时，reportlab 会把一行拆成多个
 * 文本 item（子集切换处断开），拿单 item 去比对会误报「找不到该块」。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const { getDocument, Util } = await import("pdfjs-dist/legacy/build/pdf.mjs");

const here = fileURLToPath(new URL(".", import.meta.url));
const samplesDir = join(here, "..", "public", "samples");
const pdfjsDir = join(here, "..", "node_modules", "pdfjs-dist");

const documentJson = JSON.parse(readFileSync(join(samplesDir, "sample-document.json"), "utf8"));
const extractions = JSON.parse(readFileSync(join(samplesDir, "sample-extractions.json"), "utf8"));

const failures = [];
const EPS_SIZE = 0.5; // pt
const EPS_CONTAIN = 1.5; // pt：允许基线端点贴边（bbox 来自生成器的字高估算，不是字形级精确）
const MAX_AREA_RATIO = 3.0;

function visualSize(page) {
  return page.rotation === 90 || page.rotation === 270
    ? { width: page.height_pt, height: page.width_pt }
    : { width: page.width_pt, height: page.height_pt };
}

/** 单个 item 的基线起止点（PDF 用户空间）。注意 transform 里折进了字号，推进前要先归一化方向。 */
function itemGeometry(item) {
  const [a, b] = item.transform;
  const unit = Math.hypot(a, b) || 1;
  const start = [item.transform[4], item.transform[5]];
  const end = [start[0] + (a / unit) * item.width, start[1] + (b / unit) * item.width];
  return { start, end, height: item.height };
}

/**
 * 在文本层里找「拼起来正好等于该块文字」的连续 item 区间。
 *
 * 为什么不能按行合并后整体比对：一页上同一条基线上可能并排放着多个独立绘制的块
 * （表格的三个单元格就是），并成一行会把别人的文字拼进来；
 * 而同一块又可能被拆成多个 item（内嵌 TTF 子集在子集切换处断行）。
 * 「连续窗口拼接 == 块文字」同时解决这两件事。
 */
function findBlockRun(items, text) {
  const target = text.trim();
  for (let start = 0; start < items.length; start += 1) {
    if (typeof items[start].str !== "string" || items[start].str.trim() === "") continue;
    let joined = "";
    for (let index = start; index < items.length; index += 1) {
      const candidate = items[index];
      if (typeof candidate.str !== "string") continue;
      if (joined !== "" && candidate.str === "") continue; // 跳过空 item
      joined += candidate.str;
      const trimmed = joined.trim();
      if (trimmed === target) {
        return { first: items[start], last: candidate };
      }
      if (trimmed.length >= target.length) break; // 已经比目标长还没匹配上，换下一个起点
    }
  }
  return null;
}

const pdf = await getDocument({
  url: join(samplesDir, "sample-tender.pdf"),
  cMapUrl: `${join(pdfjsDir, "cmaps")}/`,
  standardFontDataUrl: `${join(pdfjsDir, "standard_fonts")}/`,
}).promise;

for (const pageMeta of documentJson.pages) {
  const page = await pdf.getPage(pageMeta.page_no);
  const viewport = page.getViewport({ scale: 1, rotation: page.rotate });
  const declared = visualSize(pageMeta);

  const sizeOk =
    Math.abs(viewport.width - declared.width) <= EPS_SIZE &&
    Math.abs(viewport.height - declared.height) <= EPS_SIZE;
  if (!sizeOk) {
    failures.push(
      `p${pageMeta.page_no} 页面几何不一致：契约视觉尺寸 ${declared.width.toFixed(2)}×${declared.height.toFixed(2)}，` +
        `pdf.js ${viewport.width.toFixed(2)}×${viewport.height.toFixed(2)}（rotate=${page.rotate}）`,
    );
  }

  const blocks = documentJson.blocks_by_page[String(pageMeta.page_no)] ?? [];
  if (blocks.length === 0) continue;

  const content = await page.getTextContent();
  const items = content.items.filter((item) => typeof item.str === "string");

  for (const block of blocks) {
    const run = findBlockRun(items, block.text);
    if (run === null) {
      failures.push(`p${pageMeta.page_no} ${block.anchor}：文本层里找不到「${block.text.slice(0, 16)}…」`);
      continue;
    }
    const geometry = itemGeometry(run.first);
    // 基线端点 → 视觉方向（左上原点、pt）；Util.applyTransform 是就地修改，别写成函数式返回
    const startPoint = [...geometry.start];
    const endPoint = [...itemGeometry(run.last).end];
    Util.applyTransform(startPoint, viewport.transform);
    Util.applyTransform(endPoint, viewport.transform);

    const [x0, y0, x1, y1] = block.bbox;
    const box = {
      left: x0 * viewport.width,
      top: y0 * viewport.height,
      right: x1 * viewport.width,
      bottom: y1 * viewport.height,
    };
    const inside = (point) =>
      point[0] >= box.left - EPS_CONTAIN &&
      point[0] <= box.right + EPS_CONTAIN &&
      point[1] >= box.top - EPS_CONTAIN &&
      point[1] <= box.bottom + EPS_CONTAIN;
    if (!inside(startPoint) || !inside(endPoint)) {
      failures.push(
        `p${pageMeta.page_no} ${block.anchor}：bbox 没框住文字基线（框 ${[
          box.left,
          box.top,
          box.right,
          box.bottom,
        ]
          .map((v) => v.toFixed(1))
          .join(",")}，基线 ${startPoint[0].toFixed(1)},${startPoint[1].toFixed(1)} → ${endPoint[0].toFixed(1)},${endPoint[1].toFixed(1)}）`,
      );
      continue;
    }

    const baseline = Math.hypot(endPoint[0] - startPoint[0], endPoint[1] - startPoint[1]);
    const boxArea = (box.right - box.left) * (box.bottom - box.top);
    const textArea = Math.max(1, baseline * Math.max(1, geometry.height));
    const ratio = boxArea / textArea;
    if (ratio > MAX_AREA_RATIO) {
      failures.push(
        `p${pageMeta.page_no} ${block.anchor}：bbox 面积是文字面积的 ${ratio.toFixed(1)} 倍，怀疑尺度不对`,
      );
    }
  }
}

// 证据必须指向真实存在的块（假装数据也不能指向空气）
const anchors = new Set(
  Object.values(documentJson.blocks_by_page)
    .flat()
    .map((block) => block.anchor),
);
for (const item of extractions.items) {
  for (const evidence of item.evidence) {
    if (!anchors.has(evidence.anchor)) {
      failures.push(`抽取结果 ${item.field_key} 的证据指向不存在的块：${evidence.anchor}`);
    }
  }
}

await pdf.loadingTask.destroy();

if (failures.length > 0) {
  console.error(`样本坐标校验失败 ${failures.length} 项：`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(
  `样本坐标校验通过：${documentJson.pages.length} 页页面几何与全部块坐标均与渲染结果一致`,
);