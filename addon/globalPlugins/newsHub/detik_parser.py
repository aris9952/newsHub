# -*- coding: utf-8 -*-
"""
DOM-tree scoped parser for Detik.com rubric listings, RSS feeds, and full articles.

Supports all 27 official Detik.com rubrics:
- Detik news, Detik finance, DetikInet, DetikHot, DetikSport, SepakBola, DetikOto,
  DetikTravel, DetikFood, Detik Health, Wolipop, DetikX, 20Detik, DetikFoto, DetikEdu,
  DetikHikmah, DetikProperti, DetikPop, DetikJateng, DetikJatim, DetikJabar, DetikSulsel,
  DetikSumut, DetikBali, DetikSumbagsel, DetikJogja, and DetikKalimantan.
- Extracts headline lists preserving DOM order, deduplicating by normalized canonical URL,
  and capturing card metadata (category, publication timestamp, summary, author).
- Extracts full article content from `.detail__body-text`, `.itp_bodycontent`, `#detikdetailtext`,
  or `<article>` containers, including subheadings (h2/h3/h4), paragraphs, blockquotes, lists,
  news data tables, and photo captions, while stripping `[Gambas:...]`, `.linksisip`, `"Baca juga"`,
  video promo widgets, and navigation menus.
- Detects verified single-page (`?single=1`) pagination links in the DOM so multi-page Detik
  articles are loaded in full.
"""

import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Set, Tuple

from .kompas_parser import (
	EXCLUDED_TAGS,
	_DOMBuilder,
	_DOMNode,
	_extract_table_block,
	_has_class_prefix_or_exact,
	_iter_nodes,
	_extract_inline_media_blocks_from_node,
	extract_article_media_from_dom,
)
from .models import Article, ArticleStatus, ContentBlock
from .network import normalize_canonical_url


# Regular expression matching valid Detik.com article URLs across all 27 rubrics:
# - Standard articles: /d-1234567/...
# - DetikX investigative reports: /x/detail/...
# - 20Detik video reports: /detikflash/2026... or /\d{8}-\d+/...
# - Legacy / archive Detik articles: /read/\d{4}/\d{2}/\d{2}/...
DETIK_ARTICLE_URL_RE = re.compile(
	r"^https?://([a-z0-9\-]+\.)?detik\.com/"
	r"(?:"
	r"(?:[a-z0-9\-_]+/)*d-\d+/[a-z0-9\-_]+"
	r"|x/detail/[a-z0-9\-_]+/\d+/[a-z0-9\-_]+"
	r"|(?:[a-z0-9\-_]+/)*\d{8}-\d+/[a-z0-9\-_]+"
	r"|(?:[a-z0-9\-_]+/)*read/\d{4}/\d{2}/\d{2}/\d+/\d+/[a-z0-9\-_]+"
	r")",
	re.IGNORECASE,
)

# Substrings in class/id attributes on Detik.com that represent non-article widgets or ads
DETIK_EXCLUDED_ATTR_SUBSTRINGS: Tuple[str, ...] = (
	"linksisip", "baca-juga", "bacajuga", "sisip",
	"ads-", "adbox", "iklan", "banner", "billboard", "parapuan",
	"detail__body-tag", "detail__multiple", "detail__Crosslink",
	"komentar", "comment", "share", "social",
	"terpopuler", "most-popular", "rekomendasi", "related",
	"navbar", "menu-", "header", "footer", "sidebar", "widget",
	"breadcrumb", "video-box", "embed",
)

# Boilerplate and noise phrases specific to Detik.com article pages
DETIK_NOISE_PHRASES: Tuple[str, ...] = (
	"baca juga:",
	"simak video:",
	"lihat juga video:",
	"tonton juga video:",
	"simak selengkapnya di halaman berikutnya",
	"halaman selanjutnya",
	"[gambas:",
	"gambas:video",
		"pilihan redaksi",
	"copyright @",
	"detiknetwork",
	"all right reserved",
	"redaksi@detik.com",
	"informasi pasang iklan",
)

