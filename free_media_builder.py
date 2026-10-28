#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Free Media Builder
==================
Builds M3U playlists of media that is free to watch legally, sorted by
country and by category.

Sources
  Live TV  iptv-org          publicly available streams; its DMCA/NSFW
                             blocklist is applied, adult channels removed
           Free-TV/IPTV      curated free-to-air channels
  Movies   Internet Archive  public-domain film collections
  Series   Internet Archive  "Classic TV" (public-domain TV episodes)
  Radio    radio-browser.info community directory

Needs only Python 3.9 or newer (no extra packages).

  python free_media_builder.py              build everything
  python free_media_builder.py --quick      small trial run
  python free_media_builder.py --serve      build, then share the files on your Wi-Fi
  python free_media_builder.py --help       all options
"""

import argparse
import collections
import concurrent.futures as cf
import functools
import gzip
import hashlib
import html
import http.server
import json
import os
import re
import socket
import sys
import threading
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "1.0"

# ----------------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------------

IPTV_API = "https://iptv-org.github.io/api/"
FREE_TV_M3U = "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8"
IA_SCRAPE = "https://archive.org/services/search/v1/scrape"
IA_META = "https://archive.org/metadata/"
IA_DOWNLOAD = "https://archive.org/download/"
IA_DETAILS = "https://archive.org/details/"
IA_IMG = "https://archive.org/services/img/"
RB_DISCOVERY = "https://all.api.radio-browser.info/json/servers"
RB_FALLBACK = ["de1.api.radio-browser.info", "de2.api.radio-browser.info",
               "fi1.api.radio-browser.info", "nl1.api.radio-browser.info",
               "at1.api.radio-browser.info"]

# Internet Archive collections that hold public-domain films. Community upload
# areas (where copyright is unchecked) are deliberately not used.
MOVIE_COLLECTIONS = ["feature_films", "SciFi_Horror", "Film_Noir", "Comedy_Films",
                     "silent_films", "classic_cartoons", "prelinger"]
SERIES_COLLECTIONS = ["classic_tv"]

TOOL_UA = "FreeMediaBuilder/%s (personal playlist builder)" % VERSION
PLAYER_UA = ("Mozilla/5.0 (Linux; Android 11; AFTKA) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

HOUR = 3600
DAY = 24 * HOUR

# ----------------------------------------------------------------------------
# Names (Arabic / English)
# ----------------------------------------------------------------------------

COUNTRY_AR = {
    "AD": "أندورا", "AE": "الإمارات", "AF": "أفغانستان", "AG": "أنتيغوا وباربودا",
    "AI": "أنغويلا", "AL": "ألبانيا", "AM": "أرمينيا", "AO": "أنغولا",
    "AQ": "القارة القطبية الجنوبية", "AR": "الأرجنتين", "AS": "ساموا الأمريكية",
    "AT": "النمسا", "AU": "أستراليا", "AW": "أروبا", "AX": "جزر أولاند",
    "AZ": "أذربيجان", "BA": "البوسنة والهرسك", "BB": "باربادوس", "BD": "بنغلاديش",
    "BE": "بلجيكا", "BF": "بوركينا فاسو", "BG": "بلغاريا", "BH": "البحرين",
    "BI": "بوروندي", "BJ": "بنين", "BL": "سان بارتيلمي", "BM": "برمودا",
    "BN": "بروناي", "BO": "بوليفيا", "BQ": "هولندا الكاريبية", "BR": "البرازيل",
    "BS": "جزر البهاما", "BT": "بوتان", "BV": "جزيرة بوفيه", "BW": "بوتسوانا",
    "BY": "بيلاروسيا", "BZ": "بليز", "CA": "كندا", "CC": "جزر كوكوس",
    "CD": "الكونغو الديمقراطية", "CF": "أفريقيا الوسطى", "CG": "الكونغو",
    "CH": "سويسرا", "CI": "ساحل العاج", "CK": "جزر كوك", "CL": "تشيلي",
    "CM": "الكاميرون", "CN": "الصين", "CO": "كولومبيا", "CR": "كوستاريكا",
    "CU": "كوبا", "CV": "الرأس الأخضر", "CW": "كوراساو", "CX": "جزيرة الكريسماس",
    "CY": "قبرص", "CZ": "التشيك", "DE": "ألمانيا", "DJ": "جيبوتي",
    "DK": "الدنمارك", "DM": "دومينيكا", "DO": "جمهورية الدومينيكان",
    "DZ": "الجزائر", "EC": "الإكوادور", "EE": "إستونيا", "EG": "مصر",
    "EH": "الصحراء الغربية", "ER": "إريتريا", "ES": "إسبانيا", "ET": "إثيوبيا",
    "FI": "فنلندا", "FJ": "فيجي", "FK": "جزر فوكلاند", "FM": "ميكرونيزيا",
    "FO": "جزر فارو", "FR": "فرنسا", "GA": "الغابون", "GB": "المملكة المتحدة",
    "GD": "غرينادا", "GE": "جورجيا", "GF": "غويانا الفرنسية", "GG": "غيرنزي",
    "GH": "غانا", "GI": "جبل طارق", "GL": "غرينلاند", "GM": "غامبيا",
    "GN": "غينيا", "GP": "غوادلوب", "GQ": "غينيا الاستوائية", "GR": "اليونان",
    "GS": "جورجيا الجنوبية", "GT": "غواتيمالا", "GU": "غوام", "GW": "غينيا بيساو",
    "GY": "غيانا", "HK": "هونغ كونغ", "HM": "جزيرة هيرد وجزر ماكدونالد",
    "HN": "هندوراس", "HR": "كرواتيا", "HT": "هايتي", "HU": "المجر",
    "ID": "إندونيسيا", "IE": "أيرلندا", "IL": "إسرائيل", "IM": "جزيرة مان",
    "IN": "الهند", "IO": "إقليم المحيط الهندي البريطاني", "IQ": "العراق",
    "IR": "إيران", "IS": "آيسلندا", "IT": "إيطاليا", "JE": "جيرسي",
    "JM": "جامايكا", "JO": "الأردن", "JP": "اليابان", "KE": "كينيا",
    "KG": "قيرغيزستان", "KH": "كمبوديا", "KI": "كيريباتي", "KM": "جزر القمر",
    "KN": "سانت كيتس ونيفيس", "KP": "كوريا الشمالية", "KR": "كوريا الجنوبية",
    "KW": "الكويت", "KY": "جزر كايمان", "KZ": "كازاخستان", "LA": "لاوس",
    "LB": "لبنان", "LC": "سانت لوسيا", "LI": "ليختنشتاين", "LK": "سريلانكا",
    "LR": "ليبيريا", "LS": "ليسوتو", "LT": "ليتوانيا", "LU": "لوكسمبورغ",
    "LV": "لاتفيا", "LY": "ليبيا", "MA": "المغرب", "MC": "موناكو",
    "MD": "مولدوفا", "ME": "الجبل الأسود", "MF": "سانت مارتن", "MG": "مدغشقر",
    "MH": "جزر مارشال", "MK": "مقدونيا الشمالية", "ML": "مالي", "MM": "ميانمار",
    "MN": "منغوليا", "MO": "ماكاو", "MP": "جزر ماريانا الشمالية", "MQ": "مارتينيك",
    "MR": "موريتانيا", "MS": "مونتسرات", "MT": "مالطا", "MU": "موريشيوس",
    "MV": "جزر المالديف", "MW": "مالاوي", "MX": "المكسيك", "MY": "ماليزيا",
    "MZ": "موزمبيق", "NA": "ناميبيا", "NC": "كاليدونيا الجديدة", "NE": "النيجر",
    "NF": "جزيرة نورفولك", "NG": "نيجيريا", "NI": "نيكاراغوا", "NL": "هولندا",
    "NO": "النرويج", "NP": "نيبال", "NR": "ناورو", "NU": "نييوي",
    "NZ": "نيوزيلندا", "OM": "عُمان", "PA": "بنما", "PE": "بيرو",
    "PF": "بولينيزيا الفرنسية", "PG": "بابوا غينيا الجديدة", "PH": "الفلبين",
    "PK": "باكستان", "PL": "بولندا", "PM": "سان بيير وميكلون", "PN": "جزر بيتكيرن",
    "PR": "بورتوريكو", "PS": "فلسطين", "PT": "البرتغال", "PW": "بالاو",
    "PY": "باراغواي", "QA": "قطر", "RE": "لا ريونيون", "RO": "رومانيا",
    "RS": "صربيا", "RU": "روسيا", "RW": "رواندا", "SA": "السعودية",
    "SB": "جزر سليمان", "SC": "سيشل", "SD": "السودان", "SE": "السويد",
    "SG": "سنغافورة", "SH": "سانت هيلينا", "SI": "سلوفينيا", "SJ": "سفالبارد ويان ماين",
    "SK": "سلوفاكيا", "SL": "سيراليون", "SM": "سان مارينو", "SN": "السنغال",
    "SO": "الصومال", "SR": "سورينام", "SS": "جنوب السودان", "ST": "ساو تومي وبرينسيب",
    "SV": "السلفادور", "SX": "سينت مارتن", "SY": "سوريا", "SZ": "إسواتيني",
    "TC": "جزر توركس وكايكوس", "TD": "تشاد", "TF": "الأقاليم الجنوبية الفرنسية",
    "TG": "توغو", "TH": "تايلاند", "TJ": "طاجيكستان", "TK": "توكيلاو",
    "TL": "تيمور الشرقية", "TM": "تركمانستان", "TN": "تونس", "TO": "تونغا",
    "TR": "تركيا", "TT": "ترينيداد وتوباغو", "TV": "توفالو", "TW": "تايوان",
    "TZ": "تنزانيا", "UA": "أوكرانيا", "UG": "أوغندا", "UK": "المملكة المتحدة",
    "UM": "جزر الولايات المتحدة النائية", "US": "الولايات المتحدة", "UY": "الأوروغواي",
    "UZ": "أوزبكستان", "VA": "الفاتيكان", "VC": "سانت فنسنت والغرينادين",
    "VE": "فنزويلا", "VG": "جزر العذراء البريطانية", "VI": "جزر العذراء الأمريكية",
    "VN": "فيتنام", "VU": "فانواتو", "WF": "واليس وفوتونا", "WS": "ساموا",
    "XK": "كوسوفو", "YE": "اليمن", "YT": "مايوت", "ZA": "جنوب أفريقيا",
    "ZM": "زامبيا", "ZW": "زيمبابوي",
}

# Arab countries come first in every list (Gulf first).
ARAB = ["SA", "AE", "KW", "QA", "BH", "OM", "IQ", "YE", "JO", "PS", "LB", "SY",
        "EG", "SD", "LY", "TN", "DZ", "MA", "MR", "SO", "DJ", "KM"]
ARAB_RANK = {c: i for i, c in enumerate(ARAB)}
ARABIC_LANGS = {"ar", "ara", "arb", "arz", "ary", "arq", "aeb", "apc", "apd", "acm",
                "acq", "afb", "ajp", "ayl", "ayh"}

CATEGORY_AR = {
    "general": "عام", "news": "أخبار", "sports": "رياضة", "kids": "أطفال",
    "movies": "أفلام", "series": "مسلسلات", "entertainment": "ترفيه",
    "documentary": "وثائقي", "religious": "ديني", "music": "موسيقى",
    "family": "عائلي", "comedy": "كوميديا", "animation": "رسوم متحركة",
    "culture": "ثقافة", "education": "تعليم", "science": "علوم",
    "lifestyle": "نمط حياة", "cooking": "طبخ", "travel": "سفر وسياحة",
    "outdoor": "طبيعة ومغامرات", "auto": "سيارات", "business": "اقتصاد وأعمال",
    "classic": "كلاسيكيات", "legislative": "برلمان وتشريع", "public": "قنوات عامة",
    "weather": "طقس", "relax": "استرخاء", "shop": "تسوق", "interactive": "تفاعلي",
    "undefined": "غير مصنف",
}
CATEGORY_ORDER = ["general", "news", "sports", "kids", "movies", "series",
                  "entertainment", "documentary", "religious", "music", "family",
                  "comedy", "animation", "culture", "education", "science",
                  "lifestyle", "cooking", "travel", "outdoor", "auto", "business",
                  "classic", "legislative", "public", "weather", "relax", "shop",
                  "interactive"]

GENRES = {  # id: (Arabic, English) - also the display order
    "arabic": ("أفلام عربية", "Arabic Films"),
    "animation": ("رسوم متحركة", "Animation"),
    "documentary": ("وثائقيات", "Documentaries"),
    "scifi_horror": ("خيال علمي ورعب", "Sci-Fi & Horror"),
    "noir": ("جريمة وغموض", "Crime & Mystery"),
    "comedy": ("كوميديا", "Comedy"),
    "western": ("ويسترن", "Westerns"),
    "war": ("حروب", "War"),
    "adventure": ("أكشن ومغامرة", "Action & Adventure"),
    "romance": ("رومانسي", "Romance"),
    "musical": ("موسيقي واستعراضي", "Musicals"),
    "drama": ("دراما", "Drama"),
    "family": ("عائلي", "Family"),
    "silent": ("أفلام صامتة", "Silent Films"),
    "classic": ("أفلام كلاسيكية", "Classic Films"),
    "shorts": ("أفلام قصيرة", "Short Films"),
}
GENRE_ORDER = list(GENRES)
COLLECTION_GENRE = [("classic_cartoons", "animation"), ("prelinger", "documentary"),
                    ("silent_films", "silent"), ("Film_Noir", "noir"),
                    ("SciFi_Horror", "scifi_horror"), ("Comedy_Films", "comedy")]
GENRE_WORDS = [
    ("animation", ["animation", "animated", "cartoon", "cartoons"]),
    ("documentary", ["documentary", "documentaries", "newsreel", "educational film"]),
    ("western", ["western", "westerns", "cowboy", "cowboys"]),
    ("war", ["war", "world war", "wwii", "ww2", "military"]),
    ("scifi_horror", ["horror", "science fiction", "sci-fi", "scifi", "monster",
                      "zombie", "zombies", "vampire", "vampires"]),
    ("noir", ["film noir", "noir", "crime", "gangster", "detective", "mystery", "thriller"]),
    ("comedy", ["comedy", "comedies", "slapstick"]),
    ("adventure", ["adventure", "action", "swashbuckler"]),
    ("romance", ["romance", "romantic"]),
    ("musical", ["musical", "musicals"]),
    ("drama", ["drama", "melodrama"]),
    ("family", ["family", "children"]),
]
GENRE_RX = [(g, re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b"))
            for g, words in GENRE_WORDS]

LABEL_AR = {"Geo-blocked": "محجوب جغرافياً", "Not 24/7": "غير متواصل"}

# Extra spellings used by playlists for country group names.
NAME_ALIASES = {
    "usa": "US", "united states": "US", "uk": "UK", "united kingdom": "UK",
    "great britain": "UK", "england": "UK", "uae": "AE", "united arab emirates": "AE",
    "south korea": "KR", "korea": "KR", "north korea": "KP", "russia": "RU",
    "czech republic": "CZ", "czechia": "CZ", "vietnam": "VN", "iran": "IR",
    "syria": "SY", "palestine": "PS", "turkey": "TR", "turkiye": "TR",
    "netherlands": "NL", "holland": "NL", "bosnia": "BA",
    "bosnia and herzegovina": "BA", "macedonia": "MK", "north macedonia": "MK",
    "moldova": "MD", "laos": "LA", "ivory coast": "CI", "cote d'ivoire": "CI",
    "dr congo": "CD", "congo": "CG", "cape verde": "CV", "kosovo": "XK",
    "taiwan": "TW", "hong kong": "HK", "macau": "MO", "vatican": "VA",
    "brunei": "BN", "bolivia": "BO", "venezuela": "VE", "tanzania": "TZ",
    "dominican republic": "DO", "saudi arabia": "SA", "eswatini": "SZ",
    "swaziland": "SZ", "east timor": "TL", "timor-leste": "TL", "myanmar": "MM",
    "burma": "MM", "faroe islands": "FO", "faroe": "FO",
}

COUNTRY_EN = {}    # filled from iptv-org and radio-browser at run time
CATEGORY_EN = {}


class Settings:
    names = "ar"     # language of group names: ar | en | both
    plain = False    # True = no emoji flags / icons


S = Settings()

# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

TAG_RX = re.compile(r"<[^>]+>")
ATTR_RX = re.compile(r'([\w-]+)="([^"]*)"')
ENCLOSED_RX = re.compile("[\u2460-\u24ff]")          # markers such as Ⓖ Ⓨ
YOUTUBE_RX = re.compile(r"(?:youtube\.com|youtu\.be)/", re.I)
ADULT_RX = re.compile(r"\b(?:adult|erotic|erotica|xxx|porn|sex)\b", re.I)


def log(msg=""):
    print(msg, flush=True)


def as_list(v):
    if v is None or v == "":
        return []
    return list(v) if isinstance(v, (list, tuple, set)) else [v]


def first(v):
    items = as_list(v)
    return items[0] if items else ""


def int_or0(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def clean_text(v, limit=0):
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x) for x in v)
    s = html.unescape(TAG_RX.sub(" ", str(v or "")))
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit - 1].rstrip() + "…"
    return s


def year_of(v):
    m = re.search(r"\b(18[89]\d|19\d\d|20[0-4]\d)\b", str(v or ""))
    return int(m.group(1)) if m else None


def seconds(v):
    """'5423.1' or '1:30:23' -> seconds."""
    s = str(v or "").strip()
    if not s:
        return 0
    try:
        if ":" in s:
            total = 0.0
            for part in s.split(":"):
                total = total * 60 + float(part)
            return int(total)
        return int(float(s))
    except ValueError:
        return 0


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def norm_cc(code):
    c = str(code or "").strip().upper()
    return "UK" if c == "GB" else c


def norm_url(u):
    u = u.strip()
    try:
        p = urllib.parse.urlsplit(u)
        return "%s://%s%s%s" % (p.scheme.lower(), p.netloc.lower(), p.path,
                               "?" + p.query if p.query else "")
    except ValueError:
        return u


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", str(s)).strip("-") or "x"


def sort_text(s):
    # Drop the article first (plain alef), then unify alef forms, so that
    # "الأرجنتين" sorts by "أرجنتين" while "ألمانيا" keeps its first letters.
    s = re.sub(r"^(?:ال|the\s+)", "", str(s).lower().strip())
    return re.sub("[أإآ]", "ا", s)


def is_open_license(url):
    u = str(url or "").lower()
    return "publicdomain" in u or "creativecommons.org" in u


def ia_url(identifier, filename):
    return (IA_DOWNLOAD + urllib.parse.quote(identifier, safe="") + "/" +
            urllib.parse.quote(filename))


def flag(code):
    c = "GB" if code == "UK" else str(code or "")
    if S.plain or len(c) != 2 or not c.isascii() or not c.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in c.upper())


def bilingual(ar, en):
    if S.names == "en":
        return en or ar
    if S.names == "both" and ar and en and ar != en:
        return "%s | %s" % (ar, en)
    return ar or en


def with_icon(icon, text):
    return "%s %s" % (icon, text) if icon and not S.plain else text


def country_name(code):
    return bilingual(COUNTRY_AR.get(code, ""), COUNTRY_EN.get(code, "")) or code or "?"


def country_group(code):
    if not code:
        return with_icon("🌐", bilingual("دولية ومتنوعة", "International"))
    return with_icon(flag(code), country_name(code))


def country_key(code):
    if code in ARAB_RANK:
        return (0, ARAB_RANK[code], "")
    if not code:
        return (2, 0, "")
    return (1, 0, sort_text(country_name(code)))


def category_name(cat):
    en = CATEGORY_EN.get(cat) or cat.replace("_", " ").title()
    return bilingual(CATEGORY_AR.get(cat, ""), en)


def category_key(cat):
    if cat == "undefined":
        return (999, "")
    if cat in CATEGORY_ORDER:
        return (CATEGORY_ORDER.index(cat), "")
    return (500, sort_text(category_name(cat)))


def genre_group(g):
    ar, en = GENRES.get(g, (g, g))
    return with_icon("🎬", bilingual(ar, en))


def genre_key(g):
    return GENRE_ORDER.index(g) if g in GENRE_ORDER else 99


def label_text(label):
    return LABEL_AR.get(label, label) if S.names == "ar" else label


def human_time(sec):
    sec = int(sec)
    if sec < 60:
        return "%ds" % sec
    if sec < 3600:
        return "%dm %02ds" % (sec // 60, sec % 60)
    return "%dh %02dm" % (sec // 3600, sec % 3600 // 60)


# ----------------------------------------------------------------------------
# Networking, cache and parallel work
# ----------------------------------------------------------------------------

def http_get(url, headers=None, timeout=60, retries=3):
    """Download a URL, with gzip support and polite retries."""
    hdrs = {"User-Agent": TOOL_UA, "Accept-Encoding": "gzip"}
    if headers:
        hdrs.update(headers)
    error = None
    for attempt in range(retries):
        wait = 2 * (attempt + 1)
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as e:
            error = e
            if e.code in (400, 401, 403, 404, 410, 451):
                raise
            if e.code in (429, 503):
                wait = max(wait * 3, int_or0(e.headers.get("Retry-After")))
        except Exception as e:  # network trouble: try again
            error = e
        if attempt < retries - 1:
            time.sleep(min(wait, 60))
    raise error


class Cache:
    """Keeps downloads on disk so re-runs are fast and interrupted runs resume."""

    def __init__(self, folder, refresh=False):
        self.dir = Path(folder)
        self.refresh = refresh
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.dir / h[:2] / (h + ".json")

    def get(self, key, max_age, refreshable=True):
        if self.refresh and refreshable:
            return None
        p = self._path(key)
        try:
            if max_age is not None and time.time() - p.stat().st_mtime > max_age:
                return None
            return json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, key, value):
        p = self._path(key)
        try:
            p.parent.mkdir(exist_ok=True)
            tmp = p.with_name("%s.%d.tmp" % (p.name, threading.get_ident()))
            tmp.write_text(json.dumps(value, ensure_ascii=False), "utf-8")
            os.replace(tmp, p)
        except OSError:
            pass


def cached_json(cache, url, max_age, timeout=120):
    hit = cache.get(url, max_age)
    if hit is not None:
        return hit
    try:
        data = json.loads(http_get(url, timeout=timeout))
    except Exception as e:
        stale = cache.get(url, None, refreshable=False)
        if stale is not None:
            log("    (offline copy used for %s: %s)" % (url[:70], e))
            return stale
        raise
    cache.put(url, data)
    return data


def cached_text(cache, url, max_age):
    hit = cache.get(url, max_age)
    if hit is not None:
        return hit.get("text", "")
    try:
        text = http_get(url).decode("utf-8", "replace")
    except Exception as e:
        stale = cache.get(url, None, refreshable=False)
        if stale is not None:
            log("    (offline copy used for %s: %s)" % (url[:70], e))
            return stale.get("text", "")
        raise
    cache.put(url, {"text": text})
    return text


class Progress:
    def __init__(self, total, label):
        self.total, self.label, self.done = total, label, 0
        self.lock = threading.Lock()
        self.last = 0.0
        try:
            self.console = sys.stdout.isatty()
        except (AttributeError, ValueError):
            self.console = False
        self._show(True)

    def tick(self):
        with self.lock:
            self.done += 1
            self._show(self.done >= self.total)

    def _show(self, force=False):
        now = time.time()
        if not force and now - self.last < (0.5 if self.console else 60):
            return
        self.last = now
        pct = 100 * self.done // self.total if self.total else 100
        text = "    %s: %s/%s (%d%%)" % (self.label, format(self.done, ","),
                                        format(self.total, ","), pct)
        if self.console:
            sys.stdout.write("\r" + text + "   ")
        else:
            sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def close(self):
        if self.console:
            sys.stdout.write("\n")
            sys.stdout.flush()


def parallel(func, items, workers, label):
    """Run func over items in threads with a progress line. Failures give None."""
    results = [None] * len(items)
    if not items:
        return results
    prog = Progress(len(items), label)
    ex = cf.ThreadPoolExecutor(max_workers=max(1, workers))
    source = iter(enumerate(items))
    pending = {}

    def fill():
        while len(pending) < max(1, workers) * 3:
            try:
                i, item = next(source)
            except StopIteration:
                return
            pending[ex.submit(func, item)] = i

    try:
        fill()
        while pending:
            done, _ = cf.wait(list(pending), timeout=0.5, return_when=cf.FIRST_COMPLETED)
            for fut in done:
                i = pending.pop(fut)
                try:
                    results[i] = fut.result()
                except Exception:
                    results[i] = None
                prog.tick()
            fill()
    except KeyboardInterrupt:
        prog.close()
        ex.shutdown(wait=False, cancel_futures=True)
        raise
    ex.shutdown(wait=True)
    prog.close()
    return results


# ----------------------------------------------------------------------------
# M3U reading / writing
# ----------------------------------------------------------------------------

def parse_m3u(text):
    items, cur = [], None
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = {k.lower(): v for k, v in ATTR_RX.findall(line)}
            rest = ATTR_RX.sub("", line)
            name = rest.split(",", 1)[1].strip() if "," in rest else ""
            cur = {"attrs": attrs, "name": name, "opts": {}}
        elif line.startswith("#EXTVLCOPT:") and cur is not None:
            key, _, val = line[len("#EXTVLCOPT:"):].partition("=")
            cur["opts"][key.strip().lower()] = val.strip()
        elif line.startswith("#"):
            continue
        elif cur is not None:
            cur["url"] = line
            items.append(cur)
            cur = None
    return items


# Some players split an #EXTINF line at its first comma and others at its last,
# so no comma is ever written inside it: text gets a look-alike mark, links %2C.
SAFE_COMMA = "\u201a"


def esc_attr(v, link=False):
    s = re.sub(r"\s+", " ", str(v or "").replace('"', "'")).strip()
    return s.replace(",", "%2C") if link else s.replace(",", SAFE_COMMA)


def esc_title(v):
    return re.sub(r"\s+", " ", str(v or "")).strip().replace(",", SAFE_COMMA)


def m3u_item(name, url, group, logo="", tvg_id="", country="", languages=(),
             referrer="", user_agent="", extra=None, tvg_name=None):
    attrs = []
    if tvg_id:
        attrs.append('tvg-id="%s"' % esc_attr(tvg_id))
    attrs.append('tvg-name="%s"' % esc_attr(tvg_name or name))
    if logo:
        attrs.append('tvg-logo="%s"' % esc_attr(logo, link=True))
    if country:
        attrs.append('tvg-country="%s"' % esc_attr(country))
    if languages:
        attrs.append('tvg-language="%s"' % esc_attr(";".join(languages)))
    for k, v in (extra or {}).items():
        attrs.append('%s="%s"' % (k, esc_attr(v)))
    attrs.append('group-title="%s"' % esc_attr(group))
    lines = ["#EXTINF:-1 %s,%s" % (" ".join(attrs), esc_title(name))]
    if referrer:
        lines.append("#EXTVLCOPT:http-referrer=" + referrer)
    if user_agent:
        lines.append("#EXTVLCOPT:http-user-agent=" + user_agent)
    lines.append(url)
    return lines


def write_m3u(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("#EXTM3U\n")
        for lines in items:
            f.write("\n".join(lines) + "\n")
    return len(items)


# ----------------------------------------------------------------------------
# Live TV
# ----------------------------------------------------------------------------

def best_logos(logos):
    best = {}
    for lg in logos:
        if not isinstance(lg, dict) or not lg.get("url") or lg.get("in_use") is False:
            continue
        key = (lg.get("channel"), lg.get("feed"))
        svg = str(lg.get("format") or "").upper() == "SVG" or lg["url"].lower().endswith(".svg")
        score = (svg, "white" in as_list(lg.get("tags")), -min(int_or0(lg.get("width")), 800))
        if key not in best or score < best[key][0]:
            best[key] = (score, lg["url"])
    return {k: v[1] for k, v in best.items()}


def country_name_index():
    index = {}
    for code, name in COUNTRY_EN.items():
        index[name.lower()] = code
    index.update(NAME_ALIASES)
    return index


def code_from_group(group, index):
    g = unicodedata.normalize("NFKD", str(group or ""))
    g = "".join(ch for ch in g if not unicodedata.combining(ch))
    for text in (g, re.sub(r"\(.*?\)", " ", g)):
        t = re.sub(r"[^\w\s'&-]", " ", text).replace("_", " ").lower()
        t = re.sub(r"\s+", " ", t).strip()
        if t in index:
            return index[t]
    return ""


def code_from_id(channel_id):
    if channel_id and "." in channel_id:
        suffix = channel_id.rsplit(".", 1)[1]
        if len(suffix) == 2 and suffix.isalpha():
            return norm_cc(suffix)
    return ""


def collect_live(args, cache):
    log("[TV] Downloading the iptv-org channel database ...")
    db = {}
    for name, required in (("channels", True), ("streams", True), ("countries", False),
                           ("categories", False), ("feeds", False), ("logos", False),
                           ("blocklist", False)):
        try:
            db[name] = cached_json(cache, IPTV_API + name + ".json", 6 * HOUR) or []
        except Exception as e:
            if required:
                raise RuntimeError("iptv-org %s.json could not be downloaded (%s)" % (name, e))
            log("    (skipped %s.json: %s)" % (name, e))
            db[name] = []

    for c in db["countries"]:
        code = norm_cc(c.get("code"))
        if code:
            COUNTRY_EN[code] = c.get("name") or code
    for c in db["categories"]:
        if c.get("id"):
            CATEGORY_EN[c["id"]] = c.get("name") or c["id"]

    channels = {c["id"]: c for c in db["channels"] if isinstance(c, dict) and c.get("id")}
    blocked = {b.get("channel") for b in db["blocklist"] if isinstance(b, dict)}
    feeds, main_feed = {}, {}
    for f in db["feeds"]:
        if not isinstance(f, dict):
            continue
        feeds[(f.get("channel"), f.get("id"))] = f
        if f.get("is_main"):
            main_feed[f.get("channel")] = f.get("id")
    logos = best_logos(db["logos"])
    stats = collections.Counter()

    def channel_ok(cid):
        ch = channels.get(cid)
        if ch is None:
            return None, "skipped: channel not in database"
        if cid in blocked:
            return None, "removed: DMCA/blocklist"
        if ch.get("is_nsfw") or "xxx" in as_list(ch.get("categories")):
            return None, "removed: adult"
        if ch.get("closed"):
            return None, "removed: channel closed"
        return ch, ""

    def entry(source, cid, ch, feed_id, name, url, logo="", referrer="", ua="",
              quality="", labels=(), country=""):
        fkey = feed_id or main_feed.get(cid) or ""
        finfo = feeds.get((cid, fkey)) or {}
        if not name:
            name = (ch or {}).get("name") or cid or "Channel"
            if finfo.get("name") and not finfo.get("is_main"):
                name += " " + finfo["name"]
        langs = as_list(finfo.get("languages")) or as_list((ch or {}).get("languages"))
        cats = [c for c in as_list((ch or {}).get("categories")) if c]
        return {
            "type": "live", "source": source,
            "id": cid or "", "feed": fkey,
            "tvg_id": (cid + "@" + fkey) if (cid and fkey) else (cid or ""),
            "name": clean_text(name), "url": url,
            "country": country or norm_cc((ch or {}).get("country")),
            "categories": cats, "languages": [str(x) for x in langs],
            "logo": logo or logos.get((cid, fkey)) or logos.get((cid, None))
                    or (ch or {}).get("logo") or "",
            "referrer": referrer or "", "user_agent": ua or "",
            "quality": quality or "", "labels": [l for l in labels if l],
        }

    entries = []
    for s in db["streams"]:
        url = str(s.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            stats["skipped: bad link"] += 1
            continue
        cid = s.get("channel")
        ch = None
        if cid:
            ch, why = channel_ok(cid)
            if ch is None:
                stats[why] += 1
                continue
        elif not args.include_unlinked:
            stats["skipped: no channel info"] += 1
            continue
        labels = as_list(s.get("labels")) or as_list(s.get("label"))
        entries.append(entry("iptv-org", cid, ch, s.get("feed"), s.get("title") or s.get("name"),
                             url, referrer=s.get("referrer") or s.get("http_referrer"),
                             ua=s.get("user_agent"), quality=s.get("quality"),
                             labels=labels))
    log("    iptv-org: %s usable streams" % format(len(entries), ","))

    log("[TV] Downloading the Free-TV curated list ...")
    try:
        text = cached_text(cache, FREE_TV_M3U, 6 * HOUR)
    except Exception as e:
        log("    Free-TV list not available (%s) - continuing without it." % e)
        text = ""
    index = country_name_index()
    n_free = 0
    for it in parse_m3u(text):
        url = str(it.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")) or YOUTUBE_RX.search(url):
            stats["skipped: YouTube/bad link"] += 1
            continue
        a = it["attrs"]
        cid, _, feed_id = (a.get("tvg-id") or "").strip().partition("@")
        ch = None
        if cid:
            ch, why = channel_ok(cid)
            if ch is None and why != "skipped: channel not in database":
                stats[why] += 1
                continue
        raw = it["name"] or a.get("tvg-name") or cid
        labels = ["Geo-blocked"] if "Ⓖ" in raw else []
        country = "" if ch else (code_from_id(cid) or code_from_group(a.get("group-title"), index))
        entries.append(entry("free-tv", cid, ch, feed_id, ENCLOSED_RX.sub("", raw), url,
                             logo=a.get("tvg-logo", ""),
                             referrer=it["opts"].get("http-referrer", ""),
                             ua=it["opts"].get("http-user-agent", ""),
                             labels=labels, country=country))
        n_free += 1
    log("    Free-TV: %s channels" % format(n_free, ","))

    if args.countries:
        entries = [e for e in entries if e["country"] in args.countries]
        log("    kept %s streams from: %s" % (format(len(entries), ","),
                                             ", ".join(sorted(args.countries))))
    for why, n in sorted(stats.items()):
        log("    %s: %s" % (why, format(n, ",")))
    return pick_live(entries, args, cache)


def quality_rank(q):
    return int_or0(re.sub(r"\D", "", str(q or "")))


def pick_live(entries, args, cache):
    """One working stream per channel (or every working one with --keep-duplicates)."""
    entries.sort(key=lambda e: e["source"] != "free-tv")     # curated list wins ties
    seen, uniq = set(), []
    for e in entries:
        k = norm_url(e["url"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    groups = collections.OrderedDict()
    for e in uniq:
        key = (e["id"], e["feed"]) if e["id"] else ("url", norm_url(e["url"]))
        groups.setdefault(key, []).append(e)
    for cands in groups.values():
        cands.sort(key=lambda e: (e["source"] != "free-tv", "Geo-blocked" in e["labels"],
                                  -quality_rank(e["quality"])))
    log("    %s channels, %s stream links after removing duplicates"
        % (format(len(groups), ","), format(len(uniq), ",")))

    if args.no_check:
        if args.keep_duplicates:
            return [e for c in groups.values() for e in c]
        return [c[0] for c in groups.values()]

    checks_file = cache.dir / "stream_checks_v2.json"
    try:
        checks = json.loads(checks_file.read_text("utf-8"))
    except (OSError, ValueError):
        checks = {}
    now = time.time()

    def known(url):
        r = checks.get(url)
        return r is not None and now - r[1] < 3 * HOUR

    def test(batch, label):
        need = [e for e in batch if not known(e["url"])]
        res = parallel(lambda e: check_stream(e, args.timeout), need, args.workers, label)
        for e, status in zip(need, res):
            checks[e["url"]] = [status or "dead", now]

    def works(e):
        status = checks[e["url"]][0]
        if status == "ok":
            return True
        # Geo-blocked channels refuse servers abroad but play for viewers in their region.
        return status == "refused" and args.keep_geo and "Geo-blocked" in e["labels"]

    chosen = []
    try:
        if args.keep_duplicates:
            todo = [e for c in groups.values() for e in c]
            test(todo, "Testing live streams")
            chosen = [e for e in todo if works(e)]
        else:
            queue = {k: list(c) for k, c in groups.items()}
            rnd = 0
            while queue:
                rnd += 1
                batch = [(k, cands.pop(0)) for k, cands in queue.items()]
                test([e for _, e in batch],
                     "Testing live streams" if rnd == 1 else "Testing backup links (%d)" % rnd)
                nxt = {}
                for k, e in batch:
                    if works(e):
                        chosen.append(e)
                    elif queue[k]:
                        nxt[k] = queue[k]
                queue = nxt
    finally:
        keep = {u: r for u, r in checks.items() if now - r[1] < DAY}
        try:
            checks_file.write_text(json.dumps(keep), "utf-8")
        except OSError:
            pass
    if args.keep_duplicates:
        log("    working now: %s links for %s channels (offline ones were left out)"
            % (format(len(chosen), ","), format(len({(e["id"], e["feed"]) if e["id"] else e["url"]
                                                      for e in chosen}), ",")))
    else:
        log("    working now: %s channels (offline ones were left out)" % format(len(chosen), ","))
    return chosen


def _peek(url, headers, timeout, limit):
    safe = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    req = urllib.request.Request(safe, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        return resp.read(limit), ctype, resp.geturl()


def first_variant(text, base):
    lines = [l.strip() for l in text.splitlines()]
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith("#"):
                    return urllib.parse.urljoin(base, nxt)
    return None


REFUSED_CODES = (401, 403, 451)


def check_stream(e, timeout):
    """'ok' (plays), 'refused' (server said no to this location: 401/403/451) or 'dead'."""
    headers = {"User-Agent": e.get("user_agent") or PLAYER_UA, "Accept": "*/*"}
    if e.get("referrer"):
        headers["Referer"] = e["referrer"]
    try:
        data, ctype, final = _peek(e["url"], headers, timeout, 262144)
        head = data.lstrip(b"\xef\xbb\xbf \t\r\n")[:7].upper()
        if head == b"#EXTM3U" or "mpegurl" in ctype:
            text = data.decode("utf-8", "ignore")
            if "#EXT-X-STREAM-INF" in text:
                variant = first_variant(text, final)
                if not variant:
                    return "dead"
                data, _, _ = _peek(variant, headers, timeout, 262144)
                text = data.decode("utf-8", "ignore")
            ok = "#EXTINF" in text or "#EXT-X-TARGETDURATION" in text
            return "ok" if ok else "dead"
        if "text/html" in ctype:
            return "dead"
        return "ok" if data else "dead"
    except urllib.error.HTTPError as err:
        return "refused" if err.code in REFUSED_CODES else "dead"
    except Exception:
        return "dead"


def is_arabic(e):
    return e["country"] in ARAB_RANK or any(str(l).lower() in ARABIC_LANGS
                                            for l in e["languages"])


def live_title(e):
    name = e["name"]
    for label in e["labels"]:
        name += " [%s]" % label_text(label)
    return name


def live_item(e, group, title=None):
    return m3u_item(title or live_title(e), e["url"], group, e["logo"], e["tvg_id"],
                    e["country"], e["languages"], e["referrer"], e["user_agent"],
                    tvg_name=live_title(e))


def with_country(e):
    f = flag(e["country"])
    if f:
        return "%s %s" % (f, live_title(e))
    return "%s (%s)" % (live_title(e), e["country"]) if e["country"] else live_title(e)


def primary_category(e):
    return e["categories"][0] if e["categories"] else "undefined"


def write_live(out, live):
    by_country = sorted(live, key=lambda e: (country_key(e["country"]), sort_text(e["name"])))
    write_m3u(out / "live_by_country.m3u", [live_item(e, country_group(e["country"]))
                                            for e in by_country])

    pairs = [(c, e) for e in live for c in (e["categories"] or ["undefined"])]
    pairs.sort(key=lambda p: (category_key(p[0]), country_key(p[1]["country"]),
                              sort_text(p[1]["name"])))
    write_m3u(out / "live_by_category.m3u", [live_item(e, category_name(c), with_country(e))
                                             for c, e in pairs])

    intl = with_icon("🌍", bilingual("قنوات عربية دولية", "International Arabic"))
    arabic = [e for e in live if is_arabic(e)]
    arabic.sort(key=lambda e: ((0, ARAB_RANK[e["country"]], "") if e["country"] in ARAB_RANK
                               else (1, 0, sort_text(e["name"])), sort_text(e["name"])))
    write_m3u(out / "arabic_tv.m3u", [live_item(e, country_group(e["country"])
                                                if e["country"] in ARAB_RANK else intl)
                                      for e in arabic])

    folder = out / "by_country"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.m3u"):
        try:
            old.unlink()
        except OSError:
            pass
    per = collections.defaultdict(list)
    for e in live:
        per[e["country"] or "INT"].append(e)
    for code, items in per.items():
        items.sort(key=lambda e: (category_key(primary_category(e)), sort_text(e["name"])))
        name = "%s_%s.m3u" % (code, slug(COUNTRY_EN.get(code, "International" if code == "INT" else code)))
        write_m3u(folder / name, [live_item(e, category_name(primary_category(e))) for e in items])
    return len(arabic)


# ----------------------------------------------------------------------------
# Internet Archive (movies and series)
# ----------------------------------------------------------------------------

FORMAT_RANK = {"h.264 HD": 0, "h.264": 1, "h.264 IA": 2, "MPEG4": 3, "HiRes MPEG4": 4,
               "512Kb MPEG4": 5, "Matroska": 6, "WebM": 7, "QuickTime": 8, "Ogg Video": 9,
               "MPEG2": 10, "MPEG1": 11}
EXT_RANK = {".mp4": 0, ".m4v": 0, ".mkv": 1, ".webm": 1, ".mov": 2, ".ogv": 3,
            ".avi": 4, ".mpg": 5, ".mpeg": 5, ".flv": 6}


VARIANT_SUFFIX_RX = re.compile(
    r"(?:[._ -](?:512kb|256kb|64kb|2160p|1080p|720p|480p|360p|240p|hd|sd|ia|h264|x264|"
    r"mpeg4|mpeg2|mpeg1|archive|web|dvd))+$", re.I)


def video_root(f, name):
    """Files that are the same video in different formats share one key."""
    src = str(f.get("original") if f.get("source") == "derivative" and f.get("original") else name)
    folder, _, base = src.rpartition("/")
    stem = VARIANT_SUFFIX_RX.sub("", os.path.splitext(base)[0])
    key = re.sub(r"[\W_]+", "", stem.lower())
    return folder.lower() + "/" + (key or base.lower())


def pick_videos(files):
    """One playable file per video (prefers H.264 MP4 derivatives)."""
    groups = collections.OrderedDict()
    for f in files:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "")
        ext = os.path.splitext(name.lower())[1]
        if ext not in EXT_RANK or str(f.get("private", "")).lower() == "true":
            continue
        groups.setdefault(video_root(f, name), []).append(f)
    picks = []
    for fs in groups.values():
        best = min(fs, key=lambda f: (FORMAT_RANK.get(f.get("format", ""), 50),
                                      EXT_RANK.get(os.path.splitext(f["name"].lower())[1], 9),
                                      -int_or0(f.get("height"))))
        picks.append({
            "name": best["name"],
            "title": clean_text(next((f.get("title") for f in fs if f.get("title")), "")),
            "length": max(seconds(f.get("length")) for f in fs),
            "height": int_or0(best.get("height")),
            "format": best.get("format", ""),
        })
    picks.sort(key=lambda p: natural_key(p["name"]))
    return picks


def reduce_ia(meta):
    if not isinstance(meta, dict) or not meta or meta.get("is_dark"):
        return {"ok": False}
    md = meta.get("metadata") or {}
    if str(first(md.get("access-restricted-item"))).lower() == "true":
        return {"ok": False}
    videos = pick_videos(meta.get("files") or [])
    if not videos:
        return {"ok": False}
    return {
        "ok": True,
        "title": clean_text(first(md.get("title"))),
        "year": year_of(first(md.get("year")) or first(md.get("date"))),
        "subjects": [clean_text(s) for s in as_list(md.get("subject"))][:15],
        "language": [clean_text(s) for s in as_list(md.get("language"))][:5],
        "license": clean_text(first(md.get("licenseurl"))),
        "description": clean_text(as_list(md.get("description")), 500),
        "videos": videos,
    }


def ia_search(cache, collection):
    key = "ia-search-v1:" + collection
    hit = cache.get(key, 3 * DAY)
    if hit is not None:
        return hit
    fields = ["identifier", "title", "year", "subject", "collection", "downloads",
              "licenseurl", "language"]
    query = "collection:(%s) AND mediatype:(movies)" % collection
    items, cursor = [], None
    try:
        while True:
            params = {"q": query, "fields": ",".join(fields), "count": "5000"}
            if cursor:
                params["cursor"] = cursor
            data = json.loads(http_get(IA_SCRAPE + "?" + urllib.parse.urlencode(params),
                                       timeout=120))
            if data.get("error"):
                raise RuntimeError(str(data["error"]))
            for it in data.get("items") or []:
                if it.get("identifier"):
                    items.append({k: it.get(k) for k in fields})
            cursor = data.get("cursor")
            if not cursor:
                break
    except Exception:
        stale = cache.get(key, None, refreshable=False)
        if stale is not None:
            return stale
        raise
    cache.put(key, items)
    return items


def ia_item(cache, identifier):
    key = "ia-item-v2:" + identifier
    hit = cache.get(key, 30 * DAY, refreshable=False)
    if hit is not None:
        return hit
    try:
        meta = json.loads(http_get(IA_META + urllib.parse.quote(identifier, safe=""),
                                   timeout=60))
    except urllib.error.HTTPError as e:
        if e.code not in (403, 404, 410):
            return None
        meta = {}
    except Exception:
        return None            # network trouble: not cached, retried next run
    info = reduce_ia(meta)
    cache.put(key, info)
    return info


def gather_ia(cache, names, exclude=()):
    pool = {}
    for col in names:
        try:
            found = ia_search(cache, col)
        except Exception as e:
            log("    %s: not available right now (%s)" % (col, e))
            continue
        log("    %s: %s items" % (col, format(len(found), ",")))
        for it in found:
            iid = it["identifier"]
            if iid in exclude:
                continue
            rec = pool.get(iid)
            if rec is None:
                rec = dict(it)
                rec["cols"] = set()
                pool[iid] = rec
            rec["cols"].add(col)
            rec["cols"].update(str(c) for c in as_list(it.get("collection")))
    return pool


def movie_genre(rec, info):
    langs = " ".join(as_list(info.get("language")) + [str(x) for x in as_list(rec.get("language"))])
    if re.search(r"\b(?:arabic|ara)\b|عرب", langs, re.I):
        return "arabic"
    for col, g in COLLECTION_GENRE:
        if col in rec.get("cols", ()):
            return g
    subjects = " ".join(as_list(info.get("subjects")) +
                        [str(x) for x in as_list(rec.get("subject"))]).lower()
    for g, rx in GENRE_RX:
        if rx.search(subjects):
            return g
    return "classic"


EXTRA_RX = re.compile(r"\b(?:trailer|preview|teaser|sample|intro)\b", re.I)


def unread_note(infos):
    missed = sum(1 for i in infos if i is None)
    if missed:
        log("    %s items could not be read right now - run again later to add them."
            % format(missed, ","))


def collect_movies(args, cache, exclude):
    log("[Movies] Searching Internet Archive public-domain film collections ...")
    pool = gather_ia(cache, MOVIE_COLLECTIONS, exclude)
    items = sorted(pool.values(), key=lambda r: -int_or0(r.get("downloads")))
    if args.strict_license:
        items = [r for r in items if is_open_license(r.get("licenseurl"))]
    if args.max_movies:
        items = items[:args.max_movies]
    log("    reading %s titles (cached for next time)" % format(len(items), ","))
    infos = parallel(lambda r: ia_item(cache, r["identifier"]), items, args.ia_workers,
                     "Movie details")
    unread_note(infos)
    movies = []
    for rec, info in zip(items, infos):
        if not info or not info.get("ok"):
            continue
        if args.strict_license and not is_open_license(info.get("license") or rec.get("licenseurl")):
            continue
        iid = rec["identifier"]
        base = info.get("title") or clean_text(first(rec.get("title"))) or iid
        year = info.get("year") or year_of(rec.get("year"))
        genre = movie_genre(rec, info)
        vids = info["videos"]
        if len(vids) > 1:
            longest = max(v["length"] for v in vids)
            keep = [v for v in vids
                    if not EXTRA_RX.search(re.sub(r"[._-]+", " ", v["name"]) + " " + v["title"])
                    and not (longest >= 40 * 60 and 0 < v["length"] < 5 * 60)]
            vids = keep or vids
        for n, v in enumerate(vids, 1):
            title = base
            if len(vids) > 1:
                part = v.get("title") or "Part %d" % n
                title = base if part.lower() == base.lower() else "%s - %s" % (base, part)
            if year and str(year) not in title:
                title = "%s (%d)" % (title, year)
            g = genre
            if v["length"] and v["length"] < 40 * 60 and g not in ("animation", "documentary",
                                                                    "silent", "arabic"):
                g = "shorts"
            movies.append({
                "type": "movie", "title": title, "year": year, "genre": g, "part": n,
                "url": ia_url(iid, v["name"]), "poster": IA_IMG + iid,
                "duration": v["length"], "height": v["height"],
                "description": info.get("description", ""),
                "page": IA_DETAILS + iid, "identifier": iid,
                "license": info.get("license") or rec.get("licenseurl") or "",
                "downloads": int_or0(rec.get("downloads")),
            })
    log("    movies ready: %s" % format(len(movies), ","))
    return movies


SHOW_SUFFIX_RX = re.compile(
    r"\s*[\(\[]?\b(?:the )?(?:complete series|tv series|tv show|series|episodes?|collection|"
    r"season\s*\d+|vol(?:ume)?\.?\s*\d+)\b[\)\]]?\s*$", re.I)
EPISODE_MARK_RX = re.compile(
    r"\bS\d{1,2}\s*[.\-_ ]?\s*E\d{1,3}\b|\b\d{1,2}x\d{2,3}\b|\bSeason\s*\d+|"
    r"\bEpisode\s*#?\s*\d+|\bEp\.?\s*#?\s*\d+|#\s*\d+\b", re.I)
SEP_RX = re.compile(r"\s+[-–—|:]\s+|:\s+")
SE_RXS = [re.compile(r"\bS(\d{1,2})\s*[.\-_ ]?\s*E(\d{1,3})\b", re.I),
          re.compile(r"\b(\d{1,2})x(\d{2,3})\b"),
          re.compile(r"\bSeason\s*(\d{1,2})\D{1,12}?(?:Episode|Ep\.?)\s*#?\s*(\d{1,3})\b", re.I)]
E_RXS = [re.compile(r"\b(?:Episode|Ep\.?|Chapter)\s*#?\s*(\d{1,3})\b", re.I),
         re.compile(r"#\s*(\d{1,3})\b")]
SEASON_RX = re.compile(r"\bSeason\s*(\d{1,2})\b", re.I)
STRIP = " -–—|:.,_"


def split_show(title):
    """'Dragnet - The Big Cast' -> ('Dragnet', 'The Big Cast')."""
    t = clean_text(title)
    t = re.sub(r"[\(\[]\s*(?:18|19|20)\d\d\s*[\)\]]", "", t).strip()
    m = EPISODE_MARK_RX.search(t)
    if m and m.start() >= 2:
        show, rest = t[:m.start()], t[m.start():]
    else:
        parts = SEP_RX.split(t, maxsplit=1)
        if len(parts) == 2 and len(parts[0].strip()) >= 2:
            show, rest = parts
        else:
            show, rest = t, ""
    show = show.strip(STRIP)
    for _ in range(2):
        show = SHOW_SUFFIX_RX.sub("", show).strip(STRIP)
    return (show or t.strip(STRIP)), rest.strip(STRIP)


def parse_episode(*texts):
    """Returns (season, episode); either may be None."""
    for t in texts:
        for rx in SE_RXS:
            m = rx.search(t or "")
            if m:
                return int(m.group(1)), int(m.group(2))
    season = None
    for t in texts:
        m = SEASON_RX.search(t or "")
        if m:
            season = int(m.group(1))
            break
    for t in texts:
        for rx in E_RXS:
            m = rx.search(t or "")
            if m:
                return season, int(m.group(1))
    return season, None


def show_key(name):
    k = re.sub(r"^the\s+", "", str(name).lower().strip())
    return re.sub(r"[\W_]+", "", k)


def finalize_episodes(eps):
    eps.sort(key=lambda e: (e["season"] or 1,
                            e["episode"] if e["episode"] is not None else 10 ** 6,
                            natural_key(e["title"]), natural_key(e["file"])))
    seasons = collections.OrderedDict()
    for e in eps:
        e["season"] = e["season"] or 1
        seasons.setdefault(e["season"], []).append(e)
    for lst in seasons.values():
        nums = [e["episode"] for e in lst]
        if None in nums or len(set(nums)) != len(nums):
            for i, e in enumerate(lst, 1):
                e["episode"] = i


def strip_show_prefix(show, title):
    key = show_key(show)
    words = title.split()
    acc = ""
    for i, w in enumerate(words):
        nw = re.sub(r"[\W_]+", "", w.lower())
        if i == 0 and nw == "the":
            continue
        acc += nw
        if acc == key:
            return " ".join(words[i + 1:]).strip(STRIP)
        if not key.startswith(acc):
            break
    return title


def episode_name(show, e):
    t = strip_show_prefix(show, e["title"] or "")
    if show_key(t) == show_key(show):
        t = ""
    base = "%s S%02d E%02d" % (show, e["season"], e["episode"])
    return "%s - %s" % (base, t) if t else base


def collect_series(args, cache):
    log("[Series] Searching the Internet Archive 'Classic TV' collection ...")
    pool = gather_ia(cache, SERIES_COLLECTIONS)
    all_ids = set(pool)
    items = sorted(pool.values(), key=lambda r: -int_or0(r.get("downloads")))
    if args.strict_license:
        items = [r for r in items if is_open_license(r.get("licenseurl"))]
    if args.max_series:
        items = items[:args.max_series]
    log("    reading %s items (cached for next time)" % format(len(items), ","))
    infos = parallel(lambda r: ia_item(cache, r["identifier"]), items, args.ia_workers,
                     "Series details")
    unread_note(infos)
    shows = {}
    for rec, info in zip(items, infos):
        if not info or not info.get("ok"):
            continue
        if args.strict_license and not is_open_license(info.get("license") or rec.get("licenseurl")):
            continue
        iid = rec["identifier"]
        title = info.get("title") or clean_text(first(rec.get("title"))) or iid
        show, rest = split_show(title)
        key = show_key(show) or iid
        dl = int_or0(rec.get("downloads"))
        sh = shows.setdefault(key, {"names": collections.Counter(), "poster": IA_IMG + iid,
                                    "top": -1, "downloads": 0, "year": None, "episodes": []})
        sh["names"][show] += 1
        sh["downloads"] += dl
        if dl > sh["top"]:
            sh["top"], sh["poster"] = dl, IA_IMG + iid
        year = info.get("year") or year_of(rec.get("year"))
        if year and (sh["year"] is None or year < sh["year"]):
            sh["year"] = year
        vids = info["videos"]
        for v in vids:
            fname = re.sub(r"[._]+", " ", os.path.splitext(v["name"].split("/")[-1])[0]).strip()
            vtitle = v.get("title") or ""
            if len(vids) == 1:
                season, episode = parse_episode(title, vtitle, fname)
                ep_title = EPISODE_MARK_RX.sub("", rest).strip(STRIP) or vtitle
            else:
                season, episode = parse_episode(vtitle, fname)
                if season is None:
                    season = parse_episode(title)[0]
                ep_title = EPISODE_MARK_RX.sub("", vtitle or fname).strip(STRIP)
                if not vtitle and ep_title.islower():
                    ep_title = ep_title.title()
            sh["episodes"].append({"season": season, "episode": episode, "title": ep_title,
                                   "url": ia_url(iid, v["name"]), "duration": v["length"],
                                   "identifier": iid, "file": v["name"]})
    result = []
    for sh in shows.values():
        name = sh["names"].most_common(1)[0][0]
        finalize_episodes(sh["episodes"])
        result.append({"type": "series", "name": name, "poster": sh["poster"],
                       "year": sh["year"], "downloads": sh["downloads"],
                       "episodes": [dict(e, name=episode_name(name, e)) for e in sh["episodes"]]})
    result.sort(key=lambda s: (-s["downloads"], sort_text(s["name"])))
    log("    series ready: %s shows, %s episodes"
        % (format(len(result), ","), format(sum(len(s["episodes"]) for s in result), ",")))
    return result, all_ids


def movie_items(movies):
    ordered = sorted(movies, key=lambda m: (genre_key(m["genre"]), -m["downloads"],
                                            m["identifier"], m["part"]))
    return [m3u_item(m["title"], m["url"], genre_group(m["genre"]), m["poster"])
            for m in ordered]


def series_items(series):
    rows = []
    for s in series:
        group = with_icon("📺", s["name"])
        for e in s["episodes"]:
            rows.append(m3u_item(e["name"], e["url"], group, s["poster"]))
    return rows


# ----------------------------------------------------------------------------
# Radio
# ----------------------------------------------------------------------------

def collect_radio(args, cache):
    log("[Radio] Downloading the radio-browser directory ...")
    hosts = []
    try:
        data = cached_json(cache, RB_DISCOVERY, DAY, timeout=30)
        hosts = sorted({str(d.get("name")) for d in data if isinstance(d, dict) and d.get("name")})
    except Exception:
        pass
    hosts += [h for h in RB_FALLBACK if h not in hosts]
    stations = None
    for host in hosts:
        try:
            stations, offset = [], 0
            while True:
                q = urllib.parse.urlencode({"hidebroken": "true", "order": "clickcount",
                                            "reverse": "true", "limit": 10000,
                                            "offset": offset})
                page = cached_json(cache, "https://%s/json/stations/search?%s" % (host, q),
                                   12 * HOUR, timeout=180)
                stations.extend(page)
                if len(page) < 10000:
                    break
                offset += 10000
            break
        except Exception as e:
            log("    %s did not answer (%s), trying another server ..." % (host, e))
            stations = None
    if stations is None:
        raise RuntimeError("no radio-browser server answered")

    out, seen = [], set()
    per_country = collections.Counter()
    for st in stations:
        if not isinstance(st, dict) or str(st.get("lastcheckok", 1)) not in ("1", "True", "true"):
            continue
        url = str(st.get("url_resolved") or st.get("url") or "").strip()
        name = clean_text(st.get("name"))
        if not name or not url.lower().startswith(("http://", "https://")):
            continue
        if ADULT_RX.search(name + " " + str(st.get("tags") or "")):
            continue
        k = norm_url(url)
        if k in seen:
            continue
        cc = norm_cc(st.get("countrycode"))
        if args.countries and cc not in args.countries:
            continue
        if args.radio_per_country and per_country[cc] >= args.radio_per_country:
            continue
        seen.add(k)
        per_country[cc] += 1
        if cc and st.get("country"):
            COUNTRY_EN.setdefault(cc, str(st["country"]))
        out.append({"type": "radio", "name": name, "url": url, "country": cc,
                    "logo": str(st.get("favicon") or ""),
                    "tags": [t for t in str(st.get("tags") or "").split(",") if t][:8],
                    "languages": [l for l in str(st.get("languagecodes") or "").split(",") if l],
                    "codec": st.get("codec") or "", "bitrate": int_or0(st.get("bitrate")),
                    "clicks": int_or0(st.get("clickcount"))})
    log("    radio stations: %s from %s countries"
        % (format(len(out), ","), format(len(per_country), ",")))
    return out


def radio_items(radio):
    ordered = sorted(radio, key=lambda r: (country_key(r["country"]), -r["clicks"]))
    return [m3u_item(r["name"], r["url"], country_group(r["country"]), r["logo"],
                     country=r["country"], languages=r["languages"], extra={"radio": "true"})
            for r in ordered]


# ----------------------------------------------------------------------------
# Combined outputs
# ----------------------------------------------------------------------------

def write_catalog(out, res):
    def clean(d):
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}
    catalog = {
        "generator": "Free Media Builder " + VERSION,
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "live": [clean({k: e[k] for k in ("name", "url", "country", "categories", "languages",
                                          "logo", "tvg_id", "referrer", "user_agent",
                                          "labels", "source")})
                 for e in res["live"] or []],
        "movies": [clean({k: m[k] for k in ("title", "year", "genre", "url", "poster",
                                            "duration", "description", "page", "license")})
                   for m in res["movies"] or []],
        "series": [clean({"name": s["name"], "year": s["year"], "poster": s["poster"],
                          "episodes": [clean({k: e[k] for k in ("season", "episode", "title",
                                                                "url", "duration")})
                                       for e in s["episodes"]]})
                   for s in res["series"] or []],
        "radio": [clean({k: r[k] for k in ("name", "url", "country", "logo", "tags",
                                           "codec", "bitrate")})
                  for r in res["radio"] or []],
    }
    with open(out / "catalog.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False)


def write_summary(out, res, n_arabic, elapsed):
    live, movies = res["live"] or [], res["movies"] or []
    series, radio = res["series"] or [], res["radio"] or []
    n_eps = sum(len(s["episodes"]) for s in series)
    lines = [
        "Free Media Builder %s - built %s (took %s)" % (VERSION, time.strftime("%Y-%m-%d %H:%M"),
                                                       human_time(elapsed)),
        "",
        "Live TV channels : %s  (countries: %d, Arabic: %s)"
        % (format(len(live), ","), len({e["country"] for e in live}), format(n_arabic, ",")),
        "Movies           : %s" % format(len(movies), ","),
        "Series           : %s shows / %s episodes" % (format(len(series), ","), format(n_eps, ",")),
        "Radio stations   : %s" % format(len(radio), ","),
        "",
    ]
    if live:
        lines.append("Live TV by country:")
        counts = collections.Counter(e["country"] for e in live)
        for code in sorted(counts, key=country_key):
            label = COUNTRY_EN.get(code, code or "International")
            lines.append("  %-3s %-34s %6s" % (code or "-", label[:34], format(counts[code], ",")))
        lines.append("")
    if movies:
        lines.append("Movies by genre:")
        counts = collections.Counter(m["genre"] for m in movies)
        for g in sorted(counts, key=genre_key):
            lines.append("  %-38s %6s" % (GENRES.get(g, (g, g))[1], format(counts[g], ",")))
        lines.append("")
    lines += [
        "Sources: iptv-org.github.io, github.com/Free-TV/IPTV, archive.org, radio-browser.info",
        "Free streams come and go; run the builder again to refresh the lists.",
    ]
    (out / "summary.txt").write_text("\n".join(lines) + "\n", "utf-8")


# ----------------------------------------------------------------------------
# Sharing on the local network
# ----------------------------------------------------------------------------

class ShareHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{
        ".m3u": "audio/x-mpegurl; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    })

    def log_message(self, fmt, *args):
        log("    %s asked for %s" % (self.client_address[0], self.path))


def lan_ips():
    """Private IPv4 addresses of this PC, the one used for the internet first."""
    found = []
    for target in ("8.8.8.8", "10.255.255.255"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 80))
            found.append(s.getsockname()[0])
        except OSError:
            pass
        finally:
            s.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    private = re.compile(r"^(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)")
    out = []
    for ip in found:
        if private.match(ip) and ip not in out:
            out.append(ip)
    return out or found[:1] or ["127.0.0.1"]


def serve(out, port):
    if not (out / "all_in_one.m3u").exists() and not any(out.glob("*.m3u")):
        log("Nothing to share yet in %s - build the playlists first." % out)
        return
    handler = functools.partial(ShareHandler, directory=str(out))
    try:
        httpd = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    except OSError as e:
        log("Could not open port %d (%s). Try:  --port 8080" % (port, e))
        return
    ips = lan_ips()
    ip = ips[0]
    log("")
    log("Sharing on your Wi-Fi. Add one of these links as an M3U playlist in your player:")
    for name in ("all_in_one.m3u", "live_by_country.m3u", "arabic_tv.m3u",
                 "live_by_category.m3u", "movies.m3u", "series.m3u", "radio.m3u"):
        if (out / name).exists():
            log("    http://%s:%d/%s" % (ip, port, name))
    if len(ips) > 1:
        log("If the TV cannot open the link, this PC also answers on: " + ", ".join(ips[1:]))
        log("(use the address that starts like your phone's Wi-Fi address).")
    log("Phone / TV must be on the same Wi-Fi. If Windows asks, allow Python on private networks.")
    log("Keep this window open while watching. Press Ctrl+C to stop sharing.")
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        log("Sharing stopped.")
    finally:
        httpd.server_close()


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Build M3U playlists of legally free live TV, movies, series and radio, "
                    "sorted by country and category.")
    p.add_argument("--out", default="free_media", help="output folder (default: free_media)")
    p.add_argument("--names", choices=["ar", "en", "both"], default="ar",
                   help="language of group names (default: ar)")
    p.add_argument("--plain", action="store_true", help="no emoji flags or icons in group names")
    p.add_argument("--countries", default="",
                   help="only these countries for TV and radio, e.g. SA,AE,KW,EG")
    p.add_argument("--no-live", action="store_true", help="skip live TV")
    p.add_argument("--no-movies", action="store_true", help="skip movies")
    p.add_argument("--no-series", action="store_true", help="skip series")
    p.add_argument("--no-radio", action="store_true", help="skip radio")
    p.add_argument("--no-check", action="store_true",
                   help="do not test live streams (faster, but many links may be offline)")
    p.add_argument("--keep-geo", action="store_true",
                   help="keep channels marked geo-blocked when they refuse this location "
                        "(for lists built abroad, e.g. on GitHub's servers)")
    p.add_argument("--keep-duplicates", action="store_true",
                   help="keep every working link of a channel, not only the best one")
    p.add_argument("--include-unlinked", action="store_true",
                   help="also keep iptv-org streams that have no channel information")
    p.add_argument("--workers", type=int, default=80, help="parallel stream tests (default 80)")
    p.add_argument("--timeout", type=float, default=0,
                   help="seconds to wait for each stream test (default 8, quick mode 5)")
    p.add_argument("--ia-workers", type=int, default=12,
                   help="parallel Internet Archive requests (default 12)")
    p.add_argument("--max-movies", type=int, default=0,
                   help="only the N most watched movie items (default: all)")
    p.add_argument("--max-series", type=int, default=0,
                   help="only the N most watched series items (default: all)")
    p.add_argument("--radio-per-country", type=int, default=0,
                   help="most popular N stations per country (default: all)")
    p.add_argument("--strict-license", action="store_true",
                   help="movies/series only when the item states a public-domain or "
                        "Creative Commons license")
    p.add_argument("--quick", action="store_true",
                   help="trial run: 300 movie items, 150 series items, 40 radio stations "
                        "per country, faster stream tests")
    p.add_argument("--fail-on-error", action="store_true",
                   help="exit with an error code when a section fails (for automatic runs)")
    p.add_argument("--refresh", action="store_true",
                   help="download the source lists again instead of using the recent cache")
    p.add_argument("--serve", action="store_true",
                   help="after building, share the playlists on your Wi-Fi")
    p.add_argument("--serve-only", action="store_true",
                   help="only share playlists that were already built")
    p.add_argument("--port", type=int, default=8000, help="port for sharing (default 8000)")
    p.add_argument("--version", action="version", version="Free Media Builder " + VERSION)
    args = p.parse_args(argv)
    args.countries = {norm_cc(c) for c in re.split(r"[\s,;]+", args.countries) if c.strip()}
    if args.quick:
        args.max_movies = args.max_movies or 300
        args.max_series = args.max_series or 150
        args.radio_per_country = args.radio_per_country or 40
    args.timeout = args.timeout or (5.0 if args.quick else 8.0)
    return args


def section(title, func):
    try:
        return func()
    except KeyboardInterrupt:
        raise
    except Exception as e:
        log("")
        log("!! %s failed: %s" % (title, e))
        log("   " + traceback.format_exc().strip().splitlines()[-1])
        log("   The other sections continue. Run again later to retry.")
        return None


def run(args):
    out = Path(args.out).resolve()
    if args.serve_only:
        serve(out, args.port)
        return
    out.mkdir(parents=True, exist_ok=True)
    cache = Cache(out / ".cache", refresh=args.refresh)
    t0 = time.time()
    log("Free Media Builder %s  ->  %s" % (VERSION, out))
    log("")
    res = {"live": None, "radio": None, "series": None, "movies": None}
    n_arabic = 0
    failed = []

    if not args.no_live:
        res["live"] = section("Live TV", lambda: collect_live(args, cache))
        if res["live"] is not None:
            n_arabic = write_live(out, res["live"])
        else:
            failed.append("Live TV")
        log("")
    if not args.no_radio:
        res["radio"] = section("Radio", lambda: collect_radio(args, cache))
        if res["radio"] is not None:
            write_m3u(out / "radio.m3u", radio_items(res["radio"]))
        else:
            failed.append("Radio")
        log("")
    series_ids = set()
    if not args.no_series:
        got = section("Series", lambda: collect_series(args, cache))
        if got is not None:
            res["series"], series_ids = got
            write_m3u(out / "series.m3u", series_items(res["series"]))
        else:
            failed.append("Series")
        log("")
    if not args.no_movies:
        res["movies"] = section("Movies", lambda: collect_movies(args, cache, series_ids))
        if res["movies"] is not None:
            write_m3u(out / "movies.m3u", movie_items(res["movies"]))
        else:
            failed.append("Movies")
        log("")

    live = res["live"] or []
    combined = [live_item(e, country_group(e["country"]))
                for e in sorted(live, key=lambda e: (country_key(e["country"]), sort_text(e["name"])))]
    combined += movie_items(res["movies"] or [])
    combined += series_items(res["series"] or [])
    write_m3u(out / "all_in_one.m3u", combined)
    write_catalog(out, res)
    elapsed = time.time() - t0
    write_summary(out, res, n_arabic, elapsed)

    log("Done in %s" % human_time(elapsed))
    log("  Live TV : %s channels (%s Arabic)" % (format(len(live), ","), format(n_arabic, ",")))
    log("  Movies  : %s" % format(len(res["movies"] or []), ","))
    log("  Series  : %s shows" % format(len(res["series"] or []), ","))
    log("  Radio   : %s stations" % format(len(res["radio"] or []), ","))
    log("  Files   : %s" % out)
    if failed:
        log("  Not finished: %s (run again later)" % ", ".join(failed))
        if args.fail_on_error:
            return 2
    if args.serve:
        serve(out, args.port)
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    args = parse_args(argv)
    S.names = args.names
    S.plain = args.plain
    try:
        code = run(args) or 0
    except KeyboardInterrupt:
        log("")
        log("Stopped. Everything downloaded so far is cached - the next run continues faster.")
        return 130
    return code


if __name__ == "__main__":
    sys.exit(main())
