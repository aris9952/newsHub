# -*- coding: utf-8 -*-
"""
Accessible wxPython desktop user interface, native NVDA HTML Browse Mode
(`ui.browseableMessage(..., isHtml=True)` modeled on `kompasTeknoReader`),
conflict-free in-dialog reading area (`wx.TextCtrl`), cross-portal news search,
and NVDA Settings panel for NewsHub for NVDA.

Provides:
- `NewsHubSettingsPanel`: Official NVDA Settings category panel integrated into
  `NVDA Preferences -> Settings -> NewsHub for NVDA`.
- `AccessibilitySettingsDialog`: Standalone settings dialog accessible directly from the
  dashboard or Preferences menu.
- `NewsHubDashboardDialog`: Main news reader dashboard featuring:
  - Cross-portal keyword search across all 5 supported portals (`Kompas.com`, `Detik.com`,
    `CNN Indonesia`, `CNBC Indonesia`, `Tempo.co`), hiding site/rubric selectors during
    active search results and restoring the default view on `Escape`.
  - Direct in-dialog article reading area (`wx.TextCtrl` with `TE_MULTILINE | TE_READONLY | TE_RICH2`)
    so `Up`/`Down Arrow` and standard NVDA reading commands work immediately when tabbing
    into the article content section without ever trapping focus.
  - Native NVDA HTML Browse Mode (`ui.browseableMessage(html_doc, title=..., isHtml=True)`,
    identical to `kompasTeknoReader`'s "Mode Jelajah HTML") accessible via the
    `Mode Jelajah HTML (Alt+H)` button, `Alt+H` shortcut, pressing `Enter` on an article
    headline or inside the reading area, or pressing HTML quick-navigation keys
    (`H`, `T`, `K`, `L`, `Q`, `G`) inside the reading area.
"""

import time
import webbrowser
from typing import Callable, List, Optional

try:
	import wx
except ImportError:
	wx = None  # Allows importing the module in headless unit test environments

try:
	import gui
	from gui import guiHelper
	from gui.settingsDialogs import SettingsPanel
except ImportError:
	gui = None
	guiHelper = None
	SettingsPanel = object

from .article_manager import ArticleManager
from .config_manager import (
	THEME_PALETTES,
	VALID_FONT_SCALES,
	config_manager,
)
from .formatter import (
	format_article_for_reading,
	format_article_html,
	format_article_selection_announcement,
)

try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	def _(s: str) -> str:
		return s

from .models import Article, ArticleStatus, RubricConfig, SiteConfig
from .sources import get_all_sites, get_default_site, get_site_by_id


_last_announced_text: str = ""
_last_announced_time: float = 0.0
_settings_change_listeners: List[Callable[[], None]] = []


def register_settings_change_listener(callback: Callable[[], None]) -> None:
	"""Register a callback to be invoked on the GUI thread when settings are saved."""
	if callback not in _settings_change_listeners:
		_settings_change_listeners.append(callback)


def unregister_settings_change_listener(callback: Callable[[], None]) -> None:
	"""Unregister a previously registered settings change callback."""
	if callback in _settings_change_listeners:
		_settings_change_listeners.remove(callback)


def notify_settings_changed() -> None:
	"""Notify all active listeners that user preferences have been updated."""
	for callback in list(_settings_change_listeners):
		try:
			if wx is not None and not wx.IsMainThread():
				wx.CallAfter(callback)
			else:
				callback()
		except Exception:
			pass


def announce_nvda(message: str, allow_repeat_after_sec: float = 1.5) -> None:
	"""
	Safely announce a status message through NVDA (`ui.message`) on the main GUI thread
	while suppressing consecutive duplicate announcements within a short time window.
	"""
	global _last_announced_text, _last_announced_time
	if not message or not message.strip():
		return
	cleaned = " ".join(message.split()).strip()
	now = time.monotonic()
	if cleaned == _last_announced_text and (now - _last_announced_time) < allow_repeat_after_sec:
		return
	_last_announced_text = cleaned
	_last_announced_time = now

	def _speak():
		try:
			import ui
			ui.message(cleaned)
		except Exception:
			pass

	if wx is not None:
		try:
			if wx.IsMainThread():
				_speak()
			else:
				wx.CallAfter(_speak)
			return
		except Exception:
			pass
	_speak()


def _build_settings_choices():
	"""Build localized choice lists and key mappings for settings controls."""
	theme_keys = ["light", "dark", "high_contrast"]
	theme_labels = [
		_('Light (High Standard Contrast)'),
		_('Dark (Low Glare)'),
		_('High Contrast (Black - Yellow/White)'),
	]

	scale_values = list(VALID_FONT_SCALES)
	default_sfx = _(' (Default)')
	scale_labels = [f"{s}%" + (default_sfx if s == 100 else "") for s in scale_values]

	family_keys = ["sans_serif", "serif"]
	family_labels = [_('Sans-serif (Segoe UI / Arial)'), _('Serif (Georgia / Times New Roman)')]

	spacing_keys = ["normal", "wide"]
	spacing_labels = [_('Normal (1 blank line)'), _('Wide (2 blank lines)')]

	interval_values = [30, 60, 120, 180, 300, 600]
	interval_labels = [
		_('30 seconds'),
		_('1 minute (60 seconds - Default)'),
		_('2 minutes (120 seconds)'),
		_('3 minutes (180 seconds)'),
		_('5 minutes (300 seconds)'),
		_('10 minutes (600 seconds)'),
	]

	max_values = [20, 30, 40, 50, 75, 100]
	max_labels = [
		_('{count} articles{suffix}').format(count=m, suffix=default_sfx if m == 40 else "")
		for m in max_values
	]

	return {
		"theme_keys": theme_keys,
		"theme_labels": theme_labels,
		"scale_values": scale_values,
		"scale_labels": scale_labels,
		"family_keys": family_keys,
		"family_labels": family_labels,
		"spacing_keys": spacing_keys,
		"spacing_labels": spacing_labels,
		"interval_values": interval_values,
		"interval_labels": interval_labels,
		"max_values": max_values,
		"max_labels": max_labels,
	}


