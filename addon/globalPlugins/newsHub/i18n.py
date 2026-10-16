# -*- coding: utf-8 -*-
"""
Internationalization (i18n) and localization module for NewsHub for NVDA.

Provides complete bilingual support (Indonesian 'id' and English 'en') for all user interface
controls, accessible labels, NVDA announcements, network/parser error messages, rubric
descriptions, and article formatting templates.
"""

from typing import Dict

SUPPORTED_LANGUAGES: Dict[str, str] = {
	"id": "Bahasa Indonesia",
	"en": "English",
}

STRINGS: Dict[str, Dict[str, str]] = {
	"id": {
		# Global plugin & menus
		"addon_category": "NewsHub for NVDA",
		"script_open_dashboard_desc": "Membuka dashboard NewsHub for NVDA (Pembaca Berita Multisitus)",
		"tools_menu_label": "&NewsHub for NVDA (Pembaca Berita)...",
		"tools_menu_help": "Membuka dashboard pembaca berita multisitus NewsHub for NVDA",
		"prefs_menu_label": "Pengaturan &NewsHub for NVDA...",
		"prefs_menu_help": "Membuka pengaturan bahasa dan tampilan NewsHub for NVDA",
		"dashboard_active_announcement": "Dashboard NewsHub for NVDA aktif.",
		"settings_panel_title": "NewsHub for NVDA",

		# Dashboard window & controls (12-step focus order)
		"dashboard_window_title": "NewsHub for NVDA — Pembaca Berita Multisitus",
		"lbl_dashboard_header": "Judul &Dashboard:",
		"acc_dashboard_header": "Judul Dashboard NewsHub for NVDA",
		"dashboard_banner_text": (
			"NewsHub for NVDA — Pembaca Berita Multisitus "
			"(Pintasan: Alt+[ Sebelumnya, Alt+] Berikutnya, F5 Perbarui Daftar, Ctrl+R Muat Ulang Artikel, Esc Kembali/Tutup)"
		),
		"lbl_site_choice": "&Situs berita:",
		"acc_site_choice": "Pemilihan situs berita",
		"lbl_rubric_choice": "&Rubrik berita:",
		"acc_rubric_choice": "Pemilihan rubrik berita",
		"lbl_article_choice": "Daftar &artikel:",
		"acc_article_choice": "Pemilihan judul artikel",
		"no_articles_loaded": "Belum ada artikel yang dimuat",
		"lbl_status": "Status &pemuatan:",
		"acc_status": "Informasi status pemuatan",
		"initial_status_ready": "Siap. Pilih situs dan rubrik berita untuk memuat daftar artikel.",
		"lbl_content": "&Isi lengkap berita:",
		"acc_content": "Area isi berita",
		"initial_content_prompt": "Pilih sebuah judul artikel pada daftar untuk membaca isi berita lengkap.",
		"btn_prev_label": "Artikel Se&belumnya (Alt+[)",
		"acc_btn_prev": "Artikel Sebelumnya (Alt+[)",
		"btn_next_label": "Artikel Beri&kutnya (Alt+])",
		"acc_btn_next": "Artikel Berikutnya (Alt+])",
		"btn_refresh_label": "Per&barui Daftar Berita (F5)",
		"acc_btn_refresh": "Perbarui Daftar Berita (F5)",
		"btn_reload_label": "&Muat Ulang Artikel (Ctrl+R)",
		"acc_btn_reload": "Muat Ulang Artikel (Ctrl+R)",
		"btn_open_browser_label": "Buka Artikel &Asli di Peramban",
		"acc_btn_open_browser": "Buka Artikel Asli di Peramban",
		"btn_back_rubric_label": "Kembali ke Pilihan &Rubrik",
		"acc_btn_back_rubric": "Kembali ke pemilihan rubrik",
		"btn_back_site_label": "Kembali ke Pilihan Si&tus",
		"acc_btn_back_site": "Kembali ke pemilihan situs",
		"btn_settings_label": "Peng&aturan Aksesibilitas...",
		"acc_btn_settings": "Pengaturan Aksesibilitas",
		"btn_close_label": "&Tutup Dashboard (Esc)",
		"acc_btn_close": "Tutup Dashboard",

		# Site & rubric status messages
		"site_supported_badge": "Didukung penuh",
		"site_unsupported_badge": "Belum didukung pada versi ini",
		"no_rubric_unsupported_site": "Tidak ada rubrik (Situs belum didukung)",
		"no_article_item": "Tidak ada artikel",
		"site_not_supported_msg": "{site_name} belum didukung pada versi ini.",
		"site_not_supported_body": "{msg}\r\n\r\nSilakan pilih Kompas.com pada daftar Situs berita untuk membaca berita.",
		"rubric_not_accessible": "Rubrik ini tidak dapat diakses saat ini.",
		"loading_rubric_choice_item": "Memuat daftar berita {rubric_name}...",
		"loading_rubric_body": "Mengambil daftar berita {rubric_name} dari {site_name}...",
		"status_fetching_rubric": "Mengambil daftar berita {rubric_name}.",
		"status_auto_refreshed": "Daftar berita {rubric_name} diperbarui otomatis ({count} artikel).",
		"status_rubric_loaded": "Daftar berita berhasil dimuat. Ditemukan {count} artikel pada rubrik {rubric_name}.",
		"status_rubric_loaded_loading_first": "Daftar berita berhasil dimuat ({count} artikel). Memuat isi artikel pertama...",
		"status_rubric_error_with_cached": "{error_msg} Menampilkan {count} artikel yang telah dimuat sebelumnya.",
		"choice_rubric_load_failed": "Daftar berita belum dapat dimuat",
		"body_rubric_load_failed": "{error_msg}\r\n\r\nTekan F5 atau tombol Perbarui Daftar Berita untuk mencoba kembali.",
		"status_article_selected_loading": "Artikel berhasil dipilih: {title}. Sedang memuat isi lengkap.",
		"status_article_loaded_full": "Isi artikel berhasil dimuat. {summary}",
		"status_article_loaded_partial": "Isi artikel hanya berhasil dimuat sebagian. {summary}",
		"status_article_loaded_partial_err": "Isi artikel hanya berhasil dimuat sebagian ({error_msg}).",

		# Navigation announcements
		"nav_no_articles": "Belum ada daftar artikel yang tersedia.",
		"nav_at_first_article": "Anda sudah berada di artikel pertama.",
		"nav_at_last_article": "Anda sudah berada di artikel terakhir.",
		"nav_select_article_first": "Pilih sebuah artikel terlebih dahulu untuk dimuat ulang.",
		"nav_back_to_article": "Kembali ke pemilihan artikel.",
		"nav_back_to_rubric": "Kembali ke pemilihan rubrik berita.",
		"nav_back_to_site": "Kembali ke pemilihan situs berita.",
		"nav_rubric_unavailable_focus_site": "Rubrik tidak tersedia untuk situs ini. Fokus pada pemilihan situs berita.",
		"nav_no_article_url": "Tidak ada tautan artikel yang dapat dibuka.",
		"nav_opening_browser": "Membuka artikel asli di peramban: {title}",
		"nav_open_browser_failed": "Gagal membuka peramban web untuk artikel ini.",
		"settings_saved_announcement": "Pengaturan NewsHub for NVDA berhasil disimpan dan diterapkan.",

		# Settings dialog & NVDA SettingsPanel labels
		"settings_dialog_title": "Pengaturan — NewsHub for NVDA",
		"acc_settings_dialog": "Pengaturan NewsHub for NVDA",
		"lbl_language": "&Bahasa antarmuka (Language):",
		"acc_language": "Bahasa antarmuka",
		"lbl_theme": "&Tema warna tampilan:",
		"acc_theme": "Tema warna tampilan",
		"theme_light": "Terang (Kontras Standar Tinggi)",
		"theme_dark": "Gelap (Ramah Mata / Low Glare)",
		"theme_high_contrast": "Kontras Tinggi (Hitam - Kuning/Putih)",
		"lbl_font_scale": "&Ukuran huruf (85% - 150%):",
		"acc_font_scale": "Ukuran huruf",
		"default_suffix": " (Default)",
		"lbl_font_family": "&Jenis huruf bacaan:",
		"acc_font_family": "Jenis huruf bacaan",
		"font_sans_serif": "Sans-serif (Segoe UI / Arial)",
		"font_serif": "Serif (Georgia / Times New Roman)",
		"lbl_paragraph_spacing": "S&pasi antar-paragraf:",
		"acc_paragraph_spacing": "Spasi antar-paragraf",
		"spacing_normal": "Normal (1 baris kosong)",
		"spacing_wide": "Lebar (2 baris kosong)",
		"lbl_auto_refresh": "Pembaruan &otomatis latar belakang:",
		"chk_auto_refresh_label": "Aktifkan pemeriksaan daftar berita otomatis",
		"acc_chk_auto_refresh": "Aktifkan pemeriksaan daftar berita otomatis",
		"lbl_refresh_interval": "&Interval pembaruan otomatis:",
		"acc_refresh_interval": "Interval pembaruan otomatis",
		"interval_30s": "30 detik",
		"interval_60s": "1 menit (60 detik - Default)",
		"interval_120s": "2 menit (120 detik)",
		"interval_180s": "3 menit (180 detik)",
		"interval_300s": "5 menit (300 detik)",
		"interval_600s": "10 menit (600 detik)",
		"lbl_max_articles": "Jumlah &maksimum artikel per rubrik:",
		"acc_max_articles": "Jumlah maksimum artikel per rubrik",
		"max_articles_item": "{count} artikel{suffix}",
		"btn_save_settings": "&Simpan Pengaturan",
		"acc_btn_save_settings": "Simpan Pengaturan",
		"btn_cancel": "&Batal",
		"acc_btn_cancel": "Batal",

		# Article status labels
		"status_not_fetched": "Artikel belum diambil",
		"status_headline_loaded": "Judul berhasil dimuat",
		"status_content_loading": "Konten sedang dimuat",
		"status_content_loaded": "Konten berhasil dimuat",
		"status_content_partial": "Konten hanya tersedia sebagian",
		"status_content_failed": "Pengambilan konten gagal",
		"status_unknown": "Status tidak diketahui",

		# Formatter strings
		"fmt_title_missing": "Judul Artikel Tidak Tersedia",
		"fmt_rubric": "Rubrik: {value}",
		"fmt_published_at": "Waktu Publikasi: {value}",
		"fmt_author": "Penulis: {value}",
		"fmt_editor": "Editor: {value}",
		"fmt_reading_time": "Estimasi Waktu Baca: sekitar {minutes} menit (perkiraan berdasarkan panjang teks)",
		"fmt_loading_body": "Status: Sedang memuat isi lengkap artikel dari sumber. Mohon tunggu sebentar...",
		"fmt_initial_summary": "Ringkasan Awal: {summary}",
		"fmt_failed_default_reason": "Konten artikel tidak dapat diekstrak dari halaman sumber.",
		"fmt_failed_notice": (
			"Pemberitahuan: Isi lengkap artikel gagal dimuat ({reason}). "
			"Anda dapat menekan tombol Muat Ulang Artikel (Ctrl+R) atau Buka Artikel Asli di Peramban."
		),
		"fmt_available_summary": "Ringkasan yang tersedia:\r\n{summary}",
		"fmt_partial_notice": (
			"Pemberitahuan: Isi artikel hanya berhasil dimuat sebagian. "
			"Untuk membaca halaman selengkapnya, gunakan tombol Muat Ulang Artikel (Ctrl+R) "
			"atau Buka Artikel Asli di Peramban."
		),
		"fmt_summary_label": "Ringkasan: {summary}",
		"fmt_subheading": "Subjudul: {text}",
		"fmt_quote": 'Kutipan: "{text}"',
		"fmt_caption": "Keterangan Gambar: {text}",
		"fmt_credit": "Sumber/Kredit: {text}",
		"fmt_source_url": "Tautan Sumber: {url}",
		"fmt_table_start": "[Tabel Informasi Berita]",
		"fmt_table_columns": "Kolom Tabel: {columns}",
		"fmt_table_row": "Baris {row_num}: {content}",
		"fmt_table_end": "[Akhir Tabel]",
		"ann_article_pos": "Artikel {index} dari {total}: {title}.",
		"ann_article_rubric": "Rubrik {rubric}.",
		"ann_article_published": "Diterbitkan {published_at}.",
		"ann_article_reading_time": "Perkiraan waktu baca sekitar {minutes} menit.",

		# Network & parser error messages
		"err_url_empty": "Alamat URL berita kosong atau tidak valid.",
		"err_url_scheme": "Skema alamat URL tidak didukung. Hanya HTTP dan HTTPS yang diizinkan.",
		"err_url_no_domain": "Nama domain pada URL berita tidak ditemukan.",
		"err_url_domain_blocked": "Domain '{hostname}' berada di luar domain sumber berita yang diizinkan.",
		"err_invalid_content_type": "Respons dari {site_label} bukan halaman berita teks/HTML yang didukung.",
		"err_response_too_large": "Ukuran halaman dari {site_label} terlalu besar untuk dimuat secara aman.",
		"err_response_stream_too_large": "Ukuran respons halaman dari {site_label} melebihi batas aman (5 MB).",
		"err_empty_response": "Halaman dari {site_label} mengembalikan respons kosong atau tidak lengkap.",
		"err_http_403": "Akses ke halaman {site_label} ditolak oleh server (HTTP 403). Rubrik atau artikel ini mungkin dibatasi.",
		"err_http_404": "Halaman atau rubrik di {site_label} tidak ditemukan (HTTP 404).",
		"err_http_429": "Terlalu banyak permintaan ke {site_label} (HTTP 429). Tunggu beberapa saat lalu coba lagi.",
		"err_http_5xx": "Server {site_label} sedang mengalami gangguan (HTTP {code}). Silakan coba lagi nanti.",
		"err_http_other": "Gagal memuat halaman dari {site_label} (Kode HTTP {code}).",
		"err_timeout": "Waktu koneksi ke {site_label} habis. Periksa koneksi internet dan coba lagi.",
		"err_dns": "Gagal menghubungi {site_label} (kesalahan DNS atau tidak ada jaringan). Periksa koneksi internet dan coba lagi.",
		"err_ssl": "Gagal memverifikasi koneksi aman (SSL/TLS) ke {site_label}.",
		"err_connection_generic": "Gagal menghubungi {site_label}. Periksa koneksi internet dan coba lagi.",
		"err_read_timeout": "Waktu pembacaan data dari {site_label} habis. Periksa koneksi internet dan coba lagi.",
		"err_unexpected_network": "Terjadi kesalahan saat menghubungi {site_label}. Periksa koneksi internet dan coba lagi.",
		"err_rubric_empty": "Daftar berita pada rubrik {rubric_name} tidak ditemukan. Struktur halaman mungkin berubah atau rubrik sedang kosong.",
		"err_rubric_generic": "Gagal memuat daftar berita {rubric_name} dari {site_name}. Periksa koneksi internet dan coba lagi.",
		"err_article_empty": "Isi artikel tidak dapat ditemukan pada halaman ini. Struktur halaman mungkin berbeda atau merupakan konten khusus multimedia.",
		"err_article_generic": "Gagal memuat isi artikel dari {site_name}. Periksa koneksi internet dan coba lagi.",
	},
	"en": {
		# Global plugin & menus
		"addon_category": "NewsHub for NVDA",
		"script_open_dashboard_desc": "Open the NewsHub for NVDA dashboard (Multi-site News Reader)",
		"tools_menu_label": "&NewsHub for NVDA (News Reader)...",
		"tools_menu_help": "Open the NewsHub for NVDA multi-site news reader dashboard",
		"prefs_menu_label": "&NewsHub for NVDA Settings...",
		"prefs_menu_help": "Configure language and display preferences for NewsHub for NVDA",
		"dashboard_active_announcement": "NewsHub for NVDA dashboard is active.",
		"settings_panel_title": "NewsHub for NVDA",

		# Dashboard window & controls (12-step focus order)
		"dashboard_window_title": "NewsHub for NVDA — Multi-site News Reader",
		"lbl_dashboard_header": "&Dashboard Title:",
		"acc_dashboard_header": "NewsHub for NVDA Dashboard Title",
		"dashboard_banner_text": (
			"NewsHub for NVDA — Multi-site News Reader "
			"(Shortcuts: Alt+[ Previous, Alt+] Next, F5 Refresh List, Ctrl+R Reload Article, Esc Back/Close)"
		),
		"lbl_site_choice": "News &portal:",
		"acc_site_choice": "News portal selection",
		"lbl_rubric_choice": "News &rubric:",
		"acc_rubric_choice": "News rubric selection",
		"lbl_article_choice": "&Article list:",
		"acc_article_choice": "Article headline selection",
		"no_articles_loaded": "No articles loaded yet",
		"lbl_status": "Loading &status:",
		"acc_status": "Loading status information",
		"initial_status_ready": "Ready. Select a news portal and rubric to load the article list.",
		"lbl_content": "Full article &content:",
		"acc_content": "Article reading area",
		"initial_content_prompt": "Select an article headline from the list to read its full content.",
		"btn_prev_label": "Pre&vious Article (Alt+[)",
		"acc_btn_prev": "Previous Article (Alt+[)",
		"btn_next_label": "Ne&xt Article (Alt+])",
		"acc_btn_next": "Next Article (Alt+])",
		"btn_refresh_label": "Re&fresh Article List (F5)",
		"acc_btn_refresh": "Refresh Article List (F5)",
		"btn_reload_label": "&Reload Article (Ctrl+R)",
		"acc_btn_reload": "Reload Article (Ctrl+R)",
		"btn_open_browser_label": "&Open Original Article in Browser",
		"acc_btn_open_browser": "Open Original Article in Browser",
		"btn_back_rubric_label": "Back to &Rubric Selection",
		"acc_btn_back_rubric": "Back to rubric selection",
		"btn_back_site_label": "Back to &Portal Selection",
		"acc_btn_back_site": "Back to portal selection",
		"btn_settings_label": "Accessibility &Settings...",
		"acc_btn_settings": "Accessibility Settings",
		"btn_close_label": "&Close Dashboard (Esc)",
		"acc_btn_close": "Close Dashboard",

		# Site & rubric status messages
		"site_supported_badge": "Fully supported",
		"site_unsupported_badge": "Not supported in this version",
		"no_rubric_unsupported_site": "No rubrics available (Portal not supported yet)",
		"no_article_item": "No articles available",
		"site_not_supported_msg": "{site_name} is not supported in this version yet.",
		"site_not_supported_body": "{msg}\r\n\r\nPlease select Kompas.com in the News portal list to read news.",
		"rubric_not_accessible": "This rubric cannot be accessed at this time.",
		"loading_rubric_choice_item": "Loading {rubric_name} article list...",
		"loading_rubric_body": "Fetching {rubric_name} news list from {site_name}...",
		"status_fetching_rubric": "Fetching {rubric_name} news list.",
		"status_auto_refreshed": "{rubric_name} news list automatically updated ({count} articles).",
		"status_rubric_loaded": "News list loaded successfully. Found {count} articles in {rubric_name}.",
		"status_rubric_loaded_loading_first": "News list loaded ({count} articles). Loading the first article...",
		"status_rubric_error_with_cached": "{error_msg} Showing {count} previously loaded articles.",
		"choice_rubric_load_failed": "News list could not be loaded",
		"body_rubric_load_failed": "{error_msg}\r\n\r\nPress F5 or activate the Refresh Article List button to try again.",
		"status_article_selected_loading": "Article selected: {title}. Loading full content.",
		"status_article_loaded_full": "Article content loaded successfully. {summary}",
		"status_article_loaded_partial": "Article content was only partially loaded. {summary}",
		"status_article_loaded_partial_err": "Article content was only partially loaded ({error_msg}).",

		# Navigation announcements
		"nav_no_articles": "No article list is available yet.",
		"nav_at_first_article": "You are already at the first article.",
		"nav_at_last_article": "You are already at the last article.",
		"nav_select_article_first": "Please select an article first to reload.",
		"nav_back_to_article": "Returned to article selection.",
		"nav_back_to_rubric": "Returned to news rubric selection.",
		"nav_back_to_site": "Returned to news portal selection.",
		"nav_rubric_unavailable_focus_site": "Rubrics are not available for this portal. Focused on news portal selection.",
		"nav_no_article_url": "No article URL is available to open.",
		"nav_opening_browser": "Opening original article in browser: {title}",
		"nav_open_browser_failed": "Failed to open the web browser for this article.",
		"settings_saved_announcement": "NewsHub for NVDA settings have been saved and applied.",

		# Settings dialog & NVDA SettingsPanel labels
		"settings_dialog_title": "Settings — NewsHub for NVDA",
		"acc_settings_dialog": "NewsHub for NVDA Settings",
		"lbl_language": "Interface &language (Bahasa):",
		"acc_language": "Interface language",
		"lbl_theme": "Display color &theme:",
		"acc_theme": "Display color theme",
		"theme_light": "Light (High Standard Contrast)",
		"theme_dark": "Dark (Low Glare)",
		"theme_high_contrast": "High Contrast (Black - Yellow/White)",
		"lbl_font_scale": "&Font size (85% - 150%):",
		"acc_font_scale": "Font size",
		"default_suffix": " (Default)",
		"lbl_font_family": "Reading font &family:",
		"acc_font_family": "Reading font family",
		"font_sans_serif": "Sans-serif (Segoe UI / Arial)",
		"font_serif": "Serif (Georgia / Times New Roman)",
		"lbl_paragraph_spacing": "&Paragraph spacing:",
		"acc_paragraph_spacing": "Paragraph spacing",
		"spacing_normal": "Normal (1 blank line)",
		"spacing_wide": "Wide (2 blank lines)",
		"lbl_auto_refresh": "Background &auto-refresh:",
		"chk_auto_refresh_label": "Enable automatic news list updates",
		"acc_chk_auto_refresh": "Enable automatic news list updates",
		"lbl_refresh_interval": "Auto-refresh &interval:",
		"acc_refresh_interval": "Auto-refresh interval",
		"interval_30s": "30 seconds",
		"interval_60s": "1 minute (60 seconds - Default)",
		"interval_120s": "2 minutes (120 seconds)",
		"interval_180s": "3 minutes (180 seconds)",
		"interval_300s": "5 minutes (300 seconds)",
		"interval_600s": "10 minutes (600 seconds)",
		"lbl_max_articles": "&Maximum articles per rubric:",
		"acc_max_articles": "Maximum articles per rubric",
		"max_articles_item": "{count} articles{suffix}",
		"btn_save_settings": "&Save Settings",
		"acc_btn_save_settings": "Save Settings",
		"btn_cancel": "&Cancel",
		"acc_btn_cancel": "Cancel",

		# Article status labels
		"status_not_fetched": "Article not fetched yet",
		"status_headline_loaded": "Headline loaded",
		"status_content_loading": "Loading content",
		"status_content_loaded": "Content loaded",
		"status_content_partial": "Content partially available",
		"status_content_failed": "Content retrieval failed",
		"status_unknown": "Unknown status",

		# Formatter strings
		"fmt_title_missing": "Article Title Unavailable",
		"fmt_rubric": "Rubric: {value}",
		"fmt_published_at": "Published: {value}",
		"fmt_author": "Author: {value}",
		"fmt_editor": "Editor: {value}",
		"fmt_reading_time": "Estimated Reading Time: about {minutes} min (approximated from text length)",
		"fmt_loading_body": "Status: Loading full article content from the source. Please wait...",
		"fmt_initial_summary": "Initial Summary: {summary}",
		"fmt_failed_default_reason": "Article content could not be extracted from the source page.",
		"fmt_failed_notice": (
			"Notice: Full article content could not be loaded ({reason}). "
			"You can press the Reload Article button (Ctrl+R) or Open Original Article in Browser."
		),
		"fmt_available_summary": "Available summary:\r\n{summary}",
		"fmt_partial_notice": (
			"Notice: Article content was only partially loaded. "
			"To read the full web page, use the Reload Article button (Ctrl+R) "
			"or Open Original Article in Browser."
		),
		"fmt_summary_label": "Summary: {summary}",
		"fmt_subheading": "Subheading: {text}",
		"fmt_quote": 'Quote: "{text}"',
		"fmt_caption": "Image Caption: {text}",
		"fmt_credit": "Source/Credit: {text}",
		"fmt_source_url": "Source Link: {url}",
		"fmt_table_start": "[News Data Table]",
		"fmt_table_columns": "Table Columns: {columns}",
		"fmt_table_row": "Row {row_num}: {content}",
		"fmt_table_end": "[End of Table]",
		"ann_article_pos": "Article {index} of {total}: {title}.",
		"ann_article_rubric": "Rubric {rubric}.",
		"ann_article_published": "Published {published_at}.",
		"ann_article_reading_time": "Estimated reading time about {minutes} minutes.",

		# Network & parser error messages
		"err_url_empty": "The news URL is empty or invalid.",
		"err_url_scheme": "Unsupported URL scheme. Only HTTP and HTTPS are allowed.",
		"err_url_no_domain": "Domain name was not found in the news URL.",
		"err_url_domain_blocked": "Domain '{hostname}' is outside the allowed news source domains.",
		"err_invalid_content_type": "Response from {site_label} is not a supported text/HTML news page.",
		"err_response_too_large": "Page size from {site_label} is too large to load safely.",
		"err_response_stream_too_large": "Page response size from {site_label} exceeded the safe limit (5 MB).",
		"err_empty_response": "Page from {site_label} returned an empty or incomplete response.",
		"err_http_403": "Access to {site_label} was denied by the server (HTTP 403). This rubric or article may be restricted.",
		"err_http_404": "The requested page or rubric on {site_label} was not found (HTTP 404).",
		"err_http_429": "Too many requests to {site_label} (HTTP 429). Please wait a moment and try again.",
		"err_http_5xx": "{site_label} server is currently experiencing issues (HTTP {code}). Please try again later.",
		"err_http_other": "Failed to load page from {site_label} (HTTP status {code}).",
		"err_timeout": "Connection to {site_label} timed out. Please check your internet connection and try again.",
		"err_dns": "Failed to reach {site_label} (DNS error or no network). Please check your internet connection and try again.",
		"err_ssl": "Failed to verify a secure connection (SSL/TLS) to {site_label}.",
		"err_connection_generic": "Failed to reach {site_label}. Please check your internet connection and try again.",
		"err_read_timeout": "Reading data from {site_label} timed out. Please check your internet connection and try again.",
		"err_unexpected_network": "An error occurred while contacting {site_label}. Please check your internet connection and try again.",
		"err_rubric_empty": "No news articles were found in the {rubric_name} rubric. The page structure may have changed or the rubric is currently empty.",
		"err_rubric_generic": "Failed to load the {rubric_name} news list from {site_name}. Please check your internet connection and try again.",
		"err_article_empty": "Article content could not be found on this page. The page structure may differ or it may be multimedia-only content.",
		"err_article_generic": "Failed to load article content from {site_name}. Please check your internet connection and try again.",
	},
}


def get_active_language() -> str:
	"""Return the currently configured UI language code ('id' or 'en')."""
	try:
		from .config_manager import config_manager
		lang = config_manager.get("language")
		if lang in SUPPORTED_LANGUAGES:
			return lang
	except Exception:
		pass
	return "id"


def tr(key: str, lang: str = "", **kwargs) -> str:
	"""
	Translate a UI string key into the active language ('id' or 'en') and format any placeholders.
	"""
	active_lang = lang if lang in SUPPORTED_LANGUAGES else get_active_language()
	lang_dict = STRINGS.get(active_lang, STRINGS["id"])
	template = lang_dict.get(key) or STRINGS["id"].get(key) or key
	if kwargs:
		try:
			return template.format(**kwargs)
		except Exception:
			return template
	return template
