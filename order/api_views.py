import json
import traceback
from datetime import timedelta
from django.utils import timezone
from django.views import View
from rest_framework import permissions, status, views
from rest_framework.response import Response
from authentication.models import Customer
from authentication.account_merge import (
    REQUIRE_OTP_FOR_ACCOUNT_LINK, MergeConflict, customers_by_phone, merge_customer_accounts,
    resolve_order_address, verify_phone_otp,
)
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from product.models import Product, AddToCart
from offers import engine as offers_engine
from offers.engine import OfferError
from pencilwoodbd.choices import PRODUCT_GIFT_TYPE, PAYMENT_STATUS, PAYMENT_TYPE, STATUS, CATEGORY_PRODUCT_STATUS
from django.db import transaction
from order.models import Order, OrderItem, Shipment, Address, Payment, PaymentMethod, OrderAttempt, OrderActivityLog
from .utils import OrderConfirmatinoEmailSend, safe_order_bill
from site_app.order_otp import order_otp_gate
from site_app.models import DeliveryOption, OTPVerification, WebhookLog, LandingPageProduct
from .serializers import DeliveryOptionSerializer, ShipmentSerializer
from product.models import Product, ProductVariant, clean_customization_note, resolve_is_customized, customization_extra
from rest_framework.permissions import IsAuthenticated, AllowAny
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from pencilwoodbd.choices import USER_TYPE, ORDER_SOURCE
from authentication.utils import normalize_bd_phone, get_client_identity, check_is_blocked, record_order_track, get_or_verify_otp_override, get_blocked_order_policy
from authentication.courier_check import courier_gate
from authentication.courier_restricted import record_restricted_attempt
from authentication.courier_badge import render_courier_badge
from site_app.delivery_charge import (
    DeliveryChargeResolver, compute_regular_charge, get_delivery_rule, line_delivery_charges,
)
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from marketing.models import Coupon, CouponUsage
from pencilwoodbd.extra_module import safe_error_message
from site_app.bd_districts import normalize_district
from campaigns import checkout as campaign_checkout, delivery as campaign_delivery
from campaigns.models import Campaign