DETIK_NAV_EXACT_ITEMS = frozenset([
	"login", "daftar detikid", "masuk", "detikcom", "detiknews", "detikfinance",
	"detikinet", "detikhot", "detiksport", "sepakbola", "detikoto", "detiktravel",
	"detikfood", "detikhealth", "wolipop", "detikx", "20detik", "detikfoto",
	"detikedu", "detikhikmah", "detikproperti", "detikpop", "detikjateng",
	"detikjatim", "detikjabar", "detiksulsel", "detiksumut", "detikbali",
	"detiksumbagsel", "detikjogja", "detikkalimantan", "indeks", "terpopuler",
	"berita utama", "most popular", "selengkapnya", "lihat semua", "komentar", "bagikan",
])


def is_valid_detik_article_url(url: str) -> bool:
	"""Verify whether a URL points to an actual Detik.com news article page."""
	if not url:
		return False
	cleaned = url.strip()
	if DETIK_ARTICLE_URL_RE.match(cleaned):
		return True
	try:
		parsed = urllib.parse.urlparse(cleaned)
		host = (parsed.hostname or "").lower()
		path = (parsed.path or "").lower()
		if host == "detik.com" or host.endswith(".detik.com"):
			if re.search(r"/d-\d+/", path) or "/x/detail/" in path:
				return True
	except Exception:
		pass
	return False


def _is_detik_noise_text(text: str) -> bool:
	"""Check whether text is a Detik boilerplate line, Gambas embed marker, or nav label."""
	if not text:
		return True
	low = text.lower().strip()
	if low in DETIK_NAV_EXACT_ITEMS:
		return True
	if low.startswith("baca juga") or low.startswith("simak video") or low.startswith("lihat juga"):
		return True
	if low.startswith("tonton juga") or low.startswith("[gambas:"):
		return True
	for phrase in DETIK_NOISE_PHRASES:
		if phrase in low:
			return True
	return False


def _is_detik_inline_sisip_node(node: _DOMNode) -> bool:
	"""Detect inline 'Baca juga' / 'linksisip' elements inside a Detik article body."""
	cls_id = (" ".join(node.classes) + " " + node.id).lower()
	if any(k in cls_id for k in ("linksisip", "baca-juga", "bacajuga", "sisip")):
		return True
	if node.tag in ("table", "div", "p", "span", "strong", "a"):
		txt = node.get_text(exclude_baca_juga=False).lower()
		if (
			txt.startswith("baca juga:")
			or txt.startswith("simak video:")
			or txt.startswith("lihat juga:")
			or txt.startswith("[gambas:")
		):
			return True
	return False


def _is_detik_excluded_node(node: _DOMNode) -> bool:
	"""Check whether a DOM node is an excluded widget, ad, tag list, or inline link table on Detik."""
	if node.tag in EXCLUDED_TAGS:
		return True
	cls_lower = " ".join(node.classes).lower()
	id_lower = node.id.lower()
	combined = f"{cls_lower} {id_lower}"
	for sub in DETIK_EXCLUDED_ATTR_SUBSTRINGS:
		if sub in combined:
			return True
	return False


def _find_detik_enclosing_card(a_node: _DOMNode) -> Optional[_DOMNode]:
	"""Locate the nearest enclosing article card on a Detik rubric page."""
	curr = a_node.parent
	depth = 0
	while curr is not None and depth < 6:
		if curr.tag in ("article", "li") or (
			curr.tag == "div"
			and any(
				c in curr.classes
				for c in ("list-content__item", "media", "grid-row", "nhl", "box-content", "card", "article_lb")
			)
		):
			return curr
		curr = curr.parent
		depth += 1
	return None


def _extract_detik_card_metadata(card_node: Optional[_DOMNode], default_category: str) -> Tuple[str, str, str, str]:
	"""Extract (category, published_at, summary, author) from a Detik rubric listing card."""
	category = default_category
	published_at = ""
	summary = ""
	author = ""
	if card_node is None:
		return category, published_at, summary, author

	for node in _iter_nodes(card_node):
		cls_joined = " ".join(node.classes).lower()
		if not category or category == default_category:
			if any(k in cls_joined for k in ("media__subtitle", "sub-judul", "kanal", "category")):
				txt = node.get_text()
				if txt and len(txt) < 45 and not _is_detik_noise_text(txt):
					category = txt
		if (
			node.tag == "time"
			or "d-time" in node.attrs
			or any(k in cls_joined for k in ("media__date", "date", "time"))
			or (node.tag == "span" and node.attrs.get("title"))
		):
			title_attr = (node.attrs.get("title") or "").strip()
			if title_attr and len(title_attr) < 60:
				published_at = title_attr
			elif not published_at:
				txt = node.get_text()
				if txt and len(txt) < 65:
					published_at = txt
		if not summary:
			if any(k in cls_joined for k in ("media__desc", "desc", "lead", "summary")):
				txt = node.get_text()
				if txt and len(txt) > 20 and not _is_detik_noise_text(txt):
					summary = txt
		if not author:
			if any(k in cls_joined for k in ("author", "penulis", "writer")):
				txt = node.get_text()
				if txt and len(txt) < 60:
					author = txt

	return category, published_at, summary, author


