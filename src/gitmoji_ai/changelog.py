"""
Changelog generator — AI-powered release notes and changelogs
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from openai import AsyncOpenAI

from gitmoji_ai.config import get_settings
from gitmoji_ai.git_ops import get_recent_commits, get_commit_tags

logger = logging.getLogger(__name__)


@dataclass
class ChangelogEntry:
    """A single changelog entry"""
    type: str
    scope: str
    description: str
    hash: str
    author: str
    date: str


SYSTEM_PROMPT_CHANGELOG = """You are an expert at writing beautiful, well-organized changelogs.

Rules:
1. Group changes by type: Features, Bug Fixes, Improvements, Documentation, etc.
2. Write in user-friendly language (not technical jargon)
3. Each entry should start with a verb in imperative mood
4. Include breaking changes prominently
5. Keep it concise but informative
6. Format as Markdown

Output a complete changelog section in Markdown format.
"""

SYSTEM_PROMPT_CHANGELOG_RU = """Ты — эксперт по написанию красивых и понятных списков изменений.

Правила:
1. Группируй изменения по типу: Новые функции, Исправления, Улучшения, Документация и т.д.
2. Пиши понятным языком для пользователей, а не техническим жаргоном
3. Каждый пункт начинай с глагола в повелительном наклонении
4. Критические изменения выдели prominently
5. Будь кратким, но информативным
6. Формат — Markdown

Выведи полный раздел changelog в формате Markdown.
"""


SYSTEM_PROMPT_CHANGELOG_ES = """Eres un experto en escribir listas de cambios bonitas y bien organizadas.

Reglas:
1. Agrupa los cambios por tipo: Nuevas funciones, Correcciones, Mejoras, Documentación, etc.
2. Escribe en lenguaje amigable para el usuario (sin jerga técnica)
3. Cada entrada debe comenzar con un verbo en modo imperativo
4. Incluye los cambios importantes de forma destacada
5. Sé conciso pero informativo
6. Formato Markdown

Genera una sección completa de changelog en formato Markdown.
"""

SYSTEM_PROMPT_CHANGELOG_DE = """Du bist ein Experte für das Schreiben schöner, gut organisierter Changelogs.

Regeln:
1. Gruppiere Änderungen nach Typ: Neue Funktionen, Fehlerbehebungen, Verbesserungen, Dokumentation usw.
2. Schreibe in benutzerfreundlicher Sprache (kein Fachjargon)
3. Jeder Eintrag sollte mit einem Verb im Imperativ beginnen
4. Brechende Änderungen hervorheben
5. Sei prägnant aber informativ
6. Format als Markdown

Erstelle einen vollständigen Changelog-Abschnitt im Markdown-Format.
"""

SYSTEM_PROMPT_CHANGELOG_FR = """Vous êtes un expert en rédaction de changelogs beaux et bien organisés.

Règles :
1. Groupez les changements par type : Nouvelles fonctionnalités, Corrections, Améliorations, Documentation, etc.
2. Écrivez dans un langage convivial (sans jargon technique)
3. Chaque entrée doit commencer par un verbe à l'impératif
4. Incluez les changements cassants de manière visible
5. Soyez concis mais informatif
6. Format Markdown

Générez une section de changelog complète au format Markdown.
"""

SYSTEM_PROMPT_CHANGELOG_JA = """あなたは美しく整理されたチェンジログを書くエキスパートです。

ルール:
1. 変更をタイプ別にグループ化：新機能、バグ修正、改善、ドキュメントなど
2. ユーザーフレンドリーな言葉で書く（技術用語を避ける）
3. 各項目は命令形の動詞で始める
4. 破壊的変更を目立たせる
5. 簡潔だが情報豊かに
6. Markdown形式

Markdown形式で完全なチェンジログセクションを出力してください。
"""

SYSTEM_PROMPT_CHANGELOG_ZH = """你是一位撰写美观、组织良好的变更日志的专家。

规则：
1. 按类型分组变更：新功能、错误修复、改进、文档等
2. 使用用户友好的语言（避免技术术语）
3. 每个条目以祈使语气的动词开头
4. 突出显示破坏性变更
5. 简洁但信息丰富
6. Markdown 格式

