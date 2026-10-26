"""Raw Trendyol HTML / JSON -> clean dicts for every /trendyol/* endpoint.
Pure functions, no I/O.

Sources (fetch.py): the product page's window["__envoy__SHARED_PROPS"]
blob, the home page's window["__navigation__PROPS"] menu, the search /
store / reviews / Q&A / rankings gateway JSON, and the best-sellers
fragment (a {"main": "<html>"} stream carrying window["__top-ranking__PROPS"]).

Value conventions (shared with the other scraper packages):
  * money    numbers; `currency` is the storefront's ISO code (the payloads
             say "TL" or a symbol — mapped through the storefront table)
  * dates    ISO 8601 UTC from the epoch-millisecond stamps
             ("2026-02-26T18:41:08Z"); the site's own "YYYY-MM-DD" kept
  * images   full-size CDN links (the "/mnresize/<w>/<h>/" thumbnail
             segment removed; relative "/ty.../1_org_zoom.jpg" paths
             prefixed with the CDN host)
  * keys     snake_case; `link` not `url`; booleans as questions; absent
             values are null

Fixtures captured 2026-10-23/24 (trendyol/fixtures/): an electronics
product page with 8 other sellers (iPhone 15), a fashion product page with
size variants and a single seller, the not-found page, search pages
(iphone / elbise / no-result), filters, reviews (with photos, sizes,
fit), Q&A, variants, similar products, store header / followers / facets
/ products / reviews, best-seller rankings and the ranking category tree
— each with its unknown-id counterpart where the gateway has one.
"""
import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from trendyol.refs import (absolute_link, product_link, slug_id, store_link, storefront)

CDN = "https://cdn.dsmcdn.com"

_RESIZE_RE = re.compile(r"/mnresize/[^/]*/[^/]*/")
_PERCENT_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_CANONICAL_RE = re.compile(r'<link\s+rel="canonical"\s+href="([^"]+)"', re.I)
_WEB_URL_ID_RE = re.compile(r"-x-(?:g(\d+)-)?c(\d+)$")
_COLLECTION_ID_RE = re.compile(r"-y-s(\d+)$")


# ---- value helpers --------------------------------------------------------------------

def _clean(value):
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = " ".join(str(value).split())
    return text or None


def _num(value):
    """2029.1 / "2.029,10" / "477,48" / "519" -> float; None otherwise."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        # "2.029,10" (tr) vs "2,029.10" (en): the last separator is the decimal one
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif text.count(".") >= 1 and all(len(g) == 3 for g in text.lstrip("-").split(".")[1:]):
        # Turkish thousands dots ("59.799", "1.250.000"); a rating "4.4" keeps its decimal
        text = text.replace(".", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _int(value):
    number = _num(value)
    return int(number) if isinstance(number, (int, float)) else None


def _percent(value):
    """"-%8" / "%12" / 8 -> 8 (an absolute integer percentage)."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return abs(int(value)) if value else 0
    match = _PERCENT_RE.search(str(value))
    return abs(int(float(match.group(0).replace(",", ".")))) if match else None


def _iso_ms(value):
    """Epoch milliseconds -> "2026-02-26T18:41:08Z"."""
    number = _num(value)
    if not number or number < 1e11:
        return None
    try:
        return datetime.fromtimestamp(number / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


_TR_MONTHS = {"ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5, "haziran": 6,
              "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11, "kasim": 11,
              "aralık": 12, "aralik": 12}
_TR_DATE_RE = re.compile(r"^(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})$")


def _iso_date(value):
    """"2026-11-30T23:00:00" / "2026-10-23" / "23 Ekim 2026" -> "2026-10-23" (the site's own local date)."""
    text = _clean(value)
    if not text:
        return None
    if re.match(r"\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    match = _TR_DATE_RE.match(text)
    if match and match.group(2).lower() in _TR_MONTHS:
        return f"{int(match.group(3)):04d}-{_TR_MONTHS[match.group(2).lower()]:02d}-{int(match.group(1)):02d}"
    return None


def _image(url):
    """Full-size CDN link: thumbnail resize segment dropped, relative paths absolutized."""
    text = _clean(url)
    if not text:
        return None
    if text.startswith("/"):
        text = CDN + text
    return _RESIZE_RE.sub("/", text)


def _images(urls):
    return [link for link in (_image(u) for u in (urls or []) if isinstance(u, str)) if link]


def _currency(payload_currency, country):
    """3-letter codes pass through; "TL" / "₺" / symbols -> the storefront's currency."""
    code = _clean(payload_currency)
    if isinstance(code, str) and len(code) == 3 and code.isalpha():
        return code.upper()
    return storefront(country)["currency"]


def _price_pair(current, original, currency, discount=None):
    current = _num(current)
    original = _num(original)
    if original is None or (current is not None and original < current):
        original = current
    if discount is None and current is not None and original and original > current:
        discount = int(round((original - current) * 100 / original))
    return {"current": current, "original": original, "discount_rate": discount if (discount or 0) > 0 else None,
            "currency": currency}


def _rating(score):
    score = score if isinstance(score, dict) else {}
    average = _num(score.get("averageRating"))
    return {"average": round(average, 2) if isinstance(average, float) else average,
            "count": _int(score.get("totalCount") if score.get("totalCount") is not None else score.get("totalComments"))}


def extract_props(html, name):
    """window["<name>"]={...} -> the parsed object (brace-matched, string-aware); None when absent."""
    marker = f'window["{name}"]='
    start = (html or "").find(marker)
    if start < 0:
        return None
    i = start + len(marker)
    if i >= len(html) or html[i] != "{":
        return None
    depth, k, in_string = 0, i, False
    while k < len(html):
        char = html[k]
        if in_string:
            if char == "\\":
                k += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[i:k + 1])
                except ValueError:
                    return None
        k += 1
    return None


def _html_text(html):
    """Description HTML -> readable text (block elements separated by newlines)."""
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "iframe", "noscript"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    lines = []
    for block in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "span", "b", "strong"]):
        if block.find(["p", "li", "div", "h1", "h2", "h3", "h4", "tr"]):
            continue
        text = " ".join(block.get_text(" ", strip=True).split())
        if text and (not lines or lines[-1] != text):
            lines.append(text)
    text = "\n".join(lines) if lines else " ".join(soup.get_text(" ", strip=True).split())
    return text or None


