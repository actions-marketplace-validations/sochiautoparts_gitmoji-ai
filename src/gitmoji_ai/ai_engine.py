"""
AI engine — commit message generation and analysis
"""

import re
import json
import logging
from typing import Optional
from dataclasses import dataclass

from openai import AsyncOpenAI

from gitmoji_ai.config import get_settings

logger = logging.getLogger(__name__)

# === GitMoji definitions ===
GITMOJI_MAP = {
    "feat": "✨",
    "fix": "🐛",
    "docs": "📚",
    "style": "💎",
    "refactor": "♻️",
    "perf": "⚡",
    "test": "✅",
    "build": "📦",
    "ci": "👷",
    "chore": "🔧",
    "revert": "⏪",
    "security": "🔒",
    "i18n": "🌐",
    "accessibility": "♿",
    "analytics": "📈",
    "deps": "➕",
    "remove-deps": "➖",
    "config": "🔧",
    "docker": "🐳",
    "ui": "💄",
    "init": "🎉",
    "wip": "🚧",
    "dead-code": "⚰️",
    "licensing": "📝",
    "boom": "💥",
    "mock": "🧪",
    "typo": "✏️",
    "poo": "💩",
    "merge": "🔀",
    "auth": "🛂",
    "api": "🔌",
    "logging": "🔊",
    "database": "🗃️",
    "cleanup": "🧹",
}

CONVENTIONAL_TYPES = [
    "feat", "fix", "docs", "style", "refactor", "perf",
    "test", "build", "ci", "chore", "revert"
]

# Available commit styles: conventional, emoji, plain (free)
# semantic-release, gitmoji-dict (Pro only)
AVAILABLE_STYLES = ["conventional", "emoji", "plain", "semantic-release", "gitmoji-dict"]
PRO_ONLY_STYLES = ["semantic-release", "gitmoji-dict"]


@dataclass
class CommitSuggestion:
    """A single commit message suggestion"""
    message: str
    type: str
    scope: str
    description: str
    body: str
    emoji: str
    confidence: float


@dataclass
class DiffAnalysis:
    """Analysis of a git diff"""
    files_changed: int
    lines_added: int
    lines_removed: int
    file_types: list[str]
    is_new_feature: bool
    is_bug_fix: bool
    is_refactor: bool
    is_docs: bool
    is_test: bool
    is_config: bool
    summary: str


def analyze_diff(diff_text: str) -> DiffAnalysis:
    """Analyze a git diff to understand what changed"""
    if not diff_text or not diff_text.strip():
        return DiffAnalysis(
            files_changed=0, lines_added=0, lines_removed=0,
            file_types=[], is_new_feature=False, is_bug_fix=False,
            is_refactor=False, is_docs=False, is_test=False,
            is_config=False, summary="No changes detected"
        )

    files_changed = diff_text.count("diff --git")
    lines_added = sum(1 for line in diff_text.split("\n") if line.startswith("+") and not line.startswith("+++"))
    lines_removed = sum(1 for line in diff_text.split("\n") if line.startswith("-") and not line.startswith("---"))

    # Detect file types
    file_types = list(set(
        re.findall(r'\.(\w+)(?:\s|$)', diff_text)
    ))[:10]

    # Detect change type
    diff_lower = diff_text.lower()
    is_new_feature = any(w in diff_lower for w in ["new file", "feat", "add ", "create", "implement"])
    is_bug_fix = any(w in diff_lower for w in ["fix", "bug", "patch", "issue", "resolve"])
    is_refactor = any(w in diff_lower for w in ["refactor", "rename", "move", "reorganize"])
    is_docs = any(w in diff_lower for w in ["readme", "doc", "changelog", ".md"])
    is_test = any(w in diff_lower for w in ["test", "spec", "__test__", ".test.", ".spec."])
    is_config = any(w in diff_lower for w in [".yml", ".yaml", ".json", ".toml", "dockerfile", "makefile"])

    # Quick summary
    parts = []
    if is_new_feature: parts.append("new feature")
    if is_bug_fix: parts.append("bug fix")
    if is_refactor: parts.append("refactoring")
    if is_docs: parts.append("documentation")
    if is_test: parts.append("tests")
    if is_config: parts.append("configuration")
    summary = f"Changed {files_changed} file(s): {', '.join(parts) if parts else 'general changes'}"

    return DiffAnalysis(
        files_changed=files_changed,
        lines_added=lines_added,
        lines_removed=lines_removed,
        file_types=file_types,
        is_new_feature=is_new_feature,
        is_bug_fix=is_bug_fix,
        is_refactor=is_refactor,
        is_docs=is_docs,
        is_test=is_test,
        is_config=is_config,
        summary=summary,
    )


