from __future__ import annotations

from typing import Sequence

from flask import render_template


def render_email(
    subject: str,
    *,
    greeting: str | None = None,
    intro: str | None = None,
    paragraphs: Sequence[str] | None = None,
    details: Sequence[tuple[str, str]] | None = None,
    message_title: str | None = None,
    message_lines: Sequence[str] | None = None,
    cta_label: str | None = None,
    cta_url: str | None = None,
    footer_lines: Sequence[str] | None = None,
    preheader: str | None = None,
) -> tuple[str, str]:
    """Render matching plain text and HTML e-mail bodies for Motio."""
    context = {
        "subject": subject,
        "greeting": _clean_string(greeting),
        "intro": _clean_string(intro),
        "paragraphs": _clean_list(paragraphs),
        "details": _normalize_details(details),
        "message_block": _normalize_message_block(message_title, message_lines),
        "cta": _normalize_cta(cta_label, cta_url),
        "footer_lines": _clean_list(footer_lines)
        or ["Groeten,", "Motio"],
        "preheader": _clean_string(preheader) or _clean_string(intro) or "",
    }

    text_body = _render_plain_text(context)
    html_body = render_template("email/base.html", **context)
    return text_body, html_body


def _clean_string(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _clean_list(values: Sequence[str] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        cleaned = _clean_string(value)
        if cleaned:
            result.append(cleaned)
    return result


def _normalize_details(details: Sequence[tuple[str, str]] | None) -> list[dict[str, str]]:
    if not details:
        return []
    normalized: list[dict[str, str]] = []
    for label, value in details:
        clean_label = _clean_string(label)
        clean_value = _clean_string(value)
        if clean_label and clean_value:
            normalized.append({"label": clean_label, "value": clean_value})
    return normalized


def _normalize_message_block(
    title: str | None,
    lines: Sequence[str] | None,
) -> dict[str, list[str]] | None:
    msg_lines = _clean_list(lines)
    clean_title = _clean_string(title)
    if not msg_lines and not clean_title:
        return None
    return {
        "title": clean_title,
        "lines": msg_lines,
    }


def _normalize_cta(label: str | None, url: str | None) -> dict[str, str] | None:
    clean_url = _clean_string(url)
    if not clean_url:
        return None
    clean_label = _clean_string(label) or "Bekijk"
    return {"label": clean_label, "url": clean_url}


def _render_plain_text(context: dict) -> str:
    sections: list[list[str]] = []

    def add_section(lines: Sequence[str] | None) -> None:
        cleaned = _clean_list(lines or [])
        if cleaned:
            sections.append(cleaned)

    greeting = context.get("greeting")
    if greeting:
        add_section([greeting])

    intro = context.get("intro")
    if intro:
        add_section([intro])

    for paragraph in context.get("paragraphs", []):
        add_section([paragraph])

    detail_items = context.get("details") or []
    if detail_items:
        add_section([f"{item['label']}: {item['value']}" for item in detail_items])

    message_block = context.get("message_block")
    if message_block:
        block_lines: list[str] = []
        title = message_block.get("title")
        if title:
            block_lines.append(title)
        block_lines.extend(message_block.get("lines", []))
        add_section(block_lines)

    cta = context.get("cta")
    if cta:
        label = cta.get("label", "Bekijk")
        url = cta.get("url", "")
        add_section([f"{label}: {url}"])

    footer = context.get("footer_lines") or []
    if footer:
        add_section(footer)

    if not sections:
        return ""

    text_lines: list[str] = []
    for idx, section in enumerate(sections):
        if idx > 0:
            text_lines.append("")
        text_lines.extend(section)

    return "\n".join(text_lines)
