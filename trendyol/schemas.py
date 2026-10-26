"""Marshmallow request schemas for every /trendyol/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair; trendyol/refs.py resolves each):

    product    a contentId (762254881) OR any trendyol.com product link
    store      a merchant id (968) OR a store link (/magaza/<name>-m-<id>)
    brand      a web brand id (101470) OR a brand link (/<name>-x-b<id>)
    category   a web category id (103498) OR a category link (/<name>-x-c<id>)
    country    a storefront code (TR default; DE, AE, SA, QA, … refs.STOREFRONTS):
               prices come in that storefront's currency

Sort / page bounds follow the gateway's own limits (fetch.py): 36 products
a page and ~120 pages for listings, 50 reviews / questions a page, 20 for
store products and reviews, 5 pages of 20 for a best-seller list.
"""
from marshmallow import validates_schema, ValidationError

from schema_fields import (BaseSchema, ChoiceField, Flag, PageField, Price, QueryField, RefField,
                           StrippedString)
from trendyol import refs
from trendyol.fetch import SEARCH_MAX_PAGE

# public value -> the gateway's `sst` token
LISTING_SORTS = {
    "relevance": "SCORE",
    "price_asc": "PRICE_BY_ASC",
    "price_desc": "PRICE_BY_DESC",
    "newest": "MOST_RECENT",
    "best_seller": "BEST_SELLER",
    "most_favourite": "MOST_FAVOURITE",
    "most_rated": "MOST_RATED",
}
# public value -> (orderBy, order) of the review gateway
REVIEW_SORTS = {
    "most_helpful": ("Score", "DESC"),
    "newest": ("LastModifiedDate", "DESC"),
    "oldest": ("LastModifiedDate", "ASC"),
}
RANKING_TYPES = {
    "best_seller": "bestSeller",
    "most_viewed": "topViewed",
    "most_favourite": "mostFavourite",
    "most_rated": "mostRated",
    "most_repurchased": "topRepurchased",
}
GENDERS = {"women": 1, "men": 2}

MAX_REVIEW_PAGE = 500      # 50 a page; the busiest products have ~20k comments
MAX_STORE_PAGE = 500       # 20 a page; the biggest stores list ~30k products
MAX_RANKING_PAGE = 5       # 100 products a list


class CountryField(ChoiceField):
    """Storefront code (TR default)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", refs.DEFAULT_COUNTRY)
        kwargs.setdefault("metadata", {"description": "storefront: TR (default), DE, AE, SA, QA, KW, "
                                                      "UA, PL, RO, … (prices in that storefront's currency)"})
        super().__init__(list(refs.COUNTRY_CODES), **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        return value.upper() if value else refs.DEFAULT_COUNTRY


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class StoreRefField(RefField):
    resolver = staticmethod(refs.resolve_store)


class BrandRefField(RefField):
    resolver = staticmethod(refs.resolve_brand)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


class RankingCategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_ranking_category)


class _ListingSchema(BaseSchema):
    sort = ChoiceField(LISTING_SORTS, metadata={"description": "relevance (default), price_asc, price_desc, newest, "
                                                               "best_seller, most_favourite, most_rated"})
    min_price = Price(metadata={"description": "lowest price, in the storefront's currency"})
    max_price = Price(metadata={"description": "highest price, in the storefront's currency"})
    page = PageField(max_page=SEARCH_MAX_PAGE, metadata={"description": "page of 36 products (1-120)"})
    country = CountryField()

    @validates_schema
    def _price_order(self, data, **kwargs):
        lo, hi = data.get("min_price"), data.get("max_price")
        if lo is not None and hi is not None and lo > hi:
            raise ValidationError("Must not be lower than min_price.", "max_price")


class ProductsSearchSchema(_ListingSchema):
    query = QueryField(metadata={"description": "search term (product, brand or category words)"})
    brand = BrandRefField(required=False, load_default=None, metadata={
        "description": "limit to a brand: web brand id or trendyol.com brand link"})
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "limit to a category: web category id or trendyol.com category link"})


class CategoryProductsSchema(_ListingSchema):
    category = CategoryRefField(metadata={"description": "web category id (103498) or trendyol.com category link"})
    brand = BrandRefField(required=False, load_default=None, metadata={
        "description": "limit to a brand: web brand id or trendyol.com brand link"})


class BrandProductsSchema(_ListingSchema):
    brand = BrandRefField(metadata={"description": "web brand id (101470) or trendyol.com brand link"})
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "limit to a category: web category id or trendyol.com category link"})


class ProductSchema(BaseSchema):
    product = ProductRefField(metadata={"description": "product id (762254881) or trendyol.com product link"})
    country = CountryField()


class ProductReviewsSchema(ProductSchema):
    sort = ChoiceField(REVIEW_SORTS, metadata={"description": "most_helpful (default), newest, oldest"})
    rating = ChoiceField({"1": 1, "2": 2, "3": 3, "4": 4, "5": 5}, metadata={"description": "only reviews with this star rating (1-5)"})
    page = PageField(max_page=MAX_REVIEW_PAGE, metadata={"description": "page of 50 reviews"})


class ProductQuestionsSchema(ProductSchema):
    page = PageField(max_page=MAX_REVIEW_PAGE, metadata={"description": "page of 50 answered questions"})


class ProductSimilarSchema(ProductSchema):
    page = PageField(max_page=20, metadata={"description": "page of 24 similar products"})


class StoreSchema(BaseSchema):
    store = StoreRefField(metadata={"description": "merchant id (968) or trendyol.com store link"})
    country = CountryField()


class StoreProductsSchema(StoreSchema):
    query = StrippedString(load_default=None, metadata={"description": "search term within the store"})
    sort = ChoiceField(LISTING_SORTS, metadata={"description": "relevance (default), price_asc, price_desc, newest, "
                                                               "best_seller, most_favourite, most_rated"})
    page = PageField(max_page=MAX_STORE_PAGE, metadata={"description": "page of 20 products"})


class StoreReviewsSchema(StoreSchema):
    with_photos = Flag(load_default=False, metadata={"description": "true: only reviews with photos"})
    page = PageField(max_page=MAX_STORE_PAGE, metadata={"description": "page of 20 reviews"})


class CountrySchema(BaseSchema):
    country = CountryField()


class RankingsSchema(BaseSchema):
    category = RankingCategoryRefField(metadata={
        "description": "ranking category id (27; see rankings/categories) or trendyol.com best-sellers link"})
    type = ChoiceField(RANKING_TYPES, load_default="bestSeller", metadata={
        "description": "best_seller (default), most_viewed, most_favourite, most_rated, most_repurchased"})
    gender = ChoiceField(GENDERS, load_default=1, metadata={"description": "women (default) or men: the site's two ranking menus"})
    page = PageField(max_page=MAX_RANKING_PAGE, metadata={"description": "page of 20 (a list holds 100 products)"})
    country = CountryField()
