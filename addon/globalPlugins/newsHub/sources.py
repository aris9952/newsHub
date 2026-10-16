# -*- coding: utf-8 -*-
"""
Centralized news portal and rubric registry for NewsHub for NVDA.

In version 1.0, Kompas.com serves as the fully functional pilot project supporting all 23
official rubrics with bilingual descriptions (Indonesian and English). The registry is
modular so additional news portals can be added cleanly in future releases.
"""

from typing import Dict, List, Optional
from .models import RubricConfig, SiteConfig


# Complete list of 23 official Kompas.com rubrics matching the initial configuration specification
KOMPAS_RUBRICS: List[RubricConfig] = [
	RubricConfig(
		rubric_id="news",
		name="News",
		description="berita umum",
		description_en="general news",
		url="https://news.kompas.com",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="nasional",
		name="Nasional",
		description="berita dalam negeri",
		description_en="national domestic news",
		url="https://nasional.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="global",
		name="Global",
		description="berita internasional",
		description_en="international news",
		url="https://global.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="megapolitan",
		name="Megapolitan",
		description="Jakarta dan sekitarnya",
		description_en="Greater Jakarta news",
		url="https://megapolitan.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="regional",
		name="Regional",
		description="berita daerah",
		description_en="regional news across Indonesia",
		url="https://regional.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="pemilu",
		name="Pemilu",
		description="pemilihan umum",
		description_en="general elections",
		url="https://pemilu.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="ikn",
		name="IKN",
		description="Ibu Kota Nusantara",
		description_en="Nusantara Capital City",
		url="https://ikn.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="bola",
		name="Bola",
		description="sepak bola",
		description_en="football and sports",
		url="https://bola.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="tekno",
		name="Tekno",
		description="teknologi dan digital",
		description_en="technology and digital",
		url="https://tekno.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="otomotif",
		name="Otomotif",
		description="kendaraan dan industri otomotif",
		description_en="vehicles and automotive industry",
		url="https://otomotif.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="entertainment",
		name="Entertainment",
		description="dunia hiburan",
		description_en="entertainment world",
		url="https://entertainment.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="sains",
		name="Sains",
		description="ilmu pengetahuan",
		description_en="science and research",
		url="https://sains.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="health",
		name="Health",
		description="kesehatan",
		description_en="health and wellness",
		url="https://health.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="money",
		name="Money",
		description="ekonomi dan keuangan",
		description_en="economy and finance",
		url="https://money.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="tren",
		name="Tren",
		description="topik yang sedang ramai",
		description_en="trending topics",
		url="https://www.kompas.com/tren",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="properti",
		name="Properti",
		description="rumah dan properti",
		description_en="housing and real estate",
		url="https://properti.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="lifestyle",
		name="Lifestyle",
		description="gaya hidup",
		description_en="lifestyle and fashion",
		url="https://lifestyle.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="hype",
		name="Hype",
		description="kabar selebritas dan budaya populer",
		description_en="celebrity news and pop culture",
		url="https://www.kompas.com/hype",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="travel",
		name="Travel",
		description="wisata dan perjalanan",
		description_en="tourism and travel",
		url="https://travel.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="homey",
		name="Homey",
		description="rumah dan kehidupan domestik",
		description_en="home and domestic living",
		url="https://www.kompas.com/homey",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="food",
		name="Food",
		description="makanan dan kuliner",
		description_en="food and culinary",
		url="https://www.kompas.com/food",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="umkm",
		name="UMKM",
		description="usaha mikro, kecil, dan menengah",
		description_en="micro, small, and medium enterprises",
		url="https://umkm.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
	RubricConfig(
		rubric_id="edukasi",
		name="Edukasi",
		description="pendidikan",
		description_en="education and schools",
		url="https://edukasi.kompas.com/",
		supported=True,
		parser_id="kompas_dom",
	),
]


# Multi-site news portal registry.
# Only Kompas.com is active in version 1.0; other portals are marked supported=False
# so unsupported portals are handled transparently without fake data.
SITES_REGISTRY: List[SiteConfig] = [
	SiteConfig(
		site_id="kompas",
		name="Kompas.com",
		description="Portal berita nasional dan internasional KG Media (Indonesia)",
		description_en="KG Media national and international news portal (Indonesia)",
		base_url="https://www.kompas.com",
		supported=True,
		parser_id="kompas_dom",
		rubrics=KOMPAS_RUBRICS,
	),
	SiteConfig(
		site_id="cnn_indonesia",
		name="CNN Indonesia",
		description="Portal berita nasional dan internasional (Belum didukung pada versi ini)",
		description_en="National and international news portal (Not supported in this version)",
		base_url="https://www.cnnindonesia.com",
		supported=False,
		parser_id="unsupported",
		rubrics=[],
	),
	SiteConfig(
		site_id="detik",
		name="Detik.com",
		description="Portal berita terkini Indonesia (Belum didukung pada versi ini)",
		description_en="Indonesian breaking news portal (Not supported in this version)",
		base_url="https://www.detik.com",
		supported=False,
		parser_id="unsupported",
		rubrics=[],
	),
	SiteConfig(
		site_id="tempo",
		name="Tempo.co",
		description="Portal berita investigasi dan nasional (Belum didukung pada versi ini)",
		description_en="Investigative and national news portal (Not supported in this version)",
		base_url="https://www.tempo.co",
		supported=False,
		parser_id="unsupported",
		rubrics=[],
	),
]

SITES_BY_ID: Dict[str, SiteConfig] = {site.id: site for site in SITES_REGISTRY}


def get_all_sites() -> List[SiteConfig]:
	"""Return the list of all registered news portal configurations."""
	return list(SITES_REGISTRY)


def get_site_by_id(site_id: str) -> Optional[SiteConfig]:
	"""Look up a news portal configuration by its unique ID."""
	return SITES_BY_ID.get((site_id or "").strip().lower())


def get_default_site() -> SiteConfig:
	"""Return the primary default news portal (Kompas.com)."""
	return SITES_REGISTRY[0]