def parse_detik_rss_or_headlines(
	raw_text: str,
	source_id: str = "detik",
	rubric_id: str = "detik_news",
	rubric_name: str = "Detik news",
	base_url: str = "https://news.detik.com/",
	max_articles: int = 40,
) -> List[Article]:
	"""Extract an article list from a Detik RSS/XML feed or rubric HTML page."""
	stripped = (raw_text or "").lstrip()
	if stripped.startswith("<?xml") or stripped.startswith("<rss") or stripped.startswith("<feed"):
		rss_items = _parse_detik_rss_xml(stripped, source_id, rubric_id, rubric_name, max_articles)
		if rss_items:
			return rss_items

	return parse_detik_rubric_headlines(
		html_string=raw_text,
		source_id=source_id,
		rubric_id=rubric_id,
		rubric_name=rubric_name,
		base_url=base_url,
		max_articles=max_articles,
	)


def _parse_detik_rss_xml(
	xml_string: str,
	source_id: str,
	rubric_id: str,
	rubric_name: str,
	max_articles: int = 40,
) -> List[Article]:
	"""Parse an RSS 2.0 XML feed for Detik.com rubrics."""
	articles: List[Article] = []
	seen_canonical: Set[str] = set()
	try:
		root = ET.fromstring(xml_string)
		for item in root.iter("item"):
			title = (item.findtext("title") or "").strip()
			link = (item.findtext("link") or "").strip()
			pub_date = (item.findtext("pubDate") or "").strip()
			desc_raw = (item.findtext("description") or "").strip()
			desc_clean = re.sub(r"<[^>]+>", " ", html.unescape(desc_raw))
			desc_clean = " ".join(desc_clean.split()).strip()

			if not title or not link or not is_valid_detik_article_url(link):
				continue
			canonical = normalize_canonical_url(link)
			if not canonical or canonical in seen_canonical:
				continue
			seen_canonical.add(canonical)

			articles.append(
				Article(
					source_id=source_id,
					rubric_id=rubric_id,
					title=title,
					url=link,
					canonical_url=canonical,
					published_at=pub_date,
					summary=desc_clean,
					category_label=rubric_name,
					content_status=ArticleStatus.HEADLINE_LOADED,
				)
			)
			if len(articles) >= max_articles:
				break
	except Exception:
		return []
	return articles


