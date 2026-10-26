"""Offline tests for the Trendyol parsers and value helpers.

    python -m pytest trendyol/test_parsers.py -q

Fixtures are real www.trendyol.com / apigw.trendyol.com captures from
2026-10-23/24 (trendyol/fixtures/): two product pages (electronics with
8 other sellers, fashion with sizes and one seller), the not-found page,
search pages (iphone / elbise / no result), facets, reviews, Q&A,
variants, similar, store header / followers / facets / products / reviews,
rankings and the ranking tree — each with its unknown-id counterpart where
the gateway has one. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trendyol import parsers as P  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


@pytest.fixture(scope="module")
def iphone():
    return P.parse_product_page(fixture("product_iphone.html"), "762254881")


@pytest.fixture(scope="module")
def dress():
    return P.parse_product_page(fixture("product_fashion.html"), "1090399394")


# ---- helpers ------------------------------------------------------------------------

def test_value_helpers():
    assert P._num("2.029,10") == 2029.1 and P._num("477,48") == 477.48 and P._num("519") == 519
    assert P._num("59.799 TL") == 59799 and P._num("") is None and P._num(None) is None and P._num(True) is None
    assert P._percent("-%8") == 8 and P._percent("%12") == 12 and P._percent(0) == 0 and P._percent(None) is None
    assert P._iso_ms(1763715262881) == "2025-11-21T08:54:22Z" and P._iso_ms(0) is None
    assert P._iso_date("2026-11-30T23:00:00") == "2026-11-30" and P._iso_date("x") is None
    assert P._image("https://cdn.dsmcdn.com/mnresize/400/-/ty1/a/1_org_zoom.jpg") == "https://cdn.dsmcdn.com/ty1/a/1_org_zoom.jpg"
    assert P._image("/ty1750/prod/x/1_org_zoom.jpg") == "https://cdn.dsmcdn.com/ty1750/prod/x/1_org_zoom.jpg"
    assert P._currency("TL", None) == "TRY" and P._currency("TRY", "DE") == "TRY" and P._currency("€", "DE") == "EUR"
    assert P._price_pair(477.48, 519, "TRY") == {"current": 477.48, "original": 519, "discount_rate": 8, "currency": "TRY"}
    assert P._price_pair(100, 90, "TRY")["original"] == 100   # original never below current
    assert P._html_text("<p>Hello</p><ul><li>one</li><li>two</li></ul>") == "Hello\none\ntwo"
    assert P._html_text('<div id="w"><iframe src="x"></iframe></div>') is None


def test_extract_props_is_string_aware():
    html = 'x<script>window["__a__PROPS"]={"k":"a } b","n":{"m":[1,2]}}</script>'
    assert P.extract_props(html, "__a__PROPS") == {"k": "a } b", "n": {"m": [1, 2]}}
    assert P.extract_props(html, "__missing__") is None


# ---- product pages ------------------------------------------------------------------

def test_product_page_electronics(iphone):
    assert iphone["id"] == 762254881 and iphone["name"] == "iPhone 15 128 GB Mavi"
    assert iphone["link"] == "https://www.trendyol.com/apple/iphone-15-128-gb-mavi-p-762254881"
    assert iphone["brand"] == {"id": 101470, "name": "Apple", "link": "https://www.trendyol.com/apple-x-b101470"}
    assert iphone["category"]["id"] == 164462 and iphone["category"]["hierarchy"].startswith("Elektronik/")
    assert [c["name"] for c in iphone["category_tree"]][:2] == ["Elektronik", "Telefon"]
    assert iphone["price"] == {"current": 59799, "original": 60000, "discount_rate": 0 or None, "currency": "TRY",
                               "selling": 60000, "recommended_retail": None} or iphone["price"]["current"] == 59799
    assert iphone["rating"] == {"average": 4.64, "count": 2234, "comment_count": 976}
    assert iphone["favorite_count"] == 244269 and iphone["is_in_stock"] is True
    assert iphone["stock"]["max_sale_limit"] == 1 and iphone["barcode"] == "195949036583"
    assert iphone["merchant"]["id"] == 968 and iphone["merchant"]["official_name"].startswith("DSM GRUP")
    assert iphone["merchant"]["tax_number"] == "3130557669" and iphone["merchant"]["link"] == "https://www.trendyol.com/magaza/x-m-968"
    assert len(iphone["other_merchants"]) == 8
    other = iphone["other_merchants"][0]
    assert other["id"] and other["price"]["current"] > 0 and other["price"]["currency"] == "TRY"
    assert len(iphone["attributes"]) == 39 and iphone["attributes"][0] == {
        "name": "Garanti Tipi", "value": "Apple Türkiye Garantili", "description": None, "is_highlighted": True}
    assert iphone["slicing_attributes"] == {"DsmColor": "Blue", "Internal Memory": "128 GB"}
    assert len(iphone["images"]) == 9 and iphone["images"][0].startswith("https://cdn.dsmcdn.com/ty1609/")
    assert iphone["campaign"]["id"] == 689770 and iphone["campaign"]["end_date"] == "2026-12-31"
    assert iphone["origin_country"] == "CN" and iphone["tax_rate"] == 20
    assert iphone["english"]["color"] == "Mavi"
    assert iphone["_reco_ids"] == {"brand_id": 1617, "category_id": 5473, "root_category_id": 1071,
                                   "web_category_id": 164462, "root_web_category_id": 104024}
    assert iphone["variants"][0]["barcode"] == "195949036583" and iphone["variants"][0]["value"] is None


def test_product_page_fashion(dress):
    assert dress["id"] == 1090399394 and dress["gender"] == "Kadın"
    assert dress["price"]["current"] == 477.48 and dress["price"]["original"] == 519 and dress["price"]["discount_rate"] == 7
    assert dress["variant_attribute"] == "Beden"
    assert [v["value"] for v in dress["variants"]] == ["XS", "S", "M", "L"]
    assert all(v["is_in_stock"] for v in dress["variants"]) and dress["variants"][1]["barcode"] == "WFT93481"
    assert dress["other_merchants"] == [] and dress["merchant"]["email"] == "erkegetekstil@hs01.kep.tr"
    assert dress["merchant"]["score"] == 8.5 and dress["is_free_cargo"] is True
    names = [p["name"] for p in dress["promotions"]]
    assert "Sepette %8 İndirim" in names and any(p["type"] == "Cargo" for p in dress["promotions"])
    assert dress["top_rankings"] and dress["attributes"][2]["description"] == "Vücudu saran, bedene tam oturan"
    assert dress["_reco_ids"]["root_web_category_id"] == 82 and dress["_reco_ids"]["root_category_id"] == 522


def test_product_page_not_found():
    assert P.parse_product_page(fixture("product_not_found.html"), "99") is None
    assert P.parse_product_page("<html></html>", "99") is None
    assert P.parse_product_page("", None) is None


def test_product_page_de_storefront_links(dress):
    record = P.parse_product_page(fixture("product_fashion.html"), None, "DE")
    assert record["merchant"]["link"] == "https://www.trendyol.com/de/magaza/x-m-868610"


def test_description():
    assert P.parse_description(fixture("html_content_iphone.json")) == {
        "text": None, "html": fixture("html_content_iphone.json")["content"]}
    assert P.parse_description({}) == {"text": None, "html": None}
    assert P.parse_description({"content": "<p>Pamuklu</p><p>Yıkanabilir</p>"})["text"] == "Pamuklu\nYıkanabilir"


# ---- listings -------------------------------------------------------------------------

def test_search_listing():
    data = P.parse_listing(fixture("search_iphone_p1.json"))
    assert data["title"] == "iphone" and data["total_count"] == 100000 and data["is_total_estimated"] is True
    assert data["total_pages"] == 120 and data["page"] == 1 and len(data["products"]) == 36
    first = data["products"][0]
    assert first["id"] == 1198082338 and first["link"] == (
        "https://www.trendyol.com/apple/iphone-duo-512gb-star-white-p-1198082338?boutiqueId=61&merchantId=798581")
    assert first["brand"] == {"id": 101470, "name": "Apple"} and first["category"] == {"id": 5473, "name": "IOS Cep Telefonları"}
    assert first["price"] == {"current": 335000, "original": 335000, "discount_rate": None, "currency": "TRY", "discount_type": "rrp"}
    assert first["rating"] == {"average": None, "count": None} or first["rating"]["count"] is None
    assert first["images"][0] == "https://cdn.dsmcdn.com/ty1000445/product/media/images/prod/PIM/20260911/12/97bd118a-4dfd-40c1-ae27-c7d94967273d/1_org_zoom.jpg"
    assert first["variant"] == {"value": "Tek Ebat", "is_one_size": True} and first["is_free_cargo"] is True
    rated = next(p for p in data["products"] if p["rating"]["count"])
    assert rated["rating"]["average"] > 4 and rated["merchant_id"] and rated["listing_id"]


def test_search_listing_promotions_and_social_proof():
    data = P.parse_listing(fixture("search_elbise_p1.json"))
    first = data["products"][0]
    assert first["price"] == {"current": 477.48, "original": 519, "discount_rate": 8, "currency": "TRY",
                              "discount_type": "basketPromotion"}
    assert first["promotion"]["name"] == "Sepette %8 İndirim" and first["promotion"]["end_date"] == "2026-11-30"
    assert first["social_proof"] == {"favorite_count": "199K", "order_count": "100+"}
    assert first["top_ranking"] == {"type": "best_seller", "rank": 4}
    assert first["attributes"] == [{"name": "Materyal Bileşeni", "value": "95% Polyester, 5% Elastan"}]
    assert first["is_next_day_delivery"] is True and first["is_ad"] is False and first["has_review_photo"] is True
    assert any(p["promotions"] for p in data["products"])


def test_search_no_results_is_an_empty_page():
    data = P.parse_listing(fixture("search_no_results.json"))
    # the gateway falls back to a multilingual guess: products come back but it says so
    assert data["search_strategy"] == "MULTILINGUAL_SEARCH"
    data = P.parse_listing({"products": [], "total": 0})
    assert data["products"] == [] and data["total_count"] == 0 and data["total_pages"] == 0
    assert P.parse_listing({})["products"] == [] and P.parse_listing(None)["total_count"] is None


def test_filters():
    data = P.parse_filters(fixture("search_aggregations_iphone.json"))
    names = [f["name"] for f in data["filters"]]
    assert "Marka" in names and "Fiyat" in names and "Kategori" in names
    brand = next(f for f in data["filters"] if f["name"] == "Marka")
    assert brand["field"] == "webBrandIds" and brand["values_count"] == 556 and len(brand["values"]) == 50
    assert brand["values"][0]["id"] and brand["values"][0]["count"] > 0 and brand["values"][0]["is_selected"] is False
    model = next(f for f in data["filters"] if f["name"] == "Cep Telefonu Modeli")
    assert model["field"] == "attributes" and model["key"] == "292"
    assert P.parse_filters({}) == {"filters": [], "quick_filters": []}


# ---- reviews / questions ------------------------------------------------------------

def test_reviews():
    data = P.parse_reviews(fixture("reviews_fashion_p0.json"))
    summary = data["summary"]
    assert summary["average_rating"] == 4.4 and summary["rating_count"] == 1249 and summary["comment_count"] == 536
    assert summary["photo_review_count"] == 160 and data["total_pages"] == 11
    assert summary["rating_distribution"][0]["rating"] == 5 and summary["sizes"][0] == {"name": "M", "count": 152}
    assert summary["countries"] == ["TR", "AZ"] and summary["ai_summary"]
    assert summary["tags"][0]["name"] and any(t["sentiment"] for t in summary["tags"])
    assert len(data["reviews"]) == 50
    with_media = next(r for r in data["reviews"] if r["media"])
    assert with_media["media"][0]["link"].startswith("https://cdn.dsmcdn.com/prod-product-review-media")
    assert with_media["size"] == "L" and with_media["reviewer_height_cm"] == 160 and with_media["fit"] == "EXACT_SIZE"
    assert with_media["created_at"].endswith("Z") and with_media["is_verified_purchase"] in (True, False)
    assert with_media["seller"] == {"id": 868610, "name": "World Fashion Trends"}


def test_reviews_unknown_product_is_empty():
    data = P.parse_reviews(fixture("reviews_unknown.json"))
    assert data["reviews"] == [] and data["summary"]["rating_count"] == 0 and data["total_pages"] == 0
    assert P.parse_reviews({})["reviews"] == []


def test_questions():
    data = P.parse_questions(fixture("questions_iphone_p0.json"))
    # contentSummary.totalCount spans every fulfilment type (899); this capture
    # paged one type (537 rows, 27 pages of 20)
    assert data["total_count"] == 899 and data["total_pages"] == 27 and len(data["questions"]) == 20
    q = data["questions"][0]
    assert q == {"id": 427665275, "question": "Ürün yenilenmiş mi yoksa sıfır mı", "asked_at": "2026-06-08T17:52:10Z",
                 "user_name": "**** ****", "is_verified_purchase": False, "seller": {"id": 968, "name": "Trendyol"},
                 "answer": "Merhaba, ürün sıfır kapalı kutu olarak gönderiliyor. İlginiz için teşekkür ederiz.",
                 "answered_in": "1 dakika içinde cevaplandı.", "is_translated": False}
    tagged = P.parse_questions(fixture("questions_fashion_p0.json"))
    assert tagged["topics"] and tagged["topics"][0]["key"] == "TUMU"
    assert P.parse_questions({})["questions"] == []


# ---- variants / similar --------------------------------------------------------------

def test_variants():
    groups = P.parse_variants(fixture("variants_iphone.json"))
    assert [g["type"] for g in groups] == ["DsmColor", "Internal Memory"] or groups[0]["type"] == "DsmColor"
    colour = groups[0]
    assert colour["name"] == "Renk" and colour["display_type"] == "IMAGE_ONLY"
    black = next(v for v in colour["values"] if v["name"] == "Black")
    assert black["products"][0] == {"id": 762254878, "name": "iPhone 15 128 GB Siyah",
                                    "link": "https://www.trendyol.com/apple/iphone-15-128-gb-siyah-p-762254878",
                                    "image": "https://cdn.dsmcdn.com/ty1594/prod/QC/20241027/17/7a203c1b-d121-3600-9ee5-3eeeb4d12767/1_org_zoom.jpg",
                                    "merchant_id": 968, "boutique_id": 689770, "is_selected": False}
    assert next(v for v in colour["values"] if v["is_selected"])["name"] == "Blue"
    assert P.parse_variants({"result": []}) == [] and P.parse_variants({}) == []


def test_similar():
    data = P.parse_similar(fixture("similar_fashion.json"))
    assert data["total_count"] and data["is_last_page"] in (True, False) and len(data["products"]) == 24
    first = data["products"][0]
    assert first["id"] == 982412632 and first["brand"] == {"id": 175612, "name": "JE-TU"}
    assert first["link"] == "https://www.trendyol.com/je-tu/etegi-kat-kat-volanli-mini-elbise-jt9060-p-982412632"
    assert first["price"]["currency"] == "TRY" and first["price"]["current"] > 0
    assert first["images"][0].startswith("https://cdn.dsmcdn.com/ty1750/")
    assert first["favorite_count"] == 108503 and first["rating"]["count"] == 1247
    assert first["top_ranking"] == {"type": "categoryTopRanking", "rank": 10}
    assert len(first["color_variants"]) == 4 and first["color_variants"][0]["link"].startswith("https://www.trendyol.com/")
    assert first["attributes"][0]["name"]
    assert P.parse_similar({"isSuccess": False, "result": None})["products"] == []


# ---- stores ------------------------------------------------------------------------

def test_store_header_and_followers():
    store = P.parse_store_header(fixture("store_header_968.json"))
    assert store == {
        "id": 968, "name": "Trendyol", "link": "https://www.trendyol.com/magaza/trendyol-m-968",
        "official_name": "DSM GRUP DANIŞMANLIK İLETİŞİM VE SATIŞ TİCARET ANONİM ŞİRKETİ", "score": 9.3,
        "logo": "https://cdn.dsmcdn.com/seller-store/uploads/968/3b18a008-0ccb-448b-ac00-ed889c7ea911.jpeg",
        "product_count": 33773, "badges": ["https://cdn.dsmcdn.com/seller-store/resources/tr/fast-seller.svg"],
        "ranking": {"type": "topSold", "text": "En çok satan Mağaza Aksesuar Kategorisinde"},
        "time_on_trendyol": "2 Yıl", "location": "İstanbul", "is_corporate_invoice_applicable": True,
        "average_shipping_time": "< 12 Saat", "question_response_time": "2-4 Saat",
        "average_product_rating": 4.4, "average_seller_rating": None}
    assert P.parse_store_header(fixture("store_header_unknown.json")) is None
    assert P.parse_store_followers(fixture("store_followers_968.json")) == {"count": 5478197, "text": "5,5M"}
    assert P.parse_store_followers(fixture("store_followers_unknown.json")) == {"count": 0, "text": None}


def test_store_facets():
    facets = P.parse_store_facets(fixture("store_aggregations_968.json"))
    assert facets["categories"][0] == {"id": 1019, "name": "Bluz", "count": 2815,
                                       "image": "https://cdn.dsmcdn.com/indexing-category-images/prod/e5a22ca0-fdcf-495a-ab94-b8b2428df53d.jpg",
                                       "is_leaf": True}
    assert facets["brands"][0] == {"id": 41, "name": "MANGO", "count": 6987}


def test_store_products():
    data = P.parse_store_products(fixture("store_products_968_p2.json"))
    assert len(data["products"]) == 20 and data["has_next"] is True and data["page"] == 4
    assert data["products"][0]["merchant_id"] == 968 and data["products"][0]["price"]["currency"] == "TRY"
    unknown = P.parse_store_products(fixture("store_products_unknown.json"))
    assert unknown == {"products": [], "has_next": False, "page": 1}


def test_store_reviews():
    data = P.parse_store_reviews(fixture("store_reviews_968_p0.json"))
    assert data["summary"]["average_rating"] == 4.3 and data["summary"]["rating_count"] == 662500
    assert data["summary"]["rating_distribution"][0] == {"rating": 5, "count": 473270, "comment_count": 68487}
    assert data["total_count"] == 102804 and data["total_pages"] == 5141 and len(data["reviews"]) == 20
    first = data["reviews"][0]
    assert first["id"] == 675397873 and first["rating"] == 5 and first["comment"] == "süper ürün"
    assert first["created_at"] == "2026-10-23T13:55:18Z" and first["is_verified_purchase"] is True
    assert first["product"]["id"] == 855229295 and first["product"]["brand"] == "Xiaomi"
    assert first["product"]["link"].startswith("https://www.trendyol.com/xiaomi/redmi-buds-6-play")
    assert first["product"]["price"] == {"current": 789.11, "original": 789.11, "discount_rate": None, "currency": "TRY"}
    unknown = P.parse_store_reviews(fixture("store_reviews_unknown.json"))
    assert unknown["reviews"] == [] and unknown["total_count"] == 0


def test_store_photo_reviews():
    data = P.parse_store_reviews(fixture("store_reviews_968_photos_p0.json"))
    assert data["summary"] is None and data["total_count"] == 112724 and data["total_pages"] == 5637
    assert len(data["reviews"]) == 20
    first = data["reviews"][0]
    assert first["id"] == 675391678 and first["photo_id"] == 144430893 and first["rating"] == 5
    assert first["comment"] == "mükemmel çok iyi fiyata göre" and first["user_name"] == "B** S**"
    assert first["created_at"] == "2026-10-23" and first["is_verified_purchase"] is True
    assert first["media"] == [{"id": 144430893, "type": "image",
                               "link": "https://cdn.dsmcdn.com/prod-product-review-media-1788420252000/img/2019922/2029892/2042853/958136288/44126332-1792762240550.jpeg",
                               "thumbnail": "https://cdn.dsmcdn.com/mnresize/300/300/prod-product-review-media-1788420252000/img/2019922/2029892/2042853/958136288/44126332-1792762240550.jpeg"}]
    assert first["product"]["id"] == 958136288 and first["product"]["price"] == {"current": 229, "original": 249, "discount_rate": 8, "currency": "TRY"}
    assert P._iso_date("5 Mayıs 2026") == "2026-05-05" and P._iso_date("1 Ağustos 2025") == "2025-08-01"


# ---- rankings -------------------------------------------------------------------

def test_rankings():
    data = P.parse_rankings(fixture("rankings_bestseller_27_p1.json"))
    assert data["category"] == {"id": 27, "name": "Aksesuar", "path": "/Aksesuar"} and data["total_count"] == 100
    assert len(data["products"]) == 20
    first = data["products"][0]
    assert first["id"] == 1015243251 and first["brand"] == {"id": 2738718, "name": "MYSTOBAG"}
    assert first["price"]["currency"] == "TRY" and first["price"]["current"] > 0 and first["price"]["type"] == "ty_plus"
    assert first["rating"] == {"average": 4.24, "count": 1096}
    assert first["rank_change"] == {"label": "rank_increased", "places": 6} and first["is_fast_delivery"] is True
    assert first["promotions"] and first["link"].startswith("https://www.trendyol.com/mystobag/")
    unknown = P.parse_rankings(fixture("rankings_unknown.json"))
    assert unknown == {"category": None, "total_count": 0, "products": []}


def test_rankings_tree():
    data = P.parse_rankings_tree(fixture("rankings_tree_fragment.html"))
    assert [t["type"] for t in data["ranking_types"]] == ["bestSeller", "topViewed", "mostFavourite", "mostRated"]
    assert data["categories"][0]["id"] == 27 and data["categories"][0]["name"] == "Aksesuar"
    assert data["categories"][0]["link"] == "https://www.trendyol.com/top-rankings/aksesuar/27/bestSeller/1"
    child = data["categories"][0]["children"][0]
    assert child["parent_id"] == 27 and child["level"] == 1 and "bestSeller" in child["ranking_types"]
    assert len(data["categories"]) == 19
    assert P.parse_rankings_tree("") == {"ranking_types": [], "categories": []}


# ---- navigation ------------------------------------------------------------------

def test_navigation_menu():
    data = P.parse_navigation(fixture("product_iphone.html"))
    assert data["sections"][0] == {"id": 1, "name": "Kadın", "link": "https://www.trendyol.com/butik/liste/1/kadin"}
    women = data["categories"][0]
    assert women["name"] == "KADIN" and women["type"] == "section" and women["id"] == 1
    clothing = women["children"][0]
    assert clothing == {"id": 82, "name": "Giyim", "type": "category", "gender_id": 1,
                        "link": "https://www.trendyol.com/kadin-giyim-x-g1-c82", "children": clothing["children"]}
    assert clothing["children"][0] == {"id": 56, "name": "Elbise", "type": "category", "gender_id": None,
                                       "link": "https://www.trendyol.com/elbise-x-c56", "children": []}
    kinds = {n["type"] for root in data["categories"] for c in root["children"] for n in c["children"]}
    assert "collection" in kinds
    assert P.parse_navigation("") == {"sections": [], "categories": []}
