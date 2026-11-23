/** 共用控件只维护一套样式，避免项目、分析与设置页面出现不同的操作语义。 */
export const INPUT_CLASS =
  "ui-input rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 " +
  "placeholder:text-slate-400 hover:border-slate-300 focus:border-sky-500 focus:outline-none focus:ring-3 focus:ring-sky-100 " +
  "disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400 transition-colors";
export const SELECT_CLASS = INPUT_CLASS + " ui-select";
const BUTTON_BASE = "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl px-4 py-2.5 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 ";
export const BUTTON_CLASS = BUTTON_BASE + "border border-slate-200 bg-white text-slate-600 hover:border-sky-200 hover:bg-sky-50 hover:text-sky-700";
export const PRIMARY_BUTTON_CLASS = BUTTON_BASE + "border border-transparent bg-sky-600 text-white shadow-sm hover:bg-sky-700";
export const DANGER_BUTTON_CLASS = BUTTON_BASE + "border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100";
export const DATA_CLASS = "font-mono tabular-nums";
export const EYEBROW_CLASS = "text-[11px] font-medium tracking-[0.12em] text-slate-400";
export const FORM_ROW_CLASS = "grid gap-2";
export const FORM_LABEL_CLASS = "text-[13px] font-medium leading-5 text-slate-600";
