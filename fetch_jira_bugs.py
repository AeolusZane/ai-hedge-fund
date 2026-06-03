#!/usr/bin/env python3
"""Jira Bug Auto-Fetch — 自动从 Jira 拉取 bug 并触发修复流程。

使用方式:
    # 拉取指定项目的 Open bug
    python fetch_jira_bugs.py --project AI

    # 拉取多个项目
    python fetch_jira_bugs.py --project AI --project BUSSINESS --project DATAFUSION

    # 指定状态
    python fetch_jira_bugs.py --project AI --status "To Do"

    # 只列出 bug，不触发修复
    python fetch_jira_bugs.py --project AI --dry-run

    # 指定 API 地址
    python fetch_jira_bugs.py --project AI --api-url http://localhost:8080
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import httpx

# 项目 key 到仓库名的映射
PROJECT_REPO_MAP = {
    "AI": "corevo",
    "BUSSINESS": "nuclear-webui",
    "DATAFUSION": "data-fusion-web",
}


async def fetch_bugs_from_jira(
    project_key: str,
    status: str = "Open",
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """从 Jira 拉取 bug 列表。"""
    from app.backend.domains.bug_fix.jira_client import search_bugs

    try:
        bugs = await search_bugs(
            project_key=project_key,
            status=status,
            max_results=max_results,
        )
        return bugs
    except Exception as e:
        print(f"❌ 拉取 {project_key} 的 bug 失败: {e}", file=sys.stderr)
        return []


async def trigger_bug_fix(
    api_url: str,
    issue_key: str,
    repo_name: str,
    project_key: str,
) -> dict[str, Any] | None:
    """触发 bug-fix 流程。"""
    url = f"{api_url}/api/v1/bug-fix"
    payload = {
        "jira_issue": issue_key,
        "repo_name": repo_name,
        "project_key": project_key,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        print(f"❌ 无法连接到 API: {api_url}", file=sys.stderr)
        return None
    except httpx.HTTPStatusError as e:
        print(f"❌ API 返回错误: {e.response.status_code} - {e.response.text[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ 触发修复失败: {e}", file=sys.stderr)
        return None


def print_bug_table(bugs: list[dict[str, Any]], project_key: str) -> None:
    """打印 bug 列表表格。"""
    if not bugs:
        print(f"\n📭 {project_key}: 没有找到匹配的 bug")
        return

    print(f"\n📋 {project_key}: 找到 {len(bugs)} 个 bug\n")
    print(f"{'Key':<15} {'Priority':<10} {'Status':<12} {'Assignee':<15} {'Summary'}")
    print("-" * 100)
    for bug in bugs:
        key = bug.get("key", "")
        priority = bug.get("priority", "")[:8]
        status = bug.get("status", "")[:10]
        assignee = bug.get("assignee", "")[:13] or "Unassigned"
        summary = bug.get("summary", "")[:50]
        print(f"{key:<15} {priority:<10} {status:<12} {assignee:<15} {summary}")


async def main():
    parser = argparse.ArgumentParser(description="Jira Bug Auto-Fetch")
    parser.add_argument(
        "--project", "-p",
        action="append",
        dest="projects",
        required=True,
        help="Jira project key (可多次指定)",
    )
    parser.add_argument(
        "--status", "-s",
        default="Open",
        help="Bug status to filter (default: Open)",
    )
    parser.add_argument(
        "--max", "-m",
        type=int,
        default=20,
        help="Maximum bugs per project (default: 20)",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Only list bugs, don't trigger fix",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080",
        help="Bug-fix API URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--auto-trigger",
        action="store_true",
        help="Auto-trigger fix without confirmation",
    )

    args = parser.parse_args()

    all_bugs: dict[str, list[dict[str, Any]]] = {}

    # 拉取所有项目的 bug
    for project_key in args.projects:
        print(f"🔍 正在拉取 {project_key} 的 bug...")
        bugs = await fetch_bugs_from_jira(
            project_key=project_key,
            status=args.status,
            max_results=args.max,
        )
        all_bugs[project_key] = bugs
        print_bug_table(bugs, project_key)

    # 统计
    total_bugs = sum(len(bugs) for bugs in all_bugs.values())
    print(f"\n{'='*60}")
    print(f"📊 总计: {total_bugs} 个 bug")

    if args.dry_run:
        print("🔸 Dry-run 模式，不触发修复")
        return

    if total_bugs == 0:
        print("✅ 没有需要处理的 bug")
        return

    # 确认是否触发修复
    if not args.auto_trigger:
        print(f"\n⚠️  即将触发 {total_bugs} 个 bug 的修复流程")
        response = input("继续? (y/N): ").strip().lower()
        if response != "y":
            print("已取消")
            return

    # 触发修复
    triggered = 0
    for project_key, bugs in all_bugs.items():
        repo_name = PROJECT_REPO_MAP.get(project_key, project_key.lower())
        for bug in bugs:
            issue_key = bug.get("key", "")
            if not issue_key:
                continue

            print(f"\n🚀 触发修复: {issue_key} ({bug.get('summary', '')[:40]}...)")
            result = await trigger_bug_fix(
                api_url=args.api_url,
                issue_key=issue_key,
                repo_name=repo_name,
                project_key=project_key,
            )

            if result:
                task_id = result.get("task_id") or result.get("run_id") or "unknown"
                print(f"   ✅ 已提交，任务 ID: {task_id}")
                triggered += 1
            else:
                print(f"   ❌ 提交失败")

    print(f"\n{'='*60}")
    print(f"✅ 已触发 {triggered}/{total_bugs} 个 bug 的修复流程")


if __name__ == "__main__":
    asyncio.run(main())
