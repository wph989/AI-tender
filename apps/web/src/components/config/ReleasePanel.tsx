"use client";
import { Alert, App, Button, Drawer, Input, Spin, Table } from "antd";

/**
 * 配置版本面板：版本列表 + 详情（diff / 影响清单逐条确认 / 门禁 / 审计）。
 *
 * 门禁的关键是"每条影响单独确认"（设计文档 09 第 7.1 节）：这里不给"全部确认"按钮，
 * 一次点击就能过掉的确认等同于没有确认——门禁事后要能回答"谁看了哪一条"。
 */

import { useState } from "react";

import {
  blockerLabel,
  diffRows,
  impactKindLabel,
  releaseStatusLabel,
} from "@/lib/config/draft";
import { configLabel, configValueLabel } from "@/lib/config/presentation";
import { formatTime } from "@/lib/llm/format";
import type {
  ConfigRelease,
  ConfigReleaseDetail,
  ImpactEntry,
} from "@/types/config";

interface Props {
  error: string | null;
  onRetry: () => void;
  releases: ConfigRelease[];
  detail: ConfigReleaseDetail | null;
  busy: boolean;
  onSelect: (id: number) => void;
  onAcknowledge: (entry: ImpactEntry, comment: string) => Promise<void>;
  onActivate: (force: boolean, reason: string) => Promise<void>;
  onRollback: (reason: string) => Promise<void>;
}

/** 状态的圆点色。为什么不用药丸：一列版本号各顶一个填色胶囊，眼睛会被色块带走，
 *  反而读不到版本号本身；圆点的重量刚好够把六种状态区分开。 */
const STATUS_DOT_CLASS: Record<string, string> = {
  draft: "bg-amber-500",
  active: "bg-emerald-500",
  archived: "bg-slate-400",
  rolled_back: "bg-rose-500",
};

const STATUS_TEXT_CLASS: Record<string, string> = {
  draft: "text-amber-700",
  active: "text-emerald-700",
  archived: "text-slate-500",
  rolled_back: "text-rose-700",
};

