"""The /trendyol/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs). Every function caches through
cache.cached_call keyed on its validated params.

products/details, products/variants and products/similar slice ONE cached
product-page parse (trendyol.product, keyed on product + country): the
page carries the record, the product-group id the variants call needs and
the category/brand ids the reco engine needs, so hitting all three on a
product costs one page fetch.
"""
from cache import cached_call
from trendyol import cache_config as ttl
from trendyol import fetch, parsers
from trendyol.fetch import (RANKINGS_PAGE_SIZE, REVIEWS_PAGE_SIZE, QUESTIONS_PAGE_SIZE, SEARCH_MAX_PAGE,
                            SEARCH_PAGE_SIZE, SIMILAR_PAGE_SIZE, STORE_PAGE_SIZE, STORE_REVIEWS_PAGE_SIZE,
                            TrendyolNotFound)
from trendyol.refs import slug_id, storefront


def _pages(total_count, page_size, cap=None):
    if total_count is None:
        return None
    pages = -(-total_count // page_size)
    return min(pages, cap) if cap else pages


def _storefront_block(country):
    sf = storefront(country)
    return {"code": sf["code"], "currency": sf["currency"], "language": sf["language"]}


# ---- listings (products/search, categories/products, brands/products) -------------

def _listing(country, page, sort, min_price, max_price, query=None, path_model=None,
             brand=None, category=None):
    kw = dict(query=query, path_model=path_model, page=page, sort=sort, min_price=min_price,
              max_price=max_price, brand=brand, category=category)
    data = parsers.parse_listing(fetch.fetch_listing(country=country, **kw), country,
                                 SEARCH_PAGE_SIZE, SEARCH_MAX_PAGE)
    filters = parsers.parse_filters(fetch.fetch_listing_filters(country=country, **kw))
    total = data.pop("total_count")
    total_pages = data.pop("total_pages")
    data.pop("page", None)
    products = data.pop("products")
    return {
        **data,
        "storefront": _storefront_block(country),
        **filters,
        "products": products,
        "pagination": {"page": page, "items_per_page": SEARCH_PAGE_SIZE,
                       "total_pages": total_pages, "total_count": total},
    }


def _brand_filter(brand):
    """A brand ref ("apple-x-b101470" / "-x-b101470") -> the `wb` id."""
    return slug_id(brand, "b") if brand else None


def _category_filter(category):
    return slug_id(category, "c") if category else None


def _products_search(query, sort, min_price, max_price, page, country, brand, category):
    return _listing(country, page, sort, min_price, max_price, query=query,
                    brand=_brand_filter(brand), category=_category_filter(category))


def products_search(**data):
    return cached_call("trendyol.products_search", data, _products_search, ttl.LISTING_CACHE)


def _categories_products(category, sort, min_price, max_price, page, country, brand):
    return {"category": {"id": int(slug_id(category, "c")) if slug_id(category, "c") else None, "slug": category},
            **_listing(country, page, sort, min_price, max_price, path_model=category, brand=_brand_filter(brand))}


def categories_products(**data):
    return cached_call("trendyol.categories_products", data, _categories_products, ttl.LISTING_CACHE)


def _brands_products(brand, sort, min_price, max_price, page, country, category):
    return {"brand": {"id": int(slug_id(brand, "b")) if slug_id(brand, "b") else None, "slug": brand},
            **_listing(country, page, sort, min_price, max_price, path_model=brand, category=_category_filter(category))}


def brands_products(**data):
    return cached_call("trendyol.brands_products", data, _brands_products, ttl.LISTING_CACHE)


# ---- the shared product record ----------------------------------------------------

def _product_record(product, country):
    record = parsers.parse_product_page(fetch.fetch_product_page(product, country), product, country)
    if record is None:
        raise TrendyolNotFound(f"product {product} not found")
    return record


def _record(product, country):
    return cached_call("trendyol.product", {"product": product, "country": country}, _product_record,
                       ttl.PRODUCT_CACHE)


def _identity(record):
    return {"id": record["id"], "name": record["name"], "link": record["link"]}


def _product_details(product, country):
    record = dict(_record(product, country))
    reco_ids = record.pop("_reco_ids", None)
    description = None
    if record.get("has_html_description"):
        try:
            description = parsers.parse_description(fetch.fetch_html_content(product, country))
        except TrendyolNotFound:
            description = None
    record.pop("has_html_description", None)
    record["description"] = description["text"] if description else None
    record["description_html"] = description["html"] if description else None
    record["storefront"] = _storefront_block(country)
    return record


def product_details(**data):
    return cached_call("trendyol.product_details", data, _product_details, ttl.PRODUCT_CACHE)


def _product_variants(product, country):
    record = _record(product, country)
    groups = parsers.parse_variants(fetch.fetch_variants(product, record["group_id"], country), country) \
        if record.get("group_id") else []
    return {**_identity(record), "group_id": record.get("group_id"),
            "variant_attribute": record.get("variant_attribute"), "variants": record.get("variants"),
            "sibling_products": groups}


def product_variants(**data):
    return cached_call("trendyol.product_variants", data, _product_variants, ttl.PRODUCT_CACHE)


def _product_similar(product, country, page):
    record = _record(product, country)
    payload = fetch.fetch_similar(product, record.get("_reco_ids") or {}, page - 1, country)
    data = parsers.parse_similar(payload, country)
    products = data.pop("products")
    return {
        **_identity(record),
        "title": data["title"],
        "storefront": _storefront_block(country),
        "products": products,
        "pagination": {"page": page, "items_per_page": SIMILAR_PAGE_SIZE,
                       "has_next": not data["is_last_page"] and bool(products),
                       "total_pages": _pages(data["total_count"], SIMILAR_PAGE_SIZE),
                       "total_count": data["total_count"]},
    }


def product_similar(**data):
    return cached_call("trendyol.product_similar", data, _product_similar, ttl.SIMILAR_CACHE)


# ---- reviews / questions ---------------------------------------------------------

def _product_reviews(product, country, sort, rating, page):
    sort_by, order = sort if sort else (None, None)
    payload = fetch.fetch_reviews(product, page - 1, sort_by, order, rating, country)
    data = parsers.parse_reviews(payload, REVIEWS_PAGE_SIZE)
    reviews = data.pop("reviews")
    summary = data["summary"]
    if not reviews and not summary.get("rating_count") and page == 1:
        # the gateway answers an empty summary for an unknown id and for a
        # product with no reviews alike: tell them apart through the page
        _record(product, country)
    total_pages = data.get("total_pages")
    return {
        "product": {"id": int(product)},
        "summary": summary,
        "reviews": reviews,
        "pagination": {"page": page, "items_per_page": REVIEWS_PAGE_SIZE,
                       "total_pages": total_pages,
                       "total_count": (summary.get("comment_count") if not rating else None)},
    }


def product_reviews(**data):
    return cached_call("trendyol.product_reviews", data, _product_reviews, ttl.REVIEWS_CACHE)


def _product_questions(product, country, page):
    data = parsers.parse_questions(fetch.fetch_questions(product, page - 1, country))
    questions = data.pop("questions")
    if page == 1 and not questions:
        _record(product, country)   # unknown id -> 404 (same empty shape as "no questions yet")
    return {
        "product": {"id": int(product)},
        "topics": data["topics"],
        "questions": questions,
        "pagination": {"page": page, "items_per_page": QUESTIONS_PAGE_SIZE,
                       "total_pages": data["total_pages"], "total_count": data["total_count"]},
    }


def product_questions(**data):
    return cached_call("trendyol.product_questions", data, _product_questions, ttl.QUESTIONS_CACHE)


# ---- stores ----------------------------------------------------------------------

def _store_header(store, country):
    header = parsers.parse_store_header(fetch.fetch_store_header(store, country), country)
    if header is None:
        raise TrendyolNotFound(f"store {store} not found")
    return header


def _header(store, country):
    return cached_call("trendyol.store", {"store": store, "country": country}, _store_header, ttl.STORE_CACHE)


def _store_details(store, country):
    header = dict(_header(store, country))
    followers = parsers.parse_store_followers(fetch.fetch_store_followers(store, country))
    facets = parsers.parse_store_facets(fetch.fetch_store_aggregations(store, country))
    header["follower_count"] = followers["count"]
    header["follower_count_text"] = followers["text"]
    header["top_categories"] = facets["categories"]
    header["top_brands"] = facets["brands"]
    header["storefront"] = _storefront_block(country)
    return header


def store_details(**data):
    return cached_call("trendyol.store_details", data, _store_details, ttl.STORE_CACHE)


def _store_products(store, country, query, sort, page):
    header = _header(store, country)
    data = parsers.parse_store_products(fetch.fetch_store_products(store, page, query, sort, country),
                                        country, STORE_PAGE_SIZE)
    total = header.get("product_count") if not query else None
    return {
        "store": {"id": header["id"], "name": header["name"], "link": header["link"]},
        "query": query,
        "storefront": _storefront_block(country),
        "products": data["products"],
        "pagination": {"page": page, "items_per_page": STORE_PAGE_SIZE, "has_next": data["has_next"],
                       "total_pages": _pages(total, STORE_PAGE_SIZE), "total_count": total},
    }


def store_products(**data):
    return cached_call("trendyol.store_products", data, _store_products, ttl.LISTING_CACHE)


def _store_reviews(store, country, with_photos, page):
    header = _header(store, country)
    data = parsers.parse_store_reviews(fetch.fetch_store_reviews(store, page - 1, with_photos, country), country)
    reviews = data.pop("reviews")
    return {
        "store": {"id": header["id"], "name": header["name"], "link": header["link"]},
        "summary": data["summary"],
        "reviews": reviews,
        "pagination": {"page": page, "items_per_page": STORE_REVIEWS_PAGE_SIZE,
                       "total_pages": data["total_pages"], "total_count": data["total_count"]},
    }


def store_reviews(**data):
    return cached_call("trendyol.store_reviews", data, _store_reviews, ttl.REVIEWS_CACHE)


# ---- categories / rankings ------------------------------------------------------

def _categories_list(country):
    data = parsers.parse_navigation(fetch.fetch_home_page(country), country)
    return {"storefront": _storefront_block(country), **data}


def categories_list(**data):
    return cached_call("trendyol.categories_list", data, _categories_list, ttl.TREE_CACHE)


def _rankings_categories(country):
    return {"storefront": _storefront_block(country),
            **parsers.parse_rankings_tree(fetch.fetch_rankings_tree(country), country)}


def rankings_categories(**data):
    return cached_call("trendyol.rankings_categories", data, _rankings_categories, ttl.TREE_CACHE)


def _rankings_products(category, type, gender, page, country):
    payload = fetch.fetch_rankings(category, type, page, gender, country)
    data = parsers.parse_rankings(payload, country)
    if page == 1 and not data["products"] and payload.get("isSuccess") is not False and not data["category"]:
        raise TrendyolNotFound(f"ranking category {category} not found")
    products = data.pop("products")
    total = data["total_count"]
    return {
        "category": data["category"],
        "ranking_type": type,
        "gender": "women" if gender == 1 else "men",
        "storefront": _storefront_block(country),
        "products": products,
        "pagination": {"page": page, "items_per_page": RANKINGS_PAGE_SIZE,
                       "total_pages": _pages(total, RANKINGS_PAGE_SIZE), "total_count": total},
    }


def rankings_products(**data):
    return cached_call("trendyol.rankings_products", data, _rankings_products, ttl.RANKINGS_CACHE)
