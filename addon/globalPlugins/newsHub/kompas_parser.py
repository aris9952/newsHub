# -*- coding: utf-8 -*-
"""
DOM-tree scoped parser for Kompas.com rubric listings, RSS feeds, and full articles.

Extends the DOM-Tree Scoped Parser approach from `scraper.py` to support:
- All 23 official Kompas.com rubrics (both `*.kompas.com` subdomains and `www.kompas.com/<rubric>` paths).
- Official RSS/XML feed extraction when XML is provided.
- Full headline list extraction with complete titles, canonical URLs, rubrics, publication timestamps, summaries, and authors (when present on listing cards).
- Full article content extraction: title, publication date/time, author, editor, summary/deck, subheadings (h2/h3/h4), paragraphs (including valid short paragraphs or paragraphs with inline links), blockquotes, ordered/unordered lists (ol/ul), news data tables (table), relevant image captions (figcaption/photo caption), and source/credits.
- Verified full-page (`?page=all`) detection from DOM pagination links without blindly guessing URL parameters.
- Strict filtering of non-news elements (navigation menus, "Baca juga" recommendations, user comments, advertisements, share buttons, archive/subscription banners, "Apresiasi Spesial", and KG Media footers).
"""

import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import Article, ArticleStatus, ContentBlock
from .network import normalize_canonical_url


VOID_TAGS = frozenset([
	"area", "base", "br", "col", "embed", "hr", "img", "input",
	"link", "meta", "param", "source", "track", "wbr",
])

# Non-content HTML tags that must always be excluded from main article body extraction
EXCLUDED_TAGS = frozenset([
	"script", "style", "iframe", "noscript", "svg", "canvas",
	"nav", "header", "footer", "aside", "form", "button",
	"dialog", "select", "option", "input", "textarea",
])

# Substrings in class/id attributes for ad widgets, related links, tags, modals, and site navigation
EXCLUDED_ATTR_SUBSTRINGS: Tuple[str, ...] = (
	"ads-on-body", "ads-box", "ads_", "iklan", "banner",
	"inner-link-baca-juga", "baca-juga", "bacajuga",
	"video-box", "galeri", "infografik",
	"kompasid", "paywall", "arsip", "subscription",
	"apresiasi", "donate", "donasi", "sawer",
	"tagging", "topik-pilihan", "related", "terkait",
	"share", "social", "komentar", "comment",
	"terpopuler", "recomend",
	"navbar", "menu-", "site-header", "site-footer", "sidebar", "widget",
	"breadcrumb",
)

# Boilerplate and noise phrases that must be excluded from extracted article body blocks
NOISE_PHRASES: Tuple[str, ...] = (
	"baca juga:",
	"gabung kompas.com+",
	"lihat foto",
	"jagatliterasi",
	"dapatkan informasi dan insight pilihan redaksi",
	"apresiasi spesial adalah fitur dukungan",
	"kontribusi ini bersifat sukarela",
	"seluruh kontribusi akan digunakan untuk mendukung",
	"kompas.com tidak berkewajiban memberikan laporan",
	"pembaca dapat menyertakan pesan singkat bersama kontribusi",
	"pesan dalam kolom komentar akan melewati kurasi",
	"pesan yang bersifat ofensif, diskriminatif",
	"apresiasi spesial tidak dapat dianggap sebagai iklan",
	"kontribusi yang sudah dilakukan tidak dapat dikembalikan",
	"kompas.com berhak menutup atau menonaktifkan fitur ini",
	"data pribadi kontributor akan diperlakukan sesuai",
	"informasi pembayaran diproses oleh penyedia layanan",
	"dengan menggunakan apresiasi spesial, pembaca dianggap",
	"kompas.com tidak bertanggung jawab atas kerugian langsung",
	"kontribusi tidak menciptakan hubungan kerja",
	"liputan ini masih bisa kamu baca",
	"artikel ini telah masuk arsip",
	"berlangganan untuk membacanya kembali kapan saja",
	"copyright 2008",
	"pt. kompas cyber media",
	"all rights reserved",
	"konten yang disimpan",
	"konten yang disukai",
	"atur minat",
	"setelan perangkat",
	"mode gelap",
	"mode terang",
	"kabar palmerah",
	"pedoman media siber",
	"kebijakan data pribadi",
	"ketentuan penggunaan",
	"langkah emas bsi",
	"langkahemas bsi",
	"ikuti whatsapp channel",
	"simak berita update",
	"kompas.com di google news",
)

# Exact navigation menu and footer item labels that must not be treated as headlines or list items
NAV_MENU_EXACT_ITEMS = frozenset([
	"login", "gabung kompas.com+", "konten yang disimpan", "konten yang disukai",
	"atur minat", "setelan perangkat", "mode gelap", "mode terang",
	"kolumnis indeks", "langkahemas bsi", "artikel foto video rolls donasi",
	"pemerintah", "swasta", "lsm/figur", "bumn", "umkm", "nusatirta", "mulai dari kamu",
	"kehidupan sehat dan sejahtera", "air bersih dan sanitasi layak", "pendidikan berkualitas",
	"energi bersih dan terjangkau", "penanganan perubahan iklim", "ekosistem lautan",
	"ekosistem daratan", "tanpa kemiskinan", "tanpa kelaparan", "kesetaraan gender",
	"pekerjaan layak dan pertumbuhan ekonomi", "industri, inovasi & infrastruktur",
	"berkurangnya kesenjangan", "kota & pemukiman yang berkelanjutan",
	"konsumsi & produksi yang bertanggungjawab",
	"news", "nasional", "global", "megapolitan", "regional", "pemilu", "ikn", "bola",
	"tekno", "otomotif", "entertainment", "sains", "health", "money", "tren", "properti",
	"lifestyle", "hype", "travel", "homey", "food", "edukasi", "parapuan", "foto", "video",
	"kolom", "vik", "jeo", "lestari", "ohayo jepang", "event", "store", "pesona indonesia",
	"play", "artikel terpopuler", "artikel terkini", "topik pilihan", "artikel headline",
	"kompas.com", "harian kompas", "kompastv", "kompasiana", "kg media", "kgnow!",
	"pasangiklan.com", "kontan", "sonora", "grid.id", "gridoto.com", "bolasport.com",
	"tribunnews", "gramedia.com", "gramedia digital", "santika indonesia",
	"kabar palmerah", "about us", "advertise", "ketentuan penggunaan",
	"kebijakan data pribadi", "pedoman media siber", "career", "contact us",
	"selengkapnya", "lihat semua", "indeks", "komentar", "bagikan",
])

