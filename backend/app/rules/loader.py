"""规则加载器 —— 从 YAML 读取规则，校验，转给 RuleEngine"""
from pathlib import Path
import yaml


class RulesBundle:
    def __init__(
        self,
        engine_version: str,
        rules: list[dict],
        advice_templates: dict[str, dict],
        metadata: dict,
    ):
        self.engine_version = engine_version
        self.rules = rules
        self.advice_templates = advice_templates
        self.metadata = metadata


def load_rules(path: Path) -> RulesBundle:
    """加载 + 基础校验。详细校验留待后续。"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return RulesBundle(
        engine_version=data["engine_version"],
        rules=data["rules"],
        advice_templates=data.get("advice_templates", {}),
        metadata=data.get("metadata", {}),
    )
