def get_price_for_promo(promo_type):
    PROMOTION_PRICING = {
        "featured": {7: 500, 30: 1500, 60: 2500},
        "boosted": {7: 1000, 30: 2500, 60: 4000},
        "top": {7: 1500, 30: 3000, 60: 5000}
    }
    return PROMOTION_PRICING.get(promo_type)


