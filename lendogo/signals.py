print("SIGNALS.PY LOADED")
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from .models import Listing

def run_simple_scan(listing):
    """Fast scam detector. Runs after transaction commits to avoid DB locks."""
    
    similar = Listing.objects.filter(
        product__iexact=listing.product.strip(),
        status='ACTIVE'
    ).exclude(pk=listing.pk).only('price')[:50]
    
    similar_count = len(similar)
    print(f"SCAN: Checking {similar_count} similar listings for '{listing.product}'")
    
    if similar_count >= 2:
        avg_price = sum(l.price for l in similar) / similar_count
    else:
        avg_price = 0
        print("SCAN: Not enough listings to compare")
    
    listing.market_avg_price = int(avg_price)
    
    # Rule 1: Price too low = suspicious - FIXED FOR DECIMALS
    if avg_price > 0 and listing.price < avg_price * Decimal('0.2'):
        listing.suspicion_level = 3
        listing.scam_warning = f"Price 99% below MK {avg_price:.0f} market average. Extremely suspicious."
    elif avg_price > 0 and listing.price < avg_price * Decimal('0.5'):
        listing.suspicion_level = 2  
        listing.scam_warning = f"Price 50% below MK {avg_price:.0f} market average. Be cautious."
    else:
        listing.suspicion_level = 0
        listing.scam_warning = ""
    
    listing.last_scanned = timezone.now()
    listing.scam_score = listing.suspicion_level * 30
    print(f"SCAN DONE: suspicion={listing.suspicion_level}, avg={avg_price}")
    return listing.suspicion_level

@receiver(pre_save, sender=Listing)
def track_listing_changes(sender, instance, **kwargs):
    """Track if price or product changed so we only rescan when needed."""
    if instance.pk:
        try:
            old = Listing.objects.get(pk=instance.pk)
            instance._price_changed = old.price != instance.price
            instance._product_changed = old.product != instance.product
            print(f"PRE_SAVE: old_price={old.price}, new_price={instance.price}, changed={instance._price_changed}")
        except Listing.DoesNotExist:
            instance._price_changed = True
            instance._product_changed = True
    else:
        instance._price_changed = True
        instance._product_changed = True

def _do_scan_update(instance_id):
    """This runs AFTER the save commits, so no DB lock."""
    try:
        instance = Listing.objects.get(pk=instance_id)
        run_simple_scan(instance)
        Listing.objects.filter(pk=instance_id).update(
            suspicion_level=instance.suspicion_level,
            scam_warning=instance.scam_warning,
            market_avg_price=instance.market_avg_price,
            last_scanned=instance.last_scanned,
            scam_score=instance.scam_score
        )
    except Listing.DoesNotExist:
        print("SCAN: Listing deleted before scan could run")

@receiver(post_save, sender=Listing)
def auto_scan_listing(sender, instance, created, **kwargs):
    """Auto-run scam detection after every save."""
    # Prevent infinite loop from our own update
    if kwargs.get('update_fields') and 'last_scanned' in kwargs.get('update_fields', []):
        return
    
    should_scan = created or getattr(instance, '_price_changed', False) or getattr(instance, '_product_changed', False)
    
    if should_scan and instance.status == 'ACTIVE':
        print("SCHEDULING SCAN AFTER COMMIT...")
        # This prevents the SQLite deadlock
        transaction.on_commit(lambda: _do_scan_update(instance.pk))
    else:
        print(f"SKIP SCAN: should_scan={should_scan}, status={instance.status}")