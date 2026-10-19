# -*- coding: utf-8 -*-
"""
Accessible text and HTML Browse Mode (`ui.browseableMessage`) formatting and
reading-time calculation module for NewsHub for NVDA.

Provides:
- `format_article_for_reading(article, ...)`: Formats an `Article` into structured
  multiline text for the in-dialog reading area (`wx.TextCtrl` with `TE_MULTILINE | TE_READONLY | TE_RICH2`),
  ensuring instant, conflict-free line-by-line and paragraph-by-paragraph NVDA navigation.
- `format_article_html(article, ...)`: Formats an `Article` into clean, semantic HTML
  (following the proven `kompasTeknoReader` `format_article_html` architecture) for
  NVDA's native `ui.browseableMessage(html_doc, title=..., isHtml=True)` HTML Browse Mode,
  supporting headings (`h1`-`h4`), paragraphs (`p`), blockquotes (`blockquote`),
  lists (`ul`/`ol`), tables (`table`), inline photos (`figure`/`img`/`figcaption`),
  inline videos (`video`/`a`), and original source links (`a`).
"""

import html
import re
from typing import Any, Dict, List, Set

try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	def _(s: str) -> str:
		return s

from .models import Article, ArticleStatus


WORDS_PER_MINUTE_DEFAULT = 180  # Average news reading speed in words per minute


