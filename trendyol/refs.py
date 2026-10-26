"""Reference resolvers + the storefront table for /trendyol/*.

ONE param per input (tripadvisor QueryOrIdField convention): every id
param also accepts the trendyol.com link of the same record. Resolvers
raise ValueError with a user-facing message (RefField turns it into a 400).

Identifier shapes (trendyol.com, captured 2026-10-23):
  * product   contentId, the number after "-p-" in
              /<brand>/<slug>-p-<contentId>?boutiqueId=..&merchantId=..
              (any slug serves the same page; the query is the listing shown)
  * store     merchantId, the number after "-m-" in /magaza/<slug>-m-<id>
              (also /magaza/profil/<slug>-m-<id>, and the merchantId= query
              of a product link)
  * brand     web brand id, the number after "-x-b" in /<slug>-x-b<id>
              (also /sr/<slug>-x-b<id>); the search gateway takes the whole
              slug as `pathModel`, and "-x-b<id>" alone resolves the same
              listing, so a bare id works too
  * category  web category id, the number after "-x-c" in /<slug>-x-c<id>
              (also gendered slugs /<slug>-x-g<gender>-c<id>); same
              pathModel rule, "-x-c<id>" alone resolves
  * ranking category  the category id of the best-sellers tree
              (/cok-satanlar, rankings/categories), also the second segment
              of /top-rankings/<name>/<id>/<type>/<gender>

Storefronts: the site is one host with a cookie-selected storefront
(storefrontId / countryCode / language). Türkiye is the default (no path
prefix); the others carry a path prefix for their pages — the language
("/de"), the culture ("/ar-qa") — or live on their own host (trendyol.ae,
trendyol.sa). The gateway JSON calls only need the cookies. Table from the
site's own storefrontList (navigation props, 2026-10-23); the entries that
share Türkiye's storefront id (GE, KZ, KG, IQ ship-from-TR variants) and
the disabled ones (GB, US, CA, IE, MT, RU, JO, LB) are left out.
"""
import re
from urllib.parse import parse_qs, urlparse

SITE = "https://www.trendyol.com"
GATEWAY = "https://apigw.trendyol.com"

# code -> (storefront id, language, culture, currency, page host, page path prefix)
_SF = {
    "TR": ("1", "tr", "tr-TR", "TRY", "www.trendyol.com", ""),
    "DE": ("2", "de", "de-DE", "EUR", "www.trendyol.com", "/de"),
    "AT": ("8", "de", "de-AT", "EUR", "www.trendyol.com", "/de"),
    "AE": ("36", "en", "en-AE", "AED", "www.trendyol.ae", ""),
    "SA": ("35", "ar", "ar-SA", "SAR", "www.trendyol.sa", ""),
    "QA": ("43", "ar", "ar-QA", "QAR", "www.trendyol.com", "/ar-qa"),
    "KW": ("48", "ar", "ar-KW", "KWD", "www.trendyol.com", "/ar-kw"),
    "OM": ("49", "ar", "ar-OM", "OMR", "www.trendyol.com", "/ar-om"),
    "BH": ("50", "ar", "ar-BH", "BHD", "www.trendyol.com", "/ar-bh"),
    "UA": ("110", "uk", "uk-UA", "UAH", "www.trendyol.com", "/uk"),
    "MD": ("111", "ro", "ro-MD", "MDL", "www.trendyol.com", "/ro"),
    "BE": ("9", "en", "en-BE", "EUR", "www.trendyol.com", "/en"),
    "BG": ("12", "bg", "bg-BG", "EUR", "www.trendyol.com", "/bg"),
    "HR": ("13", "en", "en-HR", "EUR", "www.trendyol.com", "/en"),
    "CZ": ("14", "cs", "cs-CZ", "CZK", "www.trendyol.com", "/cs"),
    "DK": ("15", "en", "en-DK", "EUR", "www.trendyol.com", "/en"),
    "EE": ("16", "en", "en-EE", "EUR", "www.trendyol.com", "/en"),
    "FI": ("17", "en", "en-FI", "EUR", "www.trendyol.com", "/en"),
    "FR": ("18", "en", "en-FR", "EUR", "www.trendyol.com", "/en"),
    "GR": ("19", "el", "el-GR", "EUR", "www.trendyol.com", "/el"),
    "HU": ("20", "hu", "hu-HU", "HUF", "www.trendyol.com", "/hu"),
    "IT": ("22", "en", "en-IT", "EUR", "www.trendyol.com", "/en"),
    "LV": ("23", "en", "en-LV", "EUR", "www.trendyol.com", "/en"),
    "LT": ("24", "en", "en-LT", "EUR", "www.trendyol.com", "/en"),
    "NL": ("26", "en", "en-NL", "EUR", "www.trendyol.com", "/en"),
    "PL": ("27", "pl", "pl-PL", "PLN", "www.trendyol.com", "/pl"),
    "PT": ("28", "en", "en-PT", "EUR", "www.trendyol.com", "/en"),
    "RO": ("29", "ro", "ro-RO", "RON", "www.trendyol.com", "/ro"),
    "SK": ("30", "sk", "sk-SK", "EUR", "www.trendyol.com", "/sk"),
    "RS": ("115", "rs", "rs-RS", "RSD", "www.trendyol.com", "/rs"),
    "SI": ("31", "en", "en-SI", "EUR", "www.trendyol.com", "/en"),
    "ES": ("32", "en", "en-ES", "EUR", "www.trendyol.com", "/en"),
    "SE": ("33", "en", "en-SE", "EUR", "www.trendyol.com", "/en"),
    "LU": ("42", "en", "en-LU", "EUR", "www.trendyol.com", "/en"),
    "AZ": ("85", "tr", "tr-AZ", "AZN", "www.trendyol.com", ""),
}

