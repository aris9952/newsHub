# -*- coding: utf-8 -*-
"""
Structured data models for NewsHub for NVDA.

Defines article lifecycle statuses, multimedia items (photos and videos),
content blocks (paragraphs, subheadings, blockquotes, lists, data tables,
images, videos, captions, and credits), the article entity, rubric configuration,
and news portal configuration.
"""

import hashlib
import time
from typing import Any, Dict, List, Optional

try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	def _(s: str) -> str:
		return s


class ArticleStatus:
	"""Lifecycle status constants for article loading."""
	NOT_FETCHED = "not_fetched"          # Article has not been fetched yet
	HEADLINE_LOADED = "headline_loaded"  # Headline metadata loaded from rubric or search list
	CONTENT_LOADING = "content_loading"  # Full content is currently loading in background
	CONTENT_LOADED = "content_loaded"    # Full content loaded successfully
	CONTENT_PARTIAL = "content_partial"  # Content is only partially available
	CONTENT_FAILED = "content_failed"    # Content retrieval failed

	@classmethod
	def get_label(cls, status: str) -> str:
		"""Return a localized screen-reader-friendly label for the given article status."""
		labels = {
			cls.NOT_FETCHED: _("Article not fetched yet"),
			cls.HEADLINE_LOADED: _("Headline loaded"),
			cls.CONTENT_LOADING: _("Loading content"),
			cls.CONTENT_LOADED: _("Content loaded"),
			cls.CONTENT_PARTIAL: _("Content partially available"),
			cls.CONTENT_FAILED: _("Content retrieval failed"),
		}
		return labels.get(status, _("Unknown status"))


def make_stable_article_id(source_id: str, canonical_url: str) -> str:
	"""Generate a deterministic, stable article ID from source_id and canonical_url."""
	normalized = f"{(source_id or 'unknown').strip().lower()}::{(canonical_url or '').strip()}"
	digest = hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]
	return f"art-{source_id}-{digest}"


class MediaItem:
	"""Representation of a photo or video attached to a news article."""
	__slots__ = ("media_type", "url", "caption", "thumbnail_url", "provider", "stream_url")

	def __init__(
		self,
		media_type: str,
		url: str,
		caption: str = "",
		thumbnail_url: str = "",
		provider: str = "",
		stream_url: str = "",
	):
		self.media_type = (media_type or "photo").strip().lower()
		self.url = (url or "").strip()
		self.caption = " ".join((caption or "").split()).strip()
		self.thumbnail_url = (thumbnail_url or "").strip()
		self.provider = (provider or "").strip()
		self.stream_url = (stream_url or "").strip()

	def to_dict(self) -> Dict[str, str]:
		data: Dict[str, str] = {
			"media_type": self.media_type,
			"url": self.url,
		}
		if self.caption:
			data["caption"] = self.caption
		if self.thumbnail_url:
			data["thumbnail_url"] = self.thumbnail_url
		if self.provider:
			data["provider"] = self.provider
		if self.stream_url:
			data["stream_url"] = self.stream_url
		return data

	@classmethod
	def from_dict(cls, data: Dict[str, Any]) -> "MediaItem":
		return cls(
			media_type=str(data.get("media_type", "photo")),
			url=str(data.get("url", "")),
			caption=str(data.get("caption", "")),
			thumbnail_url=str(data.get("thumbnail_url", "")),
			provider=str(data.get("provider", "")),
			stream_url=str(data.get("stream_url", "")),
		)


class ContentBlock:
	"""
	Representation of a single structured article content element.

	Supported block types:
	- 'h2', 'h3', 'h4': Subheadings
	- 'p': Paragraph
	- 'blockquote': Blockquote
	- 'ul': Unordered list (uses `items`)
	- 'ol': Ordered list (uses `items`)
	- 'table': News data table (uses `headers` and `rows`)
	- 'image': Inline article photo (uses `url` and `text` as caption/alt)
	- 'video': Inline article video (uses `url`, `stream_url`, and `text` as title/caption)
	- 'caption': Relevant image caption
	- 'credit': Source or credit note
	"""
	__slots__ = ("block_type", "text", "items", "headers", "rows", "url", "stream_url")

	def __init__(
		self,
		block_type: str,
		text: str = "",
		items: Optional[List[str]] = None,
		headers: Optional[List[str]] = None,
		rows: Optional[List[List[str]]] = None,
		url: str = "",
		stream_url: str = "",
	):
		self.block_type = block_type
		self.text = text.strip() if text else ""
		self.items = list(items) if items else []
		self.headers = list(headers) if headers else []
		self.rows = [list(r) for r in rows] if rows else []
		self.url = (url or "").strip()
		self.stream_url = (stream_url or "").strip()

	def to_dict(self) -> Dict[str, Any]:
		data: Dict[str, Any] = {"type": self.block_type}
		if self.text:
			data["text"] = self.text
		if self.items:
			data["items"] = list(self.items)
		if self.headers:
			data["headers"] = list(self.headers)
		if self.rows:
			data["rows"] = [list(r) for r in self.rows]
		if self.url:
			data["url"] = self.url
		if self.stream_url:
			data["stream_url"] = self.stream_url
		return data

	@classmethod
	def from_dict(cls, data: Dict[str, Any]) -> "ContentBlock":
		return cls(
			block_type=data.get("type", "p"),
			text=data.get("text", ""),
			items=data.get("items"),
			headers=data.get("headers"),
			rows=data.get("rows"),
			url=data.get("url", ""),
			stream_url=data.get("stream_url", ""),
		)