def calculate_reading_time_minutes(blocks: List[Dict[str, Any]], summary: str = "") -> int:
	"""Calculate estimated reading time in minutes based on actual word count."""
	total_words = 0
	for block in blocks or []:
		b_type = block.get("type", "p")
		if b_type in ("p", "h2", "h3", "h4", "blockquote", "caption", "credit", "image", "video"):
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
	Convert an HTML table block into a clear textual representation that preserves the
	relationship between column headers and cell values for NVDA reading in `wx.TextCtrl`.
	"""
	headers: List[str] = [str(h).strip() for h in (block.get("headers") or []) if str(h).strip()]
	rows: List[List[str]] = block.get("rows") or []

	lines: List[str] = [_("[News Data Table]")]
	if headers:
		lines.append(_("Table Columns: {columns}").format(columns=" | ".join(headers)))

	for row_idx, row in enumerate(rows, start=1):
		cells = [str(c).strip() for c in row]
		if not any(cells):
			continue
		if headers and len(headers) == len(cells):
			pairs = [f"{headers[i]}: {cells[i]}" for i in range(len(cells)) if cells[i]]
			row_content = "; ".join(pairs)
		else:
			row_content = " | ".join(c for c in cells if c)
		lines.append(_("Row {row_num}: {content}").format(row_num=row_idx, content=row_content))

	lines.append(_("[End of Table]"))
	return "\r\n".join(lines)


def format_table_block_as_html(block: Dict[str, Any]) -> str:
	"""
	Convert a table block into a semantic HTML `<table border='1'>` with `<thead>`, `<th>`,
	and `<td>` (matching `kompasTeknoReader`) so NVDA table navigation commands
	(T and Ctrl+Alt+Arrow keys) work natively inside `ui.browseableMessage(..., isHtml=True)`.
	"""
	headers: List[str] = [str(h).strip() for h in (block.get("headers") or []) if str(h).strip()]
	rows: List[List[str]] = block.get("rows") or []

	ths = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
	trs: List[str] = []
	for row in rows:
		cells = [str(c).strip() for c in row]
		if not any(cells):
			continue
		tds = "".join(f"<td>{html.escape(c)}</td>" for c in cells)
		trs.append(f"<tr>{tds}</tr>")

	thead_html = f"<thead><tr>{ths}</tr></thead>" if ths else ""
	return f"<table border='1'>{thead_html}<tbody>{''.join(trs)}</tbody></table>"


def _is_direct_video_stream(url: str) -> bool:
	"""Return True if the URL points directly to an HTML5-playable video stream file."""
	if not url:
		return False
	low = url.lower().split("?")[0]
	return any(low.endswith(ext) or f"{ext}/" in low for ext in (".mp4", ".webm", ".ogg", ".ogv", ".m3u8"))


def _guess_video_mime_type(url: str) -> str:
	"""Return the MIME type for an HTML5 `<source>` tag based on the stream URL."""
	low = (url or "").lower().split("?")[0]
	if low.endswith(".webm"):
		return "video/webm"
	if low.endswith(".ogg") or low.endswith(".ogv"):
		return "video/ogg"
	if low.endswith(".m3u8"):
		return "application/x-mpegURL"
	return "video/mp4"


def _render_inline_photo_html(url: str, caption: str, index: int = 0) -> str:
	"""
	Render a photo inline for `ui.browseableMessage(..., isHtml=True)` using semantic
	`<figure>`, `<img src='...' alt='...'>`, `<figcaption>`, and a clickable link.
	"""
	esc_url = html.escape((url or "").strip())
	if not esc_url:
		return ""
	clean_cap = " ".join((caption or "").split()).strip()
	esc_cap = html.escape(clean_cap or _("Article Photo"))
	if index > 0:
		photo_lbl = html.escape(_("Photo {num}:").format(num=index))
		cap_inner = f"<strong>{photo_lbl}</strong> {esc_cap}"
	else:
		cap_prefix = html.escape(_("Image Caption: {text}").format(text=clean_cap)) if clean_cap else esc_cap
		cap_inner = cap_prefix
	open_photo_lbl = html.escape(_("View Photo"))
	return (
		f"<figure>"
		f"<img src='{esc_url}' alt='{esc_cap}' />"
		f"<figcaption><p>{cap_inner} | <a href='{esc_url}'>{open_photo_lbl}</a></p></figcaption>"
		f"</figure>"
	)


def _render_inline_video_html(
	url: str,
	caption: str,
	provider: str = "",
	thumbnail_url: str = "",
	stream_url: str = "",
	index: int = 1,
) -> str:
	"""
	Render a video inline for `ui.browseableMessage(..., isHtml=True)` using semantic
	`<figure>`, `<video controls>`, `<figcaption>`, and a direct clickable link so the user
	can play or open the video directly inside NVDA Browse Mode.
	"""
	raw_url = (url or "").strip()
	raw_stream = (stream_url or "").strip()
	if not raw_url and not raw_stream:
		return ""

	if not raw_stream and _is_direct_video_stream(raw_url):
		raw_stream = raw_url

	target_link = raw_stream or raw_url
	esc_link = html.escape(target_link)
	clean_cap = " ".join((caption or "").split()).strip() or _("Article Video")
	esc_cap = html.escape(clean_cap)
	esc_prov = html.escape((provider or "Video").strip())
	video_lbl = html.escape(_("Video {num} ({provider}):").format(num=index, provider=esc_prov))
	play_lbl = html.escape(_("Play Video"))
	poster_attr = f" poster='{html.escape(thumbnail_url.strip())}'" if thumbnail_url and thumbnail_url.strip() else ""

	parts: List[str] = ["<figure>"]
	if raw_stream:
		esc_stream = html.escape(raw_stream)
		mime_type = _guess_video_mime_type(raw_stream)
		parts.append(
			f"<video controls='controls' preload='metadata'{poster_attr} src='{esc_stream}'>"
			f"<source src='{esc_stream}' type='{mime_type}' />"
			f"</video>"
		)
	parts.append(
		f"<figcaption><p><strong>{video_lbl}</strong> {esc_cap} | "
		f"<a href='{esc_link}'>{play_lbl}</a></p></figcaption>"
	)
	parts.append("</figure>")
	return "".join(parts)


def format_article_html(
	article: Article,
	rubric_name: str = "",
	paragraph_spacing: str = "normal",
	lang: str = "",
	color_theme: str = "light",
	font_scale: int = 100,
	font_family: str = "sans_serif",
) -> str:
	"""
	Format an `Article` object into a clean, structured HTML fragment for NVDA's native
	`ui.browseableMessage(html_doc, title=..., isHtml=True)` (HTML Browse Mode),
	modeled directly on `kompasTeknoReader`'s `format_article_html`:
	- Emits pure semantic HTML tags (`<p>`, `<h1>`, `<h2>`, `<h3>`, `<h4>`, `<aside>`,
	  `<blockquote>`, `<ul>`, `<ol>`, `<li>`, `<table border='1'>`, `<figure>`, `<img>`,
	  `<video>`, `<a>`) without `<style>` or `<script>` tags so `ui.browseableMessage`
	  renders a clean VirtualBuffer where all NVDA Browse Mode keys (`Up`/`Down Arrow`,
	  `H`, `K`, `T`, `L`, `Q`, `G`, `Escape`) work natively.
	"""
	title_text = article.title or _("Article Title Unavailable")
	esc_title = html.escape(title_text)
	cat_display = article.category_label or rubric_name or "News"
	esc_cat = html.escape(cat_display)
	esc_published = html.escape(article.published_at or "")

	est_minutes = article.reading_time_minutes
	if est_minutes <= 0:
		est_minutes = calculate_reading_time_minutes(article.content, article.summary)
	est_str = html.escape(
		_("Estimated Reading Time: about {minutes} min (approximated from text length)").format(
			minutes=max(1, est_minutes)
		)
	)

	header_meta_parts = [f"<strong>[{esc_cat}]</strong>"]
	if esc_published:
		header_meta_parts.append(esc_published)
	if est_minutes > 0:
		header_meta_parts.append(est_str)

	parts: List[str] = [
		f"<p>{' &bull; '.join(header_meta_parts)}</p>",
		f"<h1>{esc_title}</h1>",
	]

	byline_parts: List[str] = []
	if article.author:
		byline_parts.append(
			f"{html.escape(_('Author: {value}').format(value=''))}<strong>{html.escape(article.author)}</strong>"
		)
	if article.editor:
		byline_parts.append(
			f"{html.escape(_('Editor: {value}').format(value=''))}<strong>{html.escape(article.editor)}</strong>"
		)
	if article.photos:
		byline_parts.append(html.escape(_("Photos in article: {count}").format(count=len(article.photos))))
	if article.videos:
		byline_parts.append(html.escape(_("Videos in article: {count}").format(count=len(article.videos))))
	if article.url:
		esc_url = html.escape(article.url)
		open_orig_lbl = html.escape(_("Open Original Article in Browser"))
		byline_parts.append(f"<a href='{esc_url}'>{open_orig_lbl}</a>")

	if byline_parts:
		parts.append(f"<p>{' &middot; '.join(byline_parts)}</p>")

	# Status notices for loading / failed / partial states
	if article.content_status == ArticleStatus.CONTENT_LOADING:
		loading_str = html.escape(_("Status: Loading full article content from the source. Please wait..."))
		parts.append(f"<p><strong>{loading_str}</strong></p>")
		if article.summary:
			init_sum = html.escape(_("Initial Summary: {summary}").format(summary=article.summary))
			parts.append(f"<p>{init_sum}</p>")
		return "\n".join(parts)

	if article.content_status == ArticleStatus.CONTENT_FAILED:
		err_detail = article.error_message or _("Article content could not be extracted from the source page.")
		notice_txt = html.escape(
			_(
				"Notice: Full article content could not be loaded ({reason}). You can press the Reload Article button (Ctrl+R) or Open Original Article in Browser."
			).format(reason=err_detail)
		)
		parts.append(f"<p><strong>{notice_txt}</strong></p>")
		if article.summary:
			avail_sum = html.escape(_("Available summary:\r\n{summary}").format(summary=article.summary))
			parts.append(f"<p>{avail_sum}</p>")
		return "\n".join(parts)

	if article.content_status == ArticleStatus.CONTENT_PARTIAL:
		partial_txt = html.escape(
			_(
				"Notice: Article content was only partially loaded. To read the full web page, use the Reload Article button (Ctrl+R) or Open Original Article in Browser."
			)
		)
		parts.append(f"<p><em>{partial_txt}</em></p>")

	# Summary / Deck (when distinct from the first paragraph)
	first_p_text = ""
	for b in article.content:
		if b.get("type") == "p" and b.get("text"):
			first_p_text = b["text"].strip()
			break

	if article.summary and article.summary.strip() != first_p_text:
		sum_heading = html.escape(_("Summary: {summary}").format(summary="").rstrip(": "))
		parts.append(f"<aside><h2>{sum_heading}</h2><p>{html.escape(article.summary.strip())}</p></aside>")

	# Track rendered photo and video URLs so media items are rendered once in natural order
	rendered_photo_keys: Set[str] = set()
	rendered_video_keys: Set[str] = set()
	photo_counter = 0
	video_counter = 0

	video_meta_by_key: Dict[str, Dict[str, str]] = {}
	for v in article.videos:
		v_u = (v.get("url") or "").strip().lower()
		if v_u:
			video_meta_by_key[v_u] = v
		v_s = (v.get("stream_url") or "").strip().lower()
		if v_s:
			video_meta_by_key[v_s] = v

	inline_photo_keys: Set[str] = set()
	inline_video_keys: Set[str] = set()
	for b in article.content:
		b_type = b.get("type", "p")
		b_url = (b.get("url") or "").strip()
		if b_type == "image" and b_url:
			inline_photo_keys.add(b_url.split("?")[0].lower())
		elif b_type == "video" and b_url:
			inline_video_keys.add(b_url.lower())

	# Render Lead / Hero Videos and Photos not already inline in paragraphs
	for video in article.videos:
		v_url = (video.get("url") or "").strip()
		v_stream = (video.get("stream_url") or "").strip()
		v_key = v_url.lower()
		if not v_url and not v_stream:
			continue
		if v_key in inline_video_keys or v_key in rendered_video_keys:
			continue
		rendered_video_keys.add(v_key)
		if v_stream:
			rendered_video_keys.add(v_stream.lower())
		video_counter += 1
		parts.append(
			_render_inline_video_html(
				url=v_url,
				caption=video.get("caption") or title_text,
				provider=video.get("provider") or "Video",
				thumbnail_url=video.get("thumbnail_url") or (article.photos[0].get("url", "") if article.photos else ""),
				stream_url=v_stream,
				index=video_counter,
			)
		)

	for photo in article.photos:
		p_url = (photo.get("url") or "").strip()
		p_key = p_url.split("?")[0].lower()
		if not p_url or p_key in inline_photo_keys or p_key in rendered_photo_keys:
			continue
		rendered_photo_keys.add(p_key)
		photo_counter += 1
		parts.append(
			_render_inline_photo_html(
				url=p_url,
				caption=photo.get("caption") or title_text,
				index=photo_counter,
			)
		)

	# Main Article Body Blocks
	has_body = False
	for block in article.content:
		b_type = block.get("type", "p")
		b_text = (block.get("text") or "").strip()
		b_url = (block.get("url") or "").strip()

		if b_type in ("h2", "h3", "h4"):
			if b_text:
				has_body = True
				parts.append(f"<{b_type}>{html.escape(b_text)}</{b_type}>")
		elif b_type == "blockquote":
			if b_text:
				has_body = True
				parts.append(f"<blockquote><p>{html.escape(b_text)}</p></blockquote>")
		elif b_type == "image":
			if b_url:
				p_key = b_url.split("?")[0].lower()
				if p_key not in rendered_photo_keys:
					rendered_photo_keys.add(p_key)
					photo_counter += 1
					has_body = True
					parts.append(
						_render_inline_photo_html(
							url=b_url,
							caption=b_text or title_text,
							index=photo_counter,
						)
					)
		elif b_type == "video":
			if b_url:
				v_key = b_url.lower()
				if v_key not in rendered_video_keys:
					rendered_video_keys.add(v_key)
					v_meta = video_meta_by_key.get(v_key, {})
					v_stream = (block.get("stream_url") or v_meta.get("stream_url") or "").strip()
					if v_stream:
						rendered_video_keys.add(v_stream.lower())
					video_counter += 1
					has_body = True
					parts.append(
						_render_inline_video_html(
							url=b_url,
							caption=b_text or v_meta.get("caption") or title_text,
							provider=v_meta.get("provider") or "Video",
							thumbnail_url=v_meta.get("thumbnail_url") or "",
							stream_url=v_stream,
							index=video_counter,
						)
					)
		elif b_type == "caption":
			if b_text:
				already_in_photo = any(
					b_text.lower() == (p.get("caption") or "").strip().lower()
					for p in article.photos
				)
				if not already_in_photo:
					has_body = True
					cap_txt = html.escape(_("Image Caption: {text}").format(text=b_text))
					parts.append(f"<p><em>{cap_txt}</em></p>")
		elif b_type == "credit":
			if b_text:
				has_body = True
				cred_txt = html.escape(_("Source/Credit: {text}").format(text=b_text))
				parts.append(f"<p><small>{cred_txt}</small></p>")
		elif b_type in ("ul", "ol"):
			items = [str(it).strip() for it in (block.get("items") or []) if str(it).strip()]
			if items:
				has_body = True
				items_html = "".join(f"<li>{html.escape(it)}</li>" for it in items)
				parts.append(f"<{b_type}>{items_html}</{b_type}>")
		elif b_type == "table":
			tbl_html = format_table_block_as_html(block)
			if tbl_html:
				has_body = True
				parts.append(tbl_html)
		else:
			if b_text:
				has_body = True
				parts.append(f"<p>{html.escape(b_text)}</p>")

	if not has_body and article.summary:
		parts.append(f"<p>{html.escape(article.summary)}</p>")

	if article.url:
		esc_url = html.escape(article.url)
		src_lbl = html.escape(_("Source Link: {url}").format(url=article.url))
		parts.append(f"<p><a href='{esc_url}'>{src_lbl}</a></p>")

	return "\n".join(parts)


def format_article_for_reading(
	article: Article,
	rubric_name: str = "",
	paragraph_spacing: str = "normal",
	lang: str = "",
	color_theme: str = "light",
	font_scale: int = 100,
	font_family: str = "sans_serif",
) -> str:
	"""
	Format an `Article` object into structured multiline text for the in-dialog
	NVDA reading control (`wx.TextCtrl` with `TE_MULTILINE | TE_READONLY | TE_RICH2`),
	so standard NVDA reading commands (`Up`/`Down Arrow`, `Ctrl+Up`/`Down`, `Say All`)
	work immediately when the user tabs into the article content area, while pressing
	`Enter` or `Alt+H` (or activating the `Mode Jelajah HTML` button) opens NVDA's
	full HTML Browse Mode (`ui.browseableMessage(..., isHtml=True)`).
	"""
	sep = "\r\n\r\n\r\n" if paragraph_spacing == "wide" else "\r\n\r\n"
	sections: List[str] = []

	# 1. Main Headline
	title_text = article.title or _("Article Title Unavailable")
	sections.append(title_text)

	# 2. Article Metadata
	meta_lines: List[str] = []
	cat_display = article.category_label or rubric_name
	if cat_display:
		meta_lines.append(_("Rubric: {value}").format(value=cat_display))
	if article.published_at:
		meta_lines.append(_("Published: {value}").format(value=article.published_at))
	if article.author:
		meta_lines.append(_("Author: {value}").format(value=article.author))
	if article.editor:
		meta_lines.append(_("Editor: {value}").format(value=article.editor))
	if article.reading_time_minutes > 0:
		meta_lines.append(
			_("Estimated Reading Time: about {minutes} min (approximated from text length)").format(
				minutes=article.reading_time_minutes
			)
		)
	if article.photos:
		meta_lines.append(_("Photos in article: {count}").format(count=len(article.photos)))
	if article.videos:
		meta_lines.append(_("Videos in article: {count}").format(count=len(article.videos)))
	if meta_lines:
		sections.append("\r\n".join(meta_lines))

	# 3. Loading / Error / Partial Status Handling
	if article.content_status == ArticleStatus.CONTENT_LOADING:
		sections.append(_("Status: Loading full article content from the source. Please wait..."))
		if article.summary:
			sections.append(_("Initial Summary: {summary}").format(summary=article.summary))
		return sep.join(sections)

	if article.content_status == ArticleStatus.CONTENT_FAILED:
		err_detail = article.error_message or _("Article content could not be extracted from the source page.")
		sections.append(
			_(
				"Notice: Full article content could not be loaded ({reason}). You can press the Reload Article button (Ctrl+R) or Open Original Article in Browser."
			).format(reason=err_detail)
		)
		if article.summary:
			sections.append(_("Available summary:\r\n{summary}").format(summary=article.summary))
		return sep.join(sections)

	if article.content_status == ArticleStatus.CONTENT_PARTIAL:
		sections.append(
			_(
				"Notice: Article content was only partially loaded. To read the full web page, use the Reload Article button (Ctrl+R) or Open Original Article in Browser."
			)
		)

	# 4. Summary / Deck (when distinct from the first paragraph)
	first_p_text = ""
	for b in article.content:
		if b.get("type") == "p" and b.get("text"):
			first_p_text = b["text"].strip()
			break

	if article.summary and article.summary.strip() != first_p_text:
		sections.append(_("Summary: {summary}").format(summary=article.summary.strip()))

	# 5. Lead Videos & Photos
	rendered_photo_keys: Set[str] = set()
	rendered_video_keys: Set[str] = set()
	photo_counter = 0
	video_counter = 0

	inline_photo_keys: Set[str] = set()
	inline_video_keys: Set[str] = set()
	for b in article.content:
		b_type = b.get("type", "p")
		b_url = (b.get("url") or "").strip()
		if b_type == "image" and b_url:
			inline_photo_keys.add(b_url.split("?")[0].lower())
		elif b_type == "video" and b_url:
			inline_video_keys.add(b_url.lower())

	body_blocks: List[str] = []
	for video in article.videos:
		v_url = (video.get("url") or "").strip()
		v_stream = (video.get("stream_url") or "").strip()
		v_key = v_url.lower()
		if not v_url and not v_stream:
			continue
		if v_key in inline_video_keys or v_key in rendered_video_keys:
			continue
		rendered_video_keys.add(v_key)
		video_counter += 1
		v_cap = (video.get("caption") or title_text).strip()
		v_prov = (video.get("provider") or "Video").strip()
		v_target = v_stream or v_url
		body_blocks.append(
			f"{_('Video {num} ({provider}):').format(num=video_counter, provider=v_prov)} {v_cap} ({v_target})"
		)

	for photo in article.photos:
		p_url = (photo.get("url") or "").strip()
		p_key = p_url.split("?")[0].lower()
		if not p_url or p_key in inline_photo_keys or p_key in rendered_photo_keys:
			continue
		rendered_photo_keys.add(p_key)
		photo_counter += 1
		p_cap = (photo.get("caption") or title_text).strip()
		body_blocks.append(f"{_('Photo {num}:').format(num=photo_counter)} {p_cap}")

	# 6. Main Article Body Blocks
	for block in article.content:
		b_type = block.get("type", "p")
		b_text = (block.get("text") or "").strip()
		b_url = (block.get("url") or "").strip()

		if b_type in ("h2", "h3", "h4"):
			if b_text:
				body_blocks.append(_("Subheading: {text}").format(text=b_text))
		elif b_type == "blockquote":
			if b_text:
				body_blocks.append(_('Quote: "{text}"').format(text=b_text))
		elif b_type == "image":
			if b_url:
				p_key = b_url.split("?")[0].lower()
				if p_key not in rendered_photo_keys:
					rendered_photo_keys.add(p_key)
					photo_counter += 1
					body_blocks.append(
						f"{_('Photo {num}:').format(num=photo_counter)} {b_text or title_text}"
					)
		elif b_type == "video":
			if b_url:
				v_key = b_url.lower()
				if v_key not in rendered_video_keys:
					rendered_video_keys.add(v_key)
					video_counter += 1
					v_target = (block.get("stream_url") or b_url).strip()
					body_blocks.append(
						f"{_('Video {num} ({provider}):').format(num=video_counter, provider='Video')} {b_text or title_text} ({v_target})"
					)
		elif b_type == "caption":
			if b_text:
				already_in_photo = any(
					b_text.lower() == (p.get("caption") or "").strip().lower()
					for p in article.photos
				)
				if not already_in_photo:
					body_blocks.append(_("Image Caption: {text}").format(text=b_text))
		elif b_type == "credit":
			if b_text:
				body_blocks.append(_("Source/Credit: {text}").format(text=b_text))
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
		sections.append(_("Source Link: {url}").format(url=article.url))

	return sep.join(sections)


def format_plain_message_as_html(
	heading: str,
	message: str,
	color_theme: str = "light",
	font_scale: int = 100,
	font_family: str = "sans_serif",
) -> str:
	"""Render a status or welcome message as a clean HTML fragment for `ui.browseableMessage`."""
	esc_h = html.escape(heading or "NewsHub for NVDA")
	paras = [p.strip() for p in (message or "").splitlines() if p.strip()]
	p_html = "".join(f"<p>{html.escape(p)}</p>" for p in paras) or f"<p>{esc_h}</p>"
	return f"<h1>{esc_h}</h1>\n{p_html}"


def format_article_selection_announcement(
	article: Article,
	index: int,
	total: int,
	rubric_name: str = "",
	lang: str = "",
) -> str:
	"""
	Build a concise NVDA announcement when an article is selected or finishes loading,
	including photo and video availability counts when present.
	"""
	parts: List[str] = [
		_("Article {index} of {total}: {title}.").format(
			index=index + 1, total=total, title=article.title
		)
	]
	cat = article.category_label or rubric_name
	if cat:
		parts.append(_("Rubric {rubric}.").format(rubric=cat))
	if article.published_at:
		parts.append(_("Published {published_at}.").format(published_at=article.published_at))
	if article.reading_time_minutes > 0:
		parts.append(
			_("Estimated reading time about {minutes} minutes.").format(
				minutes=article.reading_time_minutes
			)
		)
	if article.photos and article.videos:
		parts.append(
			_("Contains {photos} photos and {videos} videos.").format(
				photos=len(article.photos), videos=len(article.videos)
			)
		)
	elif article.photos:
		parts.append(_("Contains {photos} photos.").format(photos=len(article.photos)))
	elif article.videos:
		parts.append(_("Contains {videos} videos.").format(videos=len(article.videos)))
	return " ".join(parts)


# Aliases for compatibility across modules and tests
format_article_text = format_article_for_reading
format_article_as_html = format_article_html
format_article_for_html = format_article_html
