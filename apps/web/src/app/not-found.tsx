"use client";

import { Button, Result } from "antd";

export default function NotFound() {
  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="链接可能已失效，请返回项目空间重新选择。"
      extra={
        <Button type="primary" href="/projects">
          返回项目空间
        </Button>
      }
    />
  );
}
