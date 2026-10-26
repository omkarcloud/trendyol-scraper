"""Trendyol transport: plain curl_cffi with browser-impersonated TLS. No
browser, no token, no minted cookie: the storefront is selected by four
plain cookies (storefrontId / countryCode / language / platform=web) that
any client may set; without them a non-Turkish IP is bounced to
/en/select-country. Egress: the server's own IP by default
(config.trendyol_proxy() returns None): every surface below answered 200
from a cloud server IP with no proxy, and from datacenter and Turkish
residential proxy exits too (probed 2026-10-24). A retryable failure drops
the session, so a retry rides a fresh connection (and a fresh exit when a
proxy is configured).

Upstream surfaces (all GET, all open; captured 2026-10-23):

  PAGES    www.trendyol.com (or the storefront's host / path prefix)
    PRODUCT   /<any>/<any>-p-<contentId>   server-rendered product page; the
              record is window["__envoy__SHARED_PROPS"] (product + storefront).
              An unknown id answers HTTP 404 with an empty {"product":{}}.
    HOME      /                             any page carries the navigation
              menu (window["__navigation__PROPS"].categories), the home page
              is the cheapest one that does.

  GATEWAY  apigw.trendyol.com (JSON, channelId=1)
    discovery-sfint-search-service/api/search/
      products/?q=|pathModel=&pi=&pageSize=36&sst=&prc=&wb=&wc=&mid=
                                            listings (pageSize <= 36, pi <= ~120,
                                            `total` capped at 100000; page past
                                            the end = empty products)
      aggregations?<same params>           the filter facets of that listing
    discovery-storefront-trproductgw-service/api/
      review-read/product-reviews/detailed?contentId=&page=&pageSize<=50
                                            &order=&orderBy=&rates=
      merchant-questions/content/<id>/answered?page=&size<=50&fulfilmentType=MP
                                            &fulfilmentType=ST&fulfilmentType=FT
      slicing-attributes/product-group/<groupId>/slicing-attributes?contentId=
      reco-engine/similar/<id>?page=&size=&culture=&currentScreen=pdp&brandId=
                                            &categoryId=&rootCategoryId=&webCategoryId=
                                            &rootWebCategoryId=   (+ x-agentname / x-platform headers)
      html-content/<id>                     the description HTML
      seller-store/<id>/header-information  store header (score, metrics)
      sellerstore-follow/<id>/follower-count?culture=
    discovery-sellerstore-gateway-service/api/
      search/?q=<url-encoded "sr/?pi=&pageSize=20&mid=&q=&sst=">&storefrontId=..
                                            the store's products (20 a page)
      search/aggregations?sellerId=         the store's categories and brands
      ugc/product-reviews?sellerId=&page=&size<=20
    discovery-sfint-browsing-service/
      api/top-rankings-v2/top-ranking-contents?rankingType=&categoryId=&webGenderId=
                                            &page=&pageSize=20   (100 products a list)
      top-ranking/cok-satanlar?__renderMode=stream&...
                                            a JSON {"main": "<html>"} stream whose
                                            window["__top-ranking__PROPS"] holds the
                                            ranking category tree

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  TrendyolUpstreamError  transport failure / 5xx / non-JSON    — retryable
  TrendyolBlocked        403 / 429 / Cloudflare challenge page  — retryable
  TrendyolBadRequest     upstream 400                           — never retried
  TrendyolNotFound       404 product page / unknown store       — never retried
"""
import json
import os
import re
import sys
import threading
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from trendyol.refs import BARE_PRODUCT_PATH, GATEWAY, page_base, storefront

IMPERSONATE = "chrome"
PAGE_TIMEOUT = 30      # product pages are ~450-500 KB
API_TIMEOUT = 20