export function ReleasePanel({
  error,
  onRetry,
  releases,
  detail,
  busy,
  onSelect,
  onAcknowledge,
  onActivate,
  onRollback,
}: Props) {
  const { modal } = App.useApp();
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState("");

  const isDraft = detail?.status === "draft";
  const softBreaches = detail?.gate.soft_breaches ?? [];
  const rows = detail === null ? [] : diffRows(detail.changed);
  const unacked = detail?.impact.filter((entry) => !entry.acked).length ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="font-display font-semibold text-[19px] leading-[28px] text-slate-900">
          配置版本
        </h2>
        <p className="mt-1 text-[13px] leading-5 text-slate-500">
          查看每次配置变更，或恢复某个历史版本的设置。
        </p>
        <Table<ConfigRelease>
          className="mt-4"
          rowKey="id"
          dataSource={releases}
          size="middle"
          scroll={{ x: 580 }}
          pagination={{
            defaultPageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 个版本`,
          }}
          columns={[
            {
              title: "版本",
              key: "version",
              width: 100,
              render: (_, release) => `v${release.version_no}`,
            },
            {
              title: "状态",
              key: "status",
              width: 100,
              render: (_, release) => releaseStatusLabel(release.status),
            },
            {
              title: "变更说明",
              dataIndex: "note",
              render: (value: string | null) => value || "—",
            },
            {
              title: "创建时间",
              dataIndex: "created_at",
              width: 180,
              render: (value: string) => formatTime(value),
            },
            {
              title: "操作",
              key: "actions",
              width: 120,
              render: (_, release) => (
                <Button
                  size="small"
                  disabled={busy}
                  onClick={() => {
                    setComment("");
                    setReason("");
                    setOpen(true);
                    onSelect(release.id);
                  }}
                >
                  查看详情
                </Button>
              ),
            },
          ]}
        />
      </section>

      <Drawer
        title={detail ? `配置版本 v${detail.version_no}` : "配置版本详情"}
        open={open}
        size={880}
        destroyOnHidden
        mask={{ closable: !busy }}
        keyboard={!busy}
        closable={!busy}
        onClose={() => setOpen(false)}
      >
        {error && (
          <Alert
            className="mb-4"
            type="error"
            showIcon
            title={error}
            action={
              <Button size="small" disabled={busy} onClick={onRetry}>
                重试
              </Button>
            }
          />
        )}
        {busy && !detail && (
          <Spin description="正在读取版本详情">
            <div className="h-32" />
          </Spin>
        )}
        {detail !== null && (
          <section className="ui-panel settings-panel rounded-2xl border border-slate-200 bg-white p-6">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display font-semibold text-[19px] leading-[28px] text-slate-900">
                v{detail.version_no} 详情
              </h2>
              <span
                className={
                  "inline-flex items-center gap-1.5 text-[13px] " +
                  (STATUS_TEXT_CLASS[detail.status] ?? "text-slate-500")
                }
              >
                <span
                  aria-hidden
                  className={
                    "h-1.5 w-1.5 rounded-full " +
                    (STATUS_DOT_CLASS[detail.status] ?? "bg-slate-400")
                  }
                />
                {releaseStatusLabel(detail.status)}
              </span>
              {detail.based_on !== null && (
                <span className="text-[11px] text-slate-400">
                  基于版本 #{detail.based_on}
                </span>
              )}
              {isDraft && unacked > 0 && (
                <span className="text-[11px] text-amber-700">
                  还有 {unacked} 条影响未确认
                </span>
              )}
            </div>

            <h3 className="mt-3 font-display font-semibold text-[14px] text-slate-800">
              与当前生效版本的差异
            </h3>
            {rows.length === 0 ? (
              <p className="mt-1 text-[13px] leading-5 text-slate-500">
                没有差异。
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="mt-1 w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-[13px] text-slate-400">
                      <th className="border-b border-slate-200 py-2">配置项</th>
                      <th className="border-b border-slate-200 py-2">原值</th>
                      <th className="border-b border-slate-200 py-2">新值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.key} className="border-t border-slate-100">
                        <td className="border-b border-slate-100 py-1 pr-2">
                          <span title={row.key}>{configLabel(row.key)}</span>
                        </td>
                        <td className="py-1 pr-2 text-slate-500">
                          {configValueLabel(row.key, row.old)}
                        </td>
                        <td className="py-1 text-slate-800">
                          {configValueLabel(row.key, row.new)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <h3 className="mt-4 font-display font-semibold text-[14px] text-slate-800">
              变更影响清单
            </h3>
            <p className="mt-1 text-[13px] leading-5 text-slate-500">
              发布前请逐条确认变更影响，系统会记录确认人和时间。
            </p>
            <ul className="mt-2 flex flex-col gap-1">
              {detail.impact.map((entry) => (
                <li
                  key={entry.kind + "|" + entry.ref}
                  className="flex flex-wrap items-center gap-2 border border-slate-200 px-2 py-1"
                >
                  <span className="w-24 text-[11px] text-slate-500">
                    {impactKindLabel(entry.kind)}
                  </span>
                  <span className="min-w-0 flex-1 text-[13px]" title={entry.ref}>
                    {configLabel(entry.ref)}
                  </span>
                  {entry.acked ? (
                    <span className="text-[11px] text-emerald-700">已确认</span>
                  ) : (
                    <Button
                      htmlType="button"

                      disabled={busy || !isDraft}
                      onClick={() => void onAcknowledge(entry, comment)}
                    >
                      确认已知悉
                    </Button>
                  )}
                </li>
              ))}
              {detail.impact.length === 0 && (
                <li className="text-[13px] text-slate-500">
                  本次变更没有影响条目。
                </li>
              )}
            </ul>
            {detail.impact.length > 0 && (
              <Input
                className={" mt-2 w-full"}
                aria-label="确认备注"
                placeholder="确认备注（可选）"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
              />
            )}

            <h3 className="mt-4 font-display font-semibold text-[14px] text-slate-800">
              发布前检查
            </h3>
            {detail.gate.passed ? (
              <p className="mt-1 text-[13px] text-emerald-700">
                检查通过，可以发布。
              </p>
            ) : (
              <ul className="mt-1 flex flex-col gap-0.5 text-[13px]">
                {detail.gate.blockers.map((code) => (
                  <li key={code} className="text-rose-700">
                    暂不能发布：{blockerLabel(code)}
                  </li>
                ))}
                {softBreaches.map((code) => (
                  <li key={code} className="text-amber-700">
                    需二次确认：{blockerLabel(code)}
                  </li>
                ))}
              </ul>
            )}

            {isDraft && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Input
                  className={" min-w-0 flex-1"}
                  aria-label="发布理由"
                  placeholder={
                    softBreaches.length > 0
                      ? "强制发布必须填写理由"
                      : "发布理由（可选）"
                  }
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
                <Button
                  type="primary"
                  htmlType="button"

                  disabled={
                    busy ||
                    detail.gate.blockers.length > 0 ||
                    (softBreaches.length > 0 && reason.trim() === "")
                  }
                  onClick={() =>
                    modal.confirm({
                      title: softBreaches.length
                        ? "确认强制发布？"
                        : "确认发布该版本？",
                      content: "生效后，新任务将使用本次配置。",
                      okText: "确认发布",
                      onOk: () => onActivate(softBreaches.length > 0, reason),
                    })
                  }
                >
                  {softBreaches.length > 0 ? "强制发布" : "发布"}
                </Button>
              </div>
            )}

            {detail.status !== "draft" && detail.status !== "active" && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Input
                  className={" min-w-0 flex-1"}
                  aria-label="回滚理由"
                  placeholder="回滚理由（可选）"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
                <Button
                  danger
                  htmlType="button"

                  disabled={busy}
                  onClick={() =>
                    modal.confirm({
                      title: "确认回滚到该版本？",
                      content: "当前生效配置将被这个历史版本替换。",
                      okText: "确认回滚",
                      okButtonProps: { danger: true },
                      onOk: () => onRollback(reason),
                    })
                  }
                >
                  回滚到该版本
                </Button>
              </div>
            )}

            <h3 className="mt-4 font-display font-semibold text-[14px] text-slate-800">
              操作记录
            </h3>
            <ul className="mt-1 flex flex-col gap-0.5 text-[13px] text-slate-600">
              {detail.audit.map((entry) => (
                <li key={entry.id}>
                  {formatTime(entry.created_at)} · {entry.actor} ·{" "}
                  {({ create: "创建版本", acknowledge: "确认影响", activate: "发布版本", force_activate: "强制发布", rollback: "恢复历史版本" } as Record<string, string>)[entry.action] ?? entry.action}
                  {entry.reason !== null && entry.reason !== ""
                    ? " · " + entry.reason
                    : ""}
                </li>
              ))}
              {detail.audit.length === 0 && (
                <li className="text-slate-500">暂无操作记录。</li>
              )}
            </ul>
          </section>
        )}
      </Drawer>
    </div>
  );
}