STOREFRONTS = {
    code: {"code": code, "id": sid, "language": lang, "culture": culture, "currency": cur,
           "host": host, "prefix": prefix}
    for code, (sid, lang, culture, cur, host, prefix) in _SF.items()
}
DEFAULT_COUNTRY = "TR"
COUNTRY_CODES = tuple(STOREFRONTS)


def storefront(country=None):
    return STOREFRONTS[(country or DEFAULT_COUNTRY).upper()]


# ---- link helpers -------------------------------------------------------------------

_TRENDYOL_HOST_RE = re.compile(r"(^|\.)trendyol\.(com|ae|sa)$", re.I)
_PRODUCT_RE = re.compile(r"-p-(\d{3,12})(?:[/?#]|$)")
_STORE_RE = re.compile(r"-m-(\d{1,10})(?:[/?#]|$)")
_BRAND_RE = re.compile(r"(?:^|/)([a-z0-9][a-z0-9-]*-x-b\d{1,10}|-x-b\d{1,10})(?:[/?#]|$)", re.I)
_CATEGORY_RE = re.compile(r"(?:^|/)([a-z0-9][a-z0-9-]*-x-(?:g\d+-)?c\d{1,10}|-x-c\d{1,10})(?:[/?#]|$)", re.I)
_RANKING_LINK_RE = re.compile(r"/top-rankings/[^/]+/(\d{1,10})(?:[/?#]|$)")
_DIGITS_RE = re.compile(r"^\d{1,12}$")


def _as_link(value):
    """A trendyol.com / .ae / .sa link -> its parsed URL; None when `value`
    is not a link at all; ValueError for another site's link."""
    value = (value or "").strip()
    if not value.startswith(("http://", "https://", "//", "www.trendyol.")):
        return None
    if value.startswith("//"):
        value = "https:" + value
    elif value.startswith("www."):
        value = "https://" + value
    parsed = urlparse(value)
    if not _TRENDYOL_HOST_RE.search(parsed.hostname or ""):
        raise ValueError("Must be a trendyol.com link.")
    return parsed


def resolve_product(value):
    """Bare contentId or a product link -> the contentId as a string."""
    value = (value or "").strip()
    if _DIGITS_RE.match(value):
        return value
    link = _as_link(value)
    if link is not None:
        match = _PRODUCT_RE.search(link.path)
        if match:
            return match.group(1)
        raise ValueError("Must be a trendyol.com product link (…/<name>-p-<id>).")
    raise ValueError("Must be a product id (762254881) or a trendyol.com product link.")


