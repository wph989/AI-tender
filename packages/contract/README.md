# packages/contract

跨语言契约的共享事实源。当前只有一个文件：`coords-vectors.json`。

## 为什么需要它

`apps/api/src/tender/domain/bbox.py` 与 `apps/web/src/lib/coords/bbox.ts` 是同一套坐标规则的两份实现——
后端要算（落库、裁剪、校验），前端也要算（画高亮、缩放重算）。这是全项目唯一允许重复的逻辑。

重复必然漂移，所以把测试向量抽出来当共享事实源：任何一侧改了规则而没同步向量，另一侧的测试立刻变红。

## 向量分组与消费方

| 分组 | 内容 | 后端 | 前端 |
| --- | --- | --- | --- |
| `anchor.valid` / `anchor.invalid` | 锚点解析（`p{page}b{block}`） | ✅ | ✅ |
| `bbox.validity` | `0 <= x0 < x1 <= 1` 的有效性判定 | ✅ | ✅ |
| `bbox.rect` | 归一化 bbox → 视口像素矩形 | — | ✅ |
| `bbox.pixels` | 归一化 bbox ↔ 像素盒（换算本身不取整） | ✅ | — |
| `bbox.union` | 多块合并 | ✅ | ✅ |
| `rotation[].viewport` | 视觉方向的页面尺寸（90/270 宽高互换） | ✅ | ✅ |
| `rotation[].visual` | 页面方向 → 视觉方向的 bbox 换算 | ✅ | — |

前端不做 `rotation[].visual`：解析适配器输出的 bbox 已经是视觉方向，前端只需按视口做乘法。

消费端：
- 后端 `apps/api/tests/contract/test_coords_vectors.py`
- 前端 `apps/web/src/lib/coords/__tests__/vectors.test.ts`

## 写向量的两条规矩

1. **所有十进制量写成字符串**（`"0.1"` 而不是 `0.1`）。后端用 `Decimal` 精确比较，前端 `number` 是 float64；
   写成 JSON number 会让两侧对「相等」的理解不一致，测试红得莫名其妙。
2. **向量是契约，不是实现快照**。改向量前先问「是契约变了，还是实现错了」——
   契约变更必须同时改两侧实现、本文件，以及 `docs/设计/03-数据模型与溯源设计.md` 第 3 节。
