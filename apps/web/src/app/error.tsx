"use client";

import { Button, Result } from "antd";

/** 页面异常提供就地重试，避免用户只能面对空白页。 */
export default function ErrorPage({
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <Result
      status="error"
      title="页面暂时无法显示"
      subTitle="请重试加载；若仍失败，可返回项目空间。"
      extra={[
        <Button key="retry" type="primary" onClick={reset}>
          重新加载
        </Button>,
        <Button key="projects" href="/projects">
          返回项目空间
        </Button>,
      ]}
    />
  );
}
