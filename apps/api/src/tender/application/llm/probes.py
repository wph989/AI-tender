"""内置合成测试图片，避免测试时提交用户文档或访问第三方图片。"""

import base64

from tender.ports.llm.media import ModelImage

PROBE_IMAGE = ModelImage(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAN0lEQVR4nO3QsQ0AAAjDsML/P8MJEQNbvFeVUpObym3RedYeEBMhEyETIRMhEyETIRMhEyEThSyRegI/smNoMgAAAABJRU5ErkJggg=="
    )
)
