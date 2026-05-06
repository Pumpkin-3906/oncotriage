"""应用配置 —— 从环境变量加载

所有"魔法数字"应该在这里定义为 Settings 字段，
不要在 services/ 里写死常量。

修改临床阈值（标 ⚕️）需要临床委员会签字。
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 数据库 ────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg://sz:sz_dev_password@localhost:5432/sz_dev"
    database_pool_size: int = 10

    # ── LLM 通用 ──────────────────────────────────────────────
    # 'anthropic' | 'openai' —— 选哪种 SDK 协议；'openai' 兼容 DeepSeek/Qwen/OpenRouter/vLLM 等
    llm_provider: str = "anthropic"
    llm_timeout_seconds: int = 15
    llm_max_tokens: int = 2000
    llm_temperature: float = 0.0

    # ── LLM Anthropic 通道 ────────────────────────────────────
    # base_url 留空 = 走 Anthropic 官方；可指向兼容端点（如 DeepSeek 的 Anthropic-compat）
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    # ── LLM OpenAI-compat 通道 ───────────────────────────────
    # base_url 可指向任意 OpenAI 兼容端点（DeepSeek: https://api.deepseek.com/v1）
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # ── 应用 ──────────────────────────────────────────────────
    app_env: str = "dev"
    log_level: str = "INFO"
    cors_allow_origins: str = "http://localhost:5173"

    # ── 规则引擎 ──────────────────────────────────────────────
    rule_engine_version: str = "1.0.0"
    rules_file_path: str = "../docs/rules/rules.yaml"

    # ── Feature flags ────────────────────────────────────────
    feature_timeseries: bool = False

    # ── 可观测性 ──────────────────────────────────────────────
    event_sink: str = "stdout"  # 'stdout' | 'kafka' | 'noop'
    event_kafka_brokers: str = ""
    event_kafka_topic: str = "oncotriage.events"

    # ── ⚕️ 临床阈值 (Bad Case 自动触发) ─────────────────────────
    # 修改需临床委员会签字
    low_confidence_threshold: float = 0.6
    outcome_mismatch_window_hours: int = 24
    repeat_high_no_action_count: int = 3

    # ── 幂等性 ────────────────────────────────────────────────
    idempotency_key_ttl_hours: int = 24

    # ── 时序分析 (Advanced) ──────────────────────────────────
    trend_window_days: int = 7
    trend_comparison_days: int = 3

    # ── 合规 (预留) ──────────────────────────────────────────
    default_irb_project_id: str = ""
    aggregation_k_anonymity_threshold: int = 20

    # ── 派生属性 ──────────────────────────────────────────────
    @property
    def rules_path(self) -> Path:
        return (Path(__file__).parent.parent / self.rules_file_path).resolve()

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


settings = Settings()