if wx is not None and SettingsPanel is not object:

	class NewsHubSettingsPanel(SettingsPanel):
		"""
		Official NVDA Settings category panel registered under NVDA Preferences -> Settings.
		Allows configuring visual theme, font scale, font family, paragraph spacing,
		and background auto-refresh behavior.
		"""
		title = "NewsHub for NVDA"

		def makeSettings(self, settingsSizer: wx.Sizer) -> None:
			"""Populate the NVDA Settings panel controls using BoxSizerHelper."""
			meta = _build_settings_choices()
			self._theme_keys = meta["theme_keys"]
			self._scale_values = meta["scale_values"]
			self._family_keys = meta["family_keys"]
			self._spacing_keys = meta["spacing_keys"]
			self._interval_values = meta["interval_values"]
			self._max_values = meta["max_values"]

			s_helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

			# 1. Display Color Theme
			self.choice_theme = s_helper.addLabeledControl(
				_('Display color &theme:'),
				wx.Choice,
				choices=meta["theme_labels"],
			)
			self.choice_theme.SetName(_('Display color theme'))

			# 2. Font Size (85% - 150%)
			self.choice_scale = s_helper.addLabeledControl(
				_('&Font size (85% - 150%):'),
				wx.Choice,
				choices=meta["scale_labels"],
			)
			self.choice_scale.SetName(_('Font size'))

			# 3. Font Family (Sans-serif / Serif)
			self.choice_family = s_helper.addLabeledControl(
				_('Reading font &family:'),
				wx.Choice,
				choices=meta["family_labels"],
			)
			self.choice_family.SetName(_('Reading font family'))

			# 4. Paragraph Spacing (Normal / Wide)
			self.choice_spacing = s_helper.addLabeledControl(
				_('&Paragraph spacing:'),
				wx.Choice,
				choices=meta["spacing_labels"],
			)
			self.choice_spacing.SetName(_('Paragraph spacing'))

			# 5. Background Auto-Refresh Checkbox
			self.chk_auto_refresh = s_helper.addItem(
				wx.CheckBox(self, label=_('Enable automatic news list updates'))
			)
			self.chk_auto_refresh.SetName(_('Enable automatic news list updates'))

			# 6. Auto-Refresh Interval
			self.choice_interval = s_helper.addLabeledControl(
				_('Auto-refresh &interval:'),
				wx.Choice,
				choices=meta["interval_labels"],
			)
			self.choice_interval.SetName(_('Auto-refresh interval'))

			# 7. Maximum Articles per Rubric
			self.choice_max = s_helper.addLabeledControl(
				_('&Maximum articles per rubric:'),
				wx.Choice,
				choices=meta["max_labels"],
			)
			self.choice_max.SetName(_('Maximum articles per rubric'))

			self._load_values()

		def _load_values(self) -> None:
			"""Load current configuration values into the panel controls."""
			theme = config_manager.get("color_theme")
			self.choice_theme.SetSelection(
				self._theme_keys.index(theme) if theme in self._theme_keys else 0
			)

			scale = config_manager.get("font_scale")
			nearest_scale = min(self._scale_values, key=lambda x: abs(x - scale))
			self.choice_scale.SetSelection(self._scale_values.index(nearest_scale))

			family = config_manager.get("font_family")
			self.choice_family.SetSelection(
				self._family_keys.index(family) if family in self._family_keys else 0
			)

			spacing = config_manager.get("paragraph_spacing")
			self.choice_spacing.SetSelection(
				self._spacing_keys.index(spacing) if spacing in self._spacing_keys else 0
			)

			self.chk_auto_refresh.SetValue(bool(config_manager.get("auto_refresh_enabled")))

			interval = config_manager.get("auto_refresh_interval_sec")
			nearest_int = min(self._interval_values, key=lambda x: abs(x - interval))
			self.choice_interval.SetSelection(self._interval_values.index(nearest_int))

			max_art = config_manager.get("max_articles")
			nearest_max = min(self._max_values, key=lambda x: abs(x - max_art))
			self.choice_max.SetSelection(self._max_values.index(nearest_max))

		def onSave(self) -> None:
			"""Save updated preferences to NVDA configuration and notify any active dashboard."""
			updates = {
				"color_theme": self._theme_keys[max(0, self.choice_theme.GetSelection())],
				"font_scale": self._scale_values[max(0, self.choice_scale.GetSelection())],
				"font_family": self._family_keys[max(0, self.choice_family.GetSelection())],
				"paragraph_spacing": self._spacing_keys[max(0, self.choice_spacing.GetSelection())],
				"auto_refresh_enabled": bool(self.chk_auto_refresh.GetValue()),
				"auto_refresh_interval_sec": self._interval_values[max(0, self.choice_interval.GetSelection())],
				"max_articles": self._max_values[max(0, self.choice_max.GetSelection())],
			}
			config_manager.update_preferences(updates)
			notify_settings_changed()

else:
	NewsHubSettingsPanel = None