def parse_detik_rubric_headlines(
	html_string: str,
	source_id: str = "detik",
	rubric_id: str = "detik_news",
	rubric_name: str = "Detik news",
	base_url: str = "https://news.detik.com/",
	max_articles: int = 40,
) -> List[Article]:
	"""
	Extract the latest news article headlines from a Detik.com rubric HTML page:
	- Preserves DOM display order.
	- Deduplicates strictly by normalized `canonical_url`.
	- Preserves full article headlines without truncation.
	"""
	builder = _DOMBuilder()
	builder.feed(html_string or "")
	root = builder.root

	candidates_by_canonical: Dict[str, Dict[str, Any]] = {}
	ordered_canonicals: List[str] = []

	for node in _iter_nodes(root):
		if node.tag in ("nav", "footer", "header"):
			continue
		if node.tag == "a":
			href_raw = (node.attrs.get("href") or "").strip()
			if not href_raw or href_raw.startswith("#") or href_raw.lower().startswith("javascript:"):
				continue
			full_url = urllib.parse.urljoin(base_url, href_raw)
			if not is_valid_detik_article_url(full_url):
				continue

			parent_ptr = node.parent
			in_chrome = False
			while parent_ptr is not None:
				if parent_ptr.tag in ("nav", "footer"):
					in_chrome = True
					break
				parent_ptr = parent_ptr.parent
			if in_chrome:
				continue

			link_title = node.get_text()
			if not link_title:
				link_title = (node.attrs.get("dtr-ttl") or node.attrs.get("title") or "").strip()

			if not link_title or len(link_title) < 12 or _is_detik_noise_text(link_title):
				continue

			canonical = normalize_canonical_url(full_url)
			if not canonical:
				continue

			card = _find_detik_enclosing_card(node)
			cat, pub_at, summary, author = _extract_detik_card_metadata(card, rubric_name)

			if canonical not in candidates_by_canonical:
				candidates_by_canonical[canonical] = {
					"title": link_title,
					"url": full_url.split("#")[0],
					"canonical_url": canonical,
					"category": cat or rubric_name,
					"published_at": pub_at,
					"summary": summary,
					"author": author,
				}
				ordered_canonicals.append(canonical)
			else:
				existing = candidates_by_canonical[canonical]
				if len(link_title) > len(existing["title"]):
					existing["title"] = link_title
				if pub_at and not existing["published_at"]:
					existing["published_at"] = pub_at
				if summary and not existing["summary"]:
					existing["summary"] = summary
				if author and not existing["author"]:
					existing["author"] = author

	articles: List[Article] = []
	for canonical in ordered_canonicals:
		item = candidates_by_canonical[canonical]
		if len(item["title"]) < 14:
			continue
		articles.append(
			Article(
				source_id=source_id,
				rubric_id=rubric_id,
				title=item["title"],
				url=item["url"],
				canonical_url=item["canonical_url"],
				published_at=item["published_at"],
				author=item["author"],
				summary=item["summary"],
				category_label=item["category"],
				content_status=ArticleStatus.HEADLINE_LOADED,
			)
		)
		if len(articles) >= max_articles:
			break

	return articles


def detect_detik_all_pages_url(html_string: str, current_url: str) -> Optional[str]:
	"""
	Detect whether a Detik.com article spans multiple pages and provides a verified
	single-page view link (`?single=1`) in the DOM.
	"""
	if not html_string or not current_url:
		return None
	if "single=1" in current_url.lower():
		return None

	builder = _DOMBuilder()
	builder.feed(html_string)
	root = builder.root

	for node in _iter_nodes(root):
		if node.tag == "a":
			href = (node.attrs.get("href") or "").strip()
			if not href:
				continue
			cls_joined = " ".join(node.classes).lower()
			txt_low = node.get_text().lower()
			if "single=1" in href.lower() and (
				"detail__anchor" in cls_joined
				or "detail__multiple" in cls_joined
				or "semua" in txt_low
				or "all" in txt_low
				or is_valid_detik_article_url(urllib.parse.urljoin(current_url, href))
			):
				candidate = urllib.parse.urljoin(current_url, href)
				if is_valid_detik_article_url(candidate):
					return candidate
	return None


def _clean_detik_paragraph_text(text: str) -> str:
	"""Strip `[Gambas:...]` embeds and residual boilerplate markers from a Detik paragraph."""
	if not text:
		return ""
	cleaned = re.sub(r"\[Gambas:[^\]]+\]", " ", text, flags=re.IGNORECASE)
	cleaned = " ".join(cleaned.split()).strip()
	cleaned = re.sub(r"^(?:Baca|Simak|Lihat|Tonton)\s+juga\s*:\s*.*$", "", cleaned, flags=re.IGNORECASE).strip()
	return cleaned


