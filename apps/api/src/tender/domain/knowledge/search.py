"""检索词规则供用例与数据库召回共享，避免两个实现的中文匹配语义漂移。"""

import re


def keywords(query: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_.-]+|[\u4e00-\u9fff]+", query.lower())
    # 长中文词同时生成二字词，与既有逐段检索规则保持一致。
    return list(dict.fromkeys(
        words + [w[i:i + 2] for w in words if len(w) > 2 for i in range(len(w) - 1)]
    ))
