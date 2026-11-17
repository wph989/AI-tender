"use client";

import { Table, type TableProps } from "antd";
import { paginationDefaults } from "@/components/DataPagination";

/** 管理清单共用密度与横向滚动边界；窄屏保留表头和字段关系，不挤压整页。 */
export function DataTable<T extends object>({ className, pagination, ...props }: TableProps<T>) {
  return <Table<T> size="middle" className={["management-table", className].filter(Boolean).join(" ")}
    scroll={{ x: 780 }} {...props} pagination={pagination === false ? false : {
      ...pagination, ...paginationDefaults,
    }} />;
}