# Regular expression matching valid Kompas.com article URLs (including /read/YYYY/MM/DD/... and channel paths)
KOMPAS_READ_URL_RE = re.compile(
	r"^https?://([a-z0-9\-]+\.)?kompas\.com/(?:[a-z0-9\-]+/)*read/\d{4}/\d{2}/\d{2}/\d+",
	re.IGNORECASE,
)


class _DOMNode:
	"""Lightweight representation of an HTML element for scoped DOM traversal."""
	__slots__ = ("tag", "attrs", "classes", "id", "children", "parent")

	def __init__(self, tag: str, attrs: Optional[List[Tuple[str, Optional[str]]]] = None, parent: Optional["_DOMNode"] = None):
		self.tag = tag
		self.attrs: Dict[str, str] = {}
		if attrs:
			for k, v in attrs:
				if k:
					self.attrs[k.lower()] = v if v is not None else ""
		cls_str = self.attrs.get("class", "") or ""
		self.classes: Set[str] = set(cls_str.split())
		self.id: str = (self.attrs.get("id", "") or "").strip()
		self.children: List[Any] = []
		self.parent: Optional["_DOMNode"] = parent

	def get_text(self, exclude_baca_juga: bool = False) -> str:
		parts: List[str] = []
		self._collect_text(parts, exclude_baca_juga=exclude_baca_juga)
		raw = "".join(parts)
		return " ".join(html.unescape(raw).split()).strip()

	def _collect_text(self, parts: List[str], exclude_baca_juga: bool = False) -> None:
		for child in self.children:
			if isinstance(child, str):
				parts.append(child)
			elif isinstance(child, _DOMNode):
				if child.tag in ("script", "style", "noscript"):
					continue
				if exclude_baca_juga and _is_baca_juga_inline_node(child):
					continue
				child._collect_text(parts, exclude_baca_juga=exclude_baca_juga)
				if child.tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "td", "th"):
					parts.append(" ")


class _DOMBuilder(HTMLParser):
	"""Build a lightweight DOM tree from an HTML document, tolerant of unclosed tags."""
	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.root = _DOMNode("document")
		self._stack: List[_DOMNode] = [self.root]

	def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
		t = tag.lower()
		parent = self._stack[-1]
		node = _DOMNode(t, attrs, parent=parent)
		parent.children.append(node)
		if t not in VOID_TAGS:
			self._stack.append(node)

	def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
		t = tag.lower()
		parent = self._stack[-1]
		node = _DOMNode(t, attrs, parent=parent)
		parent.children.append(node)

	def handle_data(self, data: str) -> None:
		if self._stack and data:
			self._stack[-1].children.append(data)

	def handle_endtag(self, tag: str) -> None:
		t = tag.lower()
		if t in VOID_TAGS:
			return
		for i in range(len(self._stack) - 1, 0, -1):
			if self._stack[i].tag == t:
				del self._stack[i:]
				break


def _iter_nodes(node: _DOMNode):
	"""Pre-order traversal generator for all descendant nodes under `node`."""
	for child in node.children:
		if isinstance(child, _DOMNode):
			yield child
			yield from _iter_nodes(child)


def _has_class_prefix_or_exact(node: _DOMNode, targets: Tuple[str, ...]) -> bool:
	cls_joined = " ".join(node.classes).lower()
	for t in targets:
		if t in node.classes or t in cls_joined:
			return True
	return False


def _is_baca_juga_inline_node(node: _DOMNode) -> bool:
	"""Detect inline 'Baca juga:' cross-link elements inside a paragraph without discarding the parent paragraph."""
	cls_id = (" ".join(node.classes) + " " + node.id).lower()
	if "baca-juga" in cls_id or "bacajuga" in cls_id or "inner-link" in cls_id:
		return True
	if node.tag in ("span", "strong", "a", "p", "div"):
		txt = node.get_text(exclude_baca_juga=False).lower()
		if txt.startswith("baca juga:") or txt.startswith("baca juga :"):
			return True
	return False


def _is_excluded_node(node: _DOMNode) -> bool:
	"""Check whether a DOM node belongs to an advertisement, related link, tag list, archive modal, or navigation bar."""
	if node.tag in EXCLUDED_TAGS:
		return True
	cls_lower = " ".join(node.classes).lower()
	id_lower = node.id.lower()
	combined = f"{cls_lower} {id_lower}"
	for sub in EXCLUDED_ATTR_SUBSTRINGS:
		if sub in combined:
			return True
	return False


def _is_noise_text(text: str) -> bool:
	"""Check whether text contains boilerplate, navigation, archive, or donation noise."""
	if not text:
		return True
	low = text.lower().strip()
	if low in NAV_MENU_EXACT_ITEMS:
		return True
	if low.startswith("baca juga:") or low.startswith("baca juga :"):
		return True
	for phrase in NOISE_PHRASES:
		if phrase in low:
			return True
	if "nasional global megapolitan" in low or "apps & os gadget internet" in low:
		return True
	if "timnas indonesia liga indonesia" in low or "ekbis keuangan syariah" in low:
		return True
	return False