# ============================================================
# System prompts for all 7 languages
# ============================================================

SYSTEM_PROMPT_COMMIT_EN = """You are an expert at writing clear, concise, and conventional git commit messages.

Rules:
1. Follow Conventional Commits format: type(scope): description
2. Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
3. Scope is optional but recommended (e.g., feat(auth): add login)
4. Description: imperative mood, lowercase, no period, max 72 chars
5. Body: explain WHY, not WHAT (the diff shows what changed)
6. Be specific, not generic ("add email validation" not "update code")
7. If there are multiple logical changes, suggest multiple commits

Output format — JSON array of suggestions:
[
  {
    "message": "type(scope): description",
    "type": "feat",
    "scope": "auth",
    "description": "add email validation to login form",
    "body": "Users were able to submit invalid emails...",
    "emoji": "✨",
    "confidence": 0.95
  }
]

Provide 3 variations: one conventional, one with emoji, one detailed.
"""

SYSTEM_PROMPT_COMMIT_RU = """Ты — эксперт по написанию понятных и лаконичных git commit сообщений.

Правила:
1. Формат Conventional Commits: тип(область): описание
2. Типы: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
3. Область опциональна, но рекомендуется (например: feat(auth): добавить логин)
4. Описание: повелительное наклонение, строчные буквы, макс 72 символа
5. Body: объясни ПОЧЕМУ, а не ЧТО
6. Будь конкретным ("добавить валидацию email" а не "обновить код")

Формат вывода — JSON массив:
[
  {
    "message": "тип(область): описание",
    "type": "feat",
    "scope": "auth",
    "description": "добавить валидацию email",
    "body": "Пользователи могли отправлять невалидные email...",
    "emoji": "✨",
    "confidence": 0.95
  }
]

Предложи 3 варианта: классический, с эмодзи, подробный.
"""

SYSTEM_PROMPT_COMMIT_ES = """Eres un experto en escribir mensajes de commit de git claros, concisos y convencionales.

Reglas:
1. Sigue el formato Conventional Commits: tipo(ámbito): descripción
2. Tipos: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
3. El ámbito es opcional pero recomendado (ejemplo: feat(auth): añadir inicio de sesión)
4. Descripción: modo imperativo, minúsculas, sin punto, máximo 72 caracteres
5. Cuerpo: explica POR QUÉ, no QUÉ (el diff muestra qué cambió)
6. Sé específico, no genérico ("añadir validación de email" no "actualizar código")
7. Si hay múltiples cambios lógicos, sugiere múltiples commits

Formato de salida — arreglo JSON de sugerencias:
[
  {
    "message": "tipo(ámbito): descripción",
    "type": "feat",
    "scope": "auth",
    "description": "añadir validación de email al formulario de inicio de sesión",
    "body": "Los usuarios podían enviar emails no válidos...",
    "emoji": "✨",
    "confidence": 0.95
  }
]

Proporciona 3 variaciones: una convencional, una con emoji, una detallada.
"""

