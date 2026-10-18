"""生成合成样本：一份小体量「招标文件」PDF，外加配套的页面几何与原文坐标。

为什么要合成样本：真实标书是敏感资产，不能进版本库（见 docs/工程/07 第 3 节）。
为什么样本必须包含旋转页：定位闭环是全项目唯一无法靠单测证明的部分，
而 90 度旋转页是「高亮横过来」这类事故的唯一复现路径（见 docs/设计/03 第 3.4 节）。

旋转页按真实扫描件的形态造：**页面本身仍是竖版 A4（595.276 × 841.89），内容在页面坐标系里
逆时针转 90° 书写，再给页对象写 /Rotate 90**，于是显示出来是横版、文字正向。
这正是扫描仪横着进纸时的产物，也是「读 /Rotate 并在适配器里转坐标」这条规则的由来。

这里有一条必须钉死的契约：**width_pt / height_pt 记的是「未旋转」的页面尺寸，视觉尺寸由
rotation 换算得到**（见 docs/设计/03 第 3.3/3.4 节）。曾经踩过的坑：把「视觉尺寸」直接写进
width_pt / height_pt，再带 rotation=90，等于旋转被算了两遍——PDF 渲染出来是横版，
契约算出来是竖版，前端一致性断言立刻报警，页面右上角还会顶出「渲染基座与解析基座不一致」。

中文字体：从本机已安装的字体里挑一个（优先开源字体），把**用到的字形子集内嵌**进 PDF。

- 为什么不用 reportlab 自带的 CID 字体 STSong-Light：它是不内嵌的，而 pdf.js **没有**
  「未内嵌中文字体」的替换表（源码里连 SimSun/微软雅黑这类名字都没有），渲染结果整页豆腐块——
  实测确认过，不是配置问题。cMaps 只能解决「CID → Unicode」，解决不了「谁来画字形」。
- 为什么可以内嵌：真实标书由 Word/WPS 导出时给的就是内嵌子集 PDF，内嵌反而更接近生产形态。
- 为什么字体文件本身不进版本库：生成器只读本机已安装的字体，产物里只有子集字形；
  想换字体用 `--font` 指定（建议开源字体，如 Noto Sans SC）。

同时生成 PDF 与坐标元数据，保证文字定位可核验：
    sample-tender.pdf        样本 PDF 本体
    sample-document.json     页面几何 + 块（锚点 / 视觉方向 bbox / 原文）

跑法（仓库根目录）：
    uv run --project apps/api python scripts/make_sample_pdf.py
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from tender.domain.documents.bbox import Bbox
from tender.domain.documents.page import PageGeometry

PAGE_W, PAGE_H = 595.276, 841.89  # A4 竖版，pt
MARGIN = 56.0
REPO_ROOT = Path(__file__).resolve().parents[1]

# 候选字体（按优先级）：优先开源许可，其次系统自带。TTC 用 subfontIndex 取第一个子字体。
FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf"),  # OFL-1.1
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\Deng.ttf"),
    Path(r"/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf"),
    Path(r"/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
)


def resolve_font(explicit: Path | None) -> tuple[str, Path, int]:
    """→（注册名, 字体文件, 子字体序号）。找不到就报错退出，不静默产出豆腐块样本。"""
    if explicit is not None:
        if not explicit.is_file():
            raise SystemExit(f"指定的字体不存在：{explicit}")
        return explicit.stem, explicit, 0
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return candidate.stem, candidate, 0
    raise SystemExit(
        "找不到可用的中文字体。请用 --font 指定一个 .ttf/.ttc（建议开源中文字体，如 Noto Sans SC）。"
    )

# 行内文字的高度估算：只用来说明「这段话占哪一块」，不追求字形级精确。
# 真实落库的 bbox 由 MinerU 给；这里是造样本，宁可略宽松也不要把字切掉。
ASCENT_RATIO, DESCENT_RATIO = 0.86, 0.24

INK = "#1a1a1a"


@dataclass
class Drawn:
    """一个已绘制的块。

    rect 用**页面坐标系**（左下原点，pt）记录，最后统一归一化并转成视觉方向；
    这样横排文字与旋转页上的竖排文字可以用同一套记录方式。
    """

    page_no: int
    block_no: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def anchor(self) -> str:
        return f"p{self.page_no}b{self.block_no}"

    def page_bbox(self, page_w: float, page_h: float) -> Bbox:
        """→ 归一化 + 左上原点 + 未旋转的页面方向（再由 to_visual 转到视觉方向）。"""
        return Bbox.from_raw(
            [self.x0 / page_w, 1 - self.y1 / page_h, self.x1 / page_w, 1 - self.y0 / page_h]
        )


class Sample:
    def __init__(self, out_dir: Path, font_name: str) -> None:
        self.out_dir = out_dir
        self.font_name = font_name
        self.c = canvas.Canvas(str(out_dir / "sample-tender.pdf"), pagesize=(PAGE_W, PAGE_H))
        self.blocks: list[Drawn] = []
        self.pages: list[dict[str, object]] = []
        self.page_no = 0
        self.block_no = 0

    # ---- 绘制原语 -------------------------------------------------------

    def new_page(self, rotation: int = 0, landscape: bool = False) -> None:
        """开一页。landscape=True 表示「扫描件横版」：**MediaBox 仍是竖版 A4，靠 /Rotate 90 让显示呈横版**。

        为什么 setPageSize 这里看着是反着写的：reportlab 在写 MediaBox 时，
        只要 Rotate 是 90/270 就会再交换一次 pagewidth/pageheight（pdfbase/pdfdoc.py）。
        所以要得到「竖版 MediaBox + /Rotate 90」，setPageSize 必须传横版尺寸。
        真实扫描件正是这个样子：进纸方向与页面方向不一致，靠 /Rotate 纠正显示方向。

        落库的 width_pt / height_pt 一律记**未旋转的 MediaBox**（见 docs/设计/03 第 3.3/3.4 节），
        视觉尺寸由 rotation 换算；把视觉尺寸记进来等于旋转算两遍，前端一致性断言立刻会报。
        """
        if self.page_no:
            self.c.showPage()
        self.page_no += 1
        self.block_no = 0
        if landscape:
            rotation = 90
        self.c.setPageSize((PAGE_H, PAGE_W) if rotation in (90, 270) else (PAGE_W, PAGE_H))
        # /Rotate 写在页对象上：它改的是「怎么显示」，不改页面坐标系——
        # 这正是 bbox 必须先转成视觉方向的原因。
        self.c.setPageRotation(rotation)
        self.pages.append(
            {
                "page_no": self.page_no,
                "width_pt": PAGE_W,
                "height_pt": PAGE_H,
                "rotation": rotation,
                "has_text_layer": True,
            }
        )

    def _record(self, text: str, x0: float, y0: float, x1: float, y1: float) -> None:
        self.block_no += 1
        self.blocks.append(Drawn(self.page_no, self.block_no, text, x0, y0, x1, y1))

    def text(
        self,
        value: str,
        baseline: float,
        size: float = 10.5,
        x: float = MARGIN,
        record: bool = True,
    ) -> None:
        """横排文字（普通页面）。"""
        self.c.setFont(self.font_name, size)
        self.c.setFillColor(HexColor(INK))
        self.c.drawString(x, baseline, value)
        if not record:
            return
        width = self.c.stringWidth(value, self.font_name, size)
        self._record(
            value,
            x,
            baseline - size * DESCENT_RATIO,
            x + width,
            baseline + size * ASCENT_RATIO,
        )

    def text_ccw(self, value: str, x: float, y: float, size: float = 10.5) -> None:
        """在页面坐标系里逆时针转 90° 写字，配合 /Rotate 90 显示为正向。

        旋转后的几何：基线沿 +y 方向推进，字身朝 -x 方向长高——
        所以 x 决定「在屏幕上第几行」，y 决定「在屏幕上横向的位置」。
        注意屏幕方向是「先转内容、再按 /Rotate 顺时针转整页」的结果，
        不是页面坐标系本身的方向（验证见 apps/web/scripts/verify-sample-coords.mjs）。
        """
        self.c.setFont(self.font_name, size)
        self.c.setFillColor(HexColor(INK))
        self.c.saveState()
        self.c.translate(x, y)
        self.c.rotate(90)
        self.c.drawString(0, 0, value)
        self.c.restoreState()
        width = self.c.stringWidth(value, self.font_name, size)
        self._record(value, x - size * ASCENT_RATIO, y, x + size * DESCENT_RATIO, y + width)

    def centered(self, value: str, baseline: float, size: float) -> None:
        self.c.setFont(self.font_name, size)
        width = self.c.stringWidth(value, self.font_name, size)
        self.text(value, baseline, size, x=(PAGE_W - width) / 2)

    def rule(self, y: float) -> None:
        self.c.setStrokeColor(HexColor("#c8ccd4"))
        self.c.setLineWidth(0.6)
        self.c.line(MARGIN, y, PAGE_W - MARGIN, y)

    # ---- 内容 -----------------------------------------------------------

    def build(self) -> None:
        self._cover()
        self._front_table()
        self._scoring()
        self._technical()
        self._contract()
        self._formats()
        self.c.showPage()
        self.c.save()

    def _cover(self) -> None:
        self.new_page()
        self.centered("××市城市轨道交通 3 号线工程", PAGE_H - 260, 20)
        self.centered("招 标 文 件", PAGE_H - 292, 16)
        self.rule(PAGE_H - 320)
        self.text("招标编号：ZB-2026-0317", PAGE_H - 380)
        self.text("招 标 人：××市轨道交通集团有限公司", PAGE_H - 404)
        self.text("招标代理：××工程咨询有限公司", PAGE_H - 428)
        self.text("二〇二六年三月", PAGE_H - 470)

    def _front_table(self) -> None:
        self.new_page()
        self.text("第二章 投标人须知前附表", PAGE_H - 90, 14)
        rows = [
            ("1.1", "项目名称", "××市城市轨道交通 3 号线工程"),
            ("1.2", "招标编号", "ZB-2026-0317"),
            ("1.3", "最高投标限价", "人民币贰亿叁仟万元整（¥230,000,000.00）"),
            ("1.4", "投标保证金", "人民币伍拾万元整（¥500,000.00）"),
            ("1.5", "投标有效期", "自投标截止之日起 90 日历天"),
            ("1.6", "开标时间", "2026 年 4 月 10 日 09 时 30 分"),
            ("1.7", "开标地点", "××市公共资源交易中心 3 楼开标 2 厅"),
            ("1.8", "工期", "540 日历天"),
            ("1.9", "付款方式", "按月计量支付，进度款支付比例 80%"),
        ]
        col_x = [MARGIN, MARGIN + 60, MARGIN + 168]
        top = PAGE_H - 112
        row_h = 27.0
        self.c.setStrokeColor(HexColor("#9aa1ad"))
        self.c.setLineWidth(0.7)
        for i in range(len(rows) + 1):
            y = top - i * row_h
            self.c.line(MARGIN, y, PAGE_W - MARGIN, y)
        for x in (*col_x, PAGE_W - MARGIN):
            self.c.line(x, top, x, top - len(rows) * row_h)

        self.text("条款号", top - 18, 10, x=col_x[0] + 6, record=False)
        self.text("条款名称", top - 18, 10, x=col_x[1] + 6, record=False)
        self.text("编列内容", top - 18, 10, x=col_x[2] + 6, record=False)
        for i, (no, name, value) in enumerate(rows):
            baseline = top - (i + 1) * row_h + 9
            self.text(no, baseline, 10, x=col_x[0] + 6, record=False)
            self.text(name, baseline, 10, x=col_x[1] + 6, record=False)
            # 证据要指向「编列内容」这一格，所以只有它记成块
            self.text(value, baseline, 10, x=col_x[2] + 6)

    def _scoring(self) -> None:
        self.new_page()
        self.text("第三章 评标办法", PAGE_H - 90, 14)
        self.text("3.1 评标方法采用综合评估法，评标委员会按下表逐项打分。", PAGE_H - 130)
        self.text(
            "3.2 投标文件未按招标文件要求密封或者未加盖投标人公章的，其投标将被否决。", PAGE_H - 156
        )
        self.text("★3.3 投标人须提供近三年（2023—2025 年度）经审计的财务报告。", PAGE_H - 182)
        self.text("3.4 评标委员会发现投标人以他人名义投标的，应当否决其投标。", PAGE_H - 208)

    def _technical(self) -> None:
        self.new_page(rotation=90, landscape=True)
        # x 决定屏幕上的行位置，y 决定屏幕上的横向起点
        self.text_ccw("第四章 技术要求", MARGIN, MARGIN, 14)
        self.text_ccw("4.1 区间隧道采用盾构法施工，管片外径 6.2 m，内径 5.5 m。", MARGIN + 34, MARGIN)
        self.text_ccw("4.2 车站主体结构设计使用年限为 100 年。", MARGIN + 60, MARGIN)
        self.text_ccw("4.3 本页在 PDF 中带 /Rotate 90，用于验证旋转页高亮不横过来。", MARGIN + 86, MARGIN)

    def _contract(self) -> None:
        self.new_page()
        self.text("第五章 合同条款", PAGE_H - 90, 14)
        self.text("5.1 承包人应按监理人指示开工，工期自开工令载明之日起算。", PAGE_H - 130)
        self.text("5.2 质量保证金为结算价款的 3%，缺陷责任期满后无息返还。", PAGE_H - 156)
        # 与第二章前附表 1.9 的付款比例重复：样本里唯一的「同一字段多处溯源」场景
        self.text(
            "5.3 工程进度款按月计量支付，累计支付比例不超过 80%，竣工结算后支付至 97%。",
            PAGE_H - 182,
        )

    def _formats(self) -> None:
        self.new_page()
        self.text("第六章 投标文件格式", PAGE_H - 90, 14)
        self.text("6.1 投标函（格式见附件一）", PAGE_H - 130)
        self.text("6.2 法定代表人身份证明或授权委托书", PAGE_H - 156)
        self.text("6.3 已标价工程量清单（另册，仅存不解析）", PAGE_H - 182)

    # ---- 输出 -----------------------------------------------------------

    def page_size(self, page_no: int) -> tuple[float, float]:
        page = self.pages[page_no - 1]
        return float(str(page["width_pt"])), float(str(page["height_pt"]))

    def geometry(self, page_no: int) -> PageGeometry:
        width, height = self.page_size(page_no)
        page = self.pages[page_no - 1]
        return PageGeometry(
            page_no=page_no,
            width_pt=Decimal(str(width)),
            height_pt=Decimal(str(height)),
            rotation=int(str(page["rotation"])),
        )

    def document(self) -> dict[str, object]:
        by_page: dict[str, list[dict[str, object]]] = {}
        for drawn in self.blocks:
            width, height = self.page_size(drawn.page_no)
            visual = self.geometry(drawn.page_no).to_visual(drawn.page_bbox(width, height))
            by_page.setdefault(str(drawn.page_no), []).append(
                {
                    "anchor": drawn.anchor,
                    "type": "text",
                    "page_no": drawn.page_no,
                    "bbox": [float(v) for v in (visual.x0, visual.y0, visual.x1, visual.y1)],
                    "text": drawn.text,
                }
            )
        return {"pages": self.pages, "blocks_by_page": by_page}

    def block(self, anchor: str) -> dict[str, object]:
        for page_blocks in self.document()["blocks_by_page"].values():  # type: ignore[union-attr]
            for item in page_blocks:  # type: ignore[union-attr]
                if item["anchor"] == anchor:
                    return item  # type: ignore[return-value]
        raise KeyError(f"没有这个块：{anchor}")


# field_key / 中文标签 / 分组 / 证据指向的块（按出现顺序，可多处）/ 置信度 / 状态
def main() -> None:
    parser = argparse.ArgumentParser(description="生成合成招标文件样本")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "apps" / "web" / "public" / "samples",
        help="输出目录（默认 apps/web/public/samples：前端要按静态路径取）",
    )
    parser.add_argument("--font", type=Path, default=None, help="内嵌用的中文字体文件（.ttf/.ttc）")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    font_name, font_path, subfont_index = resolve_font(args.font)
    # 注册为 TrueType 字体：reportlab 会按用到的字符做子集内嵌（产物里只有用到的字形）
    pdfmetrics.registerFont(TTFont(font_name, str(font_path), subfontIndex=subfont_index))

    sample = Sample(args.out_dir, font_name)
    sample.build()

    document = sample.document()
    (args.out_dir / "sample-document.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"已生成 {args.out_dir}:")
    print(f"  内嵌字体                 {font_path.name}")
    print(f"  sample-tender.pdf        {len(sample.pages)} 页（其中 1 页 /Rotate 90）")
    print(f"  sample-document.json     {len(sample.pages)} 页 / {len(sample.blocks)} 个块")


if __name__ == "__main__":
    main()
