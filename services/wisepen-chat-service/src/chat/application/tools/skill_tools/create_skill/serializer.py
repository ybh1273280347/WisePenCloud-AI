from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

from chat.application.tools.skill_tools.create_skill.models import (
    SkillFile,
    SkillScript,
    SkillSection,
)


@dataclass(frozen=True, slots=True)
class SkillAssetFile:
    """Skill 资源文件数据结构，用于描述单个待上传的文件。

    Attributes:
        path: 文件所在目录路径（如 "/"、"/references"、"/scripts"、"/assets"）
        name: 文件名（如 "SKILL.md"、"helper.py"）
        content: 文件内容文本
        asset_type: 文件资源类型枚举值（MD / PYTHON_SCRIPT / TEXT / JSON / YAML / TOML）
    """
    path: str
    name: str
    content: str
    asset_type: str


def serialize_skill_markdown(
        *,
        skill_id: str,
        trigger_description: str,
        title: str,
        body: str,
        children: list[SkillSection],
        user_id: str,
        session_id: str,
        version: int = 1,
        created_at: datetime | None = None,
) -> str:
    """生成 SKILL.md 内容（YAML frontmatter + Markdown body）。

    遵循 Agent Skills 开放规范：
    - YAML frontmatter 包含 name / description / metadata
    - 审计字段放在 metadata 中，与正文分离
    - 纯函数：不鉴权、不写存储、不修改索引
    """
    now = created_at or datetime.now(timezone.utc)
    lines: list[str] = ["---", f"name: {skill_id}", "description: |-"]

    # ---- YAML frontmatter ----
    # 逐行缩进写入触发描述
    for desc_line in trigger_description.strip().split("\n"):
        lines.append(f"  {desc_line}")
    lines.append("metadata:")
    lines.append(f"  version: \"{version}\"")
    lines.append(f"  user_id: \"{_yaml_escape(user_id)}\"")
    lines.append(f"  session_id: \"{_yaml_escape(session_id)}\"")
    lines.append(f"  created_at: \"{now.isoformat()}\"")
    lines.append(f"  updated_at: \"{now.isoformat()}\"")
    lines.append("---")
    lines.append("")

    # ---- Markdown body ----
    _append_markdown_body(title, body, children, lines)

    return "\n".join(lines) + "\n"


def serialize_skill_file_markdown(
        *,
        title: str,
        body: str,
        children: list[SkillSection],
) -> str:
    """生成 references/ 或 assets/ 中的 .md 文件内容（无 YAML frontmatter）。

    复用标题树序列化逻辑，但不含 frontmatter——frontmatter 仅 SKILL.md 需要。
    """
    lines: list[str] = []
    _append_markdown_body(title, body, children, lines)
    return "\n".join(lines) + "\n"


def build_skill_assets(
        *,
        skill_id: str,
        trigger_description: str,
        title: str,
        body: str,
        children: list[SkillSection],
        references: list[SkillFile],
        scripts: list[SkillScript],
        assets: list[SkillFile],
        user_id: str,
        session_id: str,
        version: int = 1,
        created_at: datetime | None = None,
) -> list[SkillAssetFile]:
    """构建完整的 Skill 资源文件列表，替代原有的 zip 打包方式。

    返回的列表包含所有需要上传的文件，每个文件携带路径、名称、内容和资源类型，
    供后续逐文件上传到 Java ai-asset-service。

    目录结构遵循 Agent Skills 规范：
    /SKILL.md
    /references/...
    /scripts/...
    /assets/...
    """
    now = created_at or datetime.now(timezone.utc)
    result: list[SkillAssetFile] = []

    # 1. 生成主文件 SKILL.md（放在根目录 /）
    skill_md = serialize_skill_markdown(
        skill_id=skill_id,
        trigger_description=trigger_description,
        title=title,
        body=body,
        children=children,
        user_id=user_id,
        session_id=session_id,
        version=version,
        created_at=now,
    )
    result.append(SkillAssetFile(path="/", name="SKILL.md", content=skill_md, asset_type="MD"))

    # 2. references 目录下的参考文档
    for ref in references:
        content = _render_skill_file(ref)
        asset_type = _infer_asset_type(ref.path)
        result.append(SkillAssetFile(path="/references", name=ref.path, content=content, asset_type=asset_type))

    # 3. scripts 目录下的 Python 脚本（仅支持 .py）
    for script in scripts:
        asset_type = _infer_asset_type(script.path)
        result.append(SkillAssetFile(path="/scripts", name=script.path, content=script.body, asset_type=asset_type))

    # 4. assets 目录下的资源文件
    for asset in assets:
        content = _render_skill_file(asset)
        asset_type = _infer_asset_type(asset.path)
        result.append(SkillAssetFile(path="/assets", name=asset.path, content=content, asset_type=asset_type))

    return result


def _append_markdown_body(
        title: str,
        body: str,
        children: list[SkillSection],
        lines: list[str],
) -> None:
    """向 lines 追加 Markdown 正文（H1 + body + children 标题树）。"""
    # H1: 文档唯一一级标题
    lines.append(f"# {title}")
    lines.append("")

    # 根 body：一级标题与第一个二级标题之间的正文
    if body.strip():
        lines.append(body.rstrip("\n"))
        lines.append("")

    # 根 children 从二级标题开始
    for section in children:
        _serialize_section(section, level=2, lines=lines)


def _serialize_section(
        section: SkillSection,
        level: int,
        lines: list[str],
) -> None:
    """递归序列化单个标题节点。"""
    if level <= 6:
        # 标准 Markdown 标题（H1~H6）
        prefix = "#" * level
        lines.append(f"{prefix} {section.heading}")
    else:
        # 超过 H6 降级为粗体标题文本
        lines.append(f"**{section.heading}**")

    lines.append("")

    if section.body.strip():
        lines.append(section.body.rstrip("\n"))
        lines.append("")

    for child in section.children:
        _serialize_section(child, level=level + 1, lines=lines)


def _render_skill_file(f: SkillFile) -> str:
    """渲染 references/assets 中的文件内容。

    .md 文件复用标题树序列化；其他文本文件直接返回 body。
    """
    if f.path.endswith(".md") and (f.children or f.title):
        # .md 文件且有标题树结构：复用序列化
        title = f.title or _title_from_path(f.path)
        return serialize_skill_file_markdown(
            title=title,
            body=f.body,
            children=f.children,
        )
    # 非结构化文件：直接返回 body
    return f.body


def _title_from_path(path: str) -> str:
    """从文件路径推导 H1 标题（去掉扩展名，替换连字符为空格，首字母大写）。"""
    stem = PurePosixPath(path).stem
    return stem.replace("-", " ").replace("_", " ").title()


def _yaml_escape(value: str) -> str:
    """转义 YAML 双引号字符串中的特殊字符。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _infer_asset_type(path: str) -> str:
    """根据文件后缀推断 SkillAssetResourceType 枚举值。

    支持的类型：MD、PYTHON_SCRIPT、TEXT、JSON、YAML、TOML
    未知类型统一降级为 TEXT。
    """
    suffix = PurePosixPath(path).suffix.lower()
    _type_map = {
        ".md": "MD",
        ".py": "PYTHON_SCRIPT",
        ".txt": "TEXT",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".toml": "TOML",
    }
    return _type_map.get(suffix, "TEXT")