def _extract_detik_blocks_from_container(container_node: _DOMNode, blocks: List[Dict[str, Any]], page_url: str = "") -> None:
	"""
	Recursively extract clean structured content blocks (h2/h3/h4, p, blockquote, ul, ol,
	table, image, video, caption) from a Detik article body container.
	"""
	for child in container_node.children:
		if isinstance(child, str):
			# Handle direct text nodes inside `.detail__body-text` separated by `<br>` tags
			cleaned_direct = _clean_detik_paragraph_text(html.unescape(child))
			if cleaned_direct and len(cleaned_direct) >= 25 and not _is_detik_noise_text(cleaned_direct):
				blocks.append(ContentBlock(block_type="p", text=cleaned_direct).to_dict())
			continue

		if not isinstance(child, _DOMNode):
			continue
		if _is_detik_inline_sisip_node(child):
			continue
		if _extract_inline_media_blocks_from_node(child, blocks, page_url):
			continue
		if _is_detik_excluded_node(child):
			continue

		t = child.tag
		if t in ("h2", "h3", "h4"):
			text = _clean_detik_paragraph_text(child.get_text(exclude_baca_juga=True))
			if text and not _is_detik_noise_text(text):
				blocks.append(ContentBlock(block_type=t, text=text).to_dict())

		elif t == "blockquote":
			text = _clean_detik_paragraph_text(child.get_text(exclude_baca_juga=True))
			if text and not _is_detik_noise_text(text):
				blocks.append(ContentBlock(block_type="blockquote", text=text).to_dict())

		elif t in ("ul", "ol"):
			items: List[str] = []
			for li in child.children:
				if isinstance(li, _DOMNode) and li.tag == "li" and not _is_detik_excluded_node(li):
					item_text = _clean_detik_paragraph_text(li.get_text(exclude_baca_juga=True))
					if item_text and not _is_detik_noise_text(item_text):
						items.append(item_text)
			if items:
				blocks.append(ContentBlock(block_type=t, items=items).to_dict())

		elif t == "table":
			if not _is_detik_inline_sisip_node(child):
				tbl_block = _extract_table_block(child)
				if tbl_block:
					blocks.append(tbl_block)

		elif t in ("figure", "figcaption") or "detail__media-caption" in child.classes:
			cap_text = _clean_detik_paragraph_text(child.get_text(exclude_baca_juga=True))
			if cap_text and len(cap_text) > 12 and not _is_detik_noise_text(cap_text):
				blocks.append(ContentBlock(block_type="caption", text=cap_text).to_dict())

		elif t == "p":
			text = _clean_detik_paragraph_text(child.get_text(exclude_baca_juga=True))
			if text and len(text) >= 3 and not _is_detik_noise_text(text):
				blocks.append(ContentBlock(block_type="p", text=text).to_dict())

		else:
			_extract_detik_blocks_from_container(child, blocks, page_url=page_url)


