"use client";

import { Pagination, type PaginationProps } from "antd";

/** 卡片与表格共用分页文案、对齐和交互，避免切换视图后控件跳位。 */
export const paginationDefaults: PaginationProps = {
  size: "middle", align: "end", showSizeChanger: false, hideOnSinglePage: true,
  showTotal: (total, range) => `第 ${range[0]}–${range[1]} 项，共 ${total} 项`,
};

export function DataPagination(props: PaginationProps) {
  return <Pagination {...props} {...paginationDefaults} className="management-pagination" />;
}
