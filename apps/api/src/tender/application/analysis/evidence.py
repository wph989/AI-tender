"""最终选证身份保持不变，展示摘录只取能在该块确定性定位的完整句段。"""

import re

from tender.application.knowledge.content import core_is_specific, locate_in, match_text


def _texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _texts(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _texts(item)


def display_citation(ref: dict, business: dict) -> dict:
    original = str(ref.get("quote") or "")
    segments = list(re.finditer(r"[^。！？\n]+[。！？\n]?", original))
    selected: set[int] = set()
    # 不靠短数字或通用表头猜位置；完整条件、例外和证明要求也各自参与匹配。
    for value in _texts({key: business.get(key) for key in
                         ("content", "conditions", "materials", "scoring")}):
        for index, segment in enumerate(segments):
            text = segment.group()
            hit = locate_in({"content": text}, value)
            if (not hit or len(hit[0]) < 6 or not core_is_specific(hit[0], value)
                    or len(hit[0]) * 3 < len(match_text(value))):
                continue
            numbers = re.findall(r"\d+(?:\.\d+)?", value)
            if any(number not in text for number in numbers):
                continue
            # 在句内匹配再扩句，避免旧窗口把同块另一事项也扩进展示摘录。
            if len(text) <= 800:
                selected.add(index)
                following = index + 1
                while following < len(segments) and re.match(
                    r"\s*(?:但|除|否则|若|如果|仅|当|其中|发生)", segments[following].group(),
                ):
                    if len(segments[following].group()) > 800:
                        break
                    selected.add(following)
                    following += 1
    excerpts = [segments[index].group().strip() for index in sorted(selected)]
    # 多段摘录单独保存，不能用省略号拼成一条看似连续的原文。
    return {**ref, "quote": excerpts[0] if excerpts else "", "excerpts": excerpts,
            "excerpt_status": "matched" if excerpts else "block_only"}
