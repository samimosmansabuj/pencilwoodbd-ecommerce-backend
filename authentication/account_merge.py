import uuid

from django.db import transaction

from .models import CustomUser, Customer, GoogleIdentity
from .utils import normalize_bd_phone, phone_lookup_variants

REQUIRE_OTP_FOR_ACCOUNT_LINK = True


class MergeConflict(Exception):
    """The two accounts cannot be merged safely."""


def customers_by_phone(phone):
    return Customer.objects.filter(phone__in=phone_lookup_variants(phone)).order_by("created_at", "id")


def verify_phone_otp(phone, otp_code):
    from site_app.models import OTPVerification

    if not phone or not otp_code:
        return False
    otp = OTPVerification.objects.filter(phone=normalize_bd_phone(phone) or phone).order_by("-id").first()
    if not otp or otp.is_expired() or otp.is_locked:
        return False
    if otp.otp != str(otp_code).strip():
        otp.register_failed_attempt()
        return False
    otp.is_verified = True
    otp.save(update_fields=["is_verified"])
    return True


def resolve_order_address(customer, address_id, street, district, upazila):
    from order.models import Address

    street = (street or "").strip()
    district = (district or "").strip()
    saved = Address.objects.filter(customer=customer, is_deleted=False)

    if address_id:
        try:
            chosen = saved.filter(pk=int(address_id)).first()
        except (TypeError, ValueError):
            chosen = None
        if chosen and chosen.street_01.strip().lower() == street.lower() and chosen.district.strip().lower() == district.lower():
            return chosen

    same = saved.filter(street_01__iexact=street, district__iexact=district).order_by("id").first()
    if same:
        return same
    return Address.objects.create(customer=customer, street_01=street, district=district, upazila=upazila)


def _move_cart_and_wishlist(keep, drop, protect_cart_ids):
    from product.models import AddToCart, Wishlist

    protect = {str(i) for i in (protect_cart_ids or [])}
    keep_rows = list(AddToCart.objects.filter(customer=keep))
    for row in AddToCart.objects.filter(customer=drop):
        same = next((r for r in keep_rows if r.product_id == row.product_id and r.variant_id == row.variant_id
                     and (r.customization_note or "") == (row.customization_note or "")), None)
        if same and str(row.pk) in protect:
            keep_rows.remove(same)
            same.delete()
            same = None
        if same:
            same.quantity += row.quantity
            same.save()
            row.delete()
        else:
            AddToCart.objects.filter(pk=row.pk).update(customer=keep)
            keep_rows.append(row)

    for row in Wishlist.objects.filter(customer=drop):
        if Wishlist.objects.filter(customer=keep, product_id=row.product_id, variant_id=row.variant_id).exists():
            row.delete()
        else:
            Wishlist.objects.filter(pk=row.pk).update(customer=keep)


def _move_related(keep, drop, protect_cart_ids):
    from product.models import AddToCart, Wishlist

    _move_cart_and_wishlist(keep, drop, protect_cart_ids)
    for rel in Customer._meta.related_objects:
        if not rel.one_to_many or rel.related_model in (AddToCart, Wishlist):
            continue
        rel.related_model.objects.filter(**{rel.field.name: drop}).update(**{rel.field.name: keep})


def merge_customer_accounts(first, second, login_user=None, protect_cart_ids=()):
    keep, drop = sorted([first, second], key=lambda c: (c.created_at, c.pk))
    users = [u for u in (keep.user, drop.user) if u]
    for u in users:
        if u.user_type != "customer" or not u.is_active:
            raise MergeConflict("only active customer accounts can be merged")

    survivor = None
    if users:
        survivor = next((u for u in users if login_user and u.pk == login_user.pk), users[0])
    loser = next((u for u in users if survivor and u.pk != survivor.pk), None)

    with transaction.atomic():
        if loser:
            if survivor.phone and loser.phone and normalize_bd_phone(survivor.phone) != normalize_bd_phone(loser.phone):
                raise MergeConflict("two different phone numbers")

            loser_google, loser_email = loser.google_id, loser.email
            carry = {f: getattr(loser, f) for f in ("google_id", "email", "phone") if not getattr(survivor, f) and getattr(loser, f)}
            carry_password = loser.password if loser.has_usable_password() and not survivor.has_usable_password() else None

            loser.google_id = None
            loser.email = None
            loser.phone = None
            loser.is_active = False
            loser.username = f"merged-{loser.pk}-{uuid.uuid4().hex[:6]}"
            loser.set_unusable_password()
            loser.save()

            # every Google account of both logins can now log in to the survivor
            GoogleIdentity.objects.filter(user=loser).update(user=survivor)
            for google_id, email in ((loser_google, loser_email), (survivor.google_id, survivor.email)):
                if not google_id:
                    continue
                identity, _ = GoogleIdentity.objects.get_or_create(google_id=google_id, defaults={"user": survivor, "email": email})
                if identity.user_id != survivor.pk:
                    identity.user = survivor
                    identity.save(update_fields=["user"])

            for field, value in carry.items():
                setattr(survivor, field, value)
            if carry_password:
                survivor.password = carry_password
            survivor.save()

        Customer.objects.filter(pk=drop.pk).update(user=None)
        keep.refresh_from_db()
        if survivor and keep.user_id != survivor.pk:
            keep.user = survivor
        for field in ("email", "whatsapp", "second_phone", "company"):
            if not getattr(keep, field) and getattr(drop, field):
                setattr(keep, field, getattr(drop, field))
        if not keep.name or keep.name == keep.phone:
            keep.name = drop.name
        if not keep.phone:
            keep.phone = drop.phone
        keep.has_password = bool(survivor and survivor.has_usable_password()) or keep.has_password
        keep.save()

        _move_related(keep, drop, protect_cart_ids)
        drop.delete()

    return keep