def is_valid_kompas_article_url(url: str) -> bool:
	"""Verify that a link points to an actual Kompas.com news article page."""
	if not url:
		return False
	cleaned = url.strip()
	if KOMPAS_READ_URL_RE.match(cleaned):
		return True
	# Fallback check for Kompas article URLs containing `/read/` on a kompas.com domain
	try:
		parsed = urllib.parse.urlparse(cleaned)
		host = (parsed.hostname or "").lower()
		if (host == "kompas.com" or host.endswith(".kompas.com")) and "/read/" in parsed.path.lower():
			return True
	except Exception:
		pass
	return False


def _find_enclosing_card(a_node: _DOMNode) -> Optional[_DOMNode]:
	"""Locate the nearest enclosing article card container to extract date, category, or summary metadata."""
	curr = a_node.parent
	depth = 0
	while curr is not None and depth < 6:
		if curr.tag in ("article", "li") or _has_class_prefix_or_exact(
			curr,
			(
				"article__list", "articleitem", "most__list", "terkini__post",
				"headline__big", "headline__thumb", "wspec-item", "aiml", "card",
			),
		):
			return curr
		curr = curr.parent
		depth += 1
	return None


def _extract_card_metadata(card_node: Optional[_DOMNode], default_category: str) -> Tuple[str, str, str, str]:
	"""Extract (category, published_at, summary, author) from an article card on a rubric page when available."""
	category = default_category
	published_at = ""
	summary = ""
	author = ""
	if card_node is None:
		return category, published_at, summary, author

	for node in _iter_nodes(card_node):
		cls_joined = " ".join(node.classes).lower()
		if not category or category == default_category:
			if any(k in cls_joined for k in ("article__subtitle", "articleitem-subtitle", "kanal", "cat", "sub-judul")):
				txt = node.get_text()
				if txt and len(txt) < 40 and not _is_noise_text(txt):
					category = txt
		if not published_at:
			if node.tag == "time" or any(k in cls_joined for k in ("article__date", "articleitem-date", "date", "time")):
				txt = node.get_text()
				if txt and len(txt) < 60:
					published_at = txt
		if not summary:
			if any(k in cls_joined for k in ("article__lead", "articleitem-lead", "lead", "summary", "desc")):
				txt = node.get_text()
				if txt and len(txt) > 20 and not _is_noise_text(txt):
					summary = txt
		if not author:
			if any(k in cls_joined for k in ("author", "penulis", "writer")):
				txt = node.get_text()
				if txt and len(txt) < 60:
					author = txt

	return category, published_at, summary, author


def parse_rss_or_Headline_feed(
	raw_text: str,
	source_id: str,
	rubric_id: str,
	rubric_name: str,
	base_url: str = "https://www.kompas.com",
	max_articles: int = 40,
) -> List[Article]:
	"""Extract an article list from an RSS/XML feed (if XML) or from a Kompas.com rubric HTML page."""
	stripped = (raw_text or "").lstrip()
	if stripped.startswith("<?xml") or stripped.startswith("<rss") or stripped.startswith("<feed"):
		rss_articles = _parse_rss_xml(stripped, source_id, rubric_id, rubric_name, max_articles)
		if rss_articles:
			return rss_articles

	return parse_kompas_rubric_headlines(
		html_string=raw_text,
		source_id=source_id,
		rubric_id=rubric_id,
		rubric_name=rubric_name,
		base_url=base_url,
		max_articles=max_articles,
	)


def _parse_rss_xml(
	xml_string: str,
	source_id: str,
	rubric_id: str,
	rubric_name: str,
	max_articles: int = 40,
) -> List[Article]:
	"""Extract an article list from an RSS 2.0 XML feed when available."""
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

			if not title or not link or not is_valid_kompas_article_url(link):
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


def parse_kompas_rubric_headlines(
	html_string: str,
	source_id: str = "kompas",
	rubric_id: str = "news",
	rubric_name: str = "News",
	base_url: str = "https://www.kompas.com",
	max_articles: int = 40,
) -> List[Article]:
	"""
	Extract the latest news article list from a Kompas.com rubric HTML page:
	- Preserves the original display order from the source page.
	- Deduplicates strictly by normalized `canonical_url` (never merging two distinct articles with similar titles).
	- Preserves full article titles without truncation.
	"""
	builder = _DOMBuilder()
	builder.feed(html_string or "")
	root = builder.root

	# Stage 1: Collect candidate article links and their enclosing card metadata in DOM order
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
			if not is_valid_kompas_article_url(full_url):
				continue

			# Ignore links nested inside navigation or footer landmarks
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
				link_title = (node.attrs.get("title") or "").strip()

			# Skip short thumbnail badges or noise links
			if not link_title or len(link_title) < 12 or _is_noise_text(link_title):
				continue

			canonical = normalize_canonical_url(full_url)
			if not canonical:
				continue

			card = _find_enclosing_card(node)
			cat, pub_at, summary, author = _extract_card_metadata(card, rubric_name)

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
				# If an earlier link on the same card had a shorter label, upgrade to the fuller headline text
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
		# Ensure the extracted headline is substantive
		if len(item["title"]) < 15:
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


def _is_link_only_list_item(li_node: _DOMNode) -> bool:
	"""Detect whether an `<li>` element is merely a tag link (`/tag/`) or related-article widget (`/read/`)."""
	full_text = li_node.get_text(exclude_baca_juga=True)
	if not full_text:
		return True
	if _is_noise_text(full_text):
		return True

	for child in _iter_nodes(li_node):
		if child.tag == "a":
			href = (child.attrs.get("href") or "").lower()
			link_text = child.get_text()
			if "/tag/" in href or "/topik/" in href:
				return True
			if "/read/" in href and len(link_text) >= len(full_text) - 5:
				return True
	return False