def parse_detik_article_html(html_string: str, url: str, default_category: str = "") -> Dict[str, Any]:
	"""
	Parse a Detik.com article HTML document to extract metadata and structured content blocks
	ready for NVDA screen reader presentation.
	"""
	builder = _DOMBuilder()
	builder.feed(html_string or "")
	root = builder.root

	title = ""
	published_at = ""
	category = default_category or ""
	author = ""
	editor = ""
	summary_deck = ""
	main_caption = ""
	source_credit = ""
	meta_description = ""

	content_containers: List[_DOMNode] = []

	for node in _iter_nodes(root):
		# 0. Metadata from Detik <meta> tags (dtk:author, dtk:publishdate, author, description, og:title)
		if node.tag == "meta":
			meta_name = (node.attrs.get("name") or node.attrs.get("property") or "").lower()
			meta_content = (node.attrs.get("content") or "").strip()
			if not meta_content:
				continue
			if meta_name in ("dtk:author", "author", "content_author") and not author:
				author = meta_content
			elif meta_name in ("dtk:publishdate", "publishdate", "article:published_time") and not published_at:
				published_at = meta_content
			elif meta_name in ("dtk:kanal", "article:section") and not category:
				category = meta_content
			elif meta_name in ("description", "og:description") and not meta_description:
				meta_description = html.unescape(meta_content).strip()
			elif meta_name == "og:title" and not title:
				title = html.unescape(meta_content).strip()

		# 1. Article headline (h1.detail__title, h1.jdl, or primary h1)
		if node.tag == "h1":
			t_txt = node.get_text()
			if t_txt and ("detail__title" in node.classes or "jdl" in node.classes or not title):
				title = t_txt

		# 2. Publication date (.detail__date or .date)
		if "detail__date" in node.classes or (node.tag == "div" and "date" in node.classes):
			d_txt = node.get_text()
			if d_txt and len(d_txt) < 80:
				published_at = d_txt

		# 3. Author (.detail__author or .author)
		if "detail__author" in node.classes or (node.tag == "div" and "author" in node.classes):
			a_txt = node.get_text()
			cleaned_author = re.sub(r"\s*-\s*detik[A-Za-z0-9]*$", "", a_txt, flags=re.IGNORECASE).strip()
			if cleaned_author and len(cleaned_author) < 80:
				author = cleaned_author

		# 4. Breadcrumb category (.page__breadcrumb a)
		if "page__breadcrumb" in node.classes:
			for child in _iter_nodes(node):
				if child.tag == "a":
					c_txt = child.get_text()
					if c_txt and c_txt.lower() not in ("detikcom", "home", "beranda"):
						category = c_txt

		# 5. Primary photo caption (.detail__media-caption or figcaption)
		if not main_caption and (
			"detail__media-caption" in node.classes
			or (node.tag == "figcaption" and node.parent and "detail__media" in " ".join(node.parent.classes).lower())
		):
			cap_txt = _clean_detik_paragraph_text(node.get_text())
			if cap_txt and len(cap_txt) > 10 and not _is_detik_noise_text(cap_txt):
				main_caption = cap_txt

		# 6. Main article content containers (.detail__body-text, .itp_bodycontent, #detikdetailtext)
		if (
			"detail__body-text" in node.classes
			or "itp_bodycontent" in node.classes
			or node.id == "detikdetailtext"
		):
			content_containers.append(node)

	blocks: List[Dict[str, Any]] = []
	if main_caption:
		blocks.append(ContentBlock(block_type="caption", text=main_caption).to_dict())

	if content_containers:
		for container in content_containers:
			_extract_detik_blocks_from_container(container, blocks, page_url=url)
	else:
		for node in _iter_nodes(root):
			if node.tag == "article" or "detail__body" in node.classes:
				_extract_detik_blocks_from_container(node, blocks, page_url=url)
				if blocks:
					break

	# Deduplicate consecutive identical blocks
	deduped_blocks: List[Dict[str, Any]] = []
	for b in blocks:
		if deduped_blocks and deduped_blocks[-1] == b:
			continue
		deduped_blocks.append(b)
	blocks = deduped_blocks

	substantive_blocks = [
		b for b in blocks
		if b.get("type") in ("p", "ul", "ol", "table", "blockquote")
	]

	if not summary_deck:
		if substantive_blocks and substantive_blocks[0].get("text"):
			summary_deck = substantive_blocks[0]["text"]
		elif meta_description and not _is_detik_noise_text(meta_description):
			summary_deck = meta_description

	if len(substantive_blocks) >= 2 or (
		len(substantive_blocks) == 1 and len(substantive_blocks[0].get("text", "")) >= 100
	):
		status = ArticleStatus.CONTENT_LOADED
	elif len(substantive_blocks) == 1 or summary_deck:
		status = ArticleStatus.CONTENT_PARTIAL
		if not substantive_blocks and summary_deck:
			blocks.append(ContentBlock(block_type="p", text=summary_deck).to_dict())
	else:
		status = ArticleStatus.CONTENT_FAILED

	# Extract trailing Detik initials credit (e.g., "(afb/afb)") if present in the final paragraph
	if blocks and blocks[-1].get("type") == "p":
		last_txt = blocks[-1].get("text", "")
		m_cred = re.search(r"\(([a-z0-9]{2,5}/[a-z0-9]{2,5})\)\s*$", last_txt.strip(), re.IGNORECASE)
		if m_cred:
			source_credit = f"({m_cred.group(1)})"
			if not editor:
				editor = m_cred.group(1)

	photos, videos = extract_article_media_from_dom(
		root=root,
		content_containers=content_containers,
		html_string=html_string,
		page_url=url,
		main_caption=main_caption,
		default_title=title,
	)
	if (photos or videos) and status == ArticleStatus.CONTENT_FAILED:
		status = ArticleStatus.CONTENT_LOADED

	return {
		"title": title,
		"category": category or default_category or "Detik.com",
		"published_at": published_at,
		"author": author,
		"editor": editor,
		"url": url,
		"canonical_url": normalize_canonical_url(url),
		"summary": summary_deck,
		"source_credit": source_credit,
		"content": blocks,
		"photos": photos,
		"videos": videos,
		"content_status": status,
	}
