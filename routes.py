"""The 14 Trendyol endpoints. Every path is served with and without the
`/trendyol` prefix, so code generated against the hosted API on RapidAPI
(paths like /products/details) runs unchanged against this server.

Each request is validated by its schema in trendyol/schemas.py (unknown or
bad params -> 400 naming the field), then answered by trendyol/api.py.
Paged endpoints return the flat shape: count / per_page / current_page /
total_pages / next / previous, then the results.
"""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, NotFound
from trendyol import api, schemas


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so a UTF-8 "Kadın" would arrive mangled)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    parts = request.urlparts
    return f"{parts.scheme}://{parts.netloc}{parts.path}?{urlencode(query)}"


def paginate(result, raw_params):
    """Lift the `pagination` block into count / per_page / current_page /
    total_pages / next / previous. A listing with no published total sets
    `has_next` and leaves total_pages null."""
    pagination = result.pop("pagination", None) or {}
    page = _as_int(pagination.get("page")) or _as_int(raw_params.get("page")) or 1
    if "has_next" in pagination:
        has_next = bool(pagination["has_next"])
        total_pages = pagination.get("total_pages")
        if total_pages is not None:
            total_pages = _as_int(total_pages, None)
    else:
        total_pages = max(_as_int(pagination.get("total_pages")), 0)
        has_next = page < total_pages
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(raw_params, page + 1 if has_next else None),
        "previous": _page_link(raw_params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(path, schema, fn, paginated):
    """Validate -> run -> map errors: bad params 400, missing record 404,
    Trendyol failures (retries exhausted / blocked) 500."""
    raw = query_dict()
    data, error = load_query(schema, raw)
    if error:
        return json_response(error, 400)
    try:
        result = fn(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"trendyol rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:
        return json_response({"error": f"trendyol {path.strip('/')} failed: {e}"}, 500)
    if paginated:
        result = paginate(result, raw)
    return json_response(result)


ENDPOINTS = [
    ("/products/details", schemas.ProductSchema, api.product_details, False),
    ("/products/search", schemas.ProductsSearchSchema, api.products_search, True),
    ("/products/reviews", schemas.ProductReviewsSchema, api.product_reviews, True),
    ("/products/questions", schemas.ProductQuestionsSchema, api.product_questions, True),
    ("/products/variants", schemas.ProductSchema, api.product_variants, False),
    ("/products/similar", schemas.ProductSimilarSchema, api.product_similar, True),
    ("/categories/list", schemas.CountrySchema, api.categories_list, False),
    ("/categories/products", schemas.CategoryProductsSchema, api.categories_products, True),
    ("/brands/products", schemas.BrandProductsSchema, api.brands_products, True),
    ("/stores/details", schemas.StoreSchema, api.store_details, False),
    ("/stores/products", schemas.StoreProductsSchema, api.store_products, True),
    ("/stores/reviews", schemas.StoreReviewsSchema, api.store_reviews, True),
    ("/rankings/categories", schemas.CountrySchema, api.rankings_categories, False),
    ("/rankings/products", schemas.RankingsSchema, api.rankings_products, True),
]


def mount(path, schema, fn, paginated):
    """Serve one endpoint at /path and /trendyol/path."""
    def handler():
        return call(path, schema, fn, paginated)
    handler.__name__ = "trendyol_" + path.strip("/").replace("/", "_")
    route(path, method="GET")(handler)
    route("/trendyol" + path, method="GET")(handler)


for _path, _schema, _fn, _paginated in ENDPOINTS:
    mount(_path, _schema, _fn, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