SYSTEM_PROMPT_COMMIT_DE = """Du bist ein Experte für das Schreiben klarer, prägnanter und konventioneller Git-Commit-Nachrichten.

Regeln:
1. Folge dem Conventional Commits Format: typ(bereich): beschreibung
2. Typen: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
3. Bereich ist optional aber empfohlen (z.B. feat(auth): login hinzufügen)
4. Beschreibung: Imperativ, Kleinschreibung, kein Punkt, max 72 Zeichen
5. Body: erkläre WARUM, nicht WAS (der Diff zeigt was sich geändert hat)
6. Sei spezifisch, nicht generisch ("E-Mail-Validierung hinzufügen" nicht "Code aktualisieren")
7. Bei mehreren logischen Änderungen, schlage mehrere Commits vor

Ausgabeformat — JSON-Array von Vorschlägen:
[
  {
    "message": "typ(bereich): beschreibung",
    "type": "feat",
    "scope": "auth",
    "description": "E-Mail-Validierung zum Login-Formular hinzufügen",
    "body": "Benutzer konnten ungültige E-Mails senden...",
    "emoji": "✨",
    "confidence": 0.95
  }
]

Biete 3 Varianten: eine konventionelle, eine mit Emoji, eine detaillierte.
"""

SYSTEM_PROMPT_COMMIT_FR = """Vous êtes un expert en rédaction de messages de commit git clairs, concis et conventionnels.

Règles :
1. Suivez le format Conventional Commits : type(portée) : description
2. Types : feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
3. La portée est facultative mais recommandée (ex : feat(auth) : ajouter connexion)
4. Description : mode impératif, minuscules, sans point, max 72 caractères
5. Corps : expliquez POURQUOI, pas QUOI (le diff montre ce qui a changé)
6. Soyez spécifique, pas générique ("ajouter la validation email" pas "mettre à jour le code")
7. S'il y a plusieurs changements logiques, suggérez plusieurs commits

Format de sortie — tableau JSON de suggestions :
[
  {
    "message": "type(portée) : description",
    "type": "feat",
    "scope": "auth",
    "description": "ajouter la validation email au formulaire de connexion",
    "body": "Les utilisateurs pouvaient soumettre des emails invalides...",
    "emoji": "✨",
    "confidence": 0.95
  }
]

Proposez 3 variantes : une conventionnelle, une avec emoji, une détaillée.
"""

SYSTEM_PROMPT_COMMIT_JA = """あなたは明確で簡潔な conventional な git コミットメッセージを書くエキスパートです。

ルール:
1. Conventional Commits フォーマットに従う: type(scope): description
2. タイプ: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
3. スコープはオプションですが推奨されます (例: feat(auth): ログインを追加)
4. 説明: 命令形、小文字、ピリオドなし、最大72文字
5. 本文: なぜ（WHY）を説明、何（WHAT）は不要（diffに表示されます）
6. 具体的に書く（「コードを更新」ではなく「メールバリデーションを追加」）
7. 複数の論理的変更がある場合は、複数のコミットを提案

出力形式 — 提案のJSON配列:
[
  {
    "message": "type(scope): description",
    "type": "feat",
    "scope": "auth",
    "description": "ログインフォームにメールバリデーションを追加",
    "body": "ユーザーが無効なメールを送信できていました...",
    "emoji": "✨",
    "confidence": 0.95
  }
]

3つのバリエーションを提供：従来型、絵文字付き、詳細版。
"""

SYSTEM_PROMPT_COMMIT_ZH = """你是一位撰写清晰、简洁、规范化 git 提交消息的专家。

规则：
1. 遵循 Conventional Commits 格式：type(scope): description
2. 类型：feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
3. scope 是可选的但建议使用（例如：feat(auth): 添加登录）
4. 描述：祈使语气，不加句号，最多72个字符
5. 正文：解释为什么（WHY），而不是什么（WHAT）（diff 已经显示了变更内容）
6. 要具体，不要笼统（"添加邮箱验证" 而不是 "更新代码"）
7. 如果有多个逻辑变更，建议多个提交

输出格式 — 建议的 JSON 数组：
[
  {
    "message": "type(scope): description",
    "type": "feat",
    "scope": "auth",
    "description": "在登录表单中添加邮箱验证",
    "body": "用户之前可以提交无效的邮箱地址...",
    "emoji": "✨",
    "confidence": 0.95
  }
]

提供3个变体：规范型、emoji型、详细型。
"""