def _extract_table_block(table_node: _DOMNode) -> Optional[Dict[str, Any]]:
	"""Extract an HTML table containing news data into structured headers and rows."""
	headers: List[str] = []
	rows: List[List[str]] = []

	for tr in _iter_nodes(table_node):
		if tr.tag != "tr":
			continue
		th_cells: List[str] = []
		td_cells: List[str] = []
		for cell in tr.children:
			if not isinstance(child := cell, _DOMNode):
				continue
			if child.tag == "th":
				th_cells.append(child.get_text(exclude_baca_juga=True))
			elif child.tag in ("td",):
				td_cells.append(child.get_text(exclude_baca_juga=True))

		if th_cells and not headers and not td_cells:
			headers = th_cells
		elif th_cells and td_cells:
			rows.append(th_cells + td_cells)
		elif td_cells:
			if not headers and len(rows) == 0 and all(len(c) < 50 for c in td_cells):
				# The first row often serves as column headers in Kompas article tables
				headers = td_cells
			else:
				rows.append(td_cells)

	if not headers and not rows:
		return None
	if headers and not rows:
		return None
	return ContentBlock(block_type="table", headers=headers, rows=rows).to_dict()


def _clean_paragraph_text(text: str) -> str:
	"""Clean residual boilerplate prefixes without altering valid news sentences."""
	if not text:
		return ""
	cleaned = " ".join(text.split()).strip()
	# Strip residual "Baca juga: ..." lines if still attached
	cleaned = re.sub(r"^Baca\s+juga\s*:\s*.*$", "", cleaned, flags=re.IGNORECASE).strip()
	return cleaned


def _extract_clean_blocks_from_container(container_node: _DOMNode, blocks: List[Dict[str, Any]], page_url: str = "") -> None:
	"""
	Recursively extract clean content blocks (h2/h3/h4, p, blockquote, ul, ol, table, image, video, caption)
	while preserving logical reading order.
	"""
	for child in container_node.children:
		if not isinstance(child, _DOMNode):
			continue
		if _is_baca_juga_inline_node(child):
			continue
		if _extract_inline_media_blocks_from_node(child, blocks, page_url):
			continue
		if _is_excluded_node(child):
			continue

		t = child.tag
		if t in ("h2", "h3", "h4"):
			text = child.get_text(exclude_baca_juga=True)
			if text and not _is_noise_text(text):
				blocks.append(ContentBlock(block_type=t, text=text).to_dict())

		elif t == "blockquote":
			text = child.get_text(exclude_baca_juga=True)
			if text and not _is_noise_text(text):
				blocks.append(ContentBlock(block_type="blockquote", text=text).to_dict())

		elif t in ("ul", "ol"):
			items: List[str] = []
			for li in child.children:
				if isinstance(li, _DOMNode) and li.tag == "li" and not _is_excluded_node(li):
					if not _is_link_only_list_item(li):
						item_text = li.get_text(exclude_baca_juga=True)
						if item_text and not _is_noise_text(item_text):
							items.append(item_text)
			if items:
				blocks.append(ContentBlock(block_type=t, items=items).to_dict())

		elif t == "table":
			tbl_block = _extract_table_block(child)
			if tbl_block:
				blocks.append(tbl_block)

		elif t in ("figure", "figcaption") or "photo__caption" in child.classes or "read__photo__caption" in child.classes:
			cap_text = child.get_text(exclude_baca_juga=True)
			cap_text = re.sub(r"^Lihat\s+Foto\s*", "", cap_text, flags=re.IGNORECASE).strip()
			if cap_text and len(cap_text) > 15 and not _is_noise_text(cap_text):
				blocks.append(ContentBlock(block_type="caption", text=cap_text).to_dict())

		elif t == "p":
			# Preserve valid short paragraphs (such as short quotes or concise facts)
			# while filtering out noise or "Baca juga" links
			text = _clean_paragraph_text(child.get_text(exclude_baca_juga=True))
			if text and len(text) >= 3 and not _is_noise_text(text):
				blocks.append(ContentBlock(block_type="p", text=text).to_dict())

		else:
			# Traverse wrapper div/section/article/span elements inside the article container
			_extract_clean_blocks_from_container(child, blocks, page_url=page_url)


def detect_kompas_all_pages_url(html_string: str, current_url: str) -> Optional[str]:
	"""
	Check whether an article spans multiple pages and provides a verified full-page link (`?page=all`)
	in the DOM. Never appends URL parameters blindly when the article has only a single page.
	"""
	if not html_string or not current_url:
		return None
	if "page=all" in current_url.lower():
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
			if "page=all" in href.lower() and (
				"paging" in cls_joined
				or "show all" in txt_low
				or "tampilkan semua" in txt_low
				or "semua halaman" in txt_low
				or is_valid_kompas_article_url(href)
			):
				candidate = urllib.parse.urljoin(current_url, href)
				if is_valid_kompas_article_url(candidate):
					return candidate
	return None


def _parse_credit_names(raw_credit: str) -> Tuple[str, str]:
	"""Separate Author and Editor names from a Kompas.com article credit line."""
	author = ""
	editor = ""
	if not raw_credit:
		return author, editor

	cleaned = " ".join(raw_credit.split()).strip()
	# Match patterns such as "Penulis: X | Editor: Y" or "Penulis X Editor Y"
	ed_match = re.search(r"Editor\s*[:\-]?\s*([^|,\n]+)", cleaned, re.IGNORECASE)
	if ed_match:
		editor = ed_match.group(1).strip(" :-|,")

	au_match = re.search(r"Penulis\s*[:\-]?\s*([^|]+?)(?:\s+Editor\b|$)", cleaned, re.IGNORECASE)
	if au_match:
		author = au_match.group(1).strip(" :-|,")
	elif not editor and cleaned and len(cleaned) < 80:
		author = cleaned.strip(" :-|,")

	return author, editor




