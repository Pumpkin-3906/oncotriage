"""建议渲染 —— 把模板 + 上下文渲染成最终给用户看的文本

对应 DESIGN.md §5.③ 执行环节的一部分
"""
from jinja2 import Template


class AdviceRenderer:
    def __init__(self, templates: dict[str, dict]):
        # templates: { 'tpl_emergency_er': {'version': '1.0.0', 'text': '...'} }
        self.templates = templates

    def render(self, template_id: str, context: dict) -> tuple[str, str]:
        """
        返回 (rendered_text, template_version)
        TODO: 实现 Jinja2 渲染
        """
        raise NotImplementedError
