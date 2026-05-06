"""pytest fixtures"""
from pathlib import Path
import pytest


@pytest.fixture
def rules_path() -> Path:
    """指向 docs/rules/rules.yaml 的设计版规则集"""
    return Path(__file__).parent.parent.parent / "docs" / "rules" / "rules.yaml"