# Substrings in image URLs that indicate logos, icons, avatars, or ad trackers rather than news photos
NON_PHOTO_URL_SUBSTRINGS: Tuple[str, ...] = (
	"logo", "icon", "avatar", "sprite", "pixel", "1x1", "blank.", "placeholder",
	"loading", "spinner", "ads/", "/ads", "banner", "button", "badge",
	"whatsapp", "facebook", "twitter", "telegram", "instagram", "linkedin",
	"tiktok", "youtube-icon", "google-news", "gnews", "kompas-id", " doubleclick",
	"scorecardresearch", "googletagmanager", "analytics", ".svg",
)

# Known video embed host/path patterns across Indonesian news portals
VIDEO_EMBED_PATTERNS: Tuple[str, ...] = (
	"youtube.com/embed/",
	"youtube-nocookie.com/embed/",
	"youtu.be/",
	"youtube.com/watch",
	"20.detik.com/embed",
	"20.detik.com/detikflash",
	"video.detik.com",
	"cnnindonesia.com/tv/embed",
	"cnbcindonesia.com/tv/embed",
	"dailymotion.com/embed/",
	"kgnow.com",
	"kompas.tv",
	"brid.tv",
	"jwplayer",
)


def _is_valid_article_photo_url(url: str) -> bool:
	"""Return True if `url` looks like a genuine news article photo rather than a site icon or tracker."""
	if not url:
		return False
	cleaned = url.strip()
	if cleaned.startswith("data:"):
		return False
	low = cleaned.lower()
	if not (low.startswith("http://") or low.startswith("https://") or low.startswith("//")):
		return False
	for bad in NON_PHOTO_URL_SUBSTRINGS:
		if bad in low:
			return False
	return True


def _is_valid_video_url(url: str) -> bool:
	"""Return True if `url` is a playable video stream or recognized video player embed URL."""
	if not url:
		return False
	cleaned = url.strip()
	low = cleaned.lower()
	if not (low.startswith("http://") or low.startswith("https://") or low.startswith("//")):
		return False
	if any(ext in low for ext in (".mp4", ".m3u8", ".webm", ".ogg")):
		return True
	for pat in VIDEO_EMBED_PATTERNS:
		if pat in low:
			return True
	return False


def _resolve_media_url(raw_url: str, page_url: str) -> str:
	"""Normalize a relative or protocol-relative media URL against `page_url`."""
	if not raw_url:
		return ""
	cleaned = raw_url.strip()
	if cleaned.startswith("//"):
		return "https:" + cleaned
	return urllib.parse.urljoin(page_url or "https://www.kompas.com", cleaned)


def _extract_img_url_from_node(img_node: _DOMNode, page_url: str) -> str:
	"""Extract the highest-resolution image URL from an `<img>` DOM node."""
	for attr in ("data-src", "data-original", "data-lazy-src", "src"):
		val = (img_node.attrs.get(attr) or "").strip()
		if val and not val.startswith("data:"):
			resolved = _resolve_media_url(val, page_url)
			if _is_valid_article_photo_url(resolved):
				return resolved
	srcset = (img_node.attrs.get("srcset") or img_node.attrs.get("data-srcset") or "").strip()
	if srcset:
		first_part = srcset.split(",")[0].strip().split()[0]
		resolved = _resolve_media_url(first_part, page_url)
		if _is_valid_article_photo_url(resolved):
			return resolved
	return ""


