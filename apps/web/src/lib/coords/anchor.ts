/**
 * 锚点的 TS 实现：p{page}b{block}，两段均 1-based（见 docs/设计/03-数据模型与溯源设计.md）。
 *
 * 前端不分配锚点（由后端在归一化时生成），但要把它原样带回后端（反向标注），
 * 所以解析规则必须与后端逐字一致：前导零、大小写、空白全部拒绝。
 * 否则前端认为合法、后端返回 422，用户点了提交才知道。
 */

// 与后端 domain/anchor.py 的正则逐字对应；两边任何一处放宽，共享向量测试立刻失败
const ANCHOR_RE = /^p([1-9]\d*)b([1-9]\d*)$/;

export interface Anchor {
  readonly pageNo: number;
  readonly blockNo: number;
}

export function parseAnchor(raw: string): Anchor {
  const matched = ANCHOR_RE.exec(raw);
  if (matched === null) {
    throw new Error(`锚点格式非法：${JSON.stringify(raw)}`);
  }
  return { pageNo: Number(matched[1]), blockNo: Number(matched[2]) };
}

export function formatAnchor(anchor: Anchor): string {
  return `p${anchor.pageNo}b${anchor.blockNo}`;
}