# Language → system prompt mapping
LANGUAGE_PROMPTS = {
    "en": SYSTEM_PROMPT_COMMIT_EN,
    "ru": SYSTEM_PROMPT_COMMIT_RU,
    "es": SYSTEM_PROMPT_COMMIT_ES,
    "de": SYSTEM_PROMPT_COMMIT_DE,
    "fr": SYSTEM_PROMPT_COMMIT_FR,
    "ja": SYSTEM_PROMPT_COMMIT_JA,
    "zh": SYSTEM_PROMPT_COMMIT_ZH,
}

# ============================================================
# Commit style profiles (appended to the base language prompt)
# ============================================================

STYLE_PROMPTS = {
    "conventional": "",  # Default — uses the base language prompt as-is
    "emoji": """

ADDITIONAL STYLE RULE — Emoji style:
- Start the commit message with the appropriate gitmoji emoji
- Format: emoji description (no type prefix)
- Example: ✨ add email validation to login form
- Example: 🐛 fix crash on startup when config is missing""",
    "plain": """

ADDITIONAL STYLE RULE — Plain style:
- No type prefix, no emoji, just a clear description
- Use imperative mood, capitalize first letter
- Example: Add email validation to login form
- Example: Fix crash on startup when config is missing""",
    "semantic-release": """

ADDITIONAL STYLE RULE — Semantic Release style (Pro only):
- Follow semantic-release conventions strictly
- Use feat: for features (triggers MINOR release)
- Use fix: for bug fixes (triggers PATCH release)
- Use feat!: or fix!: for breaking changes (triggers MAJOR release)
- Include BREAKING CHANGE: in body for breaking changes
- Always include scope when possible
- Example: feat(api)!: change authentication endpoint response format
- Body must include: BREAKING CHANGE: The /auth endpoint now returns JWT instead of session token""",
    "gitmoji-dict": """

ADDITIONAL STYLE RULE — GitMoji Dictionary style (Pro only):
- Use the full gitmoji dictionary with detailed emoji selection
- Each commit MUST start with the most specific gitmoji from this extended list:
  ✨ feat, 🐛 fix, 📚 docs, 💎 style, ♻️ refactor, ⚡ perf, ✅ test,
  📦 build, 👷 ci, 🔧 chore, ⏪ revert, 🔒 security, 🌐 i18n,
  ♿ accessibility, 📈 analytics, ➕ add dependency, ➖ remove dependency,
  🐳 docker, 💄 ui/cosmetics, 🎉 initial commit, 🚧 wip,
  ⚰️ remove dead code, 📝 add/update license, 💥 introduce breaking changes,
  🧪 add failing test, ✏️ fix typo, 🔀 merge branch, 🛂 auth/permissions,
  🔌 add/update API, 🔊 add/update logs, 🗃️ add/update database,
  🧹 code cleanup, 💩 write bad code that needs refactoring
- Format: emoji description
- Example: 🌐 add Spanish translation for login page
- Example: ♿ improve keyboard navigation in modal dialog
- Example: 📈 add analytics tracking for user onboarding flow""",
}


def get_system_prompt(language: str, style: str) -> str:
    """Get the combined system prompt for a given language and style."""
    base = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["en"])
    style_addon = STYLE_PROMPTS.get(style, "")
    return base + style_addon


