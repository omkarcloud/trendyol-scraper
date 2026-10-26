"""Offline tests for the /trendyol/* request schemas and reference resolvers.

    python -m pytest trendyol/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trendyol import refs, schemas  # noqa: E402

IPHONE = "https://www.trendyol.com/apple/iphone-15-128-gb-mavi-p-762254881?boutiqueId=689770&merchantId=968"


# ---- refs -------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("762254881", "762254881"),
    (" 762254881 ", "762254881"),
    (IPHONE, "762254881"),
    ("https://www.trendyol.com/apple/iphone-15-128-gb-mavi-p-762254881/yorumlar", "762254881"),
    ("www.trendyol.com/x/y-p-123456", "123456"),
    ("https://www.trendyol.ae/moda-benna/cotton-dress-p-1162737615?boutiqueId=61", "1162737615"),
    ("//www.trendyol.com/de/trendyol-collection/hose-p-863132996", "863132996"),
])
def test_resolve_product(value, expected):
    assert refs.resolve_product(value) == expected


@pytest.mark.parametrize("value", ["", "iphone", "p-123", "https://www.amazon.com/dp/B0/-p-123",
                                   "https://www.trendyol.com/magaza/trendyol-m-968"])
def test_resolve_product_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_product(value)


@pytest.mark.parametrize("value,expected", [
    ("968", "968"),
    ("https://www.trendyol.com/magaza/trendyol-m-968", "968"),
    ("https://www.trendyol.com/magaza/profil/trendyol-m-968?sst=0", "968"),
    (IPHONE, "968"),
])
def test_resolve_store(value, expected):
    assert refs.resolve_store(value) == expected


def test_resolve_store_rejects():
    for value in ("", "trendyol", "https://www.trendyol.com/sr?q=x", "https://example.com/magaza/x-m-968"):
        with pytest.raises(ValueError):
            refs.resolve_store(value)


@pytest.mark.parametrize("value,expected", [
    ("101470", "-x-b101470"),
    ("https://www.trendyol.com/apple-x-b101470", "apple-x-b101470"),
    ("https://www.trendyol.com/sr/apple-x-b1617?pi=2", "apple-x-b1617"),
    ("Apple-x-b101470", "apple-x-b101470"),
])
def test_resolve_brand(value, expected):
    assert refs.resolve_brand(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("103498", "-x-c103498"),
    ("https://www.trendyol.com/cep-telefonu-x-c103498?pi=2", "cep-telefonu-x-c103498"),
    ("https://www.trendyol.com/kadin-giyim-x-g1-c82", "kadin-giyim-x-g1-c82"),
    ("elbise-x-c56", "elbise-x-c56"),
])
def test_resolve_category(value, expected):
    assert refs.resolve_category(value) == expected


def test_resolve_brand_category_reject():
    for value in ("", "apple", "https://www.trendyol.com/sr?q=apple"):
        with pytest.raises(ValueError):
            refs.resolve_brand(value)
        with pytest.raises(ValueError):
            refs.resolve_category(value)
    with pytest.raises(ValueError):
        refs.resolve_category("https://www.trendyol.com/apple-x-b101470")


@pytest.mark.parametrize("value,expected", [
    ("27", "27"),
    ("https://www.trendyol.com/top-rankings/aksesuar/27/bestSeller/1", "27"),
])
def test_resolve_ranking_category(value, expected):
    assert refs.resolve_ranking_category(value) == expected


def test_slug_ids_and_links():
    assert refs.slug_id("apple-x-b101470", "b") == "101470"
    assert refs.slug_id("-x-b101470", "b") == "101470"
    assert refs.slug_id("kadin-giyim-x-g1-c82", "c") == "82"
    assert refs.slug_id("apple-x-b101470", "c") is None
    assert refs.product_link("1", None) == "https://www.trendyol.com/x/x-p-1"
    assert refs.product_link("1", "de", "/de/x/y-p-1?merchantId=2") == "https://www.trendyol.com/de/x/y-p-1?merchantId=2"
    assert refs.page_base("AE") == "https://www.trendyol.ae"
    assert refs.page_base("QA") == "https://www.trendyol.com/ar-qa"
    assert refs.store_link(968) == "https://www.trendyol.com/magaza/x-m-968"
    assert refs.absolute_link("butik/liste/1/kadin") == "https://www.trendyol.com/butik/liste/1/kadin"


def test_storefront_table():
    assert refs.storefront(None)["id"] == "1" and refs.storefront("tr")["currency"] == "TRY"
    assert refs.storefront("DE") == {"code": "DE", "id": "2", "language": "de", "culture": "de-DE", "currency": "EUR",
                                     "host": "www.trendyol.com", "prefix": "/de"}
    assert "GB" not in refs.STOREFRONTS and "US" not in refs.STOREFRONTS   # disabled on the site


# ---- schemas ----------------------------------------------------------------------------

def test_search_schema_defaults_and_mapping():
    loaded = schemas.ProductsSearchSchema().load({"query": " iphone ", "sort": "Price_Asc", "max_price": "5000"})
    assert loaded == {"query": "iphone", "sort": "PRICE_BY_ASC", "min_price": None, "max_price": 5000.0, "page": 1,
                      "country": "TR", "brand": None, "category": None}
    loaded = schemas.ProductsSearchSchema().load({"query": "x", "brand": "101470", "category": IPHONE.replace(
        "apple/iphone-15-128-gb-mavi-p-762254881?boutiqueId=689770&merchantId=968", "cep-telefonu-x-c103498"), "country": "de"})
    assert loaded["brand"] == "-x-b101470" and loaded["category"] == "cep-telefonu-x-c103498" and loaded["country"] == "DE"


@pytest.mark.parametrize("params", [
    {}, {"query": ""}, {"query": "x", "sort": "cheapest"}, {"query": "x", "page": "0"}, {"query": "x", "page": "121"},
    {"query": "x", "min_price": "100", "max_price": "50"}, {"query": "x", "country": "XX"},
    {"query": "x", "url": "https://www.trendyol.com/sr?q=x"}, {"query": "x", "brand": "apple"},
])
def test_search_schema_rejects(params):
    with pytest.raises(ValidationError):
        schemas.ProductsSearchSchema().load(params)


def test_search_schema_error_names_the_field():
    with pytest.raises(ValidationError) as err:
        schemas.ProductsSearchSchema().load({"query": "x", "min_price": "100", "max_price": "50"})
    assert "max_price" in err.value.messages


def test_category_and_brand_schemas():
    assert schemas.CategoryProductsSchema().load({"category": "56"})["category"] == "-x-c56"
    assert schemas.BrandProductsSchema().load({"brand": "https://www.trendyol.com/apple-x-b101470"})["brand"] == "apple-x-b101470"
    with pytest.raises(ValidationError):
        schemas.CategoryProductsSchema().load({})
    with pytest.raises(ValidationError):
        schemas.BrandProductsSchema().load({"brand": "https://www.trendyol.com/elbise-x-c56"})


def test_product_schemas():
    assert schemas.ProductSchema().load({"product": IPHONE}) == {"product": "762254881", "country": "TR"}
    loaded = schemas.ProductReviewsSchema().load({"product": "762254881", "sort": "newest", "rating": "5", "page": "2"})
    assert loaded["sort"] == ("LastModifiedDate", "DESC") and loaded["rating"] == 5 and loaded["page"] == 2
    assert schemas.ProductReviewsSchema().load({"product": "1"})["sort"] is None
    with pytest.raises(ValidationError):
        schemas.ProductReviewsSchema().load({"product": "1", "rating": "6"})
    with pytest.raises(ValidationError):
        schemas.ProductSchema().load({"product": "1", "id": "1"})
    assert schemas.ProductSimilarSchema().load({"product": "1", "page": "3"})["page"] == 3
    with pytest.raises(ValidationError):
        schemas.ProductSimilarSchema().load({"product": "1", "page": "21"})


def test_store_schemas():
    loaded = schemas.StoreProductsSchema().load({"store": "https://www.trendyol.com/magaza/trendyol-m-968", "query": "telefon",
                                                 "sort": "best_seller"})
    assert loaded == {"store": "968", "country": "TR", "query": "telefon", "sort": "BEST_SELLER", "page": 1}
    loaded = schemas.StoreReviewsSchema().load({"store": "968", "with_photos": "yes"})
    assert loaded["with_photos"] is True
    with pytest.raises(ValidationError):
        schemas.StoreSchema().load({"store": "trendyol"})


def test_rankings_schema():
    loaded = schemas.RankingsSchema().load({"category": "27"})
    assert loaded == {"category": "27", "type": "bestSeller", "gender": 1, "page": 1, "country": "TR"}
    loaded = schemas.RankingsSchema().load({"category": "27", "type": "Most_Viewed", "gender": "men", "page": "5"})
    assert loaded["type"] == "topViewed" and loaded["gender"] == 2 and loaded["page"] == 5
    with pytest.raises(ValidationError):
        schemas.RankingsSchema().load({"category": "27", "page": "6"})
    with pytest.raises(ValidationError):
        schemas.RankingsSchema().load({"category": "27", "type": "trending"})


def test_country_schema():
    assert schemas.CountrySchema().load({}) == {"country": "TR"}
    assert schemas.CountrySchema().load({"country": "ae"}) == {"country": "AE"}
    with pytest.raises(ValidationError):
        schemas.CountrySchema().load({"country": "GB"})