if wx is not None:

	class AccessibilitySettingsDialog(wx.Dialog):
		"""Standalone Settings Dialog for NewsHub for NVDA."""
		def __init__(self, parent: Optional[wx.Window]):
			super().__init__(
				parent,
				title=_('Settings — NewsHub for NVDA'),
				style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
			)
			self.SetName(_('NewsHub for NVDA Settings'))
			self._init_ui()
			self._load_current_values()
			self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

		def _init_ui(self) -> None:
			meta = _build_settings_choices()
			self._theme_keys = meta["theme_keys"]
			self._scale_values = meta["scale_values"]
			self._family_keys = meta["family_keys"]
			self._spacing_keys = meta["spacing_keys"]
			self._interval_values = meta["interval_values"]
			self._max_values = meta["max_values"]

			main_sizer = wx.BoxSizer(wx.VERTICAL)
			grid_sizer = wx.FlexGridSizer(rows=0, cols=2, vgap=10, hgap=12)
			grid_sizer.AddGrowableCol(1, 1)

			lbl_theme = wx.StaticText(self, label=_('Display color &theme:'))
			self.choice_theme = wx.Choice(self, choices=meta["theme_labels"])
			self.choice_theme.SetName(_('Display color theme'))
			grid_sizer.Add(lbl_theme, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_theme, 1, wx.EXPAND)

			lbl_scale = wx.StaticText(self, label=_('&Font size (85% - 150%):'))
			self.choice_scale = wx.Choice(self, choices=meta["scale_labels"])
			self.choice_scale.SetName(_('Font size'))
			grid_sizer.Add(lbl_scale, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_scale, 1, wx.EXPAND)

			lbl_family = wx.StaticText(self, label=_('Reading font &family:'))
			self.choice_family = wx.Choice(self, choices=meta["family_labels"])
			self.choice_family.SetName(_('Reading font family'))
			grid_sizer.Add(lbl_family, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_family, 1, wx.EXPAND)

			lbl_spacing = wx.StaticText(self, label=_('&Paragraph spacing:'))
			self.choice_spacing = wx.Choice(self, choices=meta["spacing_labels"])
			self.choice_spacing.SetName(_('Paragraph spacing'))
			grid_sizer.Add(lbl_spacing, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_spacing, 1, wx.EXPAND)

			lbl_auto = wx.StaticText(self, label=_('Background &auto-refresh:'))
			self.chk_auto_refresh = wx.CheckBox(self, label=_('Enable automatic news list updates'))
			self.chk_auto_refresh.SetName(_('Enable automatic news list updates'))
			grid_sizer.Add(lbl_auto, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.chk_auto_refresh, 1, wx.EXPAND)

			lbl_interval = wx.StaticText(self, label=_('Auto-refresh &interval:'))
			self.choice_interval = wx.Choice(self, choices=meta["interval_labels"])
			self.choice_interval.SetName(_('Auto-refresh interval'))
			grid_sizer.Add(lbl_interval, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_interval, 1, wx.EXPAND)

			lbl_max = wx.StaticText(self, label=_('&Maximum articles per rubric:'))
			self.choice_max = wx.Choice(self, choices=meta["max_labels"])
			self.choice_max.SetName(_('Maximum articles per rubric'))
			grid_sizer.Add(lbl_max, 0, wx.ALIGN_CENTER_VERTICAL)
			grid_sizer.Add(self.choice_max, 1, wx.EXPAND)

			main_sizer.Add(grid_sizer, 1, wx.ALL | wx.EXPAND, 14)

			btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
			self.btn_save = wx.Button(self, wx.ID_OK, label=_('&Save Settings'))
			self.btn_save.SetName(_('Save Settings'))
			self.btn_save.SetDefault()

			self.btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_('&Cancel'))
			self.btn_cancel.SetName(_('Cancel'))

			btn_sizer.AddStretchSpacer(1)
			btn_sizer.Add(self.btn_save, 0, wx.RIGHT, 8)
			btn_sizer.Add(self.btn_cancel, 0)
			main_sizer.Add(btn_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 14)

			self.SetSizerAndFit(main_sizer)
			self.CentreOnParent()
			self.Bind(wx.EVT_BUTTON, self._on_save, id=wx.ID_OK)

		def _load_current_values(self) -> None:
			theme = config_manager.get("color_theme")
			self.choice_theme.SetSelection(
				self._theme_keys.index(theme) if theme in self._theme_keys else 0
			)

			scale = config_manager.get("font_scale")
			nearest_scale = min(self._scale_values, key=lambda x: abs(x - scale))
			self.choice_scale.SetSelection(self._scale_values.index(nearest_scale))

			family = config_manager.get("font_family")
			self.choice_family.SetSelection(
				self._family_keys.index(family) if family in self._family_keys else 0
			)

			spacing = config_manager.get("paragraph_spacing")
			self.choice_spacing.SetSelection(
				self._spacing_keys.index(spacing) if spacing in self._spacing_keys else 0
			)

			self.chk_auto_refresh.SetValue(bool(config_manager.get("auto_refresh_enabled")))

			interval = config_manager.get("auto_refresh_interval_sec")
			nearest_int = min(self._interval_values, key=lambda x: abs(x - interval))
			self.choice_interval.SetSelection(self._interval_values.index(nearest_int))

			max_art = config_manager.get("max_articles")
			nearest_max = min(self._max_values, key=lambda x: abs(x - max_art))
			self.choice_max.SetSelection(self._max_values.index(nearest_max))

		def _on_save(self, event: wx.CommandEvent) -> None:
			updates = {
				"color_theme": self._theme_keys[max(0, self.choice_theme.GetSelection())],
				"font_scale": self._scale_values[max(0, self.choice_scale.GetSelection())],
				"font_family": self._family_keys[max(0, self.choice_family.GetSelection())],
				"paragraph_spacing": self._spacing_keys[max(0, self.choice_spacing.GetSelection())],
				"auto_refresh_enabled": bool(self.chk_auto_refresh.GetValue()),
				"auto_refresh_interval_sec": self._interval_values[max(0, self.choice_interval.GetSelection())],
				"max_articles": self._max_values[max(0, self.choice_max.GetSelection())],
			}
			config_manager.update_preferences(updates)
			notify_settings_changed()
			self.EndModal(wx.ID_OK)

		def _on_char_hook(self, event: wx.KeyEvent) -> None:
			if event.GetKeyCode() == wx.WXK_ESCAPE:
				self.EndModal(wx.ID_CANCEL)
				return
			event.Skip()


	class NewsHubDashboardDialog(wx.Dialog):
		"""
		Main NewsHub for NVDA dashboard dialog with cross-portal keyword search,
		conflict-free in-dialog reading area (`wx.TextCtrl`), and native NVDA HTML
		Browse Mode (`ui.browseableMessage(..., isHtml=True)` modeled on `kompasTeknoReader`).
		"""
		def __init__(self, parent: Optional[wx.Window], article_manager: ArticleManager):
			super().__init__(
				parent,
				title=_('NewsHub for NVDA — News Reading Made Easy'),
				style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX,
				size=wx.Size(920, 720),
			)
			self.SetName(_('NewsHub for NVDA — News Reading Made Easy'))
			self.article_manager = article_manager
			self._is_closing: bool = False

			self._sites: List[SiteConfig] = get_all_sites()
			self._active_site: SiteConfig = get_default_site()
			self._active_rubrics: List[RubricConfig] = []
			self._active_rubric: Optional[RubricConfig] = None
			self._articles: List[Article] = []
			self._current_article: Optional[Article] = None

			# Search mode state: when True, site & rubric selectors are hidden until Escape is pressed
			self._is_search_mode: bool = False
			self._active_search_query: str = ""
			self._pending_open_browse_mode: bool = False

			self._auto_refresh_timer = wx.Timer(self)
			self.Bind(wx.EVT_TIMER, self._on_auto_refresh_timer, self._auto_refresh_timer)

			self._build_ui()
			self._bind_events()
			self._apply_visual_preferences()
			self._restore_last_context_and_load()
			self._configure_auto_refresh_timer()
			register_settings_change_listener(self._on_external_settings_changed)

		def _build_ui(self) -> None:
			"""
			Build the dashboard layout with:
			1. Dashboard title banner.
			2. Cross-portal keyword search bar (Search input, Search button, Clear Search button).
			3. News portal selection and News rubric selection (automatically hidden during active search results).
			4. Article headline selection.
			5. Loading status information.
			6. Full article content reading area (`wx.TextCtrl` with `TE_MULTILINE | TE_READONLY | TE_RICH2`)
			   so `Up`/`Down Arrow` works immediately when focused, plus `Enter` / `Alt+H` / `H` / `T` / `K` / `L` / `Q` / `G`
			   to launch NVDA's native HTML Browse Mode (`ui.browseableMessage(..., isHtml=True)`).
			7. Action buttons (`HTML Browse Mode (Alt+H)`, `Previous Article`, `Next Article`, `Refresh List`,
			   `Reload Article`, `Open in Browser`, `Back to Rubric`, `Back to Portal`, `Settings`, `Close`).
			"""
			self.panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
			root_sizer = wx.BoxSizer(wx.VERTICAL)

			# 1. Dashboard Title Banner
			self.lbl_header = wx.StaticText(self.panel, label=_('&Dashboard Title:'))
			self.txt_dashboard_title = wx.TextCtrl(
				self.panel,
				value=_('NewsHub for NVDA — News Reading Made Easy '),
				style=wx.TE_READONLY,
			)
			self.txt_dashboard_title.SetName(_('NewsHub for NVDA Reading Area'))
			header_sizer = wx.BoxSizer(wx.HORIZONTAL)
			header_sizer.Add(self.lbl_header, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
			header_sizer.Add(self.txt_dashboard_title, 1, wx.EXPAND)
			root_sizer.Add(header_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

			# 2. Cross-Portal News Search Bar
			search_sizer = wx.BoxSizer(wx.HORIZONTAL)
			self.lbl_search = wx.StaticText(self.panel, label=_('Search &news:'))
			self.txt_search = wx.TextCtrl(
				self.panel,
				value="",
				style=wx.TE_PROCESS_ENTER,
			)
			self.txt_search.SetName(_('Search news keyword across all portals'))

			self.btn_search = wx.Button(self.panel, label=_('&Search News'))
			self.btn_search.SetName(_('Search news across all portals'))

			self.btn_clear_search = wx.Button(self.panel, label=_('Clear &Search (Esc)'))
			self.btn_clear_search.SetName(_('Clear search results and return to default view'))
			self.btn_clear_search.Hide()

			search_sizer.Add(self.lbl_search, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
			search_sizer.Add(self.txt_search, 1, wx.EXPAND | wx.RIGHT, 8)
			search_sizer.Add(self.btn_search, 0, wx.RIGHT, 6)
			search_sizer.Add(self.btn_clear_search, 0)
			root_sizer.Add(search_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)

			# 3. Row for News Portal and News Rubric selectors (hidden when search results are active)
			self.selector_sizer = wx.FlexGridSizer(rows=0, cols=4, vgap=8, hgap=10)
			self.selector_sizer.AddGrowableCol(1, 1)
			self.selector_sizer.AddGrowableCol(3, 1)

			self.lbl_site = wx.StaticText(self.panel, label=_('News &portal:'))
			self.choice_site = wx.Choice(
				self.panel,
				choices=[s.display_label for s in self._sites],
			)
			self.choice_site.SetName(_('News portal selection'))

			self.lbl_rubric = wx.StaticText(self.panel, label=_('News &rubric:'))
			self.choice_rubric = wx.Choice(self.panel, choices=[])
			self.choice_rubric.SetName(_('News rubric selection'))

			self.selector_sizer.Add(self.lbl_site, 0, wx.ALIGN_CENTER_VERTICAL)
			self.selector_sizer.Add(self.choice_site, 1, wx.EXPAND)
			self.selector_sizer.Add(self.lbl_rubric, 0, wx.ALIGN_CENTER_VERTICAL)
			self.selector_sizer.Add(self.choice_rubric, 1, wx.EXPAND)
			root_sizer.Add(self.selector_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

			# 4. Article Headline Selection
			article_sel_sizer = wx.BoxSizer(wx.HORIZONTAL)
			self.lbl_article = wx.StaticText(self.panel, label=_('&Article list:'))
			self.choice_article = wx.Choice(self.panel, choices=[_('No articles loaded yet')])
			self.choice_article.SetName(_('Article headline selection'))
			self.choice_article.SetSelection(0)
			article_sel_sizer.Add(self.lbl_article, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
			article_sel_sizer.Add(self.choice_article, 1, wx.EXPAND)
			root_sizer.Add(article_sel_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

			# 5. Loading Status Information
			status_sizer = wx.BoxSizer(wx.HORIZONTAL)
			self.lbl_status = wx.StaticText(self.panel, label=_('Loading &status:'))
			self.txt_status = wx.TextCtrl(
				self.panel,
				value=_('Ready. Select a news portal and rubric to load the article list.'),
				style=wx.TE_READONLY,
			)
			self.txt_status.SetName(_('Loading status information'))
			status_sizer.Add(self.lbl_status, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
			status_sizer.Add(self.txt_status, 1, wx.EXPAND)
			root_sizer.Add(status_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)

			# 6. Full Article Content Area (Multiline Read-Only TextCtrl for instant Up/Down arrow reading,
			# plus Enter / Alt+H / H / T / K / L / Q / G to open native NVDA HTML Browse Mode)
			self.lbl_content = wx.StaticText(self.panel, label=_('Full article &content:'))
			root_sizer.Add(self.lbl_content, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

			self.txt_content = wx.TextCtrl(
				self.panel,
				value=_('Select an article headline from the list to read its full content.'),
				style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL,
			)
			self.txt_content.SetName(_('Article reading area'))
			# Alias html_content to txt_content for backward compatibility
			self.html_content = self.txt_content
			root_sizer.Add(self.txt_content, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)

			# 7. Action Button Bar (starting with HTML Browse Mode button just like kompasTeknoReader)
			btn_bar_sizer = wx.WrapSizer(wx.HORIZONTAL)

			self.btn_browse_mode = wx.Button(self.panel, label=_('HTML &Browse Mode (Alt+H)'))
			self.btn_browse_mode.SetName(_('HTML Browse Mode (Alt+H)'))

			self.btn_prev = wx.Button(self.panel, label=_('Pre&vious Article (Alt+[)'))
			self.btn_prev.SetName(_('Previous Article (Alt+[)'))

			self.btn_next = wx.Button(self.panel, label=_('Ne&xt Article (Alt+])'))
			self.btn_next.SetName(_('Next Article (Alt+])'))

			self.btn_refresh_list = wx.Button(self.panel, label=_('Re&fresh Article List (F5)'))
			self.btn_refresh_list.SetName(_('Refresh Article List (F5)'))

			self.btn_reload_article = wx.Button(self.panel, label=_('&Reload Article (Ctrl+R)'))
			self.btn_reload_article.SetName(_('Reload Article (Ctrl+R)'))

			self.btn_open_browser = wx.Button(self.panel, label=_('&Open Original Article in Browser'))
			self.btn_open_browser.SetName(_('Open Original Article in Browser'))

			self.btn_back_rubric = wx.Button(self.panel, label=_('Back to &Rubric Selection'))
			self.btn_back_rubric.SetName(_('Back to rubric selection'))

			self.btn_back_site = wx.Button(self.panel, label=_('Back to &Portal Selection'))
			self.btn_back_site.SetName(_('Back to portal selection'))

			self.btn_settings = wx.Button(self.panel, label=_('Accessibility &Settings...'))
			self.btn_settings.SetName(_('Accessibility Settings'))

			self.btn_close = wx.Button(self.panel, wx.ID_CLOSE, label=_('&Close Dashboard (Esc)'))
			self.btn_close.SetName(_('Close Dashboard'))

			for btn in (
				self.btn_browse_mode,
				self.btn_prev,
				self.btn_next,
				self.btn_refresh_list,
				self.btn_reload_article,
				self.btn_open_browser,
				self.btn_back_rubric,
				self.btn_back_site,
				self.btn_settings,
				self.btn_close,
			):
				btn_bar_sizer.Add(btn, 0, wx.ALL, 4)

			root_sizer.Add(btn_bar_sizer, 0, wx.EXPAND | wx.ALL, 8)
			self.panel.SetSizer(root_sizer)

			dlg_sizer = wx.BoxSizer(wx.VERTICAL)
			dlg_sizer.Add(self.panel, 1, wx.EXPAND)
			self.SetSizer(dlg_sizer)
			self.SetMinSize(wx.Size(800, 580))
			self.CentreOnScreen()

			# Enforce logical Tab order across all dashboard controls
			ordered_controls = [
				self.txt_dashboard_title,
				self.txt_search,
				self.btn_search,
				self.btn_clear_search,
				self.choice_site,
				self.choice_rubric,
				self.choice_article,
				self.txt_status,
				self.txt_content,
				self.btn_browse_mode,
				self.btn_prev,
				self.btn_next,
				self.btn_refresh_list,
				self.btn_reload_article,
				self.btn_open_browser,
				self.btn_back_rubric,
				self.btn_back_site,
				self.btn_settings,
				self.btn_close,
			]
			for idx in range(1, len(ordered_controls)):
				ordered_controls[idx].MoveAfterInTabOrder(ordered_controls[idx - 1])

		def _bind_events(self) -> None:
			self.txt_search.Bind(wx.EVT_TEXT_ENTER, lambda evt: self.perform_search())
			self.btn_search.Bind(wx.EVT_BUTTON, lambda evt: self.perform_search())
			self.btn_clear_search.Bind(wx.EVT_BUTTON, lambda evt: self.clear_search_and_restore_default())

			self.choice_site.Bind(wx.EVT_CHOICE, self._on_site_selected)
			self.choice_rubric.Bind(wx.EVT_CHOICE, self._on_rubric_selected)
			self.choice_article.Bind(wx.EVT_CHOICE, self._on_article_selected)

			self.btn_browse_mode.Bind(wx.EVT_BUTTON, self.on_open_browse_mode)
			self.btn_prev.Bind(wx.EVT_BUTTON, lambda evt: self.navigate_relative_article(-1))
			self.btn_next.Bind(wx.EVT_BUTTON, lambda evt: self.navigate_relative_article(1))
			self.btn_refresh_list.Bind(wx.EVT_BUTTON, lambda evt: self._on_refresh_list_activated())
			self.btn_reload_article.Bind(wx.EVT_BUTTON, lambda evt: self.reload_current_article())
			self.btn_open_browser.Bind(wx.EVT_BUTTON, lambda evt: self.open_current_article_in_browser())
			self.btn_back_rubric.Bind(wx.EVT_BUTTON, lambda evt: self.focus_rubric_selection())
			self.btn_back_site.Bind(wx.EVT_BUTTON, lambda evt: self.focus_site_selection())
			self.btn_settings.Bind(wx.EVT_BUTTON, self._on_open_settings)
			self.btn_close.Bind(wx.EVT_BUTTON, lambda evt: self.close_dashboard())

			self.Bind(wx.EVT_CLOSE, self._on_close_window)
			self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

		def on_open_browse_mode(self, event=None) -> None:
			"""
			Open the currently selected article in NVDA's native HTML Browse Mode
			(`ui.browseableMessage(html_doc, title=..., isHtml=True)`), matching the
			exact "Mode Jelajah HTML" implementation from `kompasTeknoReader`.
			"""
			self.open_html_browse_mode()

		def open_html_browse_mode(self) -> None:
			"""
			Format the current article as structured HTML via `format_article_html` and
			display it in NVDA's native HTML Browse Mode (`ui.browseableMessage(..., isHtml=True)`).
			If the article is currently loading in the background, queues automatic opening
			as soon as the content finishes loading.
			"""
			if self._is_closing:
				return
			if self._current_article is None:
				announce_nvda(_('No article list is available yet.'))
				return

			if self._current_article.content_status == ArticleStatus.CONTENT_LOADING:
				self._pending_open_browse_mode = True
				announce_nvda(
					_('Loading full article content. HTML Browse Mode will open automatically once loaded.')
				)
				return

			self._pending_open_browse_mode = False
			rubric_name = (
				self._current_article.category_label
				if self._is_search_mode
				else (self._active_rubric.name if self._active_rubric else "")
			)
			html_doc = format_article_html(
				article=self._current_article,
				rubric_name=rubric_name,
				paragraph_spacing=config_manager.get("paragraph_spacing"),
				color_theme=config_manager.get("color_theme"),
				font_scale=config_manager.get("font_scale"),
				font_family=config_manager.get("font_family"),
			)

			site_obj = get_site_by_id(self._current_article.source_id) or self._active_site
			portal_name = site_obj.name if site_obj else "NewsHub"
			dlg_title = f"{portal_name}: {self._current_article.title}"

			try:
				import ui
				ui.browseableMessage(
					html_doc,
					title=dlg_title,
					isHtml=True,
				)
			except Exception as e:
				try:
					from logHandler import log
					log.error(f"NewsHub: Failed to open ui.browseableMessage: {e}")
				except Exception:
					pass

		def _set_site_rubric_visibility(self, visible: bool) -> None:
			"""Show or hide the site and rubric selection controls dynamically."""
			for ctrl in (
				self.lbl_site,
				self.choice_site,
				self.lbl_rubric,
				self.choice_rubric,
				self.btn_back_rubric,
				self.btn_back_site,
			):
				ctrl.Show(visible)
			self.btn_clear_search.Show(not visible)
			self.panel.Layout()
			self.panel.Refresh()

		def perform_search(self) -> None:
			"""
			Search for news articles matching the keyword in `txt_search` across all
			available news portals (`Kompas.com`, `Detik.com`, `CNN Indonesia`, `CNBC Indonesia`, `Tempo.co`).
			"""
			if self._is_closing:
				return
			query = (self.txt_search.GetValue() or "").strip()
			if not query:
				self._set_status(_('Please enter a search keyword first.'), announce=True)
				self.txt_search.SetFocus()
				return

			self._active_search_query = query
			self._pending_open_browse_mode = False
			self._articles = []
			self._current_article = None
			self.choice_article.Clear()
			self.choice_article.Append(_('Searching news for "{query}"...').format(query=query))
			self.choice_article.SetSelection(0)
			self._update_navigation_buttons_state()

			searching_msg = _('Searching news for "{query}" across all news portals...').format(query=query)
			self.txt_content.ChangeValue(searching_msg)
			self._set_status(searching_msg, announce=True)

			def _on_search_success(q_str: str, found_articles: List[Article]) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_search_loaded_on_gui, q_str, found_articles)

			def _on_search_error(q_str: str, err_msg: str) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_search_error_on_gui, q_str, err_msg)

			self.article_manager.search_articles_across_sites_async(
				query=query,
				sites=self._sites,
				on_success=_on_search_success,
				on_error=_on_search_error,
			)

		def _handle_search_loaded_on_gui(self, query: str, found_articles: List[Article]) -> None:
			"""
			Display cross-portal search results in `choice_article` and hide the site
			and rubric selection controls until `Escape` is pressed.
			"""
			if self._is_closing:
				return
			self._is_search_mode = True
			self._active_search_query = query
			self._set_site_rubric_visibility(visible=False)

			self._articles = list(found_articles)
			self.choice_article.Clear()
			for idx, art in enumerate(self._articles, start=1):
				site_obj = get_site_by_id(art.source_id)
				portal_prefix = f"[{site_obj.name}] " if site_obj else ""
				self.choice_article.Append(f"{idx}. {portal_prefix}{art.title}")

			if self._articles:
				self.choice_article.SetSelection(0)
				self._current_article = self._articles[0]

			self._update_navigation_buttons_state()
			self._set_status(
				_('Search completed. Found {count} articles for "{query}" across all portals. Press Escape to clear search.').format(
					count=len(self._articles), query=query
				),
				announce=True,
			)

			if self._articles:
				self.choice_article.SetFocus()
				self._select_and_load_article(0, announce_selection=False, force_reload=False)

		def _handle_search_error_on_gui(self, query: str, error_msg: str) -> None:
			if self._is_closing:
				return
			self.choice_article.Clear()
			self.choice_article.Append(_('No search results found'))
			self.choice_article.SetSelection(0)
			self.txt_content.ChangeValue(error_msg)
			self._set_status(error_msg, announce=True)
			self._update_navigation_buttons_state()

		def clear_search_and_restore_default(self) -> None:
			"""
			Clear active search results, restore visibility of site and rubric selectors,
			and reload the default rubric article list.
			"""
			if self._is_closing:
				return
			self.article_manager.cancel_pending_requests()
			self._is_search_mode = False
			self._active_search_query = ""
			self._pending_open_browse_mode = False
			self.txt_search.ChangeValue("")
			self._set_site_rubric_visibility(visible=True)

			announce_nvda(_('Search results cleared. Returned to default view.'))
			self._populate_rubrics_for_active_site(restore_last_rubric=True)
			self.choice_site.SetFocus()

		def _on_refresh_list_activated(self) -> None:
			"""Refresh either the active search results or the active rubric list when F5 is pressed."""
			if self._is_search_mode and self._active_search_query:
				self.perform_search()
			else:
				self.refresh_current_rubric(force=True, is_background_auto=False)

		def refresh_ui_language(self) -> None:
			"""Dynamically update all control labels and re-render the article view."""
			if self._is_closing:
				return

			self.SetTitle(_('NewsHub for NVDA — News Reading Made Easy'))
			self.SetName(_('NewsHub for NVDA — News Reading Made Easy'))

			self.lbl_header.SetLabel(_('&Dashboard Title:'))
			self.txt_dashboard_title.ChangeValue(_('NewsHub for NVDA — News Reading Made Easy '))
			self.txt_dashboard_title.SetName(_('NewsHub for NVDA Reading Area'))

			self.lbl_search.SetLabel(_('Search &news:'))
			self.txt_search.SetName(_('Search news keyword across all portals'))
			self.btn_search.SetLabel(_('&Search News'))
			self.btn_search.SetName(_('Search news across all portals'))
			self.btn_clear_search.SetLabel(_('Clear &Search (Esc)'))
			self.btn_clear_search.SetName(_('Clear search results and return to default view'))

			self.lbl_site.SetLabel(_('News &portal:'))
			self.choice_site.SetName(_('News portal selection'))
			site_sel = self.choice_site.GetSelection()
			self.choice_site.Clear()
			for s in self._sites:
				self.choice_site.Append(s.display_label)
			if site_sel != wx.NOT_FOUND and site_sel < len(self._sites):
				self.choice_site.SetSelection(site_sel)

			self.lbl_rubric.SetLabel(_('News &rubric:'))
			self.choice_rubric.SetName(_('News rubric selection'))
			if self._active_site and self._active_site.supported and self._active_rubrics:
				rub_sel = self.choice_rubric.GetSelection()
				self.choice_rubric.Clear()
				for r in self._active_rubrics:
					self.choice_rubric.Append(r.display_label)
				if rub_sel != wx.NOT_FOUND and rub_sel < len(self._active_rubrics):
					self.choice_rubric.SetSelection(rub_sel)
			else:
				self.choice_rubric.Clear()
				self.choice_rubric.Append(_('No rubrics available (Portal not supported yet)'))
				self.choice_rubric.SetSelection(0)

			self.lbl_article.SetLabel(_('&Article list:'))
			self.choice_article.SetName(_('Article headline selection'))

			self.lbl_status.SetLabel(_('Loading &status:'))
			self.txt_status.SetName(_('Loading status information'))

			self.lbl_content.SetLabel(_('Full article &content:'))
			self.txt_content.SetName(_('Article reading area'))

			self.btn_browse_mode.SetLabel(_('HTML &Browse Mode (Alt+H)'))
			self.btn_browse_mode.SetName(_('HTML Browse Mode (Alt+H)'))

			self.btn_prev.SetLabel(_('Pre&vious Article (Alt+[)'))
			self.btn_prev.SetName(_('Previous Article (Alt+[)'))

			self.btn_next.SetLabel(_('Ne&xt Article (Alt+])'))
			self.btn_next.SetName(_('Next Article (Alt+])'))

			self.btn_refresh_list.SetLabel(_('Re&fresh Article List (F5)'))
			self.btn_refresh_list.SetName(_('Refresh Article List (F5)'))

			self.btn_reload_article.SetLabel(_('&Reload Article (Ctrl+R)'))
			self.btn_reload_article.SetName(_('Reload Article (Ctrl+R)'))

			self.btn_open_browser.SetLabel(_('&Open Original Article in Browser'))
			self.btn_open_browser.SetName(_('Open Original Article in Browser'))

			self.btn_back_rubric.SetLabel(_('Back to &Rubric Selection'))
			self.btn_back_rubric.SetName(_('Back to rubric selection'))

			self.btn_back_site.SetLabel(_('Back to &Portal Selection'))
			self.btn_back_site.SetName(_('Back to portal selection'))

			self.btn_settings.SetLabel(_('Accessibility &Settings...'))
			self.btn_settings.SetName(_('Accessibility Settings'))

			self.btn_close.SetLabel(_('&Close Dashboard (Esc)'))
			self.btn_close.SetName(_('Close Dashboard'))

			if self._current_article is not None:
				self._render_article_to_view(self._current_article, preserve_reading_pos=True)

			self.panel.Layout()
			self.panel.Refresh()

		def _on_external_settings_changed(self) -> None:
			if self._is_closing:
				return
			self.refresh_ui_language()
			self._apply_visual_preferences()
			self._configure_auto_refresh_timer()

		def _apply_visual_preferences(self) -> None:
			"""Apply color theme, font size, and font family to dashboard controls."""
			theme_key = config_manager.get("color_theme")
			palette = THEME_PALETTES.get(theme_key, THEME_PALETTES["light"])

			font_scale = config_manager.get("font_scale")
			font_family_key = config_manager.get("font_family")

			base_pt = 10
			scaled_pt = max(8, int(round(base_pt * (font_scale / 100.0))))
			heading_pt = max(9, int(round((base_pt + 1) * (font_scale / 100.0))))

			wx_family = wx.FONTFAMILY_ROMAN if font_family_key == "serif" else wx.FONTFAMILY_SWISS
			body_font = wx.Font(
				scaled_pt,
				wx_family,
				wx.FONTSTYLE_NORMAL,
				wx.FONTWEIGHT_NORMAL,
			)
			bold_font = wx.Font(
				heading_pt,
				wx_family,
				wx.FONTSTYLE_NORMAL,
				wx.FONTWEIGHT_BOLD,
			)

			dlg_bg = wx.Colour(*palette["dialog_bg"])
			text_fg = wx.Colour(*palette["text_fg"])
			ctrl_bg = wx.Colour(*palette["control_bg"])
			ctrl_fg = wx.Colour(*palette["control_fg"])
			status_bg = wx.Colour(*palette["status_bg"])
			status_fg = wx.Colour(*palette["status_fg"])

			self.SetBackgroundColour(dlg_bg)
			self.panel.SetBackgroundColour(dlg_bg)

			for lbl in (
				self.lbl_header,
				self.lbl_search,
				self.lbl_site,
				self.lbl_rubric,
				self.lbl_article,
				self.lbl_status,
				self.lbl_content,
			):
				lbl.SetForegroundColour(text_fg)
				lbl.SetFont(bold_font)

			self.txt_dashboard_title.SetBackgroundColour(status_bg)
			self.txt_dashboard_title.SetForegroundColour(status_fg)
			self.txt_dashboard_title.SetFont(bold_font)

			self.txt_search.SetBackgroundColour(ctrl_bg)
			self.txt_search.SetForegroundColour(ctrl_fg)
			self.txt_search.SetFont(body_font)

			self.txt_status.SetBackgroundColour(status_bg)
			self.txt_status.SetForegroundColour(status_fg)
			self.txt_status.SetFont(body_font)

			self.txt_content.SetBackgroundColour(ctrl_bg)
			self.txt_content.SetForegroundColour(ctrl_fg)
			self.txt_content.SetFont(body_font)

			for ctrl in (self.choice_site, self.choice_rubric, self.choice_article):
				ctrl.SetBackgroundColour(ctrl_bg)
				ctrl.SetForegroundColour(ctrl_fg)
				ctrl.SetFont(body_font)

			if self._current_article is not None:
				self._render_article_to_view(self._current_article, preserve_reading_pos=True)

			self.panel.Refresh()

		def _configure_auto_refresh_timer(self) -> None:
			"""Configure the background auto-refresh timer according to user preferences."""
			if self._auto_refresh_timer.IsRunning():
				self._auto_refresh_timer.Stop()

			if self._is_closing:
				return

			enabled = bool(config_manager.get("auto_refresh_enabled"))
			interval_sec = int(config_manager.get("auto_refresh_interval_sec") or 60)
			max_articles = int(config_manager.get("max_articles") or 40)
			cache_ttl = int(config_manager.get("cache_ttl_sec") or 180)
			self.article_manager.configure(cache_ttl_sec=cache_ttl, max_articles=max_articles)

			if enabled and self._active_site and self._active_site.supported:
				self._auto_refresh_timer.Start(interval_sec * 1000)

		def _set_status(self, message: str, announce: bool = True) -> None:
			if self._is_closing:
				return
			self.txt_status.SetValue(message)
			if announce:
				announce_nvda(message)

		def _update_navigation_buttons_state(self) -> None:
			"""Update the enabled/disabled state of navigation and action buttons."""
			has_articles = len(self._articles) > 0
			has_current = self._current_article is not None
			site_supported = bool(self._active_site and self._active_site.supported) or self._is_search_mode

			self.choice_rubric.Enable(
				not self._is_search_mode
				and bool(self._active_site and self._active_site.supported)
				and len(self._active_rubrics) > 0
			)
			self.choice_article.Enable(site_supported and has_articles)
			self.btn_browse_mode.Enable(site_supported and has_current)
			self.btn_prev.Enable(site_supported and has_articles)
			self.btn_next.Enable(site_supported and has_articles)
			self.btn_refresh_list.Enable(site_supported and (self._active_rubric is not None or self._is_search_mode))
			self.btn_reload_article.Enable(site_supported and has_current)
			self.btn_open_browser.Enable(has_current and bool(self._current_article.url))

		def _restore_last_context_and_load(self) -> None:
			"""Restore the last selected news portal and rubric when the dashboard opens."""
			last_site_id = config_manager.get("last_site_id")
			site_idx = 0
			for i, s in enumerate(self._sites):
				if s.id == last_site_id:
					site_idx = i
					break

			self.choice_site.SetSelection(site_idx)
			self._active_site = self._sites[site_idx]
			self._populate_rubrics_for_active_site(restore_last_rubric=True)
			self.choice_site.SetFocus()

		def _populate_rubrics_for_active_site(self, restore_last_rubric: bool = False) -> None:
			"""Populate the rubric list corresponding to the currently selected news portal."""
			self.article_manager.cancel_pending_requests()
			self._pending_open_browse_mode = False
			self._articles = []
			self._current_article = None

			if not self._active_site.supported:
				self._active_rubrics = []
				self._active_rubric = None
				self.choice_rubric.Clear()
				self.choice_rubric.Append(_('No rubrics available (Portal not supported yet)'))
				self.choice_rubric.SetSelection(0)

				self.choice_article.Clear()
				self.choice_article.Append(_('No articles available'))
				self.choice_article.SetSelection(0)

				msg = _('{site_name} is not supported in this version yet.').format(site_name=self._active_site.name)
				self.txt_content.ChangeValue(
					_('{msg}\r\n\r\nPlease select Kompas.com, Detik.com, CNN Indonesia, CNBC Indonesia, or Tempo.co in the News portal list to read news.').format(msg=msg)
				)
				self._set_status(msg, announce=True)
				self._update_navigation_buttons_state()
				return

			self._active_rubrics = list(self._active_site.rubrics)
			self.choice_rubric.Clear()
			for r in self._active_rubrics:
				self.choice_rubric.Append(r.display_label)

			target_idx = 0
			if restore_last_rubric:
				last_rubric_id = config_manager.get("last_rubric_id")
				for i, r in enumerate(self._active_rubrics):
					if r.id == last_rubric_id:
						target_idx = i
						break

			if self._active_rubrics:
				self.choice_rubric.SetSelection(target_idx)
				self._active_rubric = self._active_rubrics[target_idx]
				config_manager.set("last_rubric_id", self._active_rubric.id)
				self._update_navigation_buttons_state()
				self.refresh_current_rubric(force=False)

		def _on_site_selected(self, event: wx.CommandEvent) -> None:
			sel = self.choice_site.GetSelection()
			if sel == wx.NOT_FOUND or sel >= len(self._sites):
				return
			new_site = self._sites[sel]
			self._active_site = new_site
			config_manager.set("last_site_id", new_site.id)
			self._populate_rubrics_for_active_site(restore_last_rubric=False)
			self._configure_auto_refresh_timer()

		def _on_rubric_selected(self, event: wx.CommandEvent) -> None:
			sel = self.choice_rubric.GetSelection()
			if sel == wx.NOT_FOUND or sel >= len(self._active_rubrics):
				return
			new_rubric = self._active_rubrics[sel]
			if self._active_rubric and self._active_rubric.id == new_rubric.id and self._articles:
				return

			self._active_rubric = new_rubric
			config_manager.set("last_rubric_id", new_rubric.id)
			self._pending_open_browse_mode = False
			self._articles = []
			self._current_article = None
			self.choice_article.Clear()
			self.choice_article.Append(_('Loading {rubric_name} article list...').format(rubric_name=new_rubric.name))
			self.choice_article.SetSelection(0)
			self.txt_content.ChangeValue(
				_('Fetching {rubric_name} news list from {site_name}...').format(
					rubric_name=new_rubric.name, site_name=self._active_site.name
				)
			)
			self._update_navigation_buttons_state()
			self.refresh_current_rubric(force=False)

		def refresh_current_rubric(self, force: bool = False, is_background_auto: bool = False) -> None:
			if self._is_closing or self._is_search_mode or not self._active_site or not self._active_site.supported or not self._active_rubric:
				return

			rubric = self._active_rubric
			site = self._active_site

			if not is_background_auto:
				self._set_status(_('Fetching {rubric_name} news list.').format(rubric_name=rubric.name), announce=True)

			def _on_success(articles: List[Article], bg_auto: bool) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_rubric_loaded_on_gui, site.id, rubric.id, articles, bg_auto)

			def _on_error(error_msg: str, bg_auto: bool) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_rubric_error_on_gui, site.id, rubric.id, error_msg, bg_auto)

			self.article_manager.fetch_rubric_articles_async(
				site=site,
				rubric=rubric,
				force_refresh=force,
				is_background_auto=is_background_auto,
				on_success=_on_success,
				on_error=_on_error,
			)

		def _handle_rubric_loaded_on_gui(
			self,
			site_id: str,
			rubric_id: str,
			new_articles: List[Article],
			is_background_auto: bool,
		) -> None:
			if self._is_closing or self._is_search_mode or not self._active_site or not self._active_rubric:
				return
			if self._active_site.id != site_id or self._active_rubric.id != rubric_id:
				return

			previous_article = self._current_article
			merged_list = list(new_articles)

			if previous_article is not None and previous_article.rubric_id == rubric_id:
				if not any(a.canonical_url == previous_article.canonical_url for a in merged_list):
					merged_list.insert(0, previous_article)

			self._articles = merged_list
			self.choice_article.Clear()
			for idx, art in enumerate(self._articles, start=1):
				self.choice_article.Append(f"{idx}. {art.title}")

			selected_idx = 0
			if previous_article is not None:
				for i, art in enumerate(self._articles):
					if art.canonical_url == previous_article.canonical_url:
						selected_idx = i
						break

			if self._articles:
				self.choice_article.SetSelection(selected_idx)
				target_article = self._articles[selected_idx]
			else:
				target_article = None

			self._update_navigation_buttons_state()

			if is_background_auto:
				self._set_status(
					_('{rubric_name} news list automatically updated ({count} articles).').format(
						rubric_name=self._active_rubric.name, count=len(self._articles)
					),
					announce=False,
				)
				return

			self._set_status(
				_('News list loaded successfully. Found {count} articles in {rubric_name}.').format(
					count=len(self._articles), rubric_name=self._active_rubric.name
				),
				announce=True,
			)

			if target_article is not None and (
				previous_article is None or previous_article.canonical_url != target_article.canonical_url
			):
				self._select_and_load_article(selected_idx, announce_selection=False, force_reload=False)

		def _handle_rubric_error_on_gui(
			self,
			site_id: str,
			rubric_id: str,
			error_msg: str,
			is_background_auto: bool,
		) -> None:
			if self._is_closing or self._is_search_mode or not self._active_site or not self._active_rubric:
				return
			if self._active_site.id != site_id or self._active_rubric.id != rubric_id:
				return

			if is_background_auto and self._articles:
				return

			if self._articles:
				msg = _('{error_msg} Showing {count} previously loaded articles.').format(
					error_msg=error_msg, count=len(self._articles)
				)
				self._set_status(msg, announce=True)
			else:
				self.choice_article.Clear()
				self.choice_article.Append(_('News list could not be loaded'))
				self.choice_article.SetSelection(0)
				self.txt_content.ChangeValue(
					_('{error_msg}\r\n\r\nPress F5 or activate the Refresh Article List button to try again.').format(
						error_msg=error_msg
					)
				)
				self._set_status(error_msg, announce=True)
			self._update_navigation_buttons_state()

		def _on_article_selected(self, event: wx.CommandEvent) -> None:
			sel = self.choice_article.GetSelection()
			if sel == wx.NOT_FOUND or sel >= len(self._articles):
				return
			self._select_and_load_article(sel, announce_selection=True, force_reload=False)

		def _select_and_load_article(
			self,
			index: int,
			announce_selection: bool = True,
			force_reload: bool = False,
		) -> None:
			"""Select the article at `index` and fetch its full content and multimedia in the background."""
			if index < 0 or index >= len(self._articles):
				return

			self._pending_open_browse_mode = False
			self.choice_article.SetSelection(index)
			article = self._articles[index]
			self._current_article = article
			self._update_navigation_buttons_state()

			rubric_name = (
				article.category_label
				if self._is_search_mode
				else (self._active_rubric.name if self._active_rubric else "")
			)

			if not force_reload and article.content_status in (
				ArticleStatus.CONTENT_LOADED,
				ArticleStatus.CONTENT_PARTIAL,
			) and (article.content or article.photos or article.videos):
				self._render_article_to_view(article, preserve_reading_pos=False)
				if announce_selection:
					ann = format_article_selection_announcement(
						article, index, len(self._articles), rubric_name=rubric_name
					)
					self._set_status(ann, announce=True)
				return

			article.content_status = ArticleStatus.CONTENT_LOADING
			self._render_article_to_view(article, preserve_reading_pos=False)
			if announce_selection:
				self._set_status(
					_('Article selected: {title}. Loading full content.').format(title=article.title),
					announce=True,
				)
			else:
				self._set_status(
					_('News list loaded ({count} articles). Loading the first article...').format(
						count=len(self._articles)
					),
					announce=False,
				)

			article_site = get_site_by_id(article.source_id) or self._active_site

			def _on_content_success(updated_article: Article) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_article_loaded_on_gui, updated_article, index)

			def _on_content_error(failed_article: Article, err_msg: str) -> None:
				if self._is_closing:
					return
				wx.CallAfter(self._handle_article_error_on_gui, failed_article, err_msg)

			self.article_manager.fetch_article_content_async(
				site=article_site,
				article=article,
				force_reload=force_reload,
				on_success=_on_content_success,
				on_error=_on_content_error,
			)

		def _handle_article_loaded_on_gui(self, article: Article, index: int) -> None:
			if self._is_closing or self._current_article is None:
				return
			if self._current_article.id != article.id:
				return

			self._render_article_to_view(article, preserve_reading_pos=False)
			self._update_navigation_buttons_state()

			rubric_name = (
				article.category_label
				if self._is_search_mode
				else (self._active_rubric.name if self._active_rubric else "")
			)
			selection_summary = format_article_selection_announcement(
				article, index, len(self._articles), rubric_name=rubric_name
			)
			if article.content_status == ArticleStatus.CONTENT_PARTIAL:
				self._set_status(
					_('Article content was only partially loaded. {summary}').format(summary=selection_summary),
					announce=True,
				)
			else:
				self._set_status(
					_('Article content loaded successfully. {summary}').format(summary=selection_summary),
					announce=True,
				)

			if self._pending_open_browse_mode:
				self._pending_open_browse_mode = False
				self.open_html_browse_mode()

		def _handle_article_error_on_gui(self, article: Article, err_msg: str) -> None:
			if self._is_closing or self._current_article is None:
				return
			if self._current_article.id != article.id:
				return

			self._pending_open_browse_mode = False
			self._render_article_to_view(article, preserve_reading_pos=False)
			self._update_navigation_buttons_state()
			if article.content_status == ArticleStatus.CONTENT_PARTIAL:
				self._set_status(
					_('Article content was only partially loaded ({error_msg}).').format(error_msg=err_msg),
					announce=True,
				)
			else:
				self._set_status(err_msg, announce=True)

		def _render_article_to_view(self, article: Article, preserve_reading_pos: bool = False) -> None:
			"""
			Write formatted article text into `self.txt_content` while preserving the user's
			reading cursor position when requested.
			"""
			rubric_name = (
				article.category_label
				if self._is_search_mode
				else (self._active_rubric.name if self._active_rubric else "")
			)
			spacing = config_manager.get("paragraph_spacing")
			formatted_text = format_article_for_reading(
				article=article,
				rubric_name=rubric_name,
				paragraph_spacing=spacing,
			)

			saved_insertion = 0
			if preserve_reading_pos:
				try:
					saved_insertion = self.txt_content.GetInsertionPoint()
				except Exception:
					saved_insertion = 0

			self.txt_content.ChangeValue(formatted_text)
			if preserve_reading_pos and saved_insertion > 0:
				max_pos = max(0, self.txt_content.GetLastPosition())
				self.txt_content.SetInsertionPoint(min(saved_insertion, max_pos))
			else:
				self.txt_content.SetInsertionPoint(0)

		def navigate_relative_article(self, delta: int) -> None:
			if not self._articles:
				announce_nvda(_('No article list is available yet.'))
				return

			current_idx = self.choice_article.GetSelection()
			if current_idx == wx.NOT_FOUND:
				current_idx = 0

			target_idx = current_idx + delta
			if target_idx < 0:
				announce_nvda(_('You are already at the first article.'))
				return
			if target_idx >= len(self._articles):
				announce_nvda(_('You are already at the last article.'))
				return

			self._select_and_load_article(target_idx, announce_selection=True, force_reload=False)

		def reload_current_article(self) -> None:
			if not self._articles or self._current_article is None:
				announce_nvda(_('Please select an article first to reload.'))
				return
			idx = self.choice_article.GetSelection()
			if idx == wx.NOT_FOUND:
				idx = 0
			self._select_and_load_article(idx, announce_selection=True, force_reload=True)

		def focus_rubric_selection(self) -> None:
			if self._is_search_mode:
				self.clear_search_and_restore_default()
				return
			if self.choice_rubric.IsEnabled() and self.choice_rubric.IsShown():
				self.choice_rubric.SetFocus()
				announce_nvda(_('Returned to news rubric selection.'))
			else:
				self.choice_site.SetFocus()
				announce_nvda(_('Rubrics are not available for this portal. Focused on news portal selection.'))

		def focus_site_selection(self) -> None:
			if self._is_search_mode:
				self.clear_search_and_restore_default()
				return
			self.choice_site.SetFocus()
			announce_nvda(_('Returned to news portal selection.'))

		def open_current_article_in_browser(self) -> None:
			if self._current_article is None or not self._current_article.url:
				announce_nvda(_('No article URL is available to open.'))
				return
			try:
				announce_nvda(
					_('Opening original article in browser: {title}').format(title=self._current_article.title)
				)
				webbrowser.open(self._current_article.url, new=2)
			except Exception:
				self._set_status(_('Failed to open the web browser for this article.'), announce=True)

		def _on_open_settings(self, event: wx.CommandEvent) -> None:
			dlg = AccessibilitySettingsDialog(self)
			if dlg.ShowModal() == wx.ID_OK:
				self.refresh_ui_language()
				self._apply_visual_preferences()
				self._configure_auto_refresh_timer()
				announce_nvda(_('NewsHub for NVDA settings have been saved and applied.'))
			dlg.Destroy()

		def _on_auto_refresh_timer(self, event: wx.TimerEvent) -> None:
			if self._is_closing or self._is_search_mode or not self.IsShown():
				return
			if not bool(config_manager.get("auto_refresh_enabled")):
				return
			if self._active_site and self._active_site.supported and self._active_rubric:
				self.refresh_current_rubric(force=True, is_background_auto=True)

		def _on_char_hook(self, event: wx.KeyEvent) -> None:
			"""
			Handle dashboard keyboard shortcuts:
			- Alt+H  : Open current article in native NVDA HTML Browse Mode (`ui.browseableMessage`)
			- Enter  : When focused on `choice_article` or `txt_content`, open HTML Browse Mode (`ui.browseableMessage`)
			- H / T / K / L / Q / G : When focused on `txt_content`, open HTML Browse Mode (`ui.browseableMessage`)
			- Alt+[  : Previous article
			- Alt+]  : Next article
			- Ctrl+F : Focus the news search box
			- F5     : Refresh article list (or re-run active search)
			- Ctrl+R : Reload selected article content
			- Alt+R  : Return focus to the rubric selection control
			- Alt+S  : Return focus to the news portal selection control
			- Esc    : If in search mode, clear search results and return to default view;
			           otherwise step back to the previous selection stage or close the dashboard.
			"""
			key_code = event.GetKeyCode()
			alt_down = event.AltDown()
			ctrl_down = event.ControlDown()
			shift_down = event.ShiftDown()
			focused = wx.Window.FindFocus()

			# Alt+H -> Open native NVDA HTML Browse Mode (just like kompasTeknoReader)
			if alt_down and not ctrl_down and not shift_down and key_code in (ord("H"), ord("h")):
				self.open_html_browse_mode()
				return

			# Alt+[ -> Previous Article
			if alt_down and not ctrl_down and not shift_down and key_code == ord("["):
				self.navigate_relative_article(-1)
				return

			# Alt+] -> Next Article
			if alt_down and not ctrl_down and not shift_down and key_code == ord("]"):
				self.navigate_relative_article(1)
				return

			# Ctrl+F -> Focus Search Box
			if ctrl_down and not alt_down and not shift_down and key_code in (ord("F"), ord("f")):
				self.txt_search.SetFocus()
				announce_nvda(_('Search news keyword across all portals'))
				return

			# Alt+R -> Focus Rubric Selection
			if alt_down and not ctrl_down and not shift_down and key_code in (ord("R"), ord("r")):
				self.focus_rubric_selection()
				return

			# Alt+S -> Focus Site Selection
			if alt_down and not ctrl_down and not shift_down and key_code in (ord("S"), ord("s")):
				self.focus_site_selection()
				return

			# F5 -> Refresh article list or search
			if key_code == wx.WXK_F5 and not alt_down and not ctrl_down:
				self._on_refresh_list_activated()
				return

			# Ctrl+R -> Reload selected article content
			if ctrl_down and not alt_down and not shift_down and key_code in (ord("R"), ord("r")):
				self.reload_current_article()
				return

			# Enter on choice_article or txt_content -> Open native NVDA HTML Browse Mode
			if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not alt_down and not ctrl_down and not shift_down:
				if focused in (self.choice_article, self.txt_content) and self._current_article is not None:
					self.open_html_browse_mode()
					return

			# HTML Browse Mode quick keys (H, T, K, L, Q, G) inside txt_content -> Open HTML Browse Mode
			if (
				focused == self.txt_content
				and not alt_down
				and not ctrl_down
				and key_code in (
					ord("H"), ord("h"),
					ord("T"), ord("t"),
					ord("K"), ord("k"),
					ord("L"), ord("l"),
					ord("Q"), ord("q"),
					ord("G"), ord("g"),
				)
				and self._current_article is not None
			):
				self.open_html_browse_mode()
				return

			# Esc -> If search results are active, clear search and restore default view;
			# otherwise step back contextually or close the dashboard
			if key_code == wx.WXK_ESCAPE and not alt_down and not ctrl_down and not shift_down:
				if self._is_search_mode:
					self.clear_search_and_restore_default()
					return

				if focused == self.txt_content:
					self.choice_article.SetFocus()
					announce_nvda(_('Returned to article selection.'))
					return
				if focused == self.choice_article:
					self.choice_rubric.SetFocus()
					announce_nvda(_('Returned to news rubric selection.'))
					return
				if focused == self.choice_rubric:
					self.choice_site.SetFocus()
					announce_nvda(_('Returned to news portal selection.'))
					return
				self.close_dashboard()
				return

			event.Skip()

		def close_dashboard(self) -> None:
			"""Close the dashboard cleanly, stopping the timer and cancelling pending callbacks."""
			if self._is_closing:
				return
			self._is_closing = True
			unregister_settings_change_listener(self._on_external_settings_changed)
			if self._auto_refresh_timer.IsRunning():
				self._auto_refresh_timer.Stop()
			self.article_manager.cancel_pending_requests()
			self.Destroy()

		def _on_close_window(self, event: wx.CloseEvent) -> None:
			self.close_dashboard()
else:
	AccessibilitySettingsDialog = None
	NewsHubDashboardDialog = None
