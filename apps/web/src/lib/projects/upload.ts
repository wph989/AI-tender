/**
 * 交件台的逐文件结果映射：把一次上传的汇总返回摊回每一个待上传的文件。
 *
 * 为什么单放一个纯函数：后端一次请求只回一个汇总（added / skipped），而用户看的是自己
 * 挑的那几个文件——哪个入库了、哪个被拒、拒的原因是什么。名字对不上时怎么判定这件事
 * 必须有唯一一份定义，否则组件里迟早写出「找不到就当成功」这种乐观兜底。
 */

import type { UploadResult } from "@/types/projects";

export type UploadOutcomeState = "added" | "skipped" | "unknown";

export interface UploadOutcome {
  state: UploadOutcomeState;
  /** 被拒的原因，逐字来自服务端；只有 skipped 时有值。 */
  reason?: string;
}

/**
 * 判断一个待上传文件在这次返回里是什么下场。
 *
 * ZIP 要特判：压缩包自己不出现在 added 里（入库的是解压出来的成员，名字是成员名），
 * 所以只要有文件入库，就说明这个包解压并入库成功了。
 * 落到 unknown 的只有一种情况：这次请求成功、但这个名字既不在 added 也不在 skipped——
 * 那说明它确实没进库，如实标「未入库」，不要猜成成功。
 */
export function outcomeOf(name: string, result: UploadResult): UploadOutcome {
  const rejected = result.skipped.find((item) => item.name === name);
  if (rejected !== undefined) return { state: "skipped", reason: rejected.reason };
  if (result.added.some((item) => item.display_name === name)) return { state: "added" };
  if (name.toLowerCase().endsWith(".zip") && result.added.length > 0) return { state: "added" };
  return { state: "unknown" };
}