class DeliveryOptionListAPIView(views.APIView):
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, *args, **kwargs):
        try:
            delivery_options = DeliveryOption.objects.filter(is_active=True)
            serializer = DeliveryOptionSerializer(delivery_options, many=True)
            return Response(
                {
                    "success": True,
                    "delivery_options": serializer.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": safe_error_message(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class ShipmentSerializerAPIView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            order_id = kwargs.get("order_id")
            shipment = Shipment.objects.filter(order__id=order_id)
            if not shipment.exists():
                return Response(
                    {
                        "success": False,
                        "message": "No shipment information found for this order."
                    }, status=status.HTTP_404_NOT_FOUND
                )
            serializer = ShipmentSerializer(shipment, many=True)
            return Response(
                {
                    "success": True,
                    "message": "Shipment information!",
                    "data": serializer.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": safe_error_message(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class CustomerAddressListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        customer = getattr(request.user, "customer_profile", None)
        if not customer:
            return Response({"status": False, "message": "No customer profile found."}, status=400)

        addresses = Address.objects.filter(customer=customer, is_deleted=False).order_by("-id")

        return Response({
            "status": True,
            "data": [
                {
                    "id": a.id,
                    "name": customer.name,
                    "phone": customer.phone,
                    "address": a.street_01,
                    "district": a.district,
                    "upazila": a.upazila,
                }
                for a in addresses
            ]
        })

    def post(self, request):
        customer = getattr(request.user, "customer_profile", None)
        if not customer:
            return Response({"status": False, "message": "No customer profile found."}, status=400)

        street_01 = (request.data.get("address") or "").strip()
        district = normalize_district((request.data.get("district") or "").strip())
        upazila = (request.data.get("upazila") or "N/A").strip() or "N/A"
        name = (request.data.get("name") or "").strip()
        phone = (request.data.get("phone") or "").strip()

        if not street_01 or not district:
            return Response({"status": False, "message": "Address and district are required."}, status=400)

        if name and name != customer.name:
            customer.name = name
        norm_phone = normalize_bd_phone(phone) if phone else ""
        if norm_phone and norm_phone != customer.phone:
            customer.phone = norm_phone
        customer.save()

        addr = Address.objects.create(
            customer=customer,
            street_01=street_01,
            district=district,
            upazila=upazila,
        )

        return Response({
            "status": True,
            "message": "Address saved",
            "data": {
                "id": addr.id,
                "name": customer.name,
                "phone": customer.phone,
                "address": addr.street_01,
                "district": addr.district,
                "upazila": addr.upazila,
            }
        }, status=201)


class CustomerAddressDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, address_id):
        customer = getattr(request.user, "customer_profile", None)
        if not customer:
            return Response({"status": False, "message": "No customer profile found."}, status=400)

        addr = Address.objects.filter(id=address_id, customer=customer).first()
        if not addr:
            return Response({"status": False, "message": "Address not found."}, status=404)

        street_01 = (request.data.get("address") or "").strip()
        district = normalize_district((request.data.get("district") or "").strip())
        upazila = (request.data.get("upazila") or addr.upazila or "N/A").strip() or "N/A"
        name = (request.data.get("name") or "").strip()
        phone = (request.data.get("phone") or "").strip()

        if not street_01 or not district:
            return Response({"status": False, "message": "Address and district are required."}, status=400)

        if name and name != customer.name:
            customer.name = name
        norm_phone = normalize_bd_phone(phone) if phone else ""
        if norm_phone and norm_phone != customer.phone:
            customer.phone = norm_phone
        customer.save()

        addr.street_01 = street_01
        addr.district = district
        addr.upazila = upazila
        addr.save()

        return Response({
            "status": True,
            "message": "Address updated",
            "data": {
                "id": addr.id,
                "name": customer.name,
                "phone": customer.phone,
                "address": addr.street_01,
                "district": addr.district,
                "upazila": addr.upazila,
            }
        })

    def delete(self, request, address_id):
        customer = getattr(request.user, "customer_profile", None)
        if not customer:
            return Response({"status": False, "message": "No customer profile found."}, status=400)

        addr = Address.objects.filter(id=address_id, customer=customer, is_deleted=False).first()
        if not addr:
            return Response({"status": False, "message": "Address not found."}, status=404)

        addr.is_deleted = True
        addr.save(update_fields=["is_deleted"])
        return Response({"status": True, "message": "Address deleted"})
    
    
# @method_decorator(csrf_exempt, name='dispatch')
# class SteadfastWebhookView(View):
#     def post(self, request):
#         try:
#             data = json.loads(request.body)
#         except Exception:
#             return JsonResponse({"success": False, "message": "Invalid payload."}, status=400)

#         WebhookLog.objects.create(source='steadfast', payload=data)

#         consignment_id = data.get("consignment_id") or data.get("cid")
#         delivery_status = data.get("delivery_status") or data.get("status")

#         if not consignment_id:
#             return JsonResponse({"success": False, "message": "Missing consignment_id."}, status=400)

#         shipment = Shipment.objects.filter(tracking_number=str(consignment_id)).first()
#         if not shipment:
#             return JsonResponse({"success": False, "message": "Shipment not found."}, status=404)

#         shipment.status = delivery_status or shipment.status
#         shipment.save(update_fields=["status"])

#         # Optional: map courier status to Order status if you want auto-sync
#         status_map = {
#             "delivered": STATUS.DELIVERED,
#             "cancelled": STATUS.CANCELLED,
#             "returned": STATUS.RETURNED,
#         }
#         mapped = status_map.get((delivery_status or "").lower())
#         if mapped:
#             shipment.order.status = mapped
#             shipment.order.save(update_fields=["status"])

#         return JsonResponse({"success": True})

def build_gift_line_items(product, quantity, district=None):
    gift_lines = []
    gift_rows = product.gift_product.select_related("gift_product").all()

    for gift in gift_rows:
        gift_product = gift.gift_product
        if not gift_product:
            continue

        base_price = gift_product.discount_price or gift_product.price
        base_price = Decimal(str(base_price or 0))

        if gift.gift_type == PRODUCT_GIFT_TYPE.FREE:
            unit_price = Decimal("0")
        elif gift.gift_type == PRODUCT_GIFT_TYPE.FLAT:
            unit_price = base_price - Decimal(str(gift.value))
            if unit_price < 0:
                unit_price = Decimal("0")
        elif gift.gift_type == PRODUCT_GIFT_TYPE.DISCOUNT:
            unit_price = base_price * (Decimal("1") - Decimal(str(gift.value)) / Decimal("100"))
        else:
            unit_price = base_price

        line_total = unit_price * quantity

        gift_lines.append({
            "cart_id": None,
            "product_id": gift_product.id,
            "variant_id": None,
            "product": gift_product.name,
            "variant": None,
            "quantity": quantity,
            "price": unit_price,
            "total": line_total,
            "delivery_charge": 0,
            "is_gift": True,
            "gift_type": gift.gift_type,
            "gift_value": gift.value,
            "reference_product_id": product.id,
        })

    return gift_lines

def customization_payload(product, is_customized, variant=None):
    return {
        "is_customized": bool(is_customized),
        "customization_mode": product.customization_mode,
        "customization_price": float(customization_extra(product, is_customized, variant)),
        "customization_fields": (product.customization_fields or []) if is_customized else [],
        "customization_placeholder": (product.customization_placeholder or "") if is_customized else "",
    }


class CheckoutSummaryAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            selected_district = request.query_params.get("district")
            items_data = []
            results = []
            subtotal = Decimal("0")
            total_delivery_charge = Decimal("0")

            if request.user.is_authenticated and getattr(request.user, "customer_profile", None):
                customer = request.user.customer_profile
                cart_ids = request.query_params.getlist("cart_ids")
                cart_items = AddToCart.objects.select_related("product", "variant", "campaign").filter(customer=customer)
                if cart_ids:
                    cart_items = cart_items.filter(id__in=cart_ids)

                if not cart_items.exists():
                    return Response({"status": False, "message": "Cart empty"}, status=400)

                cart_rows = [ci for ci in cart_items if not ci.product.is_gift_only]
                resolved = campaign_checkout.resolve_lines([
                    {"product": ci.product, "variant": ci.variant, "quantity": ci.quantity,
                     "campaign_slug": ci.campaign.slug if ci.campaign_id else None,
                     "line_id": ci.id, "is_customized": ci.is_customized}
                    for ci in cart_rows
                ])
                # The summary never fails because a campaign ended / ran out: those lines fall back to the
                # regular price and are flagged (campaign_valid=false) so the checkout page can show the
                # "price changed" panel. Only Place Order answers 409 price_changed.
                results.extend(resolved)

                for item, line_result in zip(cart_rows, resolved):
                    product = item.product
                    # the delivery charge is decided once for the whole cart below (compute_regular_charge)
                    row = {
                        "cart_id": item.id,
                        "product_id": product.id,
                        "slug": product.slug,
                        "variant_id": item.variant.id if item.variant else None,
                        "product": product.name,
                        "variant": item.variant.attributes if item.variant else None,
                        "customization_note": item.customization_note or "",
                        **customization_payload(product, item.is_customized, item.variant),
                        "quantity": item.quantity,
                        "price": item.price,
                        "total": item.total_price,
                        "delivery_charge": 0,
                        "is_gift": False,
                    }
                    if line_result.applies:
                        row["price"] = line_result.regular_unit_price
                        row["total"] = line_result.line_total
                        row.update(campaign_checkout.line_pricing_payload(line_result))
                    elif line_result.is_campaign_line:
                        row.update(campaign_checkout.line_pricing_payload(line_result))
                    items_data.append(row)
                    subtotal += row["total"]

                    if line_result.gifts_included:
                        gift_lines = build_gift_line_items(product, item.quantity, selected_district)
                        for gift_line in gift_lines:
                            items_data.append(gift_line)
                            subtotal += gift_line["total"]
            else:
                import json as pyjson
                raw_items = request.query_params.get("items")
                guest_items = pyjson.loads(raw_items) if raw_items else []

                if not guest_items:
                    return Response({"status": False, "message": "Cart empty"}, status=400)

                prepared = []
                for line_index, row in enumerate(guest_items):
                    product = Product.objects.filter(id=row.get("product_id")).first()
                    if not product or product.is_gift_only:
                        continue
                    variant = None
                    if row.get("variant_id"):
                        variant = ProductVariant.objects.filter(id=row["variant_id"], product=product).first()
                    prepared.append((
                        line_index, row, product, variant,
                        int(row.get("quantity", 1)),
                        resolve_is_customized(product, row.get("is_customized")),
                    ))

                resolved = campaign_checkout.resolve_lines([
                    {"product": pr[2], "variant": pr[3], "quantity": pr[4], "is_customized": pr[5],
                     "campaign_slug": (str(pr[1].get("campaign") or "").strip() or None), "line_id": pr[0],
                     "surface": pr[1].get("surface")}
                    for pr in prepared
                ])
                # The summary never fails because a campaign ended / ran out: those lines fall back to the
                # regular price and are flagged (campaign_valid=false) so the checkout page can show the
                # "price changed" panel. Only Place Order answers 409 price_changed.
                results.extend(resolved)

                for (line_index, row, product, variant, quantity, row_is_customized), line_result in zip(prepared, resolved):
                    extra = customization_extra(product, row_is_customized, variant)
                    price = variant.price if variant else product.price
                    discount_price = ((variant.discount_price if variant else product.discount_price) or price) + extra
                    line_total = discount_price * quantity
                    if line_result.applies:
                        discount_price = line_result.final_unit_price
                        line_total = line_result.line_total

                    items_data.append({
                        "cart_id": None,
                        "product_id": product.id,
                        "slug": product.slug,
                        "variant_id": variant.id if variant else None,
                        "product": product.name,
                        "variant": variant.attributes if variant else None,
                        "customization_note": clean_customization_note(product, row.get("customization_note"), row_is_customized),
                        **customization_payload(product, row_is_customized, variant),
                        "line_index": line_index,
                        "quantity": quantity,
                        "price": discount_price,
                        "total": line_total,
                        "delivery_charge": 0,
                        "is_gift": False,
                        **(campaign_checkout.line_pricing_payload(line_result) if line_result.is_campaign_line else {}),
                    })
                    subtotal += line_total

                    if line_result.gifts_included:
                        gift_lines = build_gift_line_items(product, quantity, selected_district)
                        for gift_line in gift_lines:
                            items_data.append(gift_line)
                            subtotal += gift_line["total"]

            # ---------- Delivery: before a district is chosen show the LOWEST charge ----------
            delivery_rule = get_delivery_rule()
            delivery_info = {
                "district_selected": bool(selected_district),
                "count_mode": delivery_rule[0],
                "order_wise_amount_source": delivery_rule[1],
            }
            regular_charge = None
            if campaign_delivery.has_custom_delivery(results):
                custom = campaign_delivery.compute_delivery(results, selected_district)
                total_delivery_charge = custom["total"]
                delivery_breakdown = custom["breakdown"]
                for it in items_data:
                    if not it.get("is_gift"):
                        it["delivery_charge"] = 0
                if custom["range"]:
                    rng = custom["range"]
                    delivery_info.update({
                        "min": float(rng["min"]), "max": float(rng["max"]), "varies": rng["varies"],
                        "min_district": rng["min_district"],
                        "groups": [{"charge": float(g["charge"]), "districts": g["districts"]} for g in rng["groups"]],
                    })
            elif not selected_district and items_data:
                # estimate: the cheapest district's order charge (the server's rule decides, not the browser)
                pids = {it["product_id"] for it in items_data if not it.get("is_gift")}
                prods = list(Product.objects.select_related("delivery_charge").filter(id__in=pids))
                rng = DeliveryChargeResolver.cart_range(prods)
                if rng:
                    total_delivery_charge = rng["min"]
                    regular_charge = compute_regular_charge(prods, rng["min_district"], rule=delivery_rule)
                    paid_rows = [it for it in items_data if not it.get("is_gift")]
                    for it, amount in zip(paid_rows, line_delivery_charges([it["product_id"] for it in paid_rows], regular_charge)):
                        it["delivery_charge"] = float(amount)
                    delivery_info.update({
                        "min": float(rng["min"]), "max": float(rng["max"]), "varies": rng["varies"],
                        "min_district": rng["min_district"],
                        "groups": [{"charge": float(g["charge"]), "districts": g["districts"]} for g in rng["groups"]],
                    })
            elif selected_district and items_data:
                regular_charge = compute_regular_charge(
                    [r.product for r in results], selected_district, rule=delivery_rule)
                total_delivery_charge = regular_charge["amount"]
                paid_rows = [it for it in items_data if not it.get("is_gift")]
                for it, amount in zip(paid_rows, line_delivery_charges([it["product_id"] for it in paid_rows], regular_charge)):
                    it["delivery_charge"] = float(amount)
            if not campaign_delivery.has_custom_delivery(results):
                delivery_breakdown = campaign_delivery.plain_breakdown(
                    results, selected_district, total_delivery_charge, charge=regular_charge)

            # ---------- Offers (buy X get Y free) ----------
            offers_ui = []
            try:
                import json as _json
                raw_picks = request.query_params.get("offer_picks")
                offer_picks = _json.loads(raw_picks) if raw_picks else {}
            except ValueError:
                offer_picks = {}
            paid_lines = campaign_checkout.offer_engine_lines(
                [it for it in items_data if not it.get("is_gift")]
            )
            offer_result = offers_engine.evaluate(
                paid_lines, picks=offer_picks, strict=False, abs_url=request.build_absolute_uri
            )
            offers_ui = offer_result["offers"]
            for gl in offer_result["gift_lines"]:
                gp = gl["product"]
                img = gp.primary_image
                items_data.append({
                    "cart_id": None,
                    "product_id": gp.id,
                    "variant_id": gl["variant"].id if gl["variant"] else None,
                    "product": gp.name,
                    "variant": gl["variant"].attributes if gl["variant"] else None,
                    "quantity": gl["quantity"],
                    "price": 0,
                    "total": 0,
                    "delivery_charge": 0,
                    "is_gift": True,
                    "gift_type": "FREE",
                    "gift_value": 0,
                    "offer_id": gl["offer"].id,
                    "offer_name": gl["offer"].name,
                    "image": request.build_absolute_uri(img) if img else "",
                })

            grand_total = subtotal + total_delivery_charge

            return Response({
                "status": True,
                "data": {
                    "items": items_data,
                    "offers": offers_ui,
                    "delivery_info": delivery_info,
                    "delivery_breakdown": delivery_breakdown,
                    "has_campaign": any(r.applies for r in results),
                    "subtotal": subtotal,
                    "delivery_charge": total_delivery_charge,
                    "grand_total": grand_total
                }
            })

        except Exception as e:
            return Response({"status": False, "message": safe_error_message(e)}, status=500)
        
        
class PlaceOrderAPIView(APIView):
    permission_classes = [AllowAny]  

    def post(self, request):
        try:
            phone = normalize_bd_phone(request.data.get("phone", ""))
            ip, user_agent, device_hash = get_client_identity(request)
            blocked = check_is_blocked(ip, device_hash, phone=phone)

            otp_override_verified = False
            if blocked:
                blocked_mode, blocked_msg = get_blocked_order_policy()
                if blocked_mode == "deny":
                    return Response(
                        {"status": False, "blocked": True, "otp_required": False, "message": blocked_msg},
                        status=403,
                    )
                elif blocked_mode == "allow":
                    otp_override_verified = True
                else:
                    otp_code = request.data.get("otp_code")
                    if otp_code:
                        otp_override_verified = get_or_verify_otp_override(phone, otp_code)

                    if not otp_override_verified:
                        return Response(
                            {
                                "status": False,
                                "otp_required": True,
                                "phone": phone,
                                "message": "Apnar account block kora ase. Age OTP verify korun.",
                            },
                            status=403,
                        )

            gate = courier_gate(phone, "ecom", otp_code=request.data.get("otp_code"))
            if gate.response:
                if gate.restricted:
                    record_restricted_attempt(request, phone, gate, "ecom")
                return Response({"status": False, **gate.response}, status=gate.status_code)
            otp_override_verified = otp_override_verified or gate.otp_verified
            _otp_resp = order_otp_gate(request, phone, "ecom", "status")
            if _otp_resp is not None:
                return _otp_resp

            with transaction.atomic():
                name = request.data.get("name")
                address_text = request.data.get("address")
                district = normalize_district(request.data.get("district"))
                upazila = request.data.get("upazila") or "N/A"

                INVALID_DISTRICT_VALUES = ["", "জেলা নির্বাচন করুন", "district select", "select district", "n/a", "none"]

                if not phone or not name or not address_text or not district or district.strip().lower() in INVALID_DISTRICT_VALUES:
                    return Response(
                        {"status": False, "message": "Please select a valid district"},
                        status=400
                    )

                cart_ids_in_request = request.data.get("cart_ids", [])
                items_in_request = request.data.get("items", [])
                customization_notes = request.data.get("customization_notes") or {}
                if not isinstance(customization_notes, dict):
                    customization_notes = {}

                auth_customer = getattr(request.user, "customer_profile", None) if request.user.is_authenticated else None
                if cart_ids_in_request and not auth_customer:
                    return Response(
                        {"status": False, "message": "Please log in to check out with your saved cart."},
                        status=401,
                    )

                cart_owner = auth_customer
                phone_accounts = list(customers_by_phone(phone))

                if auth_customer:
                    others = [c for c in phone_accounts if c.pk != auth_customer.pk]
                    own_phone = normalize_bd_phone(auth_customer.phone or "")

                    if others and (not own_phone or own_phone == phone):
                        # This number already has an account: link both accounts into one.
                        if REQUIRE_OTP_FOR_ACCOUNT_LINK and not (
                            otp_override_verified or verify_phone_otp(phone, request.data.get("otp_code"))
                        ):
                            return Response(
                                {
                                    "status": False,
                                    "otp_required": True,
                                    "phone": phone,
                                    "message": "This number already has an account. Verify it with the OTP to link it with your account.",
                                },
                                status=403,
                            )
                        customer = auth_customer
                        try:
                            for other in others:
                                customer = merge_customer_accounts(
                                    customer, other, login_user=request.user, protect_cart_ids=cart_ids_in_request
                                )
                            cart_owner = customer
                        except MergeConflict:
                            traceback.print_exc()
                            customer = others[0]
                    elif others:

                        customer = others[0]
                    else:
                        customer = auth_customer

                    if customer.pk == auth_customer.pk or cart_owner.pk == customer.pk:
                        update_fields = []
                        if customer.phone != phone:
                            customer.phone = phone
                            update_fields.append("phone")
                        if name and not customer.name:
                            customer.name = str(name)[:50]
                            update_fields.append("name")
                        if update_fields:
                            customer.save(update_fields=update_fields)
                else:
                    if phone_accounts:
                        customer = phone_accounts[0]
                        customer.name = name
                        customer.save()
                    else:
                        customer = Customer.objects.create(phone=phone, name=name)

                if cart_ids_in_request:
                    cart_ids = cart_ids_in_request
                    if not cart_ids:
                        return Response({"status": False, "message": "No cart items selected"}, status=400)

                    cart_items = AddToCart.objects.select_related("product", "variant", "campaign").filter(
                        customer=cart_owner, id__in=cart_ids
                    )
                    if not cart_items.exists():
                        return Response({"status": False, "message": "Cart empty"}, status=400)

                    active_cart_items = [
                        ci for ci in cart_items if ci.product.status == CATEGORY_PRODUCT_STATUS.ACTIVE
                    ]
                    if not active_cart_items:
                        return Response({"status": False, "message": "Cart items are no longer available"}, status=400)

                    line_items = []
                    for ci in active_cart_items:
                        override = customization_notes.get(str(ci.id))
                        line_items.append({
                            "product": ci.product, "variant": ci.variant, "quantity": ci.quantity,
                            "campaign_slug": ci.campaign.slug if ci.campaign_id else None, "line_id": ci.id,
                            "is_customized": resolve_is_customized(ci.product, ci.is_customized),
                            "customization_note": clean_customization_note(
                                ci.product,
                                override if override is not None else ci.customization_note,
                                resolve_is_customized(ci.product, ci.is_customized),
                            ),
                        })
                    should_delete_cart = cart_items
                else:
                    raw_items = items_in_request
                    if not raw_items:
                        return Response({"status": False, "message": "No cart items"}, status=400)

                    line_items = []
                    for row_index, row in enumerate(raw_items):
                        product = Product.objects.filter(
                            id=row.get("product_id"), status=CATEGORY_PRODUCT_STATUS.ACTIVE
                        ).first()
                        if not product:
                            continue
                        variant = None
                        if row.get("variant_id"):
                            variant = ProductVariant.objects.filter(
                                id=row["variant_id"], product=product, is_active=True
                            ).first()
                        row_is_customized = resolve_is_customized(product, row.get("is_customized"))
                        override = customization_notes.get(str(row_index))
                        line_items.append({
                            "product": product, "variant": variant,
                            "quantity": int(row.get("quantity", 1)),
                            "campaign_slug": (str(row.get("campaign") or "").strip() or None), "line_id": row_index,
                            "surface": row.get("surface"),
                            "is_customized": row_is_customized,
                            "customization_note": clean_customization_note(
                                product,
                                override if override is not None else row.get("customization_note"),
                                row_is_customized,
                            ),
                        })

                    if not line_items:
                        return Response({"status": False, "message": "Cart empty"}, status=400)
                    should_delete_cart = None

                gift_only_names = [l["product"].name for l in line_items if l["product"].is_gift_only]
                if gift_only_names:
                    return Response(
                        {"status": False, "message": f"{', '.join(gift_only_names)} is a gift item and cannot be ordered on its own"},
                        status=400,
                    )

                for line in line_items:
                    if line.get("is_customized") and not (line.get("customization_note") or "").strip():
                        return Response(
                            {"status": False, "message": f"Please write the customization for {line['product'].name}"},
                            status=400,
                        )

                address = resolve_order_address(
                    customer, request.data.get("address_id"), address_text, district, upazila
                )

                _slug_ids = {
                    c.slug: c.id for c in Campaign.objects.filter(
                        slug__in={l["campaign_slug"] for l in line_items if l.get("campaign_slug")}
                    )
                }
                requested_signature = sorted(
                    (
                        line["product"].id,
                        line["variant"].id if line["variant"] else None,
                        line["quantity"],
                        line.get("customization_note") or "",
                        _slug_ids.get(line.get("campaign_slug")) or 0,
                    )
                    for line in line_items
                )

                recent_candidates = Order.objects.filter(
                    customer=customer,
                    shipping_address=address.street_01,
                    created_at__gte=timezone.now() - timedelta(seconds=30),
                ).prefetch_related("order_items")

                for candidate in recent_candidates:
                    candidate_signature = sorted(
                        (oi.product_id, oi.variant_id, oi.quantity, oi.customization_note or "", oi.campaign_id or 0)
                        for oi in candidate.order_items.all()
                        if not (oi.snapshot or {}).get("is_gift")
                    )
                    if candidate_signature == requested_signature:
                        return Response(
                            {
                                "status": True,
                                "duplicate": True,
                                "message": "We already received this order a moment ago.",
                                "order_id": candidate.order_id,
                            },
                            status=201,
                        )

                campaign_results = campaign_checkout.resolve_lines(line_items, lock=True)
                changed = campaign_checkout.price_changed_payload(campaign_results)
                if changed:
                    return Response(changed, status=409)
                has_campaign = any(r.applies for r in campaign_results)

                coupon_code = request.data.get("coupon_code")
                discount_amount = Decimal("0")
                applied_coupon = None
                coupon_note = None

                coupon_lines, coupon_excluded = campaign_checkout.coupon_split(campaign_results)
                cart_subtotal = Decimal("0")
                for r in coupon_lines:
                    cart_subtotal += r.final_unit_price * r.quantity

                if coupon_code:
                    applied_coupon = Coupon.objects.select_for_update().filter(
                        code__iexact=str(coupon_code).strip()
                    ).first()
                    if not applied_coupon:
                        return Response({"status": False, "message": "Invalid coupon code."}, status=400)
                    if coupon_excluded and not coupon_lines:
                        return Response(
                            {"status": False, "code": "coupon_not_applicable_to_campaign",
                             "message": campaign_checkout.COUPON_CAMPAIGN_MESSAGE},
                            status=400,
                        )
                    if coupon_excluded:
                        coupon_note = campaign_checkout.coupon_exclusion_note(coupon_excluded)

                    product_ids_in_cart = [r.product.id for r in coupon_lines]
                    discount_amount, coupon_error, _tier = applied_coupon.evaluate(
                        phone=customer.phone,
                        subtotal=cart_subtotal,
                        landing_page=None,
                        product_ids=product_ids_in_cart,
                    )
                    if coupon_error:
                        return Response({"status": False, "message": coupon_error}, status=400)

                # ---------- Offers: strict validation before anything is written ----------
                try:
                    offer_result = offers_engine.evaluate(
                        campaign_checkout.offer_engine_lines([
                            {"product_id": r.product.id, "variant_id": r.variant.id if r.variant else None,
                             "quantity": r.quantity, "offers_included": r.offers_included}
                            for r in campaign_results
                        ]),
                        picks=request.data.get("offer_picks") or {},
                        strict=True,
                    )
                except OfferError as oe:
                    return Response({"status": False, "message": str(oe)}, status=400)

                order = Order.objects.create(
                    customer=customer,
                    shipping_address=address.street_01,
                    district=address.district,
                    coupon=applied_coupon,
                    source=ORDER_SOURCE.WEBSITE,
                    note=(str(request.data.get("note") or "").strip()[:1000] or None),
                    utm_source=request.data.get("utm_source"),
                    utm_medium=request.data.get("utm_medium"),
                    utm_campaign=request.data.get("utm_campaign"),
                    click_id=request.data.get("click_id"),
                    referrer=request.data.get("referrer"),
                    landing_url=request.data.get("landing_url"),
                    placed_while_blocked=otp_override_verified,
                    has_campaign=has_campaign,
                )

                if applied_coupon:
                    CouponUsage.objects.create(
                        coupon=applied_coupon,
                        phone=customer.phone,
                        order=order,
                        discount_applied=discount_amount,
                    )

                total = Decimal("0")
                # regular delivery charge: the same central function as the checkout summary
                regular_charge = compute_regular_charge([l["product"] for l in line_items], district)
                total_delivery_charge = regular_charge["amount"]

                for line, line_result in zip(line_items, campaign_results):
                    product = Product.objects.select_for_update().get(id=line["product"].id)
                    variant = (
                        ProductVariant.objects.select_for_update().get(id=line["variant"].id)
                        if line["variant"] else None
                    )
                    quantity = line["quantity"]

                    if variant:
                        if variant.inventory_quantity < quantity:
                            transaction.set_rollback(True)
                            return Response({"status": False, "message": f"{product.name} out of stock"}, status=400)
                        variant.inventory_quantity -= quantity
                        variant.save()
                        product.inventory_quantity = sum(
                            v.inventory_quantity for v in product.variants.filter(is_active=True)
                        )
                        product.save(update_fields=["inventory_quantity"])
                        price = variant.price
                        discount_price = variant.discount_price or variant.price
                    else:
                        if not product.is_in_stock:
                            transaction.set_rollback(True)
                            return Response({"status": False, "message": f"{product.name} out of stock"}, status=400)
                        if product.inventory_type == "in_stock":
                            if product.inventory_quantity < quantity:
                                transaction.set_rollback(True)
                                return Response({"status": False, "message": f"{product.name} out of stock"}, status=400)
                            product.inventory_quantity -= quantity
                            product.save(update_fields=["inventory_quantity"])

                        price = product.price
                        discount_price = product.discount_price or product.price

                    item_note = line.get("customization_note") or ""
                    line_is_customized = bool(line.get("is_customized"))
                    extra = customization_extra(product, line_is_customized, variant)
                    price = price + extra
                    discount_price = discount_price + extra
                    item_snapshot = {
                        "is_gift": False,
                        "customized": line_is_customized,
                        "customization_price": float(extra),
                    }
                    if line_result.applies:
                        discount_price = line_result.final_unit_price
                        item_snapshot.update(campaign_checkout.campaign_snapshot(line_result))
                    OrderItem.objects.create(
                        order=order, product=product, variant=variant, product_name=product.name,
                        quantity=quantity, price=price, discount_price=discount_price,
                        customization_note=item_note or None,
                        snapshot=item_snapshot,
                        **campaign_checkout.order_item_campaign_fields(line_result),
                    )
                    total += discount_price * quantity

                    gift_rows = product.gift_product.select_related("gift_product").all() if line_result.gifts_included else []
                    for gift in gift_rows:
                        gift_product = gift.gift_product
                        if not gift_product:
                            continue

                        gift_base_price = gift_product.discount_price or gift_product.price
                        gift_base_price = Decimal(str(gift_base_price or 0))

                        if gift.gift_type == PRODUCT_GIFT_TYPE.FREE:
                            gift_unit_price = Decimal("0")
                        elif gift.gift_type == PRODUCT_GIFT_TYPE.FLAT:
                            gift_unit_price = gift_base_price - Decimal(str(gift.value))
                            if gift_unit_price < 0:
                                gift_unit_price = Decimal("0")
                        elif gift.gift_type == PRODUCT_GIFT_TYPE.DISCOUNT:
                            gift_unit_price = gift_base_price * (Decimal("1") - Decimal(str(gift.value)) / Decimal("100"))
                        else:
                            gift_unit_price = gift_base_price

                        if gift_product.has_variants:
                            gift_variant = gift_product.variants.filter(is_active=True).select_for_update().first()
                            if gift_variant and gift_variant.inventory_quantity >= quantity:
                                gift_variant.inventory_quantity -= quantity
                                gift_variant.save()
                                gift_product.inventory_quantity = sum(
                                    v.inventory_quantity for v in gift_product.variants.filter(is_active=True)
                                )
                                gift_product.save(update_fields=["inventory_quantity"])
                        else:
                            gift_product = Product.objects.select_for_update().get(id=gift_product.id)
                            if gift_product.inventory_type == "in_stock" and gift_product.inventory_quantity >= quantity:
                                gift_product.inventory_quantity -= quantity
                                gift_product.save(update_fields=["inventory_quantity"])

                        OrderItem.objects.create(
                            order=order,
                            product=gift_product,
                            variant=None,
                            product_name=gift_product.name,
                            quantity=quantity,
                            price=Decimal("0"),
                            discount_price=gift_unit_price,
                            snapshot={
                                "is_gift": True,
                                "gift_type": gift.gift_type,
                                "gift_value": gift.value,
                                "reference_product_id": product.id,
                            },
                        )
                        total += gift_unit_price * quantity

                # ---------- Offers: add free items (price 0), deduct stock ----------
                applied_offers = {}
                for gl in offer_result["gift_lines"]:
                    gqty = gl["quantity"]
                    gp = Product.objects.select_for_update().get(id=gl["product"].id)
                    gv = None
                    if gp.has_variants:
                        gv = (
                            ProductVariant.objects.select_for_update().filter(id=gl["variant"].id).first()
                            if gl["variant"] else None
                        )
                        if not gv or gv.inventory_quantity < gqty:
                            transaction.set_rollback(True)
                            return Response({"status": False, "message": f"{gp.name} out of stock"}, status=400)
                        gv.inventory_quantity -= gqty
                        gv.save()
                        gp.inventory_quantity = sum(v.inventory_quantity for v in gp.variants.filter(is_active=True))
                        gp.save(update_fields=["inventory_quantity"])
                    elif gp.inventory_type == "in_stock":
                        if gp.inventory_quantity < gqty:
                            transaction.set_rollback(True)
                            return Response({"status": False, "message": f"{gp.name} out of stock"}, status=400)
                        gp.inventory_quantity -= gqty
                        gp.save(update_fields=["inventory_quantity"])
                    elif not gp.is_in_stock:
                        transaction.set_rollback(True)
                        return Response({"status": False, "message": f"{gp.name} out of stock"}, status=400)

                    OrderItem.objects.create(
                        order=order, product=gp, variant=gv, product_name=gp.name,
                        quantity=gqty, price=Decimal("0"), discount_price=Decimal("0"),
                        snapshot={
                            "is_gift": True,
                            "gift_type": "FREE",
                            "gift_value": 0,
                            "source": "offer",
                            "offer_id": gl["offer"].id,
                            "offer_name": gl["offer"].name,
                            "tier_buy_qty": gl["tier"].buy_qty,
                        },
                    )
                    rec = applied_offers.setdefault(gl["offer"].id, {
                        "offer_id": gl["offer"].id, "name": gl["offer"].name,
                        "tier_buy_qty": gl["tier"].buy_qty, "gifts": [],
                    })
                    rec["gifts"].append({"product_id": gp.id, "name": gp.name, "quantity": gqty})

                if applied_offers:
                    promos = order.promotions_applied if isinstance(order.promotions_applied, dict) else {}
                    promos["offers"] = list(applied_offers.values())
                    order.promotions_applied = promos

                if campaign_delivery.has_custom_delivery(campaign_results):
                    custom_delivery = campaign_delivery.compute_delivery(campaign_results, district)
                    total_delivery_charge = custom_delivery["total"]
                    order.delivery_breakdown = custom_delivery["breakdown"]
                else:
                    # every order stores the rule used, so staff can see how the charge was calculated
                    order.delivery_breakdown = campaign_delivery.plain_breakdown(
                        campaign_results, district, total_delivery_charge, charge=regular_charge)

                if coupon_note:
                    promos = order.promotions_applied if isinstance(order.promotions_applied, dict) else {}
                    promos["coupon_excluded_campaign_items"] = coupon_note
                    order.promotions_applied = promos

                order.total_cost = total + total_delivery_charge - discount_amount
                order.shipping_total = total_delivery_charge
                order.coupon_discount = discount_amount
                order.save()

                if should_delete_cart is not None:
                    should_delete_cart.delete()

                # ----- Clean up matching order-attempt(s) for this phone -----
                order_product_ids = set(order.order_items.values_list("product_id", flat=True))
                for attempt in OrderAttempt.objects.filter(phone=customer.phone):
                    if attempt.status != "converted" and attempt.is_subset_of(order_product_ids):
                        attempt.set_status("converted", "Auto: customer placed order #%s" % order.pk)

                OrderActivityLog.log(
                    action="Order placed by customer (self-checkout)",
                    order=order,
                    user=None,
                )

                record_order_track(order, request)
                return Response({
                    "status": True,
                    "message": "Order placed successfully",
                    "order_id": order.order_id,
                    "bill": safe_order_bill(order, request),
                })

        except Exception as e:
            return Response({"status": False, "message": safe_error_message(e)}, status=500)
        

class OrderListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        customer = request.user.customer_profile

        orders = (
            Order.objects
            .filter(customer=customer)
            .prefetch_related(
                "order_items",
                "order_items__product",
                "order_items__product__images",
                "order_items__variant"
            )
            .order_by("-created_at")
        )

        data = []

        for order in orders:

            items = []

            for item in order.order_items.all():

                image = ""

                if item.product:
                    _img = item.product.variant_image_url(item.variant)
                    if _img:
                        image = request.build_absolute_uri(_img)

                items.append({
                    "name": item.product_name,
                    "qty": item.quantity,
                    "price": item.price,
                    "image": image,
                    "variant": item.variant.attributes if item.variant else None,
                    "customization_note": item.customization_note or "",
                    "customization_price": float(item.customization_unit_price),
                    "is_gift": item.is_gift,
                })

            data.append({
                "order_id": order.order_id,
                "date": order.created_at.strftime("%d %b %Y"),
                "status": order.status,
                "payment_status": order.payment_status,
                "total": order.total_cost,
                "items": items,
                "thumbnail": items[0]["image"] if items else "",
                "item_count": order.get_total_quantity
            })

        return Response({
            "status": True,
            "data": data
        })   


class OrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):

        try:

            customer = request.user.customer_profile

            order = get_object_or_404(
                Order,
                order_id=order_id,
                customer=customer
            )

            items = []
            subtotal = Decimal("0")

            for item in order.order_items.all():

                item_total = (
                    item.discount_total_price
                    if item.discount_total_price
                    else item.price * item.quantity
                )

                subtotal += item_total

                image = None

                try:

                    if item.product:
                        _img = item.product.variant_image_url(item.variant)
                        if _img:
                            image = request.build_absolute_uri(_img)

                except Exception:
                    image = None

                items.append({
                    "name": (
                        item.product_name
                        or (
                            item.product.name
                            if item.product
                            else "Product"
                        )
                    ),

                    "image": image,

                    "qty": item.quantity,

                    "price": item.price,

                    "total": item_total,

                    "variant": (
                        item.variant.attributes
                        if item.variant
                        else None
                    ),

                    "customization_note": item.customization_note or "",
                    "base_price": float(item.base_unit_price),
                    "customization_price": float(item.customization_unit_price),
                    "customization_total": float(item.customization_total_price),
                    "is_gift": item.is_gift,
                })

            data = {
                "order_id": order.order_id,

                "date": order.created_at,

                "status": order.status,

                "payment_status": order.payment_status,
                "payment_type": order.payment_type,

                "subtotal": subtotal,
                "shipping": order.shipping_total,
                "total": order.total_cost,

                "customer_name": (
                    customer.name
                    if customer
                    else ""
                ),

                "customer_company": (
                    customer.company
                    if customer and customer.company
                    else ""
                ),

                "customer_phone": (
                    customer.phone
                    if customer
                    else ""
                ),

                "customer_courier_badge": (
                    render_courier_badge(customer.phone)
                    if customer
                    else ""
                ),

                "address": order.shipping_address,

                "note": order.note or "",

                "items": items
            }

            return Response({
                "status": True,
                "data": data
            })

        except Exception as e:

            return Response(
                {
                    "status": False,
                    "message": safe_error_message(e)
                },
                status=500
            )

class PaymentMethodListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        methods = PaymentMethod.objects.all()

        return Response({
            "status": True,
            "data": [
                {
                    "id": m.id,
                    "name": m.payment_option,
                    "account_number": m.account_number,
                    "account_name": m.account_name
                }
                for m in methods
            ]
        })


class CreatePaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            customer = request.user.customer_profile

            order_id = request.data.get("order_id")
            payment_method_id = request.data.get("payment_method_id")
            transaction_id = request.data.get("transaction_id")

            order = Order.objects.filter(
                order_id=order_id,
                customer=customer
            ).first()

            if not order:
                return Response(
                    {"status": False, "message": "Order not found"},
                    status=404
                )

            if order.payment_status == PAYMENT_STATUS.Paid:
                return Response(
                    {"status": False, "message": "Already paid"},
                    status=400
                )

            payment_method = PaymentMethod.objects.filter(
                id=payment_method_id
            ).first()

            if not payment_method:
                return Response(
                    {"status": False, "message": "Invalid payment method"},
                    status=400
                )

            payment = Payment.objects.create(
                order=order,
                payment_method=payment_method,
                provider=payment_method.payment_option,
                amount=order.total_cost,
                transaction_id=transaction_id,
                status="pending"
            )

            order.payment_type = PAYMENT_TYPE.ONLINE
            order.payment_status = PAYMENT_STATUS.Pending
            order.save()

            return Response({
                "status": True,
                "message": "Payment submitted",
                "payment_id": payment.id
            })

        except Exception as e:
            return Response(
                {"status": False, "message": safe_error_message(e)},
                status=500
            )


class VerifyPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        if request.user.user_type not in [
            USER_TYPE.ADMIN,
            USER_TYPE.SUPER_ADMIN
        ]:
            return Response(
                {"status": False, "message": "Permission denied"},
                status=403
            )

        try:
            payment_id = request.data.get("payment_id")
            status_value = request.data.get("status")

            if status_value not in ["success", "failed"]:
                return Response(
                    {"status": False, "message": "Invalid status"},
                    status=400
                )

            payment = Payment.objects.filter(
                id=payment_id
            ).select_related("order").first()

            if not payment:
                return Response(
                    {"status": False, "message": "Payment not found"},
                    status=404
                )

            payment.status = status_value
            payment.save()

            if status_value == "success":
                payment.order.payment_status = PAYMENT_STATUS.Paid
            else:
                payment.order.payment_status = PAYMENT_STATUS.Failed

            payment.order.save()

            return Response({
                "status": True,
                "message": "Payment verified"
            })

        except Exception as e:
            return Response(
                {"status": False, "message": safe_error_message(e)},
                status=500
            )


# class EcomOrderCreateAPIView(APIView):
#     permission_classes = [AllowAny]

#     def post(self, request):
#         try:
#             with transaction.atomic():

#                 data = request.data
#                 items = data.get("items", [])

#                 if not items:
#                     return Response({"status": False, "message": "No items"}, status=400)

#                 total = Decimal("0")
#                 order_items = []

#                 customer = None
#                 if request.user.is_authenticated:
#                     customer = getattr(request.user, "customer_profile", None)
#                 else:
#                     customer, _ = Customer.objects.get_or_create(
#                         phone=data.get("phone"),
#                         defaults={"name": data.get("name")}
#                     )

#                 address = Address.objects.create(
#                     customer=customer,
#                     street_01=data.get("address"),
#                     upazila=data.get("upazila"),
#                     district=data.get("district"),
#                 )

#                 order = Order.objects.create(
#                     customer=customer,
#                     shipping_address=f"{address.street_01}, {address.district}"
#                 )

#                 for item in items:
#                     product = Product.objects.filter(id=item["product_id"]).first()
#                     variant = None

#                     if item.get("variant_id"):
#                         variant = ProductVariant.objects.filter(id=item["variant_id"]).first()
#                         price = variant.price
#                         variant.inventory_quantity -= item["quantity"]
#                         variant.save()
#                     else:
#                         price = product.price
#                         product.inventory_quantity -= item["quantity"]
#                         product.save()

#                     total += price * item["quantity"]

#                     OrderItem.objects.create(
#                         order=order,
#                         product=product,
#                         variant=variant,
#                         quantity=item["quantity"],
#                         price=price
#                     )

#                 order.total_cost = total
#                 order.save()

#                 return Response({
#                     "status": True,
#                     "order_id": order.order_id
#                 })

#         except Exception as e:
#             return Response({"status": False, "message": str(e)}, status=400)