def extract_article_media_from_dom(
	root: _DOMNode,
	content_containers: List[_DOMNode],
	html_string: str,
	page_url: str,
	main_caption: str = "",
	default_title: str = "",
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
	"""
	Extract deduplicated photos and videos from an article DOM tree, meta tags, and JSON-LD.
	Returns `(photos_list, videos_list)` where each item is a `MediaItem.to_dict()` dictionary.
	"""
	from .models import MediaItem

	photos: List[Dict[str, str]] = []
	seen_photo_urls: Set[str] = set()

	videos: List[Dict[str, str]] = []
	seen_video_urls: Set[str] = set()

	def _add_photo(url: str, caption: str = "") -> None:
		resolved = _resolve_media_url(url, page_url)
		if not _is_valid_article_photo_url(resolved):
			return
		norm_key = resolved.split("?")[0].lower()
		if norm_key in seen_photo_urls:
			if caption:
				for p in photos:
					if p["url"].split("?")[0].lower() == norm_key and not p.get("caption"):
						p["caption"] = caption
			return
		seen_photo_urls.add(norm_key)
		photos.append(
			MediaItem(
				media_type="photo",
				url=resolved,
				caption=caption or main_caption or default_title,
			).to_dict()
		)

	def _add_video(url: str, caption: str = "", thumbnail_url: str = "", provider: str = "", stream_url: str = "") -> None:
		resolved = _resolve_media_url(url, page_url)
		if not _is_valid_video_url(resolved):
			return
		# Normalize YouTube watch/short URLs to /embed/ for direct inline HTML playback
		yt_w = re.match(r"^https?://(?:www\.|m\.)?youtube\.com/watch\?.*?\bv=([a-zA-Z0-9_\-]{6,})", resolved, re.IGNORECASE)
		if yt_w:
			resolved = f"https://www.youtube.com/embed/{yt_w.group(1)}"
		yt_s = re.match(r"^https?://youtu\.be/([a-zA-Z0-9_\-]{6,})", resolved, re.IGNORECASE)
		if yt_s:
			resolved = f"https://www.youtube.com/embed/{yt_s.group(1)}"
		norm_key = resolved.lower()
		if norm_key in seen_video_urls:
			return
		seen_video_urls.add(norm_key)
		resolved_stream = _resolve_media_url(stream_url, page_url) if stream_url else ""
		if not resolved_stream and any(ext in norm_key for ext in (".mp4", ".webm", ".ogg", ".m3u8")):
			resolved_stream = resolved
		if not provider:
			low = norm_key
			if "youtube" in low or "youtu.be" in low:
				provider = "YouTube"
			elif "detik" in low:
				provider = "20Detik"
			elif "cnnindonesia" in low:
				provider = "CNN Indonesia TV"
			elif "cnbcindonesia" in low:
				provider = "CNBC Indonesia TV"
			elif "kompas" in low or "kgnow" in low or "dailymotion" in low:
				provider = "Kompas Video"
			else:
				provider = "Video"
		videos.append(
			MediaItem(
				media_type="video",
				url=resolved,
				caption=caption or default_title or "Video Berita",
				thumbnail_url=_resolve_media_url(thumbnail_url, page_url) if thumbnail_url else "",
				provider=provider,
				stream_url=resolved_stream,
			).to_dict()
		)

	# 1. Inspect <meta> tags for og:image, twitter:image, and og:video
	og_image_url = ""
	for node in _iter_nodes(root):
		if node.tag == "meta":
			m_name = (node.attrs.get("property") or node.attrs.get("name") or "").lower().strip()
			m_content = (node.attrs.get("content") or "").strip()
			if not m_content:
				continue
			if m_name in ("og:image", "twitter:image", "twitter:image:src") and not og_image_url:
				og_image_url = m_content
			elif m_name in ("og:video", "og:video:url", "og:video:secure_url"):
				_add_video(m_content, caption=default_title)

	if og_image_url:
		_add_photo(og_image_url, caption=main_caption or default_title)

	# 2. Inspect JSON-LD blocks for ImageObject and VideoObject
	if html_string:
		import json as _json
		for raw_json in re.findall(
			r"<script[^>]*type=[\"']application/ld\\+json[\"'][^>]*>(.*?)</script>",
			html_string,
			flags=re.IGNORECASE | re.DOTALL,
		):
			try:
				data = _json.loads(raw_json.strip())
			except Exception:
				continue
			items = data if isinstance(data, list) else [data]
			for obj in items:
				if not isinstance(obj, dict):
					continue
				graph = obj.get("@graph")
				if isinstance(graph, list):
					items.extend(g for g in graph if isinstance(g, dict))
				atype = str(obj.get("@type") or "").lower()
				if "videoobject" in atype:
					v_url = str(obj.get("contentUrl") or obj.get("embedUrl") or obj.get("url") or "").strip()
					v_name = html.unescape(str(obj.get("name") or obj.get("description") or default_title)).strip()
					v_thumb = obj.get("thumbnailUrl")
					if isinstance(v_thumb, list) and v_thumb:
						v_thumb = v_thumb[0]
					v_thumb_str = str(v_thumb or "").strip() if isinstance(v_thumb, str) else ""
					if v_url:
						_add_video(v_url, caption=v_name, thumbnail_url=v_thumb_str)
				img_field = obj.get("image")
				if isinstance(img_field, str):
					_add_photo(img_field, caption=main_caption or default_title)
				elif isinstance(img_field, dict) and img_field.get("url"):
					_add_photo(str(img_field["url"]), caption= str(img_field.get("caption") or main_caption or default_title))
				elif isinstance(img_field, list):
					for it in img_field:
						if isinstance(it, str):
							_add_photo(it, caption=main_caption or default_title)
						elif isinstance(it, dict) and it.get("url"):
							_add_photo(str(it["url"]), caption=str(it.get("caption") or main_caption or default_title))

	# 3. Inspect hero photo containers and article body containers for <img>, <video>, <source>, and <iframe>
	search_scopes: List[_DOMNode] = []
	for node in _iter_nodes(root):
		cls_j = " ".join(node.classes).lower()
		if node.tag == "figure" or any(
			k in cls_j
			for k in (
				"photo__wrap", "read__photo", "detail__media", "pic_artikel",
				"media_artikel", "galeri", "foto", "video",
			)
		):
			search_scopes.append(node)
	search_scopes.extend(content_containers)
	if not search_scopes:
		search_scopes.append(root)

	for scope in search_scopes:
		for node in _iter_nodes(scope):
			# Check <video> and <source>
			if node.tag in ("video", "source"):
				v_src = (node.attrs.get("src") or node.attrs.get("data-src") or "").strip()
				if v_src:
					_add_video(v_src, caption=default_title)
			# Check <iframe> for video embeds
			elif node.tag == "iframe":
				i_src = (node.attrs.get("src") or node.attrs.get("data-src") or "").strip()
				i_title = (node.attrs.get("title") or default_title or "").strip()
				if i_src and _is_valid_video_url(i_src):
					_add_video(i_src, caption=i_title)
			# Check <img> for article photos
			elif node.tag == "img":
				# Skip images inside nav/footer/related/baca-juga widgets
				parent_ptr = node.parent
				skip_img = False
				fig_caption = ""
				while parent_ptr is not None and parent_ptr != root:
					if parent_ptr.tag in ("nav", "footer", "header", "aside"):
						skip_img = True
						break
					p_cls = (" ".join(parent_ptr.classes) + " " + parent_ptr.id).lower()
					if any(
						bad_c in p_cls
						for bad_c in ("baca-juga", "bacajuga", "linksisip", "related", "terpopuler", "recomend", "ads-", "iklan", "share", "comment")
					):
						skip_img = True
						break
					if parent_ptr.tag == "figure" and not fig_caption:
						for sub in _iter_nodes(parent_ptr):
							if sub.tag == "figcaption" or "caption" in " ".join(sub.classes).lower():
								fig_caption = sub.get_text()
								break
					parent_ptr = parent_ptr.parent
				if skip_img:
					continue

				img_url = _extract_img_url_from_node(node, page_url)
				if not img_url:
					continue
				alt_txt = (node.attrs.get("alt") or node.attrs.get("title") or "").strip()
				cap = fig_caption or alt_txt or main_caption or default_title
				cap = re.sub(r"^Lihat\s+Foto\s*", "", cap, flags=re.IGNORECASE).strip()
				_add_photo(img_url, caption=cap)

	# 4. Also check raw HTML for embedded video streams (.mp4 / .m3u8) or YouTube/20Detik iframe URLs
	if html_string:
		for m_yt in re.finditer(
			r'https?://(?:www\.)?(?:youtube\.com/embed/[a-zA-Z0-9_\-]+|20\.detik\.com/embed/[a-zA-Z0-9_\-/]+|cnnindonesia\.com/tv/embed/[a-zA-Z0-9_\-/]+|cnbcindonesia\.com/tv/embed/[a-zA-Z0-9_\-/]+|dailymotion\.com/embed/video/[a-zA-Z0-9_\-]+)',
			html_string,
			flags=re.IGNORECASE,
		):
			_add_video(m_yt.group(0), caption=default_title)

		for m_mp4 in re.finditer(
			r"https?://[^\"\x27\\s<>]+\\.(?:mp4|m3u8)(?:\\?[^\"\x27\\s<>]*)?",
			html_string,
			flags=re.IGNORECASE,
		):
			candidate_stream = m_mp4.group(0)
			if not any(bad in candidate_stream.lower() for bad in ("ads", "banner", "preroll", " bumper")):
				_add_video(candidate_stream, caption=default_title)

	# 5. If the article URL itself is on 20.detik.com or a video channel and no video was added yet, include the page URL
	if not videos and page_url:
		low_page = page_url.lower()
		if "20.detik.com" in low_page or "/video/" in low_page or "/detikflash/" in low_page:
			videos.append(
				MediaItem(
					media_type="video",
					url=page_url,
					caption=default_title or "Video Berita",
					thumbnail_url=photos[0]["url"] if photos else "",
					provider="Video Portal",
				).to_dict()
			)

	return photos, videos



def _extract_inline_media_blocks_from_node(node: _DOMNode, blocks: List[Dict[str, Any]], page_url: str) -> bool:
	"""
	Inspect `node` for inline `<video>`, video `<iframe>`, or `<figure>`/`<img>` elements
	and append `ContentBlock(block_type="video"|"image")` in reading order.
	Returns True if `node` was handled as a media element or figure.
	"""
	t = node.tag
	if t == "video":
		v_src = (node.attrs.get("src") or node.attrs.get("data-src") or "").strip()
		if not v_src:
			for sub in _iter_nodes(node):
				if sub.tag == "source":
					v_src = (sub.attrs.get("src") or sub.attrs.get("data-src") or "").strip()
					if v_src:
						break
		resolved = _resolve_media_url(v_src, page_url)
		if _is_valid_video_url(resolved):
			stream = resolved if any(ext in resolved.lower() for ext in (".mp4", ".webm", ".ogg", ".m3u8")) else ""
			blocks.append(ContentBlock(block_type="video", url=resolved, stream_url=stream, text=node.attrs.get("title", "")).to_dict())
			return True
		return False

	if t == "iframe":
		i_src = (node.attrs.get("src") or node.attrs.get("data-src") or "").strip()
		resolved = _resolve_media_url(i_src, page_url)
		if _is_valid_video_url(resolved):
			m_yt = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_\-]+)", resolved, re.IGNORECASE)
			if m_yt:
				resolved = f"https://www.youtube.com/embed/{m_yt.group(1)}"
			blocks.append(ContentBlock(block_type="video", url=resolved, text=(node.attrs.get("title") or "").strip()).to_dict())
			return True
		return True

	if t == "img":
		img_url = _extract_img_url_from_node(node, page_url)
		if img_url:
			alt_txt = (node.attrs.get("alt") or node.attrs.get("title") or "").strip()
			alt_txt = re.sub(r"^Lihat\s+Foto\s*", "", alt_txt, flags=re.IGNORECASE).strip()
			blocks.append(ContentBlock(block_type="image", url=img_url, text=alt_txt).to_dict())
			return True
		return False

	if t == "figure" or "photo__wrap" in node.classes or "read__photo" in node.classes or "detail__media" in node.classes:
		cap_text = ""
		for sub in _iter_nodes(node):
			if sub.tag == "figcaption" or any(c in sub.classes for c in ("photo__caption", "read__photo__caption", "detail__media-caption")):
				cap_text = sub.get_text(exclude_baca_juga=True)
				break
		if not cap_text:
			cap_text = node.get_text(exclude_baca_juga=True)
		cap_text = re.sub(r"^Lihat\s+Foto\s*", "", cap_text, flags=re.IGNORECASE).strip()

		for sub in _iter_nodes(node):
			if sub.tag in ("video", "source"):
				v_src = (sub.attrs.get("src") or sub.attrs.get("data-src") or "").strip()
				resolved = _resolve_media_url(v_src, page_url)
				if _is_valid_video_url(resolved):
					stream = resolved if any(ext in resolved.lower() for ext in (".mp4", ".webm", ".ogg", ".m3u8")) else ""
					blocks.append(ContentBlock(block_type="video", url=resolved, stream_url=stream, text=cap_text).to_dict())
					return True
			elif sub.tag == "iframe":
				i_src = (sub.attrs.get("src") or sub.attrs.get("data-src") or "").strip()
				resolved = _resolve_media_url(i_src, page_url)
				if _is_valid_video_url(resolved):
					blocks.append(ContentBlock(block_type="video", url=resolved, text=cap_text or (sub.attrs.get("title") or "").strip()).to_dict())
					return True
			elif sub.tag == "img":
				img_url = _extract_img_url_from_node(sub, page_url)
				if img_url:
					alt_txt = (sub.attrs.get("alt") or sub.attrs.get("title") or "").strip()
					blocks.append(ContentBlock(block_type="image", url=img_url, text=cap_text or alt_txt).to_dict())
					return True

		if cap_text and len(cap_text) > 15 and not _is_noise_text(cap_text):
			blocks.append(ContentBlock(block_type="caption", text=cap_text).to_dict())
		return True

	return False


