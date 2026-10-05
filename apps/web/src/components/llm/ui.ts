/** 模型管理面板的样式入口：常量已挪到 components/ui.ts，这里只是转发，避免三处面板改 import。 */

import { SELECT_CLASS as BASE_SELECT_CLASS } from "@/components/ui";

// 模型名可能很长，窄屏下选择框必须收缩到面板内，不能被容器静默裁掉。
export const SELECT_CLASS = BASE_SELECT_CLASS + " max-w-full min-w-0";

export {
  BUTTON_CLASS,
  DANGER_BUTTON_CLASS,
  FORM_LABEL_CLASS,
  FORM_ROW_CLASS,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
} from "@/components/ui";