SEARCH_GW = f"{GATEWAY}/discovery-sfint-search-service/api/search"
PRODUCT_GW = f"{GATEWAY}/discovery-storefront-trproductgw-service/api"
STORE_GW = f"{GATEWAY}/discovery-sellerstore-gateway-service/api"
BROWSING_GW = f"{GATEWAY}/discovery-sfint-browsing-service"

SEARCH_PAGE_SIZE = 36      # the gateway's maximum (40+ answers an empty page)
SEARCH_MAX_PAGE = 120      # pi=150 answers an empty page even with 100000 hits
REVIEWS_PAGE_SIZE = 50
QUESTIONS_PAGE_SIZE = 50
STORE_PAGE_SIZE = 20       # the store gateway ignores larger sizes
STORE_REVIEWS_PAGE_SIZE = 20
SIMILAR_PAGE_SIZE = 24
RANKINGS_PAGE_SIZE = 20    # 100 products a list = 5 pages

PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "upgrade-insecure-requests": "1",
}
API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.trendyol.com",
    "referer": "https://www.trendyol.com/",
    "x-agentname": "web",       # reco-engine refuses without these two
    "x-platform": "web",
}

_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
_CHALLENGE_MARKERS = ("just a moment", "attention required", "cf-chl", "challenge-platform",
                      "sorry, you have been blocked")


class TrendyolUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unparseable body — retryable."""


class TrendyolBlocked(TrendyolUpstreamError, Blocked):
    """403 / 429 or a Cloudflare challenge where HTML/JSON was expected — retryable."""


class TrendyolBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class TrendyolNotFound(NotFound):
    """Product / store / page does not exist — never retried."""


# One session per cheroot worker thread: a curl handle must not be shared
# across threads. The storefront cookies ride on each request (not the jar)
# so one thread can serve any country.
_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.trendyol_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _local.session = sess
    return sess


def _drop_session():
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn):
    """Run fn() under the shared retry policy (TrendyolUpstreamError only;
    NotFound / BadRequest surface immediately)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except TrendyolUpstreamError as e:
            last = e
            _drop_session()
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _cookies(country):
    sf = storefront(country)
    return {"storefrontId": sf["id"], "countryCode": sf["code"], "language": sf["language"],
            "platform": "web"}


def _accept_language(country):
    sf = storefront(country)
    return f"{sf['culture']},{sf['language']};q=0.9,en;q=0.8"


def _page_title(text):
    match = _TITLE_RE.search(text or "")
    return match.group(1).strip() if match else ""


def _looks_challenged(text):
    head = (text or "")[:4000].lower()
    return any(marker in head for marker in _CHALLENGE_MARKERS)


def _classify(resp, label):
    status = resp.status_code
    if status == 404:
        raise TrendyolNotFound(f"{label} not found")
    if status == 400:
        raise TrendyolBadRequest(resp.text[:200])
    if status in (401, 403, 429) or (status == 503 and _looks_challenged(resp.text)):
        raise TrendyolBlocked(f"HTTP {status} for {label}")
    if status != 200:
        raise TrendyolUpstreamError(f"HTTP {status} for {label}")
    return resp.text


def _get(url, label, *, country=None, page=False, params=None, timeout=None):
    headers = dict(PAGE_HEADERS if page else API_HEADERS)
    headers["accept-language"] = _accept_language(country)
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urlencode(params, doseq=True)}"

    def once():
        try:
            resp = _session().get(url, headers=headers, cookies=_cookies(country),
                                  timeout=timeout or (PAGE_TIMEOUT if page else API_TIMEOUT),
                                  allow_redirects=True)
        except Exception as e:
            raise TrendyolUpstreamError(f"request failed: {type(e).__name__}: {e}")
        text = _classify(resp, label)
        if "select-country" in (resp.url or ""):
            # the storefront cookies were ignored: never a parseable page
            raise TrendyolBlocked(f"{label}: bounced to the country picker")
        return resp, text
    return _retrying(once)