# ---- product cards (search / category / brand / store listings) ----------------------

def _badge_rank(badges):
    """badges.topRankingBadge {type: BEST_SELLER, title: "4"} -> {"type": "best_seller", "rank": 4}."""
    badges = badges if isinstance(badges, dict) else {}
    top = badges.get("topRankingBadge")
    if isinstance(top, dict) and top.get("type"):
        return {"type": str(top["type"]).lower(), "rank": _int(top.get("title"))}
    return None


def parse_product_card(p, country=None):
    """One product of the search / store gateway listings."""
    if not isinstance(p, dict):
        return None
    price = p.get("price") if isinstance(p.get("price"), dict) else {}
    binary = p.get("binaryPrice") if isinstance(p.get("binaryPrice"), dict) else {}
    single = p.get("singlePrice") if isinstance(p.get("singlePrice"), dict) else {}
    currency = _currency(price.get("currency") or single.get("currency"), country)
    current = price.get("discountedPrice")
    if current is None:
        current = single.get("salePriceNumeric", price.get("current"))
    original = single.get("strikethroughPriceNumeric")
    if original is None:
        original = _num(binary.get("strikethroughPrice"))
    if original is None:
        original = max(_num(price.get("originalPrice")) or 0, _num(price.get("current")) or 0) or None
    discount = _percent(binary.get("discountPercentage"))
    pricing = _price_pair(current, original, currency, discount)
    pricing["discount_type"] = _clean(binary.get("discountType"))
    promotion = p.get("singlePromotion") if isinstance(p.get("singlePromotion"), dict) else None
    social = {}
    for item in p.get("socialProof") or []:
        if isinstance(item, dict) and item.get("key"):
            social[re.sub(r"(?<!^)(?=[A-Z])", "_", str(item["key"])).lower()] = _clean(item.get("value"))
    attributes = [{"name": _clean(a.get("attributeName")), "value": _clean(a.get("attributeValueName"))}
                  for a in ((p.get("productCardAttributes") or {}).get("attributes") or []) if isinstance(a, dict)]
    stock_bar = p.get("tagStockBar") if isinstance(p.get("tagStockBar"), dict) else {}
    advert = p.get("advert") if isinstance(p.get("advert"), dict) else {}
    brands = p.get("webBrands") or []
    web_brand = brands[0] if brands and isinstance(brands[0], dict) else {}
    category = p.get("category") if isinstance(p.get("category"), dict) else {}
    content_id = p.get("contentId") or p.get("id")
    return {
        "id": _int(content_id),
        "name": _clean(p.get("name")),
        "link": product_link(content_id, country, p.get("url")),
        "brand": {"id": _int(web_brand.get("id") or p.get("brandId")), "name": _clean(p.get("brand") or web_brand.get("name"))},
        "category": {"id": _int(category.get("id")), "name": _clean(category.get("name"))},
        "merchant_id": _int(p.get("merchantId")),
        "boutique_id": _int(p.get("boutiqueId") or p.get("campaignId")),
        "listing_id": _clean(p.get("listingId")),
        "item_number": _int(p.get("itemNumber")),
        "group_id": _int(p.get("groupId")),
        "variant": {"value": _clean(p.get("variantValue")), "is_one_size": bool(p.get("isOneSize"))},
        "price": pricing,
        "rating": _rating(p.get("ratingScore")),
        "image": _image(p.get("image")),
        "images": _images(p.get("images")),
        "is_free_cargo": bool(p.get("freeCargo")),
        "is_rush_delivery": bool(p.get("rushDelivery")),
        "is_same_day_shipping": bool(p.get("sameDayShipping")),
        "is_next_day_delivery": bool(p.get("nextDayDelivery")),
        "is_sold_out": bool(stock_bar.get("isSoldOut")),
        "is_ad": bool(advert.get("advertId")) or (p.get("advertType") not in (None, "", "DEFAULT")),
        "is_official_seller": bool(p.get("hasOfficialSellerBadge")),
        "has_review_photo": bool(p.get("hasReviewPhoto")),
        "has_coupon": bool(p.get("hasCollectableCoupon")),
        "has_video": bool(p.get("hasVideo")) if "hasVideo" in p else None,
        "is_sexual_content": bool(p.get("isSexualContent")),
        "top_ranking": _badge_rank(p.get("badges")),
        "promotion": ({"id": _int(promotion.get("id")), "name": _clean(promotion.get("name")),
                       "end_date": _iso_date(promotion.get("promotionEndDate"))} if promotion else None),
        "promotions": [{"id": _int(x.get("id")), "name": _clean(x.get("name")), "short_name": _clean(x.get("shortName"))}
                       for x in (p.get("promotions") or []) if isinstance(x, dict)],
        "social_proof": social or None,
        "attributes": attributes,
    }


