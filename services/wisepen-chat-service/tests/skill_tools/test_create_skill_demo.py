"""
模拟 Agent 创建 Skill 并真实发布的测试脚本。

功能：
1. 构造一个 BY_AGENT 来源的 Skill 示例（包含 Python 脚本）
2. 运行 validator 校验（验证 Python 脚本限制等规则）
3. 运行 serializer 生成资源文件列表
4. 真实调用 ai-asset-service 接口发布（需要 Nacos 和后端服务启动）

使用方式：
    # 仅运行校验和序列化（不调用真实接口）
    uv run python tests/skill_tools/test_create_skill_demo.py

    # 真实调用后端接口发布
    uv run python tests/skill_tools/test_create_skill_demo.py --publish
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# ── 提前加载 .env ──────────────────────────────────────────────
# 项目使用 pydantic-settings + find_dotenv(usecwd=True) 加载 .env
# .env 文件位于 src/chat/ 目录下，这里提前手动加载确保所有模块都能读到环境变量
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[2] / "src" / "chat" / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
    print(f"✅ 已加载环境配置: {_env_path}")
else:
    print(f"⚠️  未找到 .env 文件: {_env_path}")

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

# 提前导入不依赖容器的模块（validator, serializer, models）
from chat.application.tools.skill_tools.create_skill.models import (
    CreateSkillRequest,
    SkillFile,
    SkillScript,
    SkillSection,
)
from chat.application.tools.skill_tools.create_skill.serializer import (
    SkillAssetFile,
    build_skill_assets,
)
from chat.application.tools.skill_tools.create_skill.validator import (
    validate_create_skill,
)


def build_demo_skill() -> CreateSkillRequest:
    """构造一个示例 Skill，模拟 Agent 创建的带 Python 脚本的技能。

    返回值:
        CreateSkillRequest: 一个完整的 Skill 创建请求，包含:
            - skill_id: agent-data-cleaner-demo
            - 标题、触发描述、正文
            - 两个一级章节（使用方法、使用示例）
            - 1 个 reference 文档
            - 1 个 Python 脚本（数据清洗）
            - 1 个 asset 配置文件
    """

    return CreateSkillRequest(
        skill_id="agent-data-cleaner-demo",
        title="Agent 数据清洗工具",
        trigger_description=(
            "当用户需要清洗、格式化或转换 CSV/Excel 数据时触发。"
            "包括去重、缺失值填充、格式转换、数据筛选等常见数据清洗任务。"
            "支持中文数据处理和多种输出格式。"
        ),
        body=(
            "本 Skill 由 AI Agent 自动创建，用于快速执行常见的数据清洗任务。\n\n"
            "主要功能包括 CSV/Excel 数据读取与写入、缺失值检测与填充、重复数据删除、数据格式转换。"
        ),
        children=[
            SkillSection(
                node_id="features",
                heading="功能特性",
                body=(
                    "本工具提供以下数据清洗能力：\n\n"
                    "- CSV/Excel 数据读取与写入\n"
                    "- 缺失值检测与填充\n"
                    "- 重复数据删除\n"
                    "- 数据格式转换"
                ),
                children=[],
            ),
            SkillSection(
                node_id="usage",
                heading="使用方法",
                body=(
                    "调用数据清洗脚本时，请提供输入文件路径和清洗配置。\n\n"
                    "脚本会自动识别数据类型并应用相应的清洗策略。"
                ),
                children=[
                    SkillSection(
                        node_id="basic-usage",
                        heading="基础用法",
                        body=(
                            "最基本的用法是只指定输入文件，脚本会自动执行标准清洗流程。"
                        ),
                        children=[],
                    ),
                    SkillSection(
                        node_id="advanced-config",
                        heading="高级配置",
                        body=(
                            "可以通过配置文件自定义清洗规则，包括指定列名、缺失值策略等。"
                        ),
                        children=[],
                    ),
                ],
            ),
            SkillSection(
                node_id="examples",
                heading="使用示例",
                body="以下是几个常见的使用场景示例。",
                children=[],
            ),
        ],
        references=[
            SkillFile(
                path="data-formats.md",
                title="支持的数据格式",
                body="本工具支持以下数据格式：\n\n- CSV (UTF-8/GBK)\n- Excel (.xlsx, .xls)\n- JSON Lines",
                children=[],
            ),
        ],
        scripts=[
            SkillScript(
                path="clean_data.py",
                body=(
                    "#!/usr/bin/env python3\n"
                    "\"\"\"数据清洗脚本 - 由 AI Agent 生成。\"\"\"\n"
                    "import csv\n"
                    "import sys\n"
                    "\n"
                    "\n"
                    "def remove_duplicates(rows):\n"
                    "    \"\"\"去除重复行。\"\"\"\n"
                    "    seen = set()\n"
                    "    result = []\n"
                    "    for row in rows:\n"
                    "        key = tuple(row.values())\n"
                    "        if key not in seen:\n"
                    "            seen.add(key)\n"
                    "            result.append(row)\n"
                    "    return result\n"
                    "\n"
                    "\n"
                    "def fill_missing(rows, fill_value=\"\"):\n"
                    "    \"\"\"填充缺失值。\"\"\"\n"
                    "    for row in rows:\n"
                    "        for key, value in row.items():\n"
                    "            if value is None or str(value).strip() == \"\":\n"
                    "                row[key] = fill_value\n"
                    "    return rows\n"
                    "\n"
                    "\n"
                    "def clean_csv(input_path, output_path):\n"
                    "    \"\"\"清洗 CSV 文件。\"\"\"\n"
                    "    with open(input_path, \"r\", encoding=\"utf-8\") as f:\n"
                    "        reader = csv.DictReader(f)\n"
                    "        rows = list(reader)\n"
                    "\n"
                    "    rows = remove_duplicates(rows)\n"
                    "    rows = fill_missing(rows)\n"
                    "\n"
                    "    with open(output_path, \"w\", encoding=\"utf-8\", newline=\"\") as f:\n"
                    "        writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])\n"
                    "        writer.writeheader()\n"
                    "        writer.writerows(rows)\n"
                    "\n"
                    "    print(f\"清洗完成，共处理 {len(rows)} 行数据\")\n"
                    "\n"
                    "\n"
                    "if __name__ == \"__main__\":\n"
                    "    if len(sys.argv) < 3:\n"
                    "        print(\"用法: python clean_data.py <input.csv> <output.csv>\")\n"
                    "        sys.exit(1)\n"
                    "    clean_csv(sys.argv[1], sys.argv[2])\n"
                ),
            ),
        ],
        assets=[
            SkillFile(
                path="config_template.json",
                body=json.dumps(
                    {
                        "remove_duplicates": True,
                        "fill_missing": True,
                        "fill_value": "",
                        "encoding": "utf-8",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                children=[],
            ),
        ],
    )


def build_invalid_skill_non_python() -> CreateSkillRequest:
    """构造一个包含非 Python 脚本的无效 Skill（用于测试校验）。

    在正常 Skill 基础上添加一个 .sh 脚本，验证 validator 能否正确拒绝。
    """
    request = build_demo_skill()
    # 加一个 shell 脚本，应该被校验拒绝
    request.scripts = list(request.scripts) + [
        SkillScript(
            path="install.sh",
            body="#!/bin/bash\necho 'installing...'\n",
        ),
    ]
    return request


def run_validation_tests() -> None:
    """运行校验测试，验证 validator 的各项规则。"""
    print("\n" + "=" * 60)
    print("【1/4】运行校验测试")
    print("=" * 60)

    # 测试 1: 合法的 Skill（只有 Python 脚本）
    print("\n>>> 测试 1: 合法的 Skill（仅 Python 脚本）")
    valid_skill = build_demo_skill()
    errors = validate_create_skill(valid_skill)
    if errors:
        print(f"❌ 校验失败（不应该失败）: {errors}")
    else:
        print(f"✅ 校验通过，共 {len(valid_skill.scripts)} 个 Python 脚本")

    # 测试 2: 包含非 Python 脚本的 Skill
    print("\n>>> 测试 2: 包含 shell 脚本的 Skill（应该被拒绝）")
    invalid_skill = build_invalid_skill_non_python()
    errors = validate_create_skill(invalid_skill)
    if errors:
        print(f"✅ 校验成功拒绝，错误信息: {errors}")
    else:
        print(f"❌ 校验未拒绝非 Python 脚本，测试失败")

    # 测试 3: node_id 重复检测
    print("\n>>> 测试 3: node_id 重复检测")
    dup_skill = build_demo_skill()
    dup_skill.children[0].children.append(
        SkillSection(
            node_id="usage",
            heading="重复的 node_id",
            body="这个 node_id 和根级的重复了",
            children=[],
        )
    )
    errors = validate_create_skill(dup_skill)
    if any("Duplicate node_id" in e for e in errors):
        print(f"✅ 成功检测到重复 node_id: {[e for e in errors if 'Duplicate' in e]}")
    else:
        print(f"❌ 未检测到重复 node_id，测试失败")


def run_serializer_tests() -> list[SkillAssetFile]:
    """运行序列化测试，生成资源文件列表并打印预览。

    返回值:
        list[SkillAssetFile]: 生成的资源文件列表
    """
    print("\n" + "=" * 60)
    print("【2/4】运行序列化测试（生成资源文件列表）")
    print("=" * 60)

    request = build_demo_skill()
    assets = build_skill_assets(
        skill_id=request.skill_id,
        trigger_description=request.trigger_description,
        title=request.title,
        body=request.body,
        children=request.children,
        references=request.references,
        scripts=request.scripts,
        assets=request.assets,
        user_id="test-user-001",
        session_id="test-session-001",
    )

    print(f"\n✅ 生成了 {len(assets)} 个资源文件:")
    for asset in assets:
        size_kb = len(asset.content.encode("utf-8")) / 1024
        print(f"  - {asset.path}/{asset.name}  [{asset.asset_type}]  {size_kb:.2f} KB")

    # 验证 SKILL.md 存在并预览
    skill_md = next((a for a in assets if a.name == "SKILL.md"), None)
    if skill_md:
        print(f"\n>>> SKILL.md 预览（前 500 字符）:")
        print("-" * 60)
        preview = skill_md.content[:500] + "..." if len(skill_md.content) > 500 else skill_md.content
        print(preview)
        print("-" * 60)

    # 验证 Python 脚本存在
    py_scripts = [a for a in assets if a.name.endswith(".py")]
    print(f"\n>>> Python 脚本文件: {len(py_scripts)} 个")
    for s in py_scripts:
        print(f"  - {s.path}/{s.name}")

    return assets


def print_summary(assets: list[SkillAssetFile]) -> None:
    """打印资源汇总信息。"""
    print("\n" + "=" * 60)
    print("【3/4】资源汇总")
    print("=" * 60)

    from collections import Counter

    type_counts = Counter(a.asset_type for a in assets)
    print("\n按类型统计:")
    for asset_type, count in type_counts.items():
        print(f"  {asset_type}: {count} 个")

    total_size = sum(len(a.content.encode("utf-8")) for a in assets)
    print(f"\n总大小: {total_size / 1024:.2f} KB")
    print(f"source_type: BY_AGENT（Agent 创建）")
    print(f"脚本语言限制: 仅 Python (.py)")


async def run_real_publish() -> None:
    """真实调用后端接口发布 Skill。

    完整流程:
    1. 从 DI 容器获取 AIAssetClient（已通过 .env 配置好 Nacos）
    2. 创建 AIAssetSkillPublisher
    3. 调用 publish 方法执行完整发布流程

    注意: 需要 wisepen-ai-asset-service 服务已启动并注册到 Nacos。
    """
    # 延迟导入容器相关的模块
    from chat.application.tools.skill_tools.create_skill.skill_publisher import (
        AIAssetSkillPublisher,
    )
    from chat.container import container
    from chat.service_client.ai_asset_service_client import AIAssetClient

    print("\n" + "=" * 60)
    print("【4/4】真实发布 Skill 到 ai-asset-service")
    print("=" * 60)

    # 构造 Skill 数据
    request = build_demo_skill()

    # 先做一次校验，确保数据合法
    errors = validate_create_skill(request)
    if errors:
        print(f"\n❌ 校验失败，中止发布: {errors}")
        return

    print("\n✅ 校验通过，开始发布...")

    # 打印 Nacos 配置（确认配置加载正确）
    print(f"\n>>> Nacos 配置:")
    print(f"    server_addr: {os.environ.get('NACOS_SERVER_ADDR')}")
    print(f"    namespace: {os.environ.get('NACOS_NAMESPACE_ID', 'public')}")
    print(f"    group: {os.environ.get('NACOS_GROUP', 'DEFAULT_GROUP')}")

    # 从 DI 容器获取 AIAssetClient
    print("\n>>> 步骤 0: 从 DI 容器获取 AIAssetClient...")
    ai_asset_client: AIAssetClient = container.ai_asset_client()
    print("✅ AIAssetClient 获取成功")

    # 创建 Publisher
    publisher = AIAssetSkillPublisher(ai_asset_client=ai_asset_client)

    # 生成资源文件
    assets = build_skill_assets(
        skill_id=request.skill_id,
        trigger_description=request.trigger_description,
        title=request.title,
        body=request.body,
        children=request.children,
        references=request.references,
        scripts=request.scripts,
        assets=request.assets,
        user_id="test-user-001",
        session_id="test-session-001",
    )

    print(f"\n>>> 开始发布流程...")
    print(f"    - skill_id: {request.skill_id}")
    print(f"    - title: {request.title}")
    print(f"    - source_type: BY_AGENT")
    print(f"    - 资源文件数: {len(assets)}")

    try:
        result = await publisher.publish(
            skill_id=request.skill_id,
            title=request.title,
            trigger_description=request.trigger_description,
            description=request.body,
            assets=assets,
        )

        print(f"\n🎉 发布成功！")
        print(f"    resource_id: {result.skill_id}")
        print(f"    version: {result.version}")
        print(f"    status: {result.status}")
        print(f"    published_at: {result.published_at}")
        print(f"\n请在数据库中验证:")
        print(f"    SELECT * FROM ai_skill WHERE resource_id = '{result.skill_id}';")
        print(f"    SELECT * FROM ai_skill_version WHERE skill_resource_id = '{result.skill_id}';")

    except Exception as e:
        print(f"\n❌ 发布失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


def main() -> None:
    parser = argparse.ArgumentParser(description="模拟 Agent 创建 Skill 并发布的测试脚本")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="真实调用后端接口发布（需要 ai-asset-service 启动）",
    )
    args = parser.parse_args()

    print("🚀 Agent Skill 创建与发布测试")
    print(f"   Skill 来源: BY_AGENT（AI Agent 创建）")
    print(f"   脚本限制: 仅 Python (.py)")

    # 1. 校验测试
    run_validation_tests()

    # 2. 序列化测试
    assets = run_serializer_tests()

    # 3. 汇总
    print_summary(assets)

    # 4. 真实发布（如指定 --publish）
    if args.publish:
        asyncio.run(run_real_publish())
    else:
        print("\n" + "=" * 60)
        print("【4/4】跳过真实发布")
        print("=" * 60)
        print("\n💡 如需真实发布到后端，请运行:")
        print("   uv run python tests/skill_tools/test_create_skill_demo.py --publish")

    print("\n🎉 测试完成！")


if __name__ == "__main__":
    main()
