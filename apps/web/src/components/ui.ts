/**
 * 共用控件层：全站只有这一套输入框 / 按钮 / 分区样式。
 *
 * 为什么收成常量而不是每个组件各写一遍 Tailwind：两套控件样式迟早会分叉——
 * 同一个「保存」按钮在一页能点、在另一页看起来是禁用的，用户会以为是权限问题，
 * 最后怪的是产品。配色或圆角要改，也只改这一处。
 */

/** 输入框 / 文本域。hover 也换边框色：用户鼠标扫过时要知道这里可以输入。 */
export const INPUT_CLASS =
  "rounded-[2px] border border-slate-300 bg-white px-2 py-1.5 text-[14px] text-slate-800 " +
  "placeholder:text-slate-400 hover:border-slate-400 " +
  "focus:border-sky-600 focus:outline-none focus:ring-2 focus:ring-sky-100 " +
  "disabled:bg-slate-50 disabled:text-slate-400";

/** 下拉框 = 输入框外壳 + 自绘箭头（见 globals.css 的 .ui-select），否则会露出系统控件外观。 */
export const SELECT_CLASS = INPUT_CLASS + " ui-select";

/** 次级按钮：白底墨线。一屏里可以有很多个。 */
export const BUTTON_CLASS =
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[2px] border border-slate-300 bg-white " +
  "px-2.5 py-1.5 text-[13px] font-medium text-slate-700 " +
  "hover:border-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 " +
  "disabled:hover:border-slate-300 disabled:hover:bg-white";

/** 无框按钮：只用在行内动作（列表行的「重解析 / 删除」），避免一屏出现几十个方框。 */
export const GHOST_BUTTON_CLASS =
  "whitespace-nowrap rounded-[2px] px-1.5 py-0.5 text-[13px] text-slate-500 hover:bg-slate-100 " +
  "hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40";

/*
 * 主按钮是实心墨色而不是靛蓝：界面整体是灰阶的纸面，最重的一笔天然就是主操作；
 * 一屏里出现三个实心彩色按钮时，用户反而不知道该按哪个。靛蓝（ACCENT）留给
 * 极少数「必须和旁边的墨色按钮区分开」的主操作。
 */
export const PRIMARY_BUTTON_CLASS =
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[2px] bg-slate-900 px-3 py-1.5 " +
  "text-[13px] font-medium text-white hover:bg-slate-700 " +
  "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-slate-900";

/** 靛蓝实心：只在需要和相邻墨色按钮区分时用（例如同一屏里「导出」和「新建」并列）。 */
export const ACCENT_BUTTON_CLASS =
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[2px] bg-sky-600 px-3 py-1.5 " +
  "text-[13px] font-medium text-white hover:bg-sky-700 " +
  "disabled:cursor-not-allowed disabled:opacity-40";

/** 危险按钮：描边式。删除是不可逆的，但也不该全屏最显眼——所以不用实心红。 */
export const DANGER_BUTTON_CLASS =
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[2px] border border-rose-200 bg-white " +
  "px-2.5 py-1.5 text-[13px] font-medium text-rose-600 hover:border-rose-300 hover:bg-rose-50 " +
  "disabled:cursor-not-allowed disabled:opacity-40";

/** 危险动作的行内形态（列表行里的「删除」）。 */
export const DANGER_GHOST_BUTTON_CLASS =
  "whitespace-nowrap rounded-[2px] px-1.5 py-0.5 text-[13px] text-slate-400 hover:bg-rose-50 hover:text-rose-600 " +
  "disabled:cursor-not-allowed disabled:opacity-40";

/** 面板：白纸 + 一条墨线。全站不用阴影分层，靠这条线区分纸面与台面。 */
export const PANEL_CLASS = "border border-slate-200 bg-white";

/** 数据一律等宽：页码、大小、哈希、置信度都是要上下比对的值。 */
export const DATA_CLASS = "font-mono tabular-nums";

/** 小号全大写标签：区块抬头的编号行，只做定位不做装饰。 */
export const EYEBROW_CLASS = "text-[11px] tracking-[0.18em] text-slate-400 uppercase";

/** 分区标题：宋体。它是「这一块是标书里的一章」的视觉暗示。 */
export const SECTION_TITLE_CLASS = "font-serif text-[19px] leading-[28px] text-slate-900";

/**
 * 结果面板的宽度：面板和它的空态共用同一个值。
 * 右栏宽度一变，左边原文的可用宽度就跟着跳，所以这个数字只能有一处定义。
 */
export const RESULT_PANEL_WIDTH = "w-[460px]";

/**
 * 表单行：标签在左、定宽对齐，控件在右撑满。
 *
 * 为什么不用「标签在上」：设置页一屏十几行字段，标签压在上面时每行都要占两行高，
 * 输入框的左边缘还各不相同；标签左对齐定宽之后，眼睛沿着一条竖线往下扫就够了。
 */
export const FORM_ROW_CLASS =
  "grid grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-x-4 gap-y-2";

/** 表单行的标签格：浅一档的灰。它是路牌，不是内容。 */
export const FORM_LABEL_CLASS = "text-[13px] leading-5 text-slate-500";

/**
 * 设置页在超宽屏（≥1536px）的双列网格。
 *
 * 为什么落在 2xl 而不是 lg：这一层是给 1600px 的桌面屏准备的，1400px 的笔记本上
 * 强行分两栏会把表格挤成竖排——那比通栏更难读。
 */
export const SETTINGS_GRID_CLASS = "grid gap-7 2xl:grid-cols-2";
