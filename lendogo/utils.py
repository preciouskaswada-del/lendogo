from decimal import Decimal
from django.utils import timezone
from django.db.models import Avg, Count
import re

SCAM_KEYWORDS = [
    'urgent sale', 'leaving country', 'need money fast', 'today only',
    'first come first serve', 'almost new', 'barely used', 'giveaway price',
    'quick sale', 'must go', 'sacrifice price', 'call now'
]

def extract_keywords(product_name):
    """
    Pull main words for matching: 'iPhone 14 Pro Max!!!' -> ['iphone', '14', 'pro', 'max']
    Handles weird input safely - empty strings, symbols, caps all work.
    """
    if not product_name:
        return []

    # Lowercase, remove symbols, split
    name = re.sub(r'[^\w\s]', ' ', product_name.lower())
    words = name.split()

    # Remove common junk words that break matching
    junk = {'for', 'sale', 'new', 'used', 'brand', 'original', 'selling', 'item', 'the', 'a', 'an'}
    clean_words = [w for w in words if w not in junk and len(w) > 1]

    return clean_words

def get_market_average(product_name, current_listing_id=None):
    """
    Get average price from OTHER active listings of similar items on Lendogo.
    Returns None if not enough data to compare safely.
    """
    from lendogo.models import Listing

    keywords = extract_keywords(product_name)
    if not keywords:
        return None

    # Start with all active, non-scam listings
    query = Listing.objects.filter(status='ACTIVE', suspicion_level__lt=2)

    # Exclude the current listing so it doesn't compare to itself
    if current_listing_id:
        query = query.exclude(id=current_listing_id)

    # Must match the main keyword like 'iphone', 'samsung', 'sofa'
    main_keyword = keywords[0]
    query = query.filter(product__icontains=main_keyword)

    # If there's a model number, try to match it too for better accuracy
    for word in keywords[1:]:
        if word.isdigit(): # '14', '55', '32' etc
            query = query.filter(product__icontains=word)
            break # Only use first number found

    stats = query.aggregate(avg=Avg('price'), count=Count('id'))

    # Only trust the average if we have 3+ similar listings
    # This prevents false flags when there's no data
    if stats['count'] and stats['count'] >= 3:
        return stats['avg']

    return None

def run_ai_scan(listing):
    """
    Main AI scanner - compares listing to other Lendogo prices.
    Sets suspicion_level: 0=safe, 1=low, 2=medium popup, 3=high popup
    """
    suspicion = 0
    warnings = []

    market_avg = get_market_average(listing.product, listing.id)

    # If we don't have enough similar items to compare, don't flag
    if not market_avg or market_avg == 0:
        listing.suspicion_level = 0
        listing.scam_warning = ""
        listing.market_avg_price = None
        listing.last_scanned = timezone.now()
        return

    price = listing.price
    ratio = price / market_avg if market_avg > 0 else 1

    # RULE 1: Price too low vs other Lendogo listings
    if ratio < 0.25: # Less than 25% of average = extreme scam
        suspicion = 3
        warnings.append(f"Price is {int((1-ratio)*100)}% below other Lendogo listings. High scam risk.")
    elif ratio < 0.4: # Less than 40% = high risk, show modal
        suspicion = 3
        warnings.append(f"Price is {int((1-ratio)*100)}% below similar items on Lendogo.")
    elif ratio < 0.6: # Less than 60% = medium risk, show modal
        suspicion = 2
        warnings.append(f"Price is {int((1-ratio)*100)}% below average for this item.")
    elif ratio < 0.75: # Less than 75% = low risk, no popup, just yellow dot
        suspicion = 1
        warnings.append("Price is below average. Check item carefully.")

    # RULE 2: Scam keywords in description
    desc_lower = listing.description.lower() if listing.description else ""
    found_keywords = [kw for kw in SCAM_KEYWORDS if kw in desc_lower]
    if found_keywords:
        suspicion = max(suspicion, 2) # Bump to at least medium
        warnings.append(f"Suspicious phrases used: {', '.join(found_keywords[:2])}")

    # RULE 3: New account + expensive item + low price = classic scam
    if listing.seller.date_joined > timezone.now() - timezone.timedelta(days=7):
        if price > 500000 and ratio < 0.6:
            suspicion = max(suspicion, 3)
            warnings.append("New seller account with expensive item at low price.")

    # RULE 4: No images on expensive item
    if price > 200000:
        if not hasattr(listing, 'images') or not listing.images.exists():
            suspicion = max(suspicion, 2)
            warnings.append("Expensive item posted with no photos.")

    listing.suspicion_level = suspicion
    listing.scam_warning = " ".join(warnings) if warnings else ""
    listing.market_avg_price = market_avg
    listing.last_scanned = timezone.now()