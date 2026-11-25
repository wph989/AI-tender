/** HTTP JSON 错误协议只在这里解析，业务客户端保留各自的请求路径和方法。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function apiErrorFromBody(body: unknown, status: number, fallback: string): Error {
  if (typeof body === "object" && body !== null && "error" in body) {
    const problem = body.error;
    if (
      typeof problem === "object" && problem !== null && "message" in problem &&
      typeof problem.message === "string"
    ) return new ApiError(problem.message, status);
  }
  return new ApiError(fallback + " 返回 " + status, status);
}

async function responseError(response: Response, fallback: string | ((status: number) => string)) {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // 非 JSON 错误页仍保留 HTTP 状态，供调用方定位网关或代理故障。
  }
  const message = typeof fallback === "string" ? fallback : fallback(response.status);
  return apiErrorFromBody(payload, response.status, message);
}

export async function requestJson<T>(
  url: string,
  init?: RequestInit,
  fallback: string | ((status: number) => string) = "请求失败",
): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw await responseError(response, fallback);
  return (await response.json()) as T;
}

export function sendJson<T>(
  url: string,
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  body?: unknown,
  fallback = "操作失败：" + url,
): Promise<T> {
  const init: RequestInit = body === undefined
    ? { method }
    : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  return requestJson<T>(url, init, fallback);
}

export async function requestNoContent(url: string, init: RequestInit, fallback: string) {
  const response = await fetch(url, init);
  if (!response.ok) throw await responseError(response, fallback);
}
