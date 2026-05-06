"""校验：rules.yaml 引用的所有症状都在字典里

防止规则作者引用了字典里没有的症状 ID（CI 拦截这种错误）。
"""
import re

from app.rules.loader import load_rules
from app.rules.seed_dictionary import SYMPTOMS


def test_all_rule_symptoms_present_in_dictionary(rules_path):
    """rules.yaml 中 symptom: xxx 引用的 ID，必须都在字典里"""
    bundle = load_rules(rules_path)
    dictionary_ids = {s["id"] for s in SYMPTOMS}

    referenced_ids: set[str] = set()
    for rule in bundle.rules:
        # 递归扫描 when 子句里所有 symptom 字段
        _collect_symptom_ids(rule.get("when", {}), referenced_ids)

    missing = referenced_ids - dictionary_ids
    assert not missing, (
        f"Rules reference symptoms not in dictionary: {missing}. "
        f"Either add to seed_dictionary.py or fix rules.yaml."
    )


def test_dictionary_ids_are_valid_format():
    """字典 ID 必须 lowercase_underscore（防 LLM grounding 时的奇怪字符）"""
    pattern = re.compile(r"^[a-z][a-z0-9_]*$")
    for s in SYMPTOMS:
        assert pattern.match(s["id"]), f"Invalid id format: {s['id']}"


def _collect_symptom_ids(node, acc: set[str]) -> None:
    """深度遍历 when 子句，提取所有 symptom 字段"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "symptom" and isinstance(value, str):
                acc.add(value)
            else:
                _collect_symptom_ids(value, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_symptom_ids(item, acc)