生成完整的 Markdown 格式变更日志部分。
"""

CHANGELOG_LANGUAGE_PROMPTS = {
    "en": SYSTEM_PROMPT_CHANGELOG,
    "ru": SYSTEM_PROMPT_CHANGELOG_RU,
    "es": SYSTEM_PROMPT_CHANGELOG_ES,
    "de": SYSTEM_PROMPT_CHANGELOG_DE,
    "fr": SYSTEM_PROMPT_CHANGELOG_FR,
    "ja": SYSTEM_PROMPT_CHANGELOG_JA,
    "zh": SYSTEM_PROMPT_CHANGELOG_ZH,
}

CHANGELOG_TEMPLATE = """# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

{entries}
"""

KEEPACHANGELOG_SECTION = """## [{version}] - {date}

{content}
"""

ANGULAR_SECTION = """## {version} ({date})

{content}
"""


def parse_commit_subject(subject: str) -> ChangelogEntry:
    """Parse a conventional commit subject into a ChangelogEntry"""
    # Pattern: type(scope): description or type: description
    pattern = r'^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(?:\(([^)]+)\))?:\s*(.+)$'
    match = re.match(pattern, subject)

    if match:
        return ChangelogEntry(
            type=match.group(1),
            scope=match.group(2) or "",
            description=match.group(3),
            hash="",
            author="",
            date="",
        )

    return ChangelogEntry(
        type="chore",
        scope="",
        description=subject,
        hash="",
        author="",
        date="",
    )


def group_commits_by_type(commits: list[dict]) -> dict[str, list[ChangelogEntry]]:
    """Group commits by their type for changelog organization"""
    groups: dict[str, list[ChangelogEntry]] = {
        "Features": [],
        "Bug Fixes": [],
        "Improvements": [],
        "Documentation": [],
        "Performance": [],
        "Tests": [],
        "Build & CI": [],
        "Other": [],
    }

    type_map = {
        "feat": "Features",
        "fix": "Bug Fixes",
        "refactor": "Improvements",
        "style": "Improvements",
        "docs": "Documentation",
        "perf": "Performance",
        "test": "Tests",
        "build": "Build & CI",
        "ci": "Build & CI",
        "chore": "Build & CI",
        "revert": "Other",
    }

    for commit in commits:
        entry = parse_commit_subject(commit["subject"])
        entry.hash = commit["hash"][:7]
        entry.author = commit["author"]
        entry.date = commit["date"]

        group = type_map.get(entry.type, "Other")
        groups[group].append(entry)

    return {k: v for k, v in groups.items() if v}


async def generate_changelog(
    version: str = "Unreleased",
    repo_path: str = ".",
    language: str = "en",
    format_style: str = "keepachangelog",
    since_tag: Optional[str] = None,
    use_ai: bool = True,
) -> str:
    """Generate a complete changelog"""
    settings = get_settings()

    # Get commits
    commits = get_recent_commits(100, repo_path)

    # Filter by tag if specified
    if since_tag:
        tag_commits = get_commit_tags(repo_path)
        filtered = []
        for c in commits:
            if c["hash"] in tag_commits and tag_commits[c["hash"]] == since_tag:
                break
            filtered.append(c)
        commits = filtered

    if not commits:
        return "No commits found for changelog."

    # Group by type
    grouped = group_commits_by_type(commits)

    # Generate content
    if use_ai and settings.openai_api_key:
        content = await _ai_changelog(grouped, commits, language)
    else:
        content = _manual_changelog(grouped)

    # Format
    today = datetime.now().strftime("%Y-%m-%d")
    if format_style == "angular":
        section = ANGULAR_SECTION.format(version=version, date=today, content=content)
    else:
        section = KEEPACHANGELOG_SECTION.format(version=version, date=today, content=content)

    return section


def _manual_changelog(grouped: dict[str, list[ChangelogEntry]]) -> str:
    """Generate changelog without AI"""
    sections = []
    emoji_map = {
        "Features": "✨",
        "Bug Fixes": "🐛",
        "Improvements": "♻️",
        "Documentation": "📚",
        "Performance": "⚡",
        "Tests": "✅",
        "Build & CI": "👷",
        "Other": "🔧",
    }

    for group_name, entries in grouped.items():
        emoji = emoji_map.get(group_name, "🔧")
        lines = [f"### {emoji} {group_name}", ""]
        for entry in entries:
            scope = f"**{entry.scope}**: " if entry.scope else ""
            hash_ref = f"({entry.hash})" if entry.hash else ""
            lines.append(f"- {scope}{entry.description.capitalize()} {hash_ref}")
        lines.append("")
        sections.append("\n".join(lines))

    return "\n".join(sections)


async def _ai_changelog(
    grouped: dict[str, list[ChangelogEntry]],
    commits: list[dict],
    language: str,
) -> str:
    """Generate AI-enhanced changelog"""
    settings = get_settings()

    # Prepare commit summary for AI
    commit_summary = "\n".join(
        f"- {c['subject']} ({c['hash'][:7]})" for c in commits[:50]
    )

    system_prompt = CHANGELOG_LANGUAGE_PROMPTS.get(language, CHANGELOG_LANGUAGE_PROMPTS["en"])

    try:
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=60.0,
            max_retries=2,
        )

        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Generate changelog from these commits:\n\n{commit_summary}"},
            ],
            max_tokens=2000,
            temperature=0.5,
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"AI changelog generation failed: {e}")
        return _manual_changelog(grouped)


def _strip_section_header(section: str) -> str:
    """Drop the leading '## ...' heading line from a generated section."""
    lines = section.splitlines()
    if lines and lines[0].lstrip().startswith("## "):
        return "\n".join(lines[1:]).strip()
    return section.strip()


def update_changelog_file(
    new_section: str,
    changelog_path: str = "CHANGELOG.md",
    format_style: str = "keepachangelog",
    version: Optional[str] = None,
) -> bool:
    """Insert a new section into an existing CHANGELOG.md (Keep a Changelog order).

    - version "Unreleased": the new entries are merged INTO the existing
      '## [Unreleased]' section, right after its header (newest first).
    - a concrete version: the new '## [version] - date' section is inserted
      right AFTER the whole Unreleased section, before the next '## '
      heading (versions in descending order).
    """
    path = Path(changelog_path)

    if not path.exists():
        content = CHANGELOG_TEMPLATE.format(entries=new_section)
        path.write_text(content, encoding="utf-8")
        return True

    existing = path.read_text(encoding="utf-8")

    if version is None:
        # Detect the version from the generated section header
        # ("## [1.2.0] - date" for keepachangelog, "## 1.2.0 (date)" for angular)
        match = re.match(r"\s*## \[?([^\]\s]+)\]?", new_section)
        version = match.group(1) if match else "Unreleased"

    if format_style == "keepachangelog":
        marker = "## [Unreleased]"
        marker_idx = existing.find(marker)
        if marker_idx != -1 and version == "Unreleased":
            # Merge new entries into the existing Unreleased section
            # (right after the header, before the existing content)
            line_end = existing.find("\n", marker_idx)
            insert_at = line_end + 1 if line_end != -1 else len(existing)
            body = _strip_section_header(new_section)
            updated = (
                existing[:insert_at].rstrip("\n") + "\n\n" + body + "\n\n"
                + existing[insert_at:].lstrip("\n")
            )
        elif marker_idx != -1:
            # Concrete version — insert AFTER the whole Unreleased section,
            # before the next '## ' heading (or at the end of the file)
            next_header = existing.find("\n## ", marker_idx)
            insert_at = next_header + 1 if next_header != -1 else len(existing)
            updated = (
                existing[:insert_at].rstrip("\n") + "\n\n" + new_section.strip("\n") + "\n\n"
                + existing[insert_at:].lstrip("\n")
            )
        else:
            # No Unreleased section yet — add the new section before the first
            # existing '## ' heading, or append at the end of the file
            first_header = existing.find("\n## ")
            insert_at = first_header + 1 if first_header != -1 else len(existing)
            tail = existing[insert_at:].lstrip("\n")
            if tail:
                updated = (
                    existing[:insert_at].rstrip("\n") + "\n\n" + new_section.strip("\n") + "\n\n" + tail
                )
            else:
                updated = existing.rstrip("\n") + "\n\n" + new_section.strip("\n") + "\n"
    else:
        # angular and other formats — insert after the file header
        idx = existing.find("\n\n") + 2 if "\n\n" in existing else len(existing)
        updated = existing[:idx] + "\n" + new_section + "\n" + existing[idx:]

    path.write_text(updated, encoding="utf-8")
    return True
