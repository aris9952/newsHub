 NewsHub for NVDA

Author: Aris Yohanes Elean, S.Kom  
Version: 1.0.0  
Minimum NVDA Version: 2022.1.0  
Last Tested NVDA Version: 2026.1.0  
License: GNU General Public License v2.0 (GPL-2.0)

---

 Description

Reading news from various national and international news portals such as kompas.com, detik.com, and others is truly enjoyable. Not only is the news presented reliable, but it also broadens our knowledge as readers.
However, as we know, the web pages of these news portals are often not friendly to screen readers.
They are cluttered with advertisements and complex navigation that make reading difficult.
That is why "NewsHub for NVDA" is here!

With this add-on, you can read news from trusted news portals easily and comfortably. For this current version, the add-on supports "kompas.com" (across all 23 official rubrics), and support for other news portals will follow soon.
Happy reading!

---

 Key Features

- Full Support for 23 Official Kompas.com Rubrics: News, Nasional, Global, Megapolitan, Regional, Pemilu, IKN, Bola, Tekno, Otomotif, Entertainment, Sains, Health, Money, Tren, Properti, Lifestyle, Hype, Travel, Homey, Food, UMKM, and Edukasi.
- Clean DOM-Scoped Article Extraction: Extracts headlines, publication timestamps, authors, editors, subheadings, paragraphs, blockquotes, ordered/unordered lists, image captions, and news data tables while stripping out advertisements, navigation menus, and "Baca juga" distractions.
- Verified Multi-Page Article Support: Automatically detects verified `?page=all` pagination links so multi-page articles are loaded in full.
- Bilingual Interface (`Bahasa Indonesia` & `English`): Switch the interface language dynamically via NVDA Menu -> Preferences -> Settings... -> NewsHub for NVDA.
- Non-Intrusive Background Auto-Refresh: Automatically updates the active rubric's headline list every 1 minute (configurable) without stealing focus or interrupting active reading.
- Low-Vision Accessibility Options: Supports Light, Dark, and High Contrast color themes, font scaling from 85% to 150% (default 100%), Sans-serif/Serif fonts, and Normal/Wide paragraph spacing.

---

 Keyboard Shortcuts

| Shortcut | Scope | Action |
| `NVDA+Shift+K` | Global | Open the NewsHub for NVDA dashboard (global shortcut) |
| `Alt+[` | Dashboard | Open the previous article in the active rubric (when dashboard is active) |
| `Alt+]` | Dashboard | Open the next article in the active rubric (when dashboard is active) |
| `F5` | Dashboard | Refresh the article list for the active rubric |
| `Ctrl+R` | Dashboard | Reload the full content of the currently selected article |
| `Esc` | Dashboard | Step back to the previous stage (Article Content -> Article List -> Rubric -> Portal) or close the dashboard |

---

 Installation

1. Download the latest [`newsHub-1.0.0.nvda-addon`](releases/newsHub-1.0.0.nvda-addon) package from the Releases section.
2. Open NVDA, go to NVDA Menu -> Tools -> Add-on Store / Manage Add-ons, and choose Install from file... (or press `Enter` directly on the `.nvda-addon` file in Windows Explorer).
3. Restart NVDA when prompted.
4. Press `NVDA+Shift+K` anywhere to open NewsHub for NVDA.