def _get_json(url, label, **kw):
    resp, text = _get(url, label, **kw)
    try:
        return json.loads(text)
    except ValueError:
        if _looks_challenged(text):
            raise TrendyolBlocked(f"{label}: challenge page instead of JSON")
        raise TrendyolUpstreamError(f"{label}: non-JSON response: {text[:120]}")


# ---- pages ---------------------------------------------------------------------------

def fetch_product_page(product_id, country=None):
    """The product page HTML (window["__envoy__SHARED_PROPS"] carries the
    record). An unknown id is a real HTTP 404."""
    url = f"{page_base(country)}{BARE_PRODUCT_PATH}{product_id}"
    _, text = _get(url, f"product {product_id}", country=country, page=True)
    if _looks_challenged(text) and "__envoy__SHARED_PROPS" not in text:
        raise TrendyolBlocked(f"product {product_id}: challenge page")
    return text


def fetch_home_page(country=None):
    """The home page HTML: the navigation menu (category tree) rides on it."""
    _, text = _get(page_base(country) + "/", "home page", country=country, page=True)
    return text


# ---- listings ------------------------------------------------------------------------

def _listing_params(query=None, path_model=None, page=1, sort=None, min_price=None,
                    max_price=None, brand=None, category=None, store=None):
    params = {"channelId": 1, "pi": page, "pageSize": SEARCH_PAGE_SIZE}
    if query:
        params["q"] = query
    if path_model:
        params["pathModel"] = path_model
    if sort:
        params["sst"] = sort
    if min_price is not None or max_price is not None:
        lo = int(min_price) if min_price is not None else 0
        params["prc"] = f"{lo}-{int(max_price)}" if max_price is not None else f"{lo}-"
    if brand:
        params["wb"] = brand
    if category:
        params["wc"] = category
    if store:
        params["mid"] = store
    return params


def fetch_listing(country=None, **kw):
    """One page of the search gateway (search term and/or a category/brand
    pathModel, filters, sort) -> the raw JSON."""
    return _get_json(f"{SEARCH_GW}/products/", "listing", country=country,
                     params=_listing_params(**kw))


def fetch_listing_filters(country=None, **kw):
    """The facets (brands, categories, price ranges, attributes) of a listing."""
    params = _listing_params(**kw)
    params.pop("pi", None)
    params.pop("pageSize", None)
    params.setdefault("pathModel", "sr")
    return _get_json(f"{SEARCH_GW}/aggregations", "listing filters", country=country, params=params)


# ---- product sub-resources -----------------------------------------------------------

def fetch_reviews(product_id, page=0, sort_by=None, order=None, rating=None, country=None):
    params = {"contentId": product_id, "page": page, "pageSize": REVIEWS_PAGE_SIZE, "channelId": 1}
    if sort_by:
        params["orderBy"] = sort_by
        params["order"] = order or "DESC"
    if rating:
        params["rates"] = rating
    return _get_json(f"{PRODUCT_GW}/review-read/product-reviews/detailed",
                     f"reviews of {product_id}", country=country, params=params)


def fetch_questions(product_id, page=0, country=None):
    params = {"page": page, "size": QUESTIONS_PAGE_SIZE, "channelId": 1, "isMobile": "false",
              "fulfilmentType": ["MP", "ST", "FT"]}
    return _get_json(f"{PRODUCT_GW}/merchant-questions/content/{product_id}/answered",
                     f"questions of {product_id}", country=country, params=params)


def fetch_variants(product_id, group_id, country=None):
    return _get_json(f"{PRODUCT_GW}/slicing-attributes/product-group/{group_id}/slicing-attributes",
                     f"variants of {product_id}", country=country,
                     params={"contentId": product_id, "channelId": 1})


