/**
 * 功能绑定的优先级整表重排（设计文档 12 第 3 节）。
 *
 * 优先级不是可独立编辑的数字，而是「数组位置」：接口只收有序的 model_ids，
 * 服务端按位置写 1..N。页面上「设为 N 级、其余自动降级」因此必须在这里
 * 算出一个新数组再整表提交，单独改某一行的数字会造出空洞与同级。
 */

/** 与后端 api/llm_registry.MAX_BINDINGS 一致；超过这个数量后端直接拒绝。 */
export const MAX_BINDINGS = 10;

/**
 * 把 modelId 移到第 target 级，其余模型保持原相对顺序。
 *
 * 越界时夹到 `1..剩余数量+1`（等价于原数组的 1..N），不保留空洞：
 * 空洞级别没有可解释语义。target 非有限数时按原位处理，避免把 NaN 传进数组。
 */
export function moveToPriority(modelIds: readonly number[], modelId: number, target: number): number[] {
  const current = modelIds.indexOf(modelId);
  // 找不到说明页面草稿与后端数据已经不一致，保持原样比静默插入一个模型安全。
  if (current < 0) return [...modelIds];
  const rest = modelIds.filter((id) => id !== modelId);
  const wanted = Number.isFinite(target) ? Math.trunc(target) : current + 1;
  const clamped = Math.min(Math.max(wanted, 1), rest.length + 1);
  rest.splice(clamped - 1, 0, modelId);
  return rest;
}