def parse_kompas_article_html(html_string: str, url: str, default_category: str = "") -> Dict[str, Any]:
	"""
	Parse a Kompas.com article HTML document to extract metadata and structured content blocks
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
		# 0. Metadata from official Kompas.com <meta> tags as an accurate fallback
		if node.tag == "meta":
			meta_name = (node.attrs.get("name") or node.attrs.get("property") or "").lower()
			meta_content = (node.attrs.get("content") or "").strip()
			if not meta_content:
				continue
			if meta_name in ("content_author", "author") and not author:
				author = meta_content
			elif meta_name == "content_editor" and not editor:
				editor = meta_content
			elif meta_name in ("content_category", "article:section") and not category:
				category = meta_content
			elif meta_name in ("content_publisheddate", "article:published_time") and not published_at:
				published_at = meta_content
			elif meta_name in ("description", "og:description") and not meta_description:
				meta_description = html.unescape(meta_content).strip()
			elif meta_name == "og:title" and not title:
				title = html.unescape(meta_content).strip()

		# 1. Article title (h1.read__title, h1.article__title, or primary h1)
		if node.tag == "h1":
			t_txt = node.get_text()
			if t_txt and ("read__title" in node.classes or "article__title" in node.classes or not title):
				title = t_txt

		# 2. Publication timestamp (.read__time or .article__date)
		if "read__time" in node.classes or "article__date" in node.classes:
			raw_time = node.get_text()
			cleaned_time = re.sub(r"^Kompas\.com\s*[\-–,|]*\s*", "", raw_time, flags=re.IGNORECASE).strip()
			if cleaned_time:
				published_at = cleaned_time

		# 3. Category from breadcrumb (.breadcrumb__item)
		if "breadcrumb__item" in node.classes:
			cat_txt = node.get_text()
			if cat_txt and cat_txt.lower() not in ("kompas.com", "home", "beranda"):
				category = cat_txt

		# 4. Author and Editor from credit block (.read__credit, .credit-title-name)
		if "read__credit" in node.classes or "credit-title-name" in node.classes or "read__author" in node.classes:
			cred_txt = node.get_text()
			parsed_au, parsed_ed = _parse_credit_names(cred_txt)
			if parsed_au and not author:
				author = parsed_au
			if parsed_ed and not editor:
				editor = parsed_ed

		# 5. Summary or deck (.read__summary, .read__lead)
		if "read__summary" in node.classes or "read__lead" in node.classes or "article__lead" in node.classes:
			s_txt = node.get_text()
			if s_txt and not _is_noise_text(s_txt):
				summary_deck = s_txt

		# 6. Primary photo caption (.photo__caption, .read__photo__caption, or figcaption inside photo block)
		if not main_caption and (
			"photo__caption" in node.classes
			or "read__photo__caption" in node.classes
			or (node.tag == "figcaption" and node.parent and ("photo" in " ".join(node.parent.classes).lower()))
		):
			cap_txt = node.get_text()
			cap_txt = re.sub(r"^Lihat\s+Foto\s*", "", cap_txt, flags=re.IGNORECASE).strip()
			if cap_txt and len(cap_txt) > 10 and not _is_noise_text(cap_txt):
				main_caption = cap_txt

		# 7. Main article content container (.read__content or .article__content)
		if "read__content" in node.classes or "article__content" in node.classes:
			content_containers.append(node)

	blocks: List[Dict[str, Any]] = []
	if main_caption:
		blocks.append(ContentBlock(block_type="caption", text=main_caption).to_dict())

	if content_containers:
		for container in content_containers:
			_extract_clean_blocks_from_container(container, blocks, page_url=url)
	else:
		# Fallback if class names change: search for an <article> element while keeping strict noise filtering
		for node in _iter_nodes(root):
			if node.tag == "article":
				_extract_clean_blocks_from_container(node, blocks, page_url=url)
				if blocks:
					break

	# Remove consecutive identical blocks
	deduped_blocks: List[Dict[str, Any]] = []
	for b in blocks:
		if deduped_blocks and deduped_blocks[-1] == b:
			continue
		deduped_blocks.append(b)
	blocks = deduped_blocks

	# Count substantive body blocks (paragraphs, lists, tables, blockquotes)
	substantive_blocks = [
		b for b in blocks
		if b.get("type") in ("p", "ul", "ol", "table", "blockquote")
	]

	if not summary_deck:
		if substantive_blocks and substantive_blocks[0].get("text"):
			summary_deck = substantive_blocks[0]["text"]
		elif meta_description and not _is_noise_text(meta_description):
			summary_deck = meta_description

	# Determine whether content is fully loaded, partially loaded, or failed
	if len(substantive_blocks) >= 2 or (
		len(substantive_blocks) == 1 and len(substantive_blocks[0].get("text", "")) >= 120
	):
		status = ArticleStatus.CONTENT_LOADED
	elif len(substantive_blocks) == 1 or summary_deck:
		status = ArticleStatus.CONTENT_PARTIAL
		if not substantive_blocks and summary_deck:
			blocks.append(ContentBlock(block_type="p", text=summary_deck).to_dict())
	else:
		status = ArticleStatus.CONTENT_FAILED

	# Check whether the final paragraph contains editorial source/credit attribution
	if blocks and blocks[-1].get("type") == "p":
		last_txt = blocks[-1].get("text", "")
		if last_txt.lower().startswith("sumber:") or last_txt.lower().startswith("kredit:"):
			source_credit = last_txt

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
		"category": category or default_category or "Kompas.com",
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