class Article:
	"""Consistent news article data structure used across all modules."""
	def __init__(
		self,
		source_id: str,
		rubric_id: str,
		title: str,
		url: str,
		canonical_url: str,
		published_at: str = "",
		author: str = "",
		editor: str = "",
		summary: str = "",
		content: Optional[List[Dict[str, Any]]] = None,
		fetched_at: Optional[float] = None,
		content_status: str = ArticleStatus.HEADLINE_LOADED,
		reading_time_minutes: int = 0,
		category_label: str = "",
		error_message: str = "",
		article_id: Optional[str] = None,
		photos: Optional[List[Dict[str, str]]] = None,
		videos: Optional[List[Dict[str, str]]] = None,
	):
		self.source_id = source_id
		self.rubric_id = rubric_id
		self.title = " ".join((title or "").split()).strip()
		self.url = (url or "").strip()
		self.canonical_url = (canonical_url or self.url).strip()
		self.id = article_id or make_stable_article_id(source_id, self.canonical_url)
		self.published_at = " ".join((published_at or "").split()).strip()
		self.author = " ".join((author or "").split()).strip()
		self.editor = " ".join((editor or "").split()).strip()
		self.summary = " ".join((summary or "").split()).strip()
		self.content: List[Dict[str, Any]] = list(content) if content else []
		self.fetched_at: float = fetched_at if fetched_at is not None else time.time()
		self.content_status: str = content_status
		self.reading_time_minutes: int = max(0, int(reading_time_minutes or 0))
		self.category_label = " ".join((category_label or "").split()).strip()
		self.error_message = (error_message or "").strip()
		self.photos: List[Dict[str, str]] = list(photos) if photos else []
		self.videos: List[Dict[str, str]] = list(videos) if videos else []

	@property
	def has_photos(self) -> bool:
		"""Return True if the article contains at least one extracted photo."""
		return len(self.photos) > 0

	@property
	def has_videos(self) -> bool:
		"""Return True if the article contains at least one extracted video."""
		return len(self.videos) > 0

	def update_from_FullParse(self, parsed: Dict[str, Any], status: str, reading_time: int) -> None:
		"""Update article attributes from full page extraction while preserving its stable ID."""
		if parsed.get("title"):
			self.title = parsed["title"]
		if parsed.get("published_at"):
			self.published_at = parsed["published_at"]
		if parsed.get("author"):
			self.author = parsed["author"]
		if parsed.get("editor"):
			self.editor = parsed["editor"]
		if parsed.get("summary"):
			self.summary = parsed["summary"]
		if parsed.get("category"):
			self.category_label = parsed["category"]
		if parsed.get("content") is not None:
			self.content = list(parsed["content"])
		if parsed.get("photos") is not None:
			self.photos = list(parsed["photos"])
		if parsed.get("videos") is not None:
			self.videos = list(parsed["videos"])
		self.fetched_at = time.time()
		self.content_status = status
		self.reading_time_minutes = max(1, int(reading_time)) if self.content or self.summary or self.photos or self.videos else 0
		self.error_message = parsed.get("error_message", "")

	def to_dict(self) -> Dict[str, Any]:
		return {
			"id": self.id,
			"source_id": self.source_id,
			"rubric_id": self.rubric_id,
			"title": self.title,
			"url": self.url,
			"canonical_url": self.canonical_url,
			"published_at": self.published_at,
			"author": self.author,
			"editor": self.editor,
			"summary": self.summary,
			"content": self.content,
			"photos": self.photos,
			"videos": self.videos,
			"fetched_at": self.fetched_at,
			"content_status": self.content_status,
			"reading_time_minutes": self.reading_time_minutes,
			"category_label": self.category_label,
			"error_message": self.error_message,
		}


class RubricConfig:
	"""Configuration for a single news rubric/channel localized via NVDA gettext."""
	__slots__ = ("id", "name", "description", "url", "supported", "parser_id")

	def __init__(
		self,
		rubric_id: str,
		name: str,
		description: str,
		url: str,
		supported: bool = True,
		parser_id: str = "kompas_dom",
	):
		self.id = rubric_id
		self.name = name
		self.description = description
		self.url = url
		self.supported = supported
		self.parser_id = parser_id

	@property
	def display_label(self) -> str:
		"""Return the localized label displayed in the rubric selection control."""
		return f"{self.name} — {_(self.description)}"


class SiteConfig:
	"""Configuration for a news portal/website localized via NVDA gettext."""
	__slots__ = ("id", "name", "description", "base_url", "supported", "parser_id", "rubrics")

	def __init__(
		self,
		site_id: str,
		name: str,
		description: str,
		base_url: str,
		supported: bool,
		parser_id: str,
		rubrics: List[RubricConfig],
	):
		self.id = site_id
		self.name = name
		self.description = description
		self.base_url = base_url
		self.supported = supported
		self.parser_id = parser_id
		self.rubrics = list(rubrics)

	@property
	def display_label(self) -> str:
		"""Return the site name displayed in the site selection control."""
		return self.name

	def get_rubric_by_id(self, rubric_id: str) -> Optional[RubricConfig]:
		for r in self.rubrics:
			if r.id == rubric_id:
				return r
		return None
