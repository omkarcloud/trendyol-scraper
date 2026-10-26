"""Cache TTL per /trendyol/* endpoint (cache.py, keyed on the validated
params). Trendyol is a live marketplace: prices and stock move within the
day, so the product-level rows are short; lists and trees move slowly.
products/details, products/variants and products/similar share ONE cached
product-page parse (api._product_record), so hitting all three on a product
costs one upstream page fetch.
"""
from datetime import timedelta

# The parsed product page (price, stock, sellers): the hot path, kept short
# because the buy box re-ranks sellers through the day.
PRODUCT_CACHE = timedelta(minutes=30)
# Search / category / brand / store listings: ranking and prices drift, but
# a page served twice within the hour is the same page to a buyer.
LISTING_CACHE = timedelta(hours=1)
# Reviews and Q&A append slowly; a new comment showing up 6 h late is fine.
REVIEWS_CACHE = timedelta(hours=6)
QUESTIONS_CACHE = timedelta(hours=6)
# Store header (score, follower count, metrics) is recomputed daily by the site.
STORE_CACHE = timedelta(hours=6)
# "Similar products" is a recommendation slate; it changes with the catalog.
SIMILAR_CACHE = timedelta(hours=6)
# Best-seller rankings are refreshed by the site a few times a day.
RANKINGS_CACHE = timedelta(hours=3)
# Category trees (navigation menu, ranking categories) change on the order of weeks.
TREE_CACHE = timedelta(days=1)