def resolve_store(value):
    """Bare merchant id or a store / product link -> the merchant id as a string."""
    value = (value or "").strip()
    if _DIGITS_RE.match(value):
        return value
    link = _as_link(value)
    if link is not None:
        match = _STORE_RE.search(link.path)
        if match:
            return match.group(1)
        merchant = parse_qs(link.query).get("merchantId")
        if merchant and _DIGITS_RE.match(merchant[0]):
            return merchant[0]
        raise ValueError("Must be a trendyol.com store link (/magaza/<name>-m-<id>).")
    raise ValueError("Must be a merchant id (968) or a trendyol.com store link.")


def resolve_brand(value):
    """Bare web brand id or a brand link -> the search gateway pathModel
    slug ("apple-x-b101470"; "-x-b101470" for a bare id)."""
    value = (value or "").strip()
    if _DIGITS_RE.match(value):
        return f"-x-b{value}"
    link = _as_link(value)
    if link is not None:
        match = _BRAND_RE.search(link.path)
        if match:
            return match.group(1).lower()
        raise ValueError("Must be a trendyol.com brand link (/<name>-x-b<id>).")
    match = _BRAND_RE.search("/" + value.strip("/"))
    if match and match.group(1).lower() == value.strip("/").lower():
        return value.strip("/").lower()
    raise ValueError("Must be a brand id (101470) or a trendyol.com brand link.")


def resolve_category(value):
    """Bare web category id or a category link -> the pathModel slug
    ("elbise-x-c56", "kadin-giyim-x-g1-c82"; "-x-c56" for a bare id)."""
    value = (value or "").strip()
    if _DIGITS_RE.match(value):
        return f"-x-c{value}"
    link = _as_link(value)
    if link is not None:
        match = _CATEGORY_RE.search(link.path)
        if match:
            return match.group(1).lower()
        raise ValueError("Must be a trendyol.com category link (/<name>-x-c<id>).")
    match = _CATEGORY_RE.search("/" + value.strip("/"))
    if match and match.group(1).lower() == value.strip("/").lower():
        return value.strip("/").lower()
    raise ValueError("Must be a category id (103498) or a trendyol.com category link.")


def resolve_ranking_category(value):
    """Bare ranking-tree category id or a /top-rankings/... link -> the id."""
    value = (value or "").strip()
    if _DIGITS_RE.match(value):
        return value
    link = _as_link(value)
    if link is not None:
        match = _RANKING_LINK_RE.search(link.path)
        if match:
            return match.group(1)
        raise ValueError("Must be a trendyol.com best-sellers link (/top-rankings/<name>/<id>/...).")
    raise ValueError("Must be a ranking category id (27, see rankings/categories) or a "
                     "trendyol.com best-sellers link.")


def slug_id(slug, marker):
    """"apple-x-b101470" -> "101470" for marker "b"; None when absent."""
    match = re.search(rf"-x-(?:g\d+-)?{marker}(\d+)$", slug or "")
    return match.group(1) if match else None


def page_base(country=None):
    sf = storefront(country)
    return f"https://{sf['host']}{sf['prefix']}"


def product_link(product_id, country=None, path=None):
    """The product page link; `path` is the site's own relative url when
    known (/apple/iphone-15-p-762254881?boutiqueId=..), else a bare one."""
    sf = storefront(country)
    base = page_base(country)
    if path:
        path = path if path.startswith("/") else "/" + path
        if sf["prefix"] and path.startswith(sf["prefix"] + "/"):
            return f"https://{sf['host']}{path}"   # the site's own urls already carry "/de/…"
        return base + path
    return f"{base}{BARE_PRODUCT_PATH}{product_id}"


# Any two slug segments serve the product page ("/-/-p-<id>" does NOT: the
# one-char dash slug 404s, "/x/x-p-<id>" redirects to the real slug).
BARE_PRODUCT_PATH = "/x/x-p-"


def store_link(store_id, country=None):
    return f"{page_base(country)}/magaza/x-m-{store_id}"


def absolute_link(path, country=None):
    """A site-relative href ("/elbise-x-c56", "butik/liste/1/kadin") -> absolute."""
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    return page_base(country) + (path if path.startswith("/") else "/" + path)