def fetch_similar(product_id, ids, page=0, country=None):
    """`ids` = {brand_id, category_id, root_category_id, web_category_id,
    root_web_category_id} from the product page; the reco engine refuses
    without them."""
    sf = storefront(country)
    params = {"page": page, "size": SIMILAR_PAGE_SIZE, "culture": sf["culture"], "channelId": 1,
              "currentScreen": "pdp", "brandId": ids.get("brand_id") or 0,
              "categoryId": ids.get("category_id") or 0, "rootCategoryId": ids.get("root_category_id") or 0,
              "webCategoryId": ids.get("web_category_id") or 0,
              "rootWebCategoryId": ids.get("root_web_category_id") or 0}
    return _get_json(f"{PRODUCT_GW}/reco-engine/similar/{product_id}",
                     f"similar products of {product_id}", country=country, params=params)


def fetch_html_content(product_id, country=None):
    return _get_json(f"{PRODUCT_GW}/html-content/{product_id}", f"description of {product_id}",
                     country=country, params={"channelId": 1})


# ---- stores --------------------------------------------------------------------------

def fetch_store_header(store_id, country=None):
    return _get_json(f"{PRODUCT_GW}/seller-store/{store_id}/header-information",
                     f"store {store_id}", country=country, params={"channelId": 1})


def fetch_store_followers(store_id, country=None):
    sf = storefront(country)
    return _get_json(f"{PRODUCT_GW}/sellerstore-follow/{store_id}/follower-count",
                     f"followers of store {store_id}", country=country,
                     params={"culture": sf["culture"], "channelId": 1})


def _store_params(country):
    sf = storefront(country)
    return {"channelId": 1, "countryCode": sf["code"], "language": sf["language"],
            "storefrontId": sf["id"], "culture": sf["culture"]}


def fetch_store_aggregations(store_id, country=None):
    params = {"sellerId": store_id, **_store_params(country)}
    return _get_json(f"{STORE_GW}/search/aggregations", f"store {store_id} facets",
                     country=country, params=params)


def fetch_store_products(store_id, page=1, query=None, sort=None, country=None):
    """The store gateway wraps the listing query in one `q` param
    ("sr/?channelId=1&pi=2&pageSize=20&mid=968&q=term&sst=SCORE")."""
    inner = {"channelId": 1, "pi": page, "pageSize": STORE_PAGE_SIZE, "mid": store_id}
    if query:
        inner["q"] = query
    if sort:
        inner["sst"] = sort
    params = {"q": "sr/?" + urlencode(inner), **_store_params(country)}
    return _get_json(f"{STORE_GW}/search/", f"products of store {store_id}", country=country,
                     params=params)


def fetch_store_reviews(store_id, page=0, with_photos=False, country=None):
    params = {"sellerId": store_id, "page": page, "size": STORE_REVIEWS_PAGE_SIZE, **_store_params(country)}
    if with_photos:
        params["withImage"] = "true"
    return _get_json(f"{STORE_GW}/ugc/product-reviews", f"reviews of store {store_id}",
                     country=country, params=params)


# ---- rankings ------------------------------------------------------------------------

def fetch_rankings(category_id, ranking_type="bestSeller", page=1, gender_id=1, country=None):
    params = {"rankingType": ranking_type, "webGenderId": gender_id, "page": page,
              "pageSize": RANKINGS_PAGE_SIZE, "categoryId": category_id, "channelId": 1}
    return _get_json(f"{BROWSING_GW}/api/top-rankings-v2/top-ranking-contents",
                     f"rankings of category {category_id}", country=country, params=params)


def fetch_rankings_tree(country=None):
    """The best-sellers page fragment: a JSON {"main": "<html>"} stream."""
    sf = storefront(country)
    params = {"__renderMode": "stream", "type": "bestSeller", "webGenderId": 1, "channelId": 1,
              "storefrontId": sf["id"], "language": sf["language"], "countryCode": sf["code"],
              "tld": ".com", "subPathStrategy": "no-subpath"}
    _, text = _get(f"{BROWSING_GW}/top-ranking/cok-satanlar", "rankings tree", country=country,
                   params=params, timeout=PAGE_TIMEOUT)
    return text
