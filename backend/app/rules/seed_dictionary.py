"""MVP 起步症状字典 — 写入 symptom_dictionary 表

12 条覆盖 rules.yaml 中所有引用的症状（10 条）+ 2 条扩展。

执行:
    python -m app.rules.seed_dictionary

设计原则:
- 每条症状必须能被 rules.yaml 中至少一条规则引用，或者明确标注"扩展用"
- aliases_zh 来源于患者口语：决定了 LLM 抽取的"识别能力上限"
- value_type 决定 symptom_observation 中哪些字段会被填
- 修改字典需要同步检查 rules.yaml 是否还能匹配（CI 时加校验）
"""
from sqlalchemy import text

from app.db import SessionLocal


SYMPTOMS = [
    # ── 高风险（rules.yaml R001-R004 引用）─────────────────────
    {
        "id": "fever",
        "display_name_zh": "发热",
        "display_name_en": "Fever",
        "ctcae_term": "Fever",
        "ctcae_category": "General disorders and administration site conditions",
        "aliases_zh": ["发烧", "高热", "低烧", "体温升高", "烧"],
        "value_type": "numeric",       # 体温（℃）
        "grading_scheme": "ctcae_v5",
    },
    {
        "id": "shortness_of_breath",
        "display_name_zh": "呼吸困难",
        "display_name_en": "Dyspnea",
        "ctcae_term": "Dyspnea",
        "ctcae_category": "Respiratory, thoracic and mediastinal disorders",
        "aliases_zh": ["气短", "喘不上气", "胸闷", "气促", "上气不接下气"],
        "value_type": "categorical",
        "grading_scheme": "ctcae_v5",
    },
    {
        "id": "severe_chest_pain",
        "display_name_zh": "严重胸痛",
        "display_name_en": "Chest pain",
        "ctcae_term": "Chest pain - cardiac",
        "ctcae_category": "Cardiac disorders",
        "aliases_zh": ["胸口疼", "心口疼", "胸前痛", "前胸压榨感"],
        "value_type": "categorical",   # mild | moderate | severe
        "grading_scheme": "severity_3",
    },
    {
        "id": "severe_diarrhea",
        "display_name_zh": "腹泻",
        "display_name_en": "Diarrhea",
        "ctcae_term": "Diarrhea",
        "ctcae_category": "Gastrointestinal disorders",
        "aliases_zh": ["拉肚子", "腹泻", "大便次数多", "稀便", "水样便"],
        "value_type": "categorical",
        "grading_scheme": "ctcae_v5",  # G3+ 触发 R004
    },

    # ── 中风险（rules.yaml R010-R012 引用）─────────────────────
    {
        "id": "hand_foot_skin_reaction",
        "display_name_zh": "手足综合征",
        "display_name_en": "Palmar-plantar erythrodysesthesia",
        "ctcae_term": "Palmar-plantar erythrodysesthesia syndrome",
        "ctcae_category": "Skin and subcutaneous tissue disorders",
        "aliases_zh": ["手脚脱皮", "手足麻木", "手掌发红", "脚底疼", "手足红肿"],
        "value_type": "categorical",
        "grading_scheme": "ctcae_v5",
    },
    {
        "id": "vomiting",
        "display_name_zh": "呕吐",
        "display_name_en": "Vomiting",
        "ctcae_term": "Vomiting",
        "ctcae_category": "Gastrointestinal disorders",
        "aliases_zh": ["吐了", "呕吐", "吐", "恶心呕吐"],
        "value_type": "categorical",
        "grading_scheme": "ctcae_v5",
    },
    {
        "id": "peripheral_neuropathy",
        "display_name_zh": "外周神经病变",
        "display_name_en": "Peripheral neuropathy",
        "ctcae_term": "Peripheral motor neuropathy",
        "ctcae_category": "Nervous system disorders",
        "aliases_zh": ["手脚麻木", "手脚发麻", "末梢麻木", "触觉减退", "手指麻"],
        "value_type": "categorical",
        "grading_scheme": "ctcae_v5",
    },

    # ── 低风险（rules.yaml R020-R022 引用）─────────────────────
    {
        "id": "nausea",
        "display_name_zh": "恶心",
        "display_name_en": "Nausea",
        "ctcae_term": "Nausea",
        "ctcae_category": "Gastrointestinal disorders",
        "aliases_zh": ["想吐", "反胃", "恶心"],
        "value_type": "categorical",
        "grading_scheme": "ctcae_v5",
    },
    {
        "id": "fatigue",
        "display_name_zh": "疲劳",
        "display_name_en": "Fatigue",
        "ctcae_term": "Fatigue",
        "ctcae_category": "General disorders and administration site conditions",
        "aliases_zh": ["乏力", "没力气", "累", "疲劳", "疲乏", "犯困"],
        "value_type": "categorical",
        "grading_scheme": "ctcae_v5",
    },
    {
        "id": "hot_flashes",
        "display_name_zh": "潮热",
        "display_name_en": "Hot flashes",
        "ctcae_term": "Hot flashes",
        "ctcae_category": "General disorders and administration site conditions",
        "aliases_zh": ["潮热", "一阵热", "突然燥热", "出虚汗", "盗汗"],
        "value_type": "categorical",
        "grading_scheme": "severity_3",  # mild | moderate | severe
    },

    # ── 扩展（高频询问，未来规则可引用）─────────────────────
    {
        "id": "mucositis",
        "display_name_zh": "口腔黏膜炎",
        "display_name_en": "Mucositis oral",
        "ctcae_term": "Mucositis oral",
        "ctcae_category": "Gastrointestinal disorders",
        "aliases_zh": ["口腔溃疡", "口腔疼", "口疮", "吃饭疼", "嘴里破了"],
        "value_type": "categorical",
        "grading_scheme": "ctcae_v5",
    },
    {
        "id": "rash",
        "display_name_zh": "皮疹",
        "display_name_en": "Rash maculo-papular",
        "ctcae_term": "Rash maculo-papular",
        "ctcae_category": "Skin and subcutaneous tissue disorders",
        "aliases_zh": ["皮疹", "起疹子", "红疹", "皮肤痒红", "出疹"],
        "value_type": "categorical",
        "grading_scheme": "ctcae_v5",
    },
]


# ON CONFLICT DO UPDATE 让脚本可重复执行（修改字典后重跑即可）
INSERT_SQL = text("""
    INSERT INTO symptom_dictionary
        (id, display_name_zh, display_name_en, ctcae_term, ctcae_category,
         aliases_zh, value_type, grading_scheme)
    VALUES
        (:id, :display_name_zh, :display_name_en, :ctcae_term, :ctcae_category,
         :aliases_zh, :value_type, :grading_scheme)
    ON CONFLICT (id) DO UPDATE SET
        display_name_zh = EXCLUDED.display_name_zh,
        display_name_en = EXCLUDED.display_name_en,
        ctcae_term      = EXCLUDED.ctcae_term,
        ctcae_category  = EXCLUDED.ctcae_category,
        aliases_zh      = EXCLUDED.aliases_zh,
        value_type      = EXCLUDED.value_type,
        grading_scheme  = EXCLUDED.grading_scheme
""")


def main() -> None:
    with SessionLocal() as db:
        for s in SYMPTOMS:
            db.execute(INSERT_SQL, s)
        db.commit()

        count = db.execute(
            text("SELECT count(*) FROM symptom_dictionary")
        ).scalar()

    print(f"✅ Seeded {len(SYMPTOMS)} symptoms (table now has {count} rows)")


if __name__ == "__main__":
    main()
