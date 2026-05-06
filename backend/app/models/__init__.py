"""SQLAlchemy 模型 —— 与 docs/data_model/schema.sql 保持一致

注意：schema.sql 是设计文档（人类可读），这里的 ORM 模型是运行时真理。
任何 schema 改动需要：
  1. 更新 docs/data_model/schema.sql
  2. 更新此处对应模型
  3. 生成 alembic 迁移：alembic revision --autogenerate
"""
from app.models.user import User
from app.models.assessment import Assessment
from app.models.symptom_observation import SymptomObservation
from app.models.advice import Advice
from app.models.evidence import Evidence
from app.models.event_log import EventLog

# TODO: 按需补全其他模型
# from app.models.symptom_dictionary import SymptomDictionary
# from app.models.rule_source import RuleSource
# from app.models.consent import Consent
# from app.models.contact_request import ContactRequest

__all__ = [
    "User",
    "Assessment",
    "SymptomObservation",
    "Advice",
    "Evidence",
    "EventLog",
]
