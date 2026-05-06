"""
Consent Model — 方案 C：分层默认 + 渐进式询问

设计原则：
1. 注册时只给一个最小默认（CLINICAL_CARE_ONLY），用户立即能用
2. 其他更广的 scope 在首次触发对应数据流时主动弹窗询问
3. 每次新合作伙伴接入（新药企/新研究项目）需要重新询问，
   不能用旧的 AGGREGATED_INDUSTRY 笼统授权覆盖
4. 撤回必须即时生效，并产生审计事件

数据飞轮的法律边界：
  Layer 1 (PHI)            ── CLINICAL_CARE_ONLY
  Layer 2 (De-identified)  ── DEIDENTIFIED_RESEARCH
  Layer 3 (Aggregated)     ── AGGREGATED_INDUSTRY
  + 法规强制               ── REGULATORY_PV_REPORTING (无法 opt-out)
"""

from enum import Enum
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional


class ConsentScope(Enum):
    # ── Layer 1: 主治团队 ─────────────────────────
    CLINICAL_CARE_ONLY = "clinical_care_only"
    # 谁能看：用户的主治医生 / 团队护士
    # 默认：开 (注册时勾选，否则系统无法工作)

    # ── Layer 2: 脱敏科研 ─────────────────────────
    DEIDENTIFIED_RESEARCH = "deidentified_research"
    # 谁能看：经过 IRB 伦理审批的科研项目
    # 默认：关 (用户首次进入"为研究做贡献"页或被询问时主动开)

    # ── Layer 3: 聚合行业 ─────────────────────────
    AGGREGATED_INDUSTRY = "aggregated_industry"
    # 谁能看：药企（仅看聚合统计，无个体追溯）
    # 默认：关 (每次新合作方接入需要重新询问，不能复用旧授权)

    # ── 法规强制（信息披露而非授权） ──────────────
    REGULATORY_PV_REPORTING = "regulatory_pv_reporting"
    # 谁能看：药监部门（NMPA/FDA），仅在出现严重不良事件时
    # 默认：开（法律强制，但用户必须被告知）


# 默认 scope 集合 —— 注册时自动授予，其他 scope 渐进式询问
DEFAULT_GRANTED_SCOPES: set[ConsentScope] = {
    ConsentScope.CLINICAL_CARE_ONLY,
    ConsentScope.REGULATORY_PV_REPORTING,
}

# 触发渐进式询问的事件 → 对应 scope
PROGRESSIVE_PROMPTS: dict[str, ConsentScope] = {
    "user_visits_research_page": ConsentScope.DEIDENTIFIED_RESEARCH,
    "new_pharma_partner_onboarded": ConsentScope.AGGREGATED_INDUSTRY,
}


@dataclass
class Consent:
    """单条 consent 记录 —— 一行一个 (user, scope, recipient) 三元组"""
    user_id: str
    scope: ConsentScope
    granted_at: datetime
    purpose_text: str                     # 给患者看的人话说明
    data_recipient_class: str             # "treating_team" / "research_irb_xxx" / "pharma_partner_xxx"
    revoked_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None # None = 长期，但可随时撤回
    consent_version: str = "1.0.0"        # 同意书版本，文本变更时强制重新询问

    @property
    def is_active(self) -> bool:
        now = datetime.utcnow()
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and now > self.expires_at:
            return False
        return True


# ── 检查权限的核心函数 ────────────────────────────
def can_share(
    user_id: str,
    scope: ConsentScope,
    recipient: str,
    consent_store,                        # 实际是 ConsentRepository
) -> bool:
    """
    在所有数据出站调用前必须经过这里。
    AGGREGATED_INDUSTRY 还要求 recipient 精确匹配 —— 不能用"对药企A的授权"来给药企B发数据。
    """
    consents = consent_store.find_active(user_id, scope)
    if not consents:
        return False
    if scope == ConsentScope.AGGREGATED_INDUSTRY:
        return any(c.data_recipient_class == recipient for c in consents)
    return True


# ── 撤回 ─────────────────────────────────────────
def revoke(user_id: str, scope: ConsentScope, consent_store, event_log) -> None:
    """
    即时生效。已经发出去的聚合数据按合同处理（合同里要有"未来快照不再包含"条款）。
    撤回必须产生审计事件。
    """
    now = datetime.utcnow()
    consent_store.mark_revoked(user_id, scope, revoked_at=now)
    event_log.emit(
        event="consent_revoked",
        user_id=user_id,
        scope=scope.value,
        ts=now,
    )