def parse_listing(payload, country=None, page_size=36, max_page=120):
    """The search gateway page -> {title, query, total_count, products, pagination…}."""
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    data = data if isinstance(data, dict) else {}
    products = [c for c in (parse_product_card(p, country) for p in data.get("products") or []) if c]
    total = _int(data.get("total"))
    spelling = data.get("spellingCorrection") if isinstance(data.get("spellingCorrection"), dict) else {}
    resolved = data.get("resolvedQuery") if isinstance(data.get("resolvedQuery"), dict) else {}
    total_pages = None
    if total is not None:
        total_pages = min(-(-total // page_size), max_page)
    return {
        "title": _clean(data.get("title")),
        "search_strategy": _clean(data.get("appliedSearchStrategy")),
        "corrected_query": _clean(spelling.get("correctedQuery") or spelling.get("suggestion")) if spelling.get("applied") else None,
        "resolved_query": _clean(resolved.get("searchKey")),
        "sort": _clean(data.get("sortValue")),
        "total_count": total,
        "is_total_estimated": _clean(str(data.get("roughTotal") or "")).endswith("+") if data.get("roughTotal") else False,
        "total_pages": total_pages,
        "page": _int(data.get("pageIndex")),
        "products": products,
    }


def _filter_value(v):
    if not isinstance(v, dict):
        return None
    out = {"id": _clean(v.get("id")), "name": _clean(v.get("text") or v.get("name")), "count": _int(v.get("count")),
           "is_selected": bool(v.get("selected") or v.get("filtered"))}
    for key in ("min", "max", "minPrice", "maxPrice"):
        if v.get(key) is not None:
            out[re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()] = _num(v.get(key))
    return out


def parse_filters(payload, max_values=50):
    """The aggregations call -> the facets of a listing (values capped per facet)."""
    facets = []
    for agg in (payload.get("aggregation") or []) if isinstance(payload, dict) else []:
        if not isinstance(agg, dict):
            continue
        values = [x for x in (_filter_value(v) for v in agg.get("values") or []) if x]
        field = _clean(agg.get("filterField"))
        key = _clean(agg.get("filterKey"))
        facets.append({
            "name": _clean(agg.get("title")),
            "field": field,
            "key": key if field == "attributes" else None,
            "type": _clean(agg.get("filterType")),
            "is_multiple": agg.get("aggregationSelectionType") == "MULTIPLE",
            "total_count": _int(agg.get("totalCount")),
            "values_count": len(values),
            "values": values[:max_values],
        })
    quick = [{"name": _clean(q.get("text") or q.get("title")), "field": _clean(q.get("filterField")), "id": _clean(q.get("id"))}
             for q in (payload.get("quickFilters") or []) if isinstance(q, dict)] if isinstance(payload, dict) else []
    return {"filters": facets, "quick_filters": quick}


# ---- the product page ---------------------------------------------------------------

def _money(value):
    """{"value": 60000, "text": "60.000 TL"} / 60000 -> 60000."""
    if isinstance(value, dict):
        return _num(value.get("value"))
    return _num(value)


def _listing_price(price, country):
    price = price if isinstance(price, dict) else {}
    currency = _currency(price.get("currency"), country)
    current = _money(price.get("discountedPrice"))
    selling = _money(price.get("sellingPrice"))
    original = _money(price.get("originalPrice"))
    candidates = [x for x in (selling, original, current) if x is not None]
    out = _price_pair(current, max(candidates) if candidates else None, currency,
                      _percent(price.get("discountPercentage")) or None)
    out["selling"] = selling
    out["recommended_retail"] = _money(price.get("rrp")) if isinstance(price.get("rrp"), dict) and price["rrp"].get("value") else None
    return out


def _merchant(m, country):
    m = m if isinstance(m, dict) else {}
    score = m.get("sellerScore") if isinstance(m.get("sellerScore"), dict) else {}
    return {
        "id": _int(m.get("id")),
        "name": _clean(m.get("name")),
        "link": store_link(m.get("id"), country) if m.get("id") else None,
        "official_name": _clean(m.get("officialName")),
        "score": _num(score.get("value")),
        "city": _clean(m.get("cityName")),
        "country": _clean(m.get("countryName")),
        "address": _clean(m.get("address")),
        "tax_number": _clean(m.get("taxNumber")),
        "tax_office": _clean(m.get("taxOffice")),
        "registration_number": _clean(m.get("registrationNumber")),
        "email": _clean(m.get("registeredEmailAddress")),
        "logo": _image(m.get("logoUrl")),
        "is_corporate_invoice_applicable": bool(m.get("corporateInvoiceApplicable")),
        "is_cash_on_delivery_eligible": bool(m.get("codEligible")),
    }


def _other_merchant(m, country):
    m = m if isinstance(m, dict) else {}
    score = m.get("sellerScore") if isinstance(m.get("sellerScore"), dict) else {}
    variants = [v for v in (m.get("variants") or []) if isinstance(v, dict)]
    price = m.get("price") if isinstance(m.get("price"), dict) else (variants[0].get("price") if variants else {})
    return {
        "id": _int(m.get("id")),
        "name": _clean(m.get("name")),
        "link": store_link(m.get("id"), country) if m.get("id") else None,
        "score": _num(score.get("value")),
        "price": _listing_price(price, country),
        "is_free_cargo": bool(m.get("freeCargo")),
        "is_rush_delivery": bool(m.get("rushDelivery")),
        "is_corporate_invoice_applicable": bool(m.get("corporateInvoiceApplicable")),
        "variants": [{"item_number": _int(v.get("itemNumber")), "value": _clean(v.get("value")) or None,
                      "is_in_stock": bool(v.get("inStock", v.get("sellable", True))),
                      "price": _listing_price(v.get("price"), country)["current"] if isinstance(v.get("price"), dict) else None}
                     for v in variants],
        "promotions": [_clean(x.get("name")) for x in (m.get("promotions") or []) if isinstance(x, dict) and x.get("name")],
        "product_link": product_link(None, country, m.get("url")) if m.get("url") else None,
    }


def _promotion(x):
    return {"id": _int(x.get("id")), "name": _clean(x.get("name")), "short_name": _clean(x.get("shortName")),
            "type": _clean(x.get("promotionDiscountType")), "end_date": _iso_date(x.get("promotionEndDate")),
            "is_applied": bool(x.get("isApplied"))}


def parse_product_page(html, product_id=None, country=None):
    """The product page HTML -> the full product record, or None when the
    page carries no product (the not-found page serves {"product": {}})."""
    props = extract_props(html, "__envoy__SHARED_PROPS") or {}
    p = props.get("product") if isinstance(props.get("product"), dict) else {}
    if not p.get("id"):
        return None
    listing = p.get("merchantListing") if isinstance(p.get("merchantListing"), dict) else {}
    winner = listing.get("winnerVariant") if isinstance(listing.get("winnerVariant"), dict) else {}
    campaign = listing.get("campaign") if isinstance(listing.get("campaign"), dict) else {}
    brand = p.get("brand") if isinstance(p.get("brand"), dict) else {}
    web_brand = p.get("webBrand") if isinstance(p.get("webBrand"), dict) else {}
    category = p.get("category") if isinstance(p.get("category"), dict) else {}
    web_category = p.get("webCategory") if isinstance(p.get("webCategory"), dict) else {}
    gender = p.get("webGender") if isinstance(p.get("webGender"), dict) else (p.get("gender") if isinstance(p.get("gender"), dict) else {})
    unit = p.get("businessUnitData") if isinstance(p.get("businessUnitData"), dict) else {}
    rating = p.get("ratingScore") if isinstance(p.get("ratingScore"), dict) else {}
    translation = p.get("englishTranslation") if isinstance(p.get("englishTranslation"), dict) else {}
    variant_attr = next((a for a in (winner.get("variantAttributes") or []) if isinstance(a, dict)), {})
    category_tree = [{"id": _int(c.get("id")), "name": _clean(c.get("name"))} for c in (p.get("categoryTree") or []) if isinstance(c, dict)]
    web_tree = sorted([c for c in (p.get("webCategoryTree") or []) if isinstance(c, dict)], key=lambda c: c.get("level") or 0)
    canonical = _CANONICAL_RE.search(html or "")
    pid = _int(p.get("id") or product_id)
    promotions = [_promotion(x) for x in (listing.get("promotions") or []) + (listing.get("filteredPromotions") or []) if isinstance(x, dict)]
    seen, deduped = set(), []
    for promo in promotions:
        if promo["id"] not in seen:
            seen.add(promo["id"])
            deduped.append(promo)
    return {
        "id": pid,
        "name": _clean(p.get("name")),
        "link": canonical.group(1) if canonical else product_link(pid, country),
        "product_code": _clean(p.get("productCode")),
        "group_id": _int(p.get("productGroupId")),
        "brand": {"id": _int(web_brand.get("id") or brand.get("id")), "name": _clean(brand.get("name") or web_brand.get("name")),
                  "link": absolute_link(web_brand.get("url"), country)},
        "category": {"id": _int(web_category.get("id") or category.get("id")), "name": _clean(web_category.get("name") or category.get("name")),
                     "hierarchy": _clean(category.get("hierarchy"))},
        "category_tree": category_tree,
        "gender": _clean(gender.get("name")) or None,
        "images": _images(p.get("images")),
        "price": _listing_price(winner.get("price"), country),
        "rating": {"average": round(_num(rating.get("averageRating")), 2) if isinstance(_num(rating.get("averageRating")), float) else _num(rating.get("averageRating")),
                   "count": _int(rating.get("totalCount")), "comment_count": _int(rating.get("commentCount"))},
        "favorite_count": _int(p.get("favoriteCount")),
        "is_in_stock": bool(p.get("inStock")),
        "stock": {"is_running_out": bool(winner.get("isRunningOut")), "running_out_quantity": _int(winner.get("runningOutQuantity")) or None,
                  "max_sale_limit": _int(winner.get("maxSaleLimit")) or None, "is_sellable": bool(winner.get("sellable", p.get("inStock")))},
        "listing_id": _clean(winner.get("listingId")),
        "item_number": _int(winner.get("itemNumber")),
        "barcode": _clean(winner.get("barcode")),
        "fulfilment_type": _clean(winner.get("fulfilmentType")),
        "is_free_cargo": bool(winner.get("freeCargo")),
        "rush_delivery_hours": _int(winner.get("rushDeliveryDuration")) or None,
        "is_flash_sale": bool(winner.get("isFlash")),
        "is_refundable": bool(p.get("isRefundable")),
        "is_digital_goods": bool(unit.get("isDigitalGoods")),
        "is_sexual_content": bool(p.get("isSexualContent") or unit.get("isSexualContent")),
        "tax_rate": _num(p.get("tax")),
        "max_installment": _int(p.get("maxInstallment")),
        "origin_country": _clean(listing.get("originInfo")) or None,
        "variant_attribute": _clean(variant_attr.get("attributeName")) or None,
        "variants": [{"item_number": _int(v.get("itemNumber")), "value": _clean(v.get("value")) or None,
                      "barcode": _clean(v.get("barcode")), "is_in_stock": bool(v.get("inStock")),
                      "is_selected": bool(v.get("isSelected")), "price": _money(v.get("price"))}
                     for v in (p.get("variants") or []) if isinstance(v, dict)],
        "slicing_attributes": {str(k): _clean(v) for k, v in (p.get("slicingAttributes") or {}).items()} or None,
        "attributes": [{"name": _clean((a.get("key") or {}).get("name")), "value": _clean((a.get("value") or {}).get("name")),
                        "description": _clean(a.get("description")) or None, "is_highlighted": bool(a.get("isStarred"))}
                       for a in (p.get("attributes") or []) if isinstance(a, dict)],
        "merchant": _merchant(listing.get("merchant"), country),
        "other_merchants": [_other_merchant(m, country) for m in (listing.get("otherMerchants") or []) if isinstance(m, dict)],
        "campaign": {"id": _int(campaign.get("id")), "name": _clean(campaign.get("name")),
                     "start_date": _iso_date(campaign.get("startDate")), "end_date": _iso_date(campaign.get("endDate"))} if campaign else None,
        "promotions": deduped,
        "cross_promotions": [_promotion(x) for x in (listing.get("crossPromotions") or []) if isinstance(x, dict)],
        "top_rankings": [{"type": _clean(r.get("name")), "rank": _int(r.get("order"))} for r in (p.get("categoryTopRankings") or []) if isinstance(r, dict)],
        "english": {"name": _clean(translation.get("productName")), "brand": _clean(translation.get("brandName")),
                    "color": _clean(translation.get("webColorName"))} if translation else None,
        "has_html_description": bool(p.get("hasHtmlContent")),
        # the ids the reco engine wants (products/similar); not part of the public record
        "_reco_ids": {"brand_id": _int(brand.get("id")), "category_id": _int(category.get("id")),
                      "root_category_id": category_tree[0]["id"] if category_tree else None,
                      "web_category_id": _int(web_category.get("id")),
                      "root_web_category_id": _int(web_tree[0].get("id")) if web_tree else None},
    }


def parse_description(payload):
    """html-content -> {"text", "html"}; an icecat iframe shell has no text."""
    html = payload.get("content") if isinstance(payload, dict) else None
    html = html if isinstance(html, str) and html.strip() else None
    return {"text": _html_text(html), "html": html}


# ---- reviews / questions -----------------------------------------------------------

def _media(files):
    out = []
    for f in files or []:
        if not isinstance(f, dict):
            continue
        out.append({"id": _int(f.get("id")), "type": (_clean(f.get("mediaType")) or "IMAGE").lower(),
                    "link": _image(f.get("url")), "thumbnail": _clean(f.get("thumbnailUrl"))})
    return out


def _review(r):
    seller = r.get("seller") if isinstance(r.get("seller"), dict) else {}
    variant = r.get("productVariant") if isinstance(r.get("productVariant"), dict) else {}
    return {
        "id": _int(r.get("id")),
        "rating": _int(r.get("rate")),
        "comment": _clean(r.get("comment")),
        "user_name": _clean(r.get("userFullName")),   # the site masks it ("S** A**") unless the reviewer opted in
        "is_verified_purchase": bool(r.get("trusted")),
        "is_elite_member": bool(r.get("isElite")),
        "is_influencer": bool(r.get("isInfluencer")),
        "likes_count": _int(r.get("likesCount")) or 0,
        "language": _clean(r.get("language")),
        "created_at": _iso_ms(r.get("createdAt")),
        "updated_at": _iso_ms(r.get("lastModifiedAt")),
        "seller": {"id": _int(seller.get("id")), "name": _clean(seller.get("name"))} if seller else None,
        "size": _clean(r.get("productSize")) or (_clean(variant.get("value")) if variant else None),
        "variant": {"attribute": _clean(variant.get("attribute")), "value": _clean(variant.get("value"))} if variant else None,
        "reviewer_height_cm": _int(r.get("height")),
        "reviewer_weight_kg": _int(r.get("weight")),
        "fit": _clean(r.get("productFit")),
        "media": _media(r.get("mediaFiles")),
    }


def parse_reviews(payload, page_size=50):
    """review-read/product-reviews/detailed -> summary + reviews."""
    result = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    reviews = [_review(r) for r in (result.get("reviews") or []) if isinstance(r, dict)]
    tags = []
    for t in summary.get("tags") or []:
        if not isinstance(t, dict):
            continue
        sentiment = t.get("sentiment") if isinstance(t.get("sentiment"), dict) else None
        tags.append({"name": _clean(t.get("name")), "count": _int(t.get("count")),
                     "sentiment": {"positive": _int(sentiment.get("positive")) or 0, "negative": _int(sentiment.get("negative")) or 0,
                                   "positive_ratio": _int(sentiment.get("ratio"))} if sentiment else None})
    total_pages = _int(summary.get("totalPages"))
    return {
        "summary": {
            "average_rating": _num(summary.get("averageRating")),
            "rating_count": _int(summary.get("totalRatingCount")),
            "comment_count": _int(summary.get("totalCommentCount")),
            "photo_review_count": _int(summary.get("totalImageReviewCount")),
            "rating_distribution": [{"rating": _int(x.get("rate")), "count": _int(x.get("count"))}
                                    for x in (summary.get("ratingCounts") or []) if isinstance(x, dict)],
            "tags": tags,
            "sizes": [{"name": _clean(x.get("name")), "count": _int(x.get("count"))} for x in (summary.get("productSizes") or []) if isinstance(x, dict)],
            "reviewer_heights": [{"range": _clean(x.get("name")), "count": _int(x.get("count"))} for x in (summary.get("heightTags") or []) if isinstance(x, dict)],
            "reviewer_weights": [{"range": _clean(x.get("name")), "count": _int(x.get("count"))} for x in (summary.get("weightTags") or []) if isinstance(x, dict)],
            "countries": [_clean(c.get("country")) for c in (summary.get("countries") or []) if isinstance(c, dict) and c.get("reviewsExist")],
            "ai_summary": _clean(result.get("aiSummary")),
        },
        "total_pages": total_pages,
        "reviews": reviews,
    }


def parse_questions(payload):
    """merchant-questions/.../answered -> topic tags + answered questions."""
    block = payload.get("questions") if isinstance(payload, dict) and isinstance(payload.get("questions"), dict) else {}
    summary = payload.get("contentSummary") if isinstance(payload, dict) and isinstance(payload.get("contentSummary"), dict) else {}
    questions = []
    for q in block.get("content") or []:
        if not isinstance(q, dict):
            continue
        answer = q.get("answer") if isinstance(q.get("answer"), dict) else {}
        questions.append({
            "id": _int(q.get("id")),
            "question": _clean(q.get("text")),
            "asked_at": _iso_ms(q.get("creationDate")),
            "user_name": _clean(q.get("userName")),
            "is_verified_purchase": bool(q.get("trusted")),
            "seller": {"id": _int(q.get("sellerId")), "name": _clean(q.get("sellerName"))},
            "answer": _clean(answer.get("text")),
            "answered_in": _clean(q.get("answeredDateMessage")),
            "is_translated": bool(q.get("isTranslated") or answer.get("isTranslated")),
        })
    return {
        "total_count": _int(summary.get("totalCount") if summary.get("totalCount") is not None else block.get("totalElements")),
        "total_pages": _int(block.get("totalPages")),
        "topics": [{"key": _clean(t.get("tagKey")), "name": _clean(t.get("name")), "count": _int(t.get("count"))}
                   for t in (summary.get("tags") or []) if isinstance(t, dict)],
        "questions": questions,
    }


# ---- variants / similar --------------------------------------------------------------

def parse_variants(payload, country=None):
    """slicing-attributes -> the sibling products per attribute (colour, memory, …)."""
    groups = []
    for g in (payload.get("result") or []) if isinstance(payload, dict) else []:
        if not isinstance(g, dict):
            continue
        values = []
        for v in g.get("values") or []:
            if not isinstance(v, dict):
                continue
            values.append({
                "name": _clean(v.get("name")),
                "is_selected": bool(v.get("isSelected")),
                "products": [{"id": _int(x.get("id")), "name": _clean(x.get("name")),
                              "link": product_link(x.get("id"), country, x.get("pageUrl")),
                              "image": _image(x.get("previewImageUrl") or x.get("imageUrl")),
                              "merchant_id": _int(x.get("merchantId")), "boutique_id": _int(x.get("campaignId")),
                              "is_selected": bool(x.get("isSelected"))}
                             for x in (v.get("products") or []) if isinstance(x, dict)],
            })
        groups.append({"type": _clean(g.get("type")), "name": _clean(g.get("title")),
                       "display_type": _clean(g.get("displayType")), "values": values})
    return groups


def parse_similar(payload, country=None):
    """reco-engine/similar -> {title, total_count, is_last_page, products}."""
    result = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else {}
    products = []
    for c in result.get("contents") or []:
        if not isinstance(c, dict):
            continue
        brand = c.get("brand") if isinstance(c.get("brand"), dict) else {}
        web_brand = c.get("webBrand") if isinstance(c.get("webBrand"), dict) else {}
        category = c.get("webCategory") if isinstance(c.get("webCategory"), dict) else (c.get("category") if isinstance(c.get("category"), dict) else {})
        social = c.get("socialProof") if isinstance(c.get("socialProof"), dict) else {}
        badge = c.get("productBadge") if isinstance(c.get("productBadge"), dict) else {}
        products.append({
            "id": _int(c.get("id")),
            "name": _clean(c.get("name")),
            "link": product_link(c.get("id"), country, c.get("url")),
            "brand": {"id": _int(web_brand.get("id") or brand.get("id")), "name": _clean(brand.get("name") or web_brand.get("name"))},
            "category": {"id": _int(category.get("id")), "name": _clean(category.get("name"))},
            "merchant_id": _int(c.get("merchantId")),
            "listing_id": _clean(c.get("listingId")),
            "price": _listing_price(c.get("price"), country),
            "rating": _rating(c.get("ratingScore")),
            "favorite_count": _int(social.get("favoriteCount")),
            "images": _images(c.get("images")),
            "is_free_cargo": bool(c.get("freeCargo")),
            "is_rush_delivery": bool(c.get("isRushDelivery")),
            "is_running_out": bool(c.get("isRunningOut")),
            "is_verified_seller": bool(c.get("isVerifiedSeller")),
            "top_ranking": {"type": _clean(badge.get("key")), "rank": _int(badge.get("value"))} if badge.get("key") == "categoryTopRanking" else None,
            "color_variants": [{"id": _int(v.get("id")), "name": _clean(v.get("name")), "link": product_link(v.get("id"), country, v.get("url")),
                                "image": _image(v.get("image")), "price": _money((v.get("price") or {}).get("discountedPrice")) if isinstance(v.get("price"), dict) else None}
                               for v in (c.get("colorVariants") or []) if isinstance(v, dict)],
            "attributes": [{"name": _clean((a.get("key") or {}).get("name")), "value": _clean((a.get("value") or {}).get("name"))}
                           for a in (c.get("attributes") or []) if isinstance(a, dict)],
            "promotions": [_clean(x.get("name")) for x in (c.get("promotions") or []) if isinstance(x, dict) and x.get("name")],
        })
    return {"title": _clean(result.get("title")), "total_count": _int(result.get("totalCount")),
            "is_last_page": bool(result.get("isLastPage", True)) if result else True, "products": products}


# ---- stores --------------------------------------------------------------------------

def parse_store_header(payload, country=None):
    """seller-store/<id>/header-information -> the store record, or None when unknown."""
    result = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else None
    if not result or not result.get("id"):
        return None
    metrics = {m.get("id"): m for m in (result.get("sellerMetrics") or []) if isinstance(m, dict) and m.get("id")}

    def metric(key):
        return _clean((metrics.get(key) or {}).get("value")) or None

    ranking = result.get("rankingInfo") if isinstance(result.get("rankingInfo"), dict) else {}
    return {
        "id": _int(result.get("id")),
        "name": _clean(result.get("name")),
        "link": _clean(result.get("storeUrl")) or store_link(result.get("id"), country),
        "official_name": _clean(result.get("officialName")),
        "score": _num(result.get("score")),
        "logo": _image(result.get("icon")),
        "product_count": _int(result.get("productCount")),
        "badges": [_clean(b.get("url")) for b in (result.get("badges") or []) if isinstance(b, dict) and b.get("url")],
        "ranking": {"type": _clean(ranking.get("type")), "text": " ".join(x for x in (_clean(ranking.get("textbold")), _clean(ranking.get("text"))) if x) or None} if ranking else None,
        "time_on_trendyol": metric("activationDate"),
        "location": metric("location"),
        "is_corporate_invoice_applicable": metric("corporateInvoice") is not None,
        "average_shipping_time": metric("deliveryTime"),
        "question_response_time": metric("averageResponseTime"),
        "average_product_rating": _num(metric("avgProductScore")),
        "average_seller_rating": _num(metric("avgSellerReviewScore")),
    }


def parse_store_followers(payload):
    result = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else {}
    return {"count": _int(result.get("count")), "text": _clean(result.get("text"))}


def parse_store_facets(payload):
    """search/aggregations?sellerId= -> the store's categories and brands with counts."""
    payload = payload if isinstance(payload, dict) else {}
    return {
        "categories": [{"id": _int(c.get("id")), "name": _clean(c.get("text")), "count": _int(c.get("count")),
                        "image": _image(c.get("imageUrl")), "is_leaf": bool(c.get("leaf"))}
                       for c in (payload.get("categories") or []) if isinstance(c, dict)],
        "brands": [{"id": _int(b.get("id")), "name": _clean(b.get("text")), "count": _int(b.get("count"))}
                   for b in (payload.get("brands") or []) if isinstance(b, dict)],
    }


def parse_store_products(payload, country=None, page_size=20):
    """The store gateway listing -> {products, has_next}."""
    payload = payload if isinstance(payload, dict) else {}
    products = [c for c in (parse_product_card(p, country) for p in payload.get("products") or []) if c]
    links = payload.get("_links") if isinstance(payload.get("_links"), dict) else {}
    has_next = bool(links.get("next")) if "next" in links else len(products) >= page_size
    return {"products": products, "has_next": has_next and bool(products), "page": _int(payload.get("pageIndex"))}


def _store_review(r, country):
    product = r.get("product") if isinstance(r.get("product"), dict) else {}
    rating = product.get("rating") if isinstance(product.get("rating"), dict) else {}
    price = product.get("price") if isinstance(product.get("price"), dict) else {}
    return {
        "id": _int(r.get("id")),
        "rating": _int(r.get("rate")),
        "title": _clean(r.get("commentTitle")),
        "comment": _clean(r.get("comment")),
        "user_name": _clean(r.get("userFullName")),
        "user_type": _clean(r.get("userType")),
        "is_verified_purchase": bool(r.get("trusted")),
        "likes_count": _int(r.get("reviewLikeCount")) or 0,
        "language": _clean(r.get("language")),
        "created_at": _iso_ms(r.get("createdDate")) or _iso_date(r.get("commentDateISOType")),
        "media": _media(r.get("mediaFiles")),
        "product": {
            "id": _int(product.get("id")),
            "name": _clean(product.get("title")),
            "brand": _clean(product.get("brand")),
            "link": product_link(product.get("id"), country, product.get("link")),
            "image": _image(product.get("image")),
            "rating": {"average": round(_num(rating.get("average")), 2) if isinstance(_num(rating.get("average")), float) else _num(rating.get("average")),
                       "count": _int(rating.get("total"))},
            "price": _price_pair(price.get("discountedPrice", price.get("current")), price.get("original", price.get("old")),
                                 _currency(price.get("currency"), country)),
            "is_in_stock": bool(product.get("inStock")),
        } if product else None,
    }


def _store_photo_review(r, country):
    """One row of the withImage=true shape (one row per photo; reviewId is the review)."""
    item = {**r, "id": r.get("reviewId", r.get("id")), "userFullName": r.get("userName"),
            "mediaFiles": [r["mediaFile"]] if isinstance(r.get("mediaFile"), dict) else [],
            "language": r.get("reviewLanguage")}
    out = _store_review(item, country)
    out["created_at"] = _iso_date(r.get("date"))
    out["photo_id"] = _int(r.get("id"))
    return out


def parse_store_reviews(payload, country=None):
    """ugc/product-reviews -> summary + the reviews across the store's products.
    With withImage=true the gateway answers {size, totalPages, page,
    totalElements, images[]} instead: one row per photo, no summary."""
    payload = payload if isinstance(payload, dict) else {}
    if isinstance(payload.get("images"), list) and "productReviews" not in payload:
        return {
            "summary": None,
            "total_count": _int(payload.get("totalElements")),
            "total_pages": _int(payload.get("totalPages")),
            "reviews": [_store_photo_review(r, country) for r in payload["images"] if isinstance(r, dict)],
        }
    summary = payload.get("contentSummary") if isinstance(payload.get("contentSummary"), dict) else {}
    block = payload.get("productReviews") if isinstance(payload.get("productReviews"), dict) else {}
    return {
        "summary": {
            "average_rating": _num(summary.get("averageRating")),
            "rating_count": _int(summary.get("totalRatingCount")),
            "comment_count": _int(summary.get("totalCommentCount")),
            "photo_review_count": _int(summary.get("totalImageReviewCount")),
            "rating_distribution": [{"rating": _int(x.get("rate")), "count": _int(x.get("count")), "comment_count": _int(x.get("commentCount"))}
                                    for x in (summary.get("ratingCounts") or []) if isinstance(x, dict)],
            "description": _clean(summary.get("description")),
        },
        "total_count": _int(block.get("totalElements")),
        "total_pages": _int(block.get("totalPages")),
        "reviews": [_store_review(r, country) for r in (block.get("content") or []) if isinstance(r, dict)],
    }


# ---- rankings ------------------------------------------------------------------------

def parse_rankings(payload, country=None):
    """top-rankings-v2/top-ranking-contents -> {category, total_count, products}."""
    payload = payload if isinstance(payload, dict) else {}
    info = payload.get("categoryInfo") if isinstance(payload.get("categoryInfo"), dict) else {}
    products = []
    for p in payload.get("products") or []:
        if not isinstance(p, dict):
            continue
        brand = p.get("brandInfo") if isinstance(p.get("brandInfo"), dict) else {}
        price = p.get("sanitizedPrice") if isinstance(p.get("sanitizedPrice"), dict) else {}
        strip = p.get("stripBadge") if isinstance(p.get("stripBadge"), dict) else {}
        badges = p.get("badges") if isinstance(p.get("badges"), dict) else {}
        winner = p.get("winnerVariant") if isinstance(p.get("winnerVariant"), dict) else {}
        unit = price.get("unitPrice") if isinstance(price.get("unitPrice"), dict) else {}
        pricing = _price_pair(_money(price.get("finalPrice")), _money(price.get("strikeThroughPrice")), _currency(price.get("currency"), country))
        pricing["unit_price"] = {"value": _num(unit.get("value")), "unit": _clean(unit.get("unitSymbol"))} if unit.get("value") is not None else None
        pricing["type"] = _clean(price.get("type"))
        products.append({
            "id": _int(p.get("id")),
            "name": _clean(p.get("name")),
            "link": product_link(p.get("id"), country, p.get("url")),
            "brand": {"id": _int(brand.get("id")), "name": _clean(brand.get("name"))},
            "merchant_id": _int(p.get("merchantId")),
            "boutique_id": _int(p.get("boutiqueId")) or None,
            "price": pricing,
            "rating": _rating(p.get("ratingScore") or p.get("rating")),
            "image": _image(p.get("imageUrl") or p.get("image")),
            "images": _images(p.get("images")),
            "is_in_stock": bool(p.get("inStock")),
            "is_running_out": bool(p.get("isRunningOut")),
            "is_free_cargo": bool(badges.get("freeCargo") or winner.get("freeCargo")),
            "is_fast_delivery": bool(badges.get("fastDelivery")),
            "is_flash_sale": bool(p.get("isFlash")),
            "has_review_photo": bool(p.get("hasReviewPhoto")),
            "rank_change": {"label": _clean(strip.get("label")), "places": _int(strip.get("value"))} if strip.get("label") else None,
            "price_change": _clean(p.get("priceChange")),
            "promotions": [_clean(x.get("name")) for x in (p.get("promotions") or []) if isinstance(x, dict) and x.get("name")],
            "english_name": _clean((p.get("englishTranslation") or {}).get("productName")) if isinstance(p.get("englishTranslation"), dict) else None,
        })
    return {"category": {"id": _int(info.get("id")), "name": _clean(info.get("name")), "path": _clean(info.get("path"))} if info else None,
            "total_count": _int(payload.get("totalCount")), "products": products}


def _ranking_node(node, country):
    if not isinstance(node, dict):
        return None
    children = [c for c in (_ranking_node(x, country) for x in node.get("children") or []) if c]
    slug = (_clean(node.get("url")) or "").strip("/")
    link = absolute_link(f"/top-rankings/{slug}/{node.get('id')}/bestSeller/1", country) if slug and node.get("id") is not None else None
    return {"id": _int(node.get("id")), "name": _clean(node.get("name")),
            "link": link, "level": _int(node.get("level")),
            "parent_id": _int(node.get("parentId")), "ranking_types": [t for t in (node.get("topRankingRelations") or []) if isinstance(t, str)],
            "children": children}


def parse_rankings_tree(text, country=None):
    """The best-sellers fragment ({"main": "<html>"}) -> ranking types + the category tree."""
    html = text or ""
    try:
        stream = json.loads(html)
        if isinstance(stream, dict) and isinstance(stream.get("main"), str):
            html = stream["main"]
    except ValueError:
        pass
    props = extract_props(html, "__top-ranking__PROPS") or {}
    data = props.get("data") if isinstance(props.get("data"), dict) else {}
    tree = data.get("CategoryTreeData") if isinstance(data.get("CategoryTreeData"), dict) else {}
    orders = data.get("TopRankingOrdersData") if isinstance(data.get("TopRankingOrdersData"), dict) else {}
    return {
        "ranking_types": [{"type": _clean(o.get("type")), "name": _clean(o.get("displayName"))}
                          for o in sorted((x for x in orders.get("rankingTypeOrders") or [] if isinstance(x, dict)), key=lambda x: x.get("order") or 0)],
        "categories": [c for c in (_ranking_node(n, country) for n in tree.get("categories") or []) if c],
    }


# ---- navigation menu (categories/list) ----------------------------------------------

def _menu_node(node, country, section_id=None):
    if not isinstance(node, dict):
        return None
    web_url = _clean(node.get("webUrl")) or ""
    match = _WEB_URL_ID_RE.search(web_url)
    collection = _COLLECTION_ID_RE.search(web_url)
    if node.get("id") is not None and not match:
        kind, cid, gender = "section", _int(node.get("id")), None
    elif match:
        kind, cid, gender = "category", _int(match.group(2)), _int(match.group(1))
    elif collection:
        kind, cid, gender = "collection", _int(collection.group(1)), None
    else:
        kind, cid, gender = ("search" if web_url.startswith("sr") else "page"), None, None
    return {"id": cid, "name": _clean(node.get("title")), "type": kind, "gender_id": gender,
            "link": absolute_link(web_url, country) if web_url else None,
            "children": [c for c in (_menu_node(x, country, section_id) for x in node.get("children") or []) if c]}


def parse_navigation(html, country=None):
    """Any page's window["__navigation__PROPS"] -> the sections and the category menu."""
    props = extract_props(html, "__navigation__PROPS") or {}
    return {
        "sections": [{"id": _int(s.get("id")), "name": _clean(s.get("title")), "link": absolute_link(s.get("url"), country)}
                     for s in (props.get("sections") or []) if isinstance(s, dict)],
        "categories": [c for c in (_menu_node(n, country) for n in props.get("categories") or []) if c],
    }
