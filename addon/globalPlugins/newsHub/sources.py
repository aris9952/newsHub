# -*- coding: utf-8 -*-
"""
Centralized news portal and rubric registry for NewsHub for NVDA.

Supports 5 major Indonesian news portals with 76 official rubrics:
1. Kompas.com (23 rubrics)
2. Detik.com (27 rubrics)
3. CNN Indonesia (8 rubrics)
4. CNBC Indonesia (7 rubrics)
5. Tempo.co (11 rubrics)
"""

from typing import Dict, List, Optional
from .models import RubricConfig, SiteConfig

try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	def _(s: str) -> str:
		return s


# 1. Kompas.com (23 official rubrics)
KOMPAS_RUBRICS: List[RubricConfig] = [
	RubricConfig(
		rubric_id="news",
		name="News",
		description=_("general news"),
		url="https://news.kompas.com",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="nasional",
		name="Nasional",
		description=_("domestic news"),
		url="https://nasional.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="global",
		name="Global",
		description=_("international news"),
		url="https://kompas.com/global",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="megapolitan",
		name="Megapolitan",
		description=_("Greater Jakarta news"),
		url="https://megapolitan.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="regional",
		name="Regional",
		description=_("regional news across Indonesia"),
		url="https://regional.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="pemilu",
		name="Pemilu",
		description=_("general elections"),
		url="https://pemilu.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="ikn",
		name="IKN",
		description=_("Nusantara Capital City"),
		url="https://ikn.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="bola",
		name="Bola",
		description=_("football and sports"),
		url="https://bola.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="tekno",
		name="Tekno",
		description=_("technology and digital"),
		url="https://tekno.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="otomotif",
		name="Otomotif",
		description=_("vehicles and automotive industry"),
		url="https://otomotif.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="entertainment",
		name="Entertainment",
		description=_("entertainment world"),
		url="https://entertainment.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="sains",
		name="Sains",
		description=_("science and research"),
		url="https://sains.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="health",
		name="Health",
		description=_("health and wellness"),
		url="https://health.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="money",
		name="Money",
		description=_("economy and finance"),
		url="https://money.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="tren",
		name="Tren",
		description=_("trending topics"),
		url="https://www.kompas.com/tren",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="properti",
		name="Properti",
		description=_("housing and real estate"),
		url="https://properti.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="lifestyle",
		name="Lifestyle",
		description=_("lifestyle and fashion"),
		url="https://lifestyle.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="hype",
		name="Hype",
		description=_("celebrity news and pop culture"),
		url="https://www.kompas.com/hype",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="travel",
		name="Travel",
		description=_("tourism and travel"),
		url="https://travel.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="homey",
		name="Homey",
		description=_("home and domestic living"),
		url="https://www.kompas.com/homey",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="food",
		name="Food",
		description=_("food and culinary"),
		url="https://www.kompas.com/food",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="umkm",
		name="UMKM",
		description=_("micro, small, and medium enterprises"),
		url="https://umkm.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="edukasi",
		name="Edukasi",
		description=_("education"),
		url="https://edukasi.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
]


# 2. Detik.com (27 official rubrics)
DETIK_RUBRICS: List[RubricConfig] = [
	RubricConfig(
		rubric_id="detik_news",
		name="Detik news",
		description=_("breaking national and political news"),
		url="https://news.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_finance",
		name="Detik finance",
		description=_("economy, business, and investment"),
		url="https://finance.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_inet",
		name="DetikInet",
		description=_("information technology, gadgets, and internet"),
		url="https://inet.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_hot",
		name="DetikHot",
		description=_("entertainment, celebrities, and music"),
		url="https://hot.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_sport",
		name="DetikSport",
		description=_("national and international sports"),
		url="https://sport.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="sepakbola",
		name="SepakBola",
		description=_("football news and world leagues"),
		url="https://sport.detik.com/sepakbola",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_oto",
		name="DetikOto",
		description=_("automotive, cars, and motorcycles"),
		url="https://oto.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_travel",
		name="DetikTravel",
		description=_("travel destinations and tourism"),
		url="https://travel.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_food",
		name="DetikFood",
		description=_("culinary, recipes, and dining"),
		url="https://food.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_health",
		name="Detik Health",
		description=_("health, medicine, and fitness"),
		url="https://health.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="wolipop",
		name="Wolipop",
		description=_("lifestyle, fashion, and beauty"),
		url="https://wolipop.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_x",
		name="DetikX",
		description=_("in-depth and investigative journalism"),
		url="https://news.detik.com/x/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="20detik",
		name="20Detik",
		description=_("video news and visual reports"),
		url="https://20.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_foto",
		name="DetikFoto",
		description=_("photojournalism and visual events"),
		url="https://foto.detik.com/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_edu",
		name="DetikEdu",
		description=_("education, schools, and higher learning"),
		url="https://www.detik.com/edu/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_hikmah",
		name="DetikHikmah",
		description=_("Islamic world and religious inspiration"),
		url="https://www.detik.com/hikmah/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_properti",
		name="DetikProperti",
		description=_("housing, architecture, and real estate"),
		url="https://www.detik.com/properti/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_pop",
		name="DetikPop",
		description=_("pop culture, K-Pop, movies, and anime"),
		url="https://www.detik.com/pop/",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_jateng",
		name="DetikJateng",
		description=_("Central Java regional news"),
		url="https://www.detik.com/jateng",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_jatim",
		name="DetikJatim",
		description=_("East Java regional news"),
		url="https://www.detik.com/jatim",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_jabar",
		name="DetikJabar",
		description=_("West Java regional news"),
		url="https://www.detik.com/jabar",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_sulsel",
		name="DetikSulsel",
		description=_("South Sulawesi regional news"),
		url="https://www.detik.com/sulsel",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_sumut",
		name="DetikSumut",
		description=_("North Sumatra regional news"),
		url="https://www.detik.com/sumut",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_bali",
		name="DetikBali",
		description=_("Bali and Nusa Tenggara regional news"),
		url="https://www.detik.com/bali",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_sumbagsel",
		name="DetikSumbagsel",
		description=_("Southern Sumatra regional news"),
		url="https://www.detik.com/sumbagsel",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_jogja",
		name="DetikJogja",
		description=_("Yogyakarta special region news"),
		url="https://www.detik.com/jogja",
		supported=True,
		parser_id="detik_dom",
	),
	RubricConfig(
		rubric_id="detik_kalimantan",
		name="DetikKalimantan",
		description=_("Kalimantan regional news"),
		url="https://www.detik.com/kalimantan/",
		supported=True,
		parser_id="detik_dom",
	),
]


# 3. CNN Indonesia (8 official rubrics)
CNN_INDONESIA_RUBRICS: List[RubricConfig] = [
	RubricConfig(
		rubric_id="cnn_nasional",
		name="Nasional",
		description=_("politics, law, crime, and national events"),
		url="https://www.cnnindonesia.com/nasional",
		supported=True,
		parser_id="cnn_dom",
	),
	RubricConfig(
		rubric_id="cnn_internasional",
		name="Internasional",
		description=_("international news and global geopolitics"),
		url="https://www.cnnindonesia.com/internasional",
		supported=True,
		parser_id="cnn_dom",
	),
	RubricConfig(
		rubric_id="cnn_ekonomi",
		name="Ekonomi",
		description=_("finance, energy, business, and macroeconomics"),
		url="https://www.cnnindonesia.com/ekonomi",
		supported=True,
		parser_id="cnn_dom",
	),
	RubricConfig(
		rubric_id="cnn_olahraga",
		name="Olahraga",
		description=_("football, MotoGP, F1, and badminton"),
		url="https://www.cnnindonesia.com/olahraga",
		supported=True,
		parser_id="cnn_dom",
	),
	RubricConfig(
		rubric_id="cnn_teknologi",
		name="Teknologi",
		description=_("information technology, science, and telecommunications"),
		url="https://www.cnnindonesia.com/teknologi",
		supported=True,
		parser_id="cnn_dom",
	),
	RubricConfig(
		rubric_id="cnn_otomotif",
		name="Otomotif",
		description=_("cars, motorcycles, and electric vehicles"),
		url="https://www.cnnindonesia.com/otomotif",
		supported=True,
		parser_id="cnn_dom",
	),
	RubricConfig(
		rubric_id="cnn_hiburan",
		name="Hiburan",
		description=_("movies, music, celebrities, and culture"),
		url="https://www.cnnindonesia.com/hiburan",
		supported=True,
		parser_id="cnn_dom",
	),
	RubricConfig(
		rubric_id="cnn_gaya_hidup",
		name="Gaya hidup",
		description=_("health, culinary, and travel lifestyle"),
		url="https://www.cnnindonesia.com/gaya-hidup",
		supported=True,
		parser_id="cnn_dom",
	),
]


# 4. CNBC Indonesia (7 official rubrics)
CNBC_INDONESIA_RUBRICS: List[RubricConfig] = [
	RubricConfig(
		rubric_id="cnbc_market",
		name="Market",
		description=_("capital markets, stocks, forex, and commodities"),
		url="https://www.cnbcindonesia.com/market",
		supported=True,
		parser_id="cnbc_dom",
	),
	RubricConfig(
		rubric_id="cnbc_mymoney",
		name="My Money",
		description=_("personal finance, planning, and investment"),
		url="https://www.cnbcindonesia.com/mymoney",
		supported=True,
		parser_id="cnbc_dom",
	),
	RubricConfig(
		rubric_id="cnbc_news",
		name="News",
		description=_("breaking economic, business, and national policy news"),
		url="https://www.cnbcindonesia.com/news",
		supported=True,
		parser_id="cnbc_dom",
	),
	RubricConfig(
		rubric_id="cnbc_tech",
		name="Tech",
		description=_("fintech, startups, and digital economy"),
		url="https://www.cnbcindonesia.com/tech",
		supported=True,
		parser_id="cnbc_dom",
	),
	RubricConfig(
		rubric_id="cnbc_lifestyle",
		name="LifeStyle",
		description=_("modern lifestyle, trends, and entertainment"),
		url="https://www.cnbcindonesia.com/lifestyle",
		supported=True,
		parser_id="cnbc_dom",
	),
	RubricConfig(
		rubric_id="cnbc_sharia",
		name="Sharia",
		description=_("Islamic economy and sharia finance"),
		url="https://www.cnbcindonesia.com/syariah",
		supported=True,
		parser_id="cnbc_dom",
	),
	RubricConfig(
		rubric_id="cnbc_entrepreneur",
		name="Entrepreneur",
		description=_("entrepreneurship, SMEs, and business inspiration"),
		url="https://www.cnbcindonesia.com/entrepreneur",
		supported=True,
		parser_id="cnbc_dom",
	),
]


# 5. Tempo.co (11 official rubrics)
TEMPO_RUBRICS: List[RubricConfig] = [
	RubricConfig(
		rubric_id="tempo_play",
		name="Permainan baru",
		description=_("interactive features and word games by Tempo"),
		url="https://www.tempo.co/play",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_politik",
		name="Politik",
		description=_("national political dynamics and government"),
		url="https://www.tempo.co/politik",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_hukum",
		name="Hukum",
		description=_("law, judiciary, and anti-corruption"),
		url="https://www.tempo.co/hukum",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_ekonomi",
		name="Ekonomi",
		description=_("business, macroeconomics, and fiscal policy"),
		url="https://www.tempo.co/ekonomi",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_lingkungan",
		name="Lingkungan",
		description=_("climate, ecology, and environmental conservation"),
		url="https://www.tempo.co/lingkungan",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_wawancara",
		name="Wawancara",
		description=_("exclusive interviews with key figures"),
		url="https://www.tempo.co/wawancara",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_investigasi",
		name="Investigasi",
		description=_("Tempo signature in-depth investigative reporting"),
		url="https://www.tempo.co/investigasi",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_cekfakta",
		name="Cek fakta",
		description=_("fact-checking and claim verification"),
		url="https://www.tempo.co/cekfakta",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_tokoh",
		name="Tokoh",
		description=_("in-depth profiles and stories of notable figures"),
		url="https://www.tempo.co/tokoh",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_newsletter",
		name="Newsletter",
		description=_("curated newsletter editions by Tempo editorial team"),
		url="https://www.tempo.co/newsletter",
		supported=True,
		parser_id="tempo_dom",
	),
	RubricConfig(
		rubric_id="tempo_info_tempo",
		name="Info tempo",
		description=_("partnership announcements and Tempo collaborations"),
		url="https://www.tempo.co/info-tempo",
		supported=True,
		parser_id="tempo_dom",
	),
]


# Multi-site registry of news portals
SITES_REGISTRY: List[SiteConfig] = [
	SiteConfig(
		site_id="kompas",
		name="Kompas.com",
		description=_("KG Media national and international news portal (Indonesia)"),
		base_url="https://www.kompas.com",
		supported=True,
		parser_id="kompas_dom",
		rubrics=KOMPAS_RUBRICS,
	),
	SiteConfig(
		site_id="detik",
		name="Detik.com",
		description=_("Indonesian national, regional, and thematic breaking news portal"),
		base_url="https://www.detik.com",
		supported=True,
		parser_id="detik_dom",
		rubrics=DETIK_RUBRICS,
	),
	SiteConfig(
		site_id="cnn_indonesia",
		name="CNN Indonesia",
		description=_("Trans Media national, international, and economic news portal"),
		base_url="https://www.cnnindonesia.com",
		supported=True,
		parser_id="cnn_dom",
		rubrics=CNN_INDONESIA_RUBRICS,
	),
	SiteConfig(
		site_id="cnbc_indonesia",
		name="CNBC Indonesia",
		description=_("Capital markets, investment, business, and fintech news portal"),
		base_url="https://www.cnbcindonesia.com",
		supported=True,
		parser_id="cnbc_dom",
		rubrics=CNBC_INDONESIA_RUBRICS,
	),
	SiteConfig(
		site_id="tempo",
		name="Tempo.co",
		description=_("Investigative, political, legal, and fact-checking news portal"),
		base_url="https://www.tempo.co",
		supported=True,
		parser_id="tempo_dom",
		rubrics=TEMPO_RUBRICS,
	),
]

SITES_BY_ID: Dict[str, SiteConfig] = {site.id: site for site in SITES_REGISTRY}


def get_all_sites() -> List[SiteConfig]:
	"""Return the complete list of registered news site configurations."""
	return list(SITES_REGISTRY)


def get_site_by_id(site_id: str) -> Optional[SiteConfig]:
	"""Look up a news site configuration by its unique ID."""
	return SITES_BY_ID.get((site_id or "").strip().lower())


def get_default_site() -> SiteConfig:
	"""Return the default primary news site configuration (Kompas.com)."""
	return SITES_REGISTRY[0]