async def generate_commit_messages(
    diff_text: str,
    language: str = "en",
    style: str = "conventional",
    num_suggestions: int = 3,
) -> list[CommitSuggestion]:
    """Generate AI-powered commit message suggestions from a git diff"""
    settings = get_settings()

    # Check if style requires Pro
    if style in PRO_ONLY_STYLES:
        from gitmoji_ai.usage import is_pro
        if not is_pro():
            logger.warning(f"Style '{style}' requires Pro. Falling back to 'conventional'.")
            style = "conventional"

    if not settings.openai_api_key:
        return _fallback_commit_messages(diff_text, style)

    # Truncate very large diffs
    max_chars = 12000
    if len(diff_text) > max_chars:
        diff_text = diff_text[:max_chars] + "\n\n... (diff truncated)"

    system_prompt = get_system_prompt(language, style)

    user_prompt = f"""Generate commit messages for this diff:

```diff
{diff_text}
```

Style: {style}
Language: {language}
Provide {num_suggestions} variations."""

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
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1500,
            temperature=0.7,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        return _parse_commit_suggestions(content, style)

    except Exception as e:
        logger.error(f"AI generation failed: {e}")
        return _fallback_commit_messages(diff_text, style)


def _parse_commit_suggestions(content: str, style: str) -> list[CommitSuggestion]:
    """Parse AI response into CommitSuggestion objects"""
    try:
        data = json.loads(content)
        # Check the type FIRST — the model may return a bare JSON array
        # instead of an object with a "suggestions" key.
        if isinstance(data, list):
            suggestions = data
        elif isinstance(data, dict):
            suggestions = data.get("suggestions", data.get("commits", []))
        else:
            suggestions = []
        if not isinstance(suggestions, list):
            suggestions = []

        results = []
        for s in suggestions[:3]:
            if not isinstance(s, dict):
                continue
            msg_type = s.get("type", "chore")
            emoji = s.get("emoji", GITMOJI_MAP.get(msg_type, "🔧"))
            results.append(CommitSuggestion(
                message=s.get("message", s.get("commit", "chore: update")),
                type=msg_type,
                scope=s.get("scope", ""),
                description=s.get("description", ""),
                body=s.get("body", ""),
                emoji=emoji,
                confidence=s.get("confidence", 0.8),
            ))

        return results if results else _fallback_from_text(content, style)

    except json.JSONDecodeError:
        return _fallback_from_text(content, style)


def _fallback_from_text(content: str, style: str) -> list[CommitSuggestion]:
    """Fallback parsing when JSON fails"""
    lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")]
    results = []
    for line in lines[:3]:
        line = line.lstrip("-•*0-9. ")
        msg_type = "chore"
        for t in CONVENTIONAL_TYPES:
            if line.startswith(t):
                msg_type = t
                break
        results.append(CommitSuggestion(
            message=line[:100],
            type=msg_type,
            scope="",
            description=line,
            body="",
            emoji=GITMOJI_MAP.get(msg_type, "🔧"),
            confidence=0.5,
        ))
    return results if results else _fallback_commit_messages("", style)


def _fallback_commit_messages(diff_text: str, style: str) -> list[CommitSuggestion]:
    """Generate basic commit messages without AI (offline fallback)"""
    analysis = analyze_diff(diff_text)

    # Determine primary type
    if analysis.is_new_feature:
        msg_type, emoji = "feat", "✨"
    elif analysis.is_bug_fix:
        msg_type, emoji = "fix", "🐛"
    elif analysis.is_docs:
        msg_type, emoji = "docs", "📚"
    elif analysis.is_test:
        msg_type, emoji = "test", "✅"
    elif analysis.is_refactor:
        msg_type, emoji = "refactor", "♻️"
    elif analysis.is_config:
        msg_type, emoji = "chore", "🔧"
    else:
        msg_type, emoji = "chore", "🔧"

    if style == "emoji":
        message = f"{emoji} {analysis.summary}"
    elif style == "plain":
        message = analysis.summary.capitalize()
    elif style == "semantic-release":
        # Fallback for semantic-release — same as conventional but with breaking change note
        message = f"{msg_type}: {analysis.summary}"
    elif style == "gitmoji-dict":
        # Fallback for gitmoji-dict — same as emoji
        message = f"{emoji} {analysis.summary}"
    else:
        message = f"{msg_type}: {analysis.summary}"

    return [
        CommitSuggestion(
            message=message,
            type=msg_type,
            scope="",
            description=analysis.summary,
            body="",
            emoji=emoji,
            confidence=0.6,
        ),
    ]
