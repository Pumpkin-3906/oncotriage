"""同意守卫 —— 数据出站前的合规检查

对应 DESIGN.md §10 同意模型 (方案 C)
docs/data_model/consent.py 是参考实现
"""
from uuid import UUID
from sqlalchemy.orm import Session


class ConsentGuard:
    def __init__(self, db: Session):
        self.db = db

    def can_share(self, user_id: UUID, scope: str, recipient: str) -> bool:
        """
        检查 user_id 是否对 (scope, recipient) 有有效授权。

        TODO: 实现要点
        - AGGREGATED_INDUSTRY scope 必须精确匹配 recipient
        - 已 revoked 或 expired 的不算
        - 默认开的 scope (CLINICAL_CARE_ONLY / REGULATORY_PV_REPORTING)
          注册时一定有记录，否则不能 fallback 到 True —— 必须查表
        """
        raise NotImplementedError
