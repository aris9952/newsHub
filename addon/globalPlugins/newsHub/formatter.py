# -*- coding: utf-8 -*-
"""
Accessible text formatting and reading-time calculation module for NVDA.

Converts structured `ContentBlock` items (headings, paragraphs, ordered/unordered lists,
blockquotes, news data tables, image captions, and credits) into structured multiline
plain text optimized for line-by-line and paragraph-by-paragraph NVDA navigation in both
Indonesian and English.
"""

from typing import Any, Dict, List
from .i18n import tr
from .models import Article, ArticleStatus


WORDS_PER_MINUTE_DEFAULT = 180  # Average news reading speed in words per minute


def calculate_reading_time_minutes(blocks: List[Dict[str, Any]], summary: str = "") -> int:
	"""Calculate estimated reading time in minutes based on actual word count."""
	total_words = 0
	for block in blocks or []:
		b_type = block.get("type", "p")
		if b_type in ("p", "h2", "h3", "h4", "blockquote", "caption", "credit"):
			total_words += len((block.get("text") or "").split())
		elif b_type in ("ul", "ol"):
			for item in block.get("items") or []:
				total_words += len(str(item).split())
		elif b_type == "table":
			for h in block.get("headers") or []:
				total_words += len(str(h).split())
			for row in block.get("rows") or []:
				for cell in row:
					total_words += len(str(cell).split())

	if total_words == 0 and summary:
		total_words = len(summary.split())

	if total_words <= 0:
		return 0
	return max(1, round(total_words / float(WORDS_PER_MINUTE_DEFAULT)))


def format_table_block_for_nvda(block: Dict[str, Any], lang: str = "") -> str:
	"""
	Convert an HTML table block into a textual representation that preserves the relationship
	between column headers and cell values for NVDA screen reader users.
	"""
	headers: List[str] = [str(h).strip() for h in (block.get("headers") or []) if str(h).strip()]
	rows: List[List[str]] = block.get("rows") or []

	lines: List[str] = [tr("fmt_table_start", lang=lang)]
	if headers:
		lines.append(tr("fmt_table_columns", lang=lang, columns=" | ".join(headers)))

	for row_idx, row in enumerate(rows, start=1):
		cells = [str(c).strip() for c in row]
		if not any(cells):
			continue
		if headers and len(headers) == len(cells):
			pairs = [f"{headers[i]}: {cells[i]}" for i in range(len(cells)) if cells[i]]
			row_content = "; ".join(pairs)
		else:
			row_content = " | ".join(c for c in cells if c)
		lines.append(tr("fmt_table_row", lang=lang, row_num=row_idx, content=row_content))

	lines.append(tr("fmt_table_end", lang=lang))
	return "\r\n".join(lines)


