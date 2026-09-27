/**
 * 共享坐标向量的消费端（前端）。
 *
 * 后端 apps/api/tests/contract/test_coords_vectors.py 消费同一个文件。
 * 前端断言一律走 toBeCloseTo：float64 没有十进制类型，0.1 * 800 不等于精确的 80，
 * 而后端用 Decimal 是精确比较——差异来自语言，不是契约不一致。
 */
import { describe, expect, it } from 'vitest';

import rawVectors from '../../../../../../packages/contract/coords-vectors.json';

import { formatAnchor, parseAnchor } from '../anchor';
import { bboxToRect, isValidBbox, unionBbox, type Bbox } from '../bbox';
import { viewportSize, type PageGeometry } from '../page';

const EPSILON_DIGITS = 9;

interface Vectors {
  readonly anchor: {
    readonly valid: { readonly text: string; readonly pageNo: number; readonly blockNo: number }[];
    readonly invalid: readonly string[];
  };
  readonly bbox: {
    readonly validity: { readonly bbox: readonly string[]; readonly valid: boolean }[];
    readonly rect: {
      readonly bbox: readonly string[];
      readonly viewport: { readonly width: number; readonly height: number };
      readonly rect: {
        readonly left: string;
        readonly top: string;
        readonly width: string;
        readonly height: string;
      };
    }[];
    readonly union: { readonly a: readonly string[]; readonly b: readonly string[]; readonly expected: readonly string[] }[];
  };
  readonly rotation: {
    readonly label: string;
    readonly rotation: number;
    readonly widthPt: string;
    readonly heightPt: string;
    readonly viewport: { readonly width: string; readonly height: string };
  }[];
}

const vectors: Vectors = rawVectors;

function toBbox(values: readonly string[]): Bbox {
  return [Number(values[0]), Number(values[1]), Number(values[2]), Number(values[3])];
}

describe('anchor 向量', () => {
  it('接受规范形式，且解析与格式化往返一致', () => {
    for (const item of vectors.anchor.valid) {
      const anchor = parseAnchor(item.text);
      expect(anchor.pageNo).toBe(item.pageNo);
      expect(anchor.blockNo).toBe(item.blockNo);
      expect(formatAnchor(anchor)).toBe(item.text);
    }
  });

  it('拒绝所有非规范形式（前导零、大小写、空白同样拒绝）', () => {
    for (const raw of vectors.anchor.invalid) {
      expect(() => parseAnchor(raw)).toThrow();
    }
  });
});

describe('bbox 向量', () => {
  it('有效性判定与后端一致', () => {
    for (const item of vectors.bbox.validity) {
      expect(isValidBbox(toBbox(item.bbox))).toBe(item.valid);
    }
  });

  it('归一化 bbox → 视口矩形', () => {
    for (const item of vectors.bbox.rect) {
      const rect = bboxToRect(toBbox(item.bbox), item.viewport);
      expect(rect.left).toBeCloseTo(Number(item.rect.left), EPSILON_DIGITS);
      expect(rect.top).toBeCloseTo(Number(item.rect.top), EPSILON_DIGITS);
      expect(rect.width).toBeCloseTo(Number(item.rect.width), EPSILON_DIGITS);
      expect(rect.height).toBeCloseTo(Number(item.rect.height), EPSILON_DIGITS);
    }
  });

  it('合并区域', () => {
    for (const item of vectors.bbox.union) {
      const merged = unionBbox(toBbox(item.a), toBbox(item.b));
      item.expected.forEach((value, index) => {
        expect(merged[index]).toBeCloseTo(Number(value), EPSILON_DIGITS);
      });
    }
  });
});

describe('rotation 向量', () => {
  it('视觉方向尺寸与后端一致（占位高度与裁剪共用这一个换算）', () => {
    for (const item of vectors.rotation) {
      const page: PageGeometry = {
        pageNo: 1,
        widthPt: Number(item.widthPt),
        heightPt: Number(item.heightPt),
        rotation: item.rotation,
      };
      const size = viewportSize(page);
      expect(size.width).toBeCloseTo(Number(item.viewport.width), EPSILON_DIGITS);
      expect(size.height).toBeCloseTo(Number(item.viewport.height), EPSILON_DIGITS);
    }
  });
});
