"""共享的严格请求模型；统一拒绝未知字段，避免各业务入口的校验策略漂移。"""
from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