def format_article_for_reading(
	article: Article,
	rubric_name: str = "",
	paragraph_spacing: str = "normal",
	lang: str = "",
) -> str:
	"""
	Format an `Article` object into structured multiline text for the NVDA reading area:
	- Preserves title and metadata (rubric, publication time, author, editor, estimated reading time).
	- Separates paragraphs cleanly (never collapsing into a single giant paragraph).
	- Preserves subheading markers, blockquotes, numbered/bulleted lists, and textual tables.
	- Provides transparent notices when content is only partially loaded or failed.
	"""
	sep = "\r\n\r\n\r\n" if paragraph_spacing == "wide" else "\r\n\r\n"
	sections: List[str] = []

	# 1. Main Headline
	title_text = article.title or tr("fmt_title_missing", lang=lang)
	sections.append(title_text)

	# 2. Article Metadata
	meta_lines: List[str] = []
	cat_display = article.category_label or rubric_name
	if cat_display:
		meta_lines.append(tr("fmt_rubric", lang=lang, value=cat_display))
	if article.published_at:
		meta_lines.append(tr("fmt_published_at", lang=lang, value=article.published_at))
	if article.author:
		meta_lines.append(tr("fmt_author", lang=lang, value=article.author))
	if article.editor:
		meta_lines.append(tr("fmt_editor", lang=lang, value=article.editor))
	if article.reading_time_minutes > 0:
		meta_lines.append(tr("fmt_reading_time", lang=lang, minutes=article.reading_time_minutes))
	if meta_lines:
		sections.append("\r\n".join(meta_lines))

	# 3. Loading / Error / Partial Status Handling
	if article.content_status == ArticleStatus.CONTENT_LOADING:
		sections.append(tr("fmt_loading_body", lang=lang))
		if article.summary:
			sections.append(tr("fmt_initial_summary", lang=lang, summary=article.summary))
		return sep.join(sections)

	if article.content_status == ArticleStatus.CONTENT_FAILED:
		err_detail = article.error_message or tr("fmt_failed_default_reason", lang=lang)
		sections.append(tr("fmt_failed_notice", lang=lang, reason=err_detail))
		if article.summary:
			sections.append(tr("fmt_available_summary", lang=lang, summary=article.summary))
		return sep.join(sections)

	if article.content_status == ArticleStatus.CONTENT_PARTIAL:
		sections.append(tr("fmt_partial_notice", lang=lang))

	# 4. Summary / Deck (when distinct from the first paragraph)
	first_p_text = ""
	for b in article.content:
		if b.get("type") == "p" and b.get("text"):
			first_p_text = b["text"].strip()
			break

	if article.summary and article.summary.strip() != first_p_text:
		sections.append(tr("fmt_summary_label", lang=lang, summary=article.summary.strip()))

	# 5. Main Article Body Blocks
	body_blocks: List[str] = []
	for block in article.content:
		b_type = block.get("type", "p")
		b_text = (block.get("text") or "").strip()

		if b_type in ("h2", "h3", "h4"):
			if b_text:
				body_blocks.append(tr("fmt_subheading", lang=lang, text=b_text))
		elif b_type == "blockquote":
			if b_text:
				body_blocks.append(tr("fmt_quote", lang=lang, text=b_text))
		elif b_type == "caption":
			if b_text:
				body_blocks.append(tr("fmt_caption", lang=lang, text=b_text))
		elif b_type == "credit":
			if b_text:
				body_blocks.append(tr("fmt_credit", lang=lang, text=b_text))
		elif b_type == "ul":
			items = [str(it).strip() for it in (block.get("items") or []) if str(it).strip()]
			if items:
				formatted_items = "\r\n".join(f"• {it}" for it in items)
				body_blocks.append(formatted_items)
		elif b_type == "ol":
			items = [str(it).strip() for it in (block.get("items") or []) if str(it).strip()]
			if items:
				formatted_items = "\r\n".join(f"{idx}. {it}" for idx, it in enumerate(items, start=1))
				body_blocks.append(formatted_items)
		elif b_type == "table":
			body_blocks.append(format_table_block_for_nvda(block, lang=lang))
		else:
			if b_text:
				body_blocks.append(b_text)

	if body_blocks:
		sections.extend(body_blocks)
	elif article.summary:
		sections.append(article.summary)

	if article.url:
		sections.append(tr("fmt_source_url", lang=lang, url=article.url))

	return sep.join(sections)


def format_article_selection_announcement(
	article: Article,
	index: int,
	total: int,
	rubric_name: str = "",
	lang: str = "",
) -> str:
	"""
	Build a concise NVDA announcement when an article is selected or finishes loading,
	without automatically reading out the entire article body.
	"""
	parts: List[str] = [tr("ann_article_pos", lang=lang, index=index + 1, total=total, title=article.title)]
	cat = article.category_label or rubric_name
	if cat:
		parts.append(tr("ann_article_rubric", lang=lang, rubric=cat))
	if article.published_at:
		parts.append(tr("ann_article_published", lang=lang, published_at=article.published_at))
	if article.reading_time_minutes > 0:
		parts.append(tr("ann_article_reading_time", lang=lang, minutes=article.reading_time_minutes))
	return " ".join(parts)
