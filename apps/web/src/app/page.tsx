import { redirect } from "next/navigation";

/**
 * 根路由跳到项目列表。
 *
 * 为什么不用 next.config 的 redirects：那条规则在构建期定型，
 * 而这里以后可能要按登录态分流（未登录去登录页），放代码里改起来不用重新构建配置。
 */
export default function Page() {
  redirect("/projects");
}