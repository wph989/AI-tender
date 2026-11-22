/**
 * 坐标契约的 TS 实现：0–1 归一化、左上原点、视觉方向（见 docs/设计/03-数据模型与溯源设计.md）。
 *
 * 这是全项目唯一允许重复的逻辑：后端 domain/bbox.py 负责落库与裁剪，前端负责画高亮与缩放重算。
 * 两侧共用 packages/contract/coords-vectors.json 的向量，任何一侧改了规则，另一侧测试立刻变红。
 *
 * 前端用 number 而非十进制库：这里只做乘法与比较，精度需求远低于落库
 * （后端用 Decimal 是因为 NUMERIC(7,6) 要参与相等比较，见 docs/工程/10-技术选型与工程结构.md）。
 */

export type Bbox = readonly [number, number, number, number];

export interface Size {
  readonly width: number;
  readonly height: number;
}

export interface Rect {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

/** 0 <= x0 < x1 <= 1 且 0 <= y0 < y1 <= 1。零面积盒画不出高亮，同样判为无效。 */
export function isValidBbox(bbox: Bbox): boolean {
  const [x0, y0, x1, y1] = bbox;
  return 0 <= x0 && x0 < x1 && x1 <= 1 && 0 <= y0 && y0 < y1 && y1 <= 1;
}

/**
 * 归一化 bbox → 视口像素矩形。
 * 只有乘法、没有坐标系转换——这正是归一化契约换来的红利（见 docs/设计/03-数据模型与溯源设计.md）。
 */
export function bboxToRect(bbox: Bbox, viewport: Size): Rect {
  const [x0, y0, x1, y1] = bbox;
  return {
    left: x0 * viewport.width,
    top: y0 * viewport.height,
    width: (x1 - x0) * viewport.width,
    height: (y1 - y0) * viewport.height,
  };
}

/** 合并两个区域：多条证据或一次裁剪要覆盖多个块时用。 */
export function unionBbox(a: Bbox, b: Bbox): Bbox {
  return [
    Math.min(a[0], b[0]),
    Math.min(a[1], b[1]),
    Math.max(a[2], b[2]),
    Math.max(a[3], b[3]),
  ];
}
