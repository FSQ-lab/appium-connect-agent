#!/usr/bin/env python3.11
"""Run a project leaf role through the existing Codex CLI (Python >= 3.11)."""

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 11):  # noqa: UP036 - Explain Python 3.9 failure before tomllib.
    raise SystemExit("Python >= 3.11 required; select python3.11 explicitly.")

import tomllib


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--role",
        required=True,
        choices=("appium-expert", "agent-integration-engineer", "quality-engineer"),
    )
    parser.add_argument("--task-package", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--resume", metavar="THREAD_ID")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        if args.resume is not None and (
            args.role == "appium-expert"
            or not args.resume.strip()
            or args.resume.startswith("-")
        ):
            raise ValueError(
                "--resume requires an explicit engineer/reviewer thread ID"
            )
        digest = args.sha256.lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("--sha256 must contain exactly 64 hexadecimal digits")
        if not args.task_package.is_absolute():
            raise ValueError("--task-package must be an absolute path")
        task_path = args.task_package.resolve(strict=True)
        data = task_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("task package SHA256 mismatch")
        task = json.loads(data)
        required = (
            "root",
            "authorization_original",
            "goal",
            "ownership",
            "fixed",
            "stop",
        )
        if not isinstance(task, dict) or any(not task.get(k) for k in required):
            raise ValueError("task package requires: " + ", ".join(required))
        for key in ("root", "authorization_original", "goal", "stop"):
            if not isinstance(task[key], str) or not task[key].strip():
                raise ValueError("task field must be a nonempty string: " + key)
        if not isinstance(task["ownership"], dict) or not isinstance(
            task["fixed"], list
        ):
            raise ValueError("ownership must be an object; fixed must be a list")
        task_root = Path(task["root"])
        if not task_root.is_absolute() or task_root.resolve(strict=True) != root:
            raise ValueError("task root must match this script's worktree")
        role_path = root / ".codex" / "agents" / (args.role + ".toml")
        source = root / ".github" / "agents" / (args.role + ".agent.md")
        evidence = task["fixed"] + [
            task[key] for key in ("manifest", "full_diff") if key in task
        ]
        read_paths = [str(task_path)]
        for entry in evidence:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("path"), str)
                or not entry["path"].strip()
            ):
                raise ValueError("evidence path must be a nonempty string")
            path = (root / entry["path"]).resolve(strict=True)
            if not path.is_file():
                raise ValueError("evidence path must be a file: " + str(path))
            read_paths.append(str(path))
        for path in (root / "AGENTS.md", root / "SPEC.md", source, role_path):
            if not path.is_file():
                raise ValueError("required source file missing: " + str(path))
            read_paths.append(str(path))
        read_paths = list(dict.fromkeys(read_paths))
        first_read = (
            shlex.join(["cat", *read_paths])
            + " && "
            + shlex.join(["shasum", "-a", "256", *read_paths])
        )
        role = tomllib.loads(role_path.read_text(encoding="utf-8"))
        instructions = role.get("developer_instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise ValueError("role TOML requires developer_instructions")
        developer = "\n\n".join(
            (
                "你是主会话直接安排的叶角色; 禁止调用协作工具、创建或委派子角色。"
                "首个工具调用须为真实文件/命令读取及哈希; 仅最终回复结果。"
                "先完整读取 AGENTS.md、SPEC.md、角色原文及任务包, 独立核验任务包和固定证据哈希。"
                "缺入口、哈希不符或授权不足时一次报告阻塞并停止。"
                "仅遵循任务包文件所有权; 研究与审查只读。"
                "本上下文通过指令适配, 未声称加载原生角色或建立额外权限隔离。",
                instructions,
                source.read_text(encoding="utf-8"),
            )
        )
        prompt = (
            f"角色: {args.role}。仓库: {root}。\n"
            f"完整任务包: {task_path}\nSHA256: {digest}\n"
            "必须实际完整读取该文件并独立核验, 不能用提示摘要代替; 按任务包执行。"
            "首个工具调用须选用你真实可调用的文件/命令 exec schema, 完整执行以下首读命令。"
            "须保留全部原文及哈希输出, 不得删减文件或用父摘要代替; 缺入口一次报告阻塞并停止。\n"
            f"{first_read}\n"
        )
        command = [
            "codex",
            "exec",
            "--enable",
            "code_mode_host",
            "--disable",
            "multi_agent",
            "--disable",
            "sleep_tool",
            "-c",
            "agents.enabled=false",
            "-c",
            "developer_instructions=" + json.dumps(developer, ensure_ascii=True),
            "--json",
        ]
        if args.resume is not None:
            command.extend(["resume", args.resume])
        command.append("-")
        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            encoding="utf-8",
            cwd=root,
            shell=False,
        )
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except (OSError, ValueError) as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
