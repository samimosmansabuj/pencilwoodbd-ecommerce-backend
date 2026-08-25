from datetime import timedelta
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.db import transaction
from django.db.models import F
from decimal import Decimal
from product.serializers import ProductSerializer
from .models import HomeSlider, NewsFeed, LandingPageProduct
from product.models import Product, Category, ProductVariant
from pencilwoodbd.choices import (
    CATEGORY_PRODUCT_STATUS,
    STATUS,
    PRODUCT_GIFT_TYPE,
    PAYMENT_TYPE,
    PAYMENT_STATUS,
    ORDER_SOURCE,
)
from order.models import Order, OrderItem
from authentication.models import Customer
from site_app.models import OTPVerification
from order.utils import OrderConfirmatinoEmailSend
from authentication.utils import normalize_bd_phone, get_client_identity, check_is_blocked, record_order_track
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from marketing.models import Coupon, CouponUsage

# =========================
# HOME PAGE
# =========================
class HomePageAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        sliders = HomeSlider.objects.filter(is_active=True)
        news = NewsFeed.objects.filter(is_active=True)

        products = Product.objects.filter(status=CATEGORY_PRODUCT_STATUS.ACTIVE)[:10]

        categories = Category.objects.filter(
            status=CATEGORY_PRODUCT_STATUS.ACTIVE, parent__isnull=True
        )

        return Response(
            {
                "status": True,
                "data": {
                    "sliders": [
                        {"image": s.image.url if s.image else None} for s in sliders
                    ],
                    "news": [{"text": n.news} for n in news],
                    "products": [
                        {"id": p.id, "name": p.name, "price": p.price} for p in products
                    ],
                    "categories": [{"id": c.id, "name": c.name} for c in categories],
                },
            }
        )


# =========================
# LANDING PAGE (READ ONLY)
# =========================
class LandingPageProductViews(APIView):
    permission_classes = [AllowAny]

    def get(self, request, code, *args, **kwargs):
        try:
            landing_page = LandingPageProduct.objects.get(code=code)
            if landing_page:
                main = [landing_page.main_product] if landing_page.main_product else []
                many = list(landing_page.product.all())
                product = main + many
                return Response(
                    {
                        "status": True,
                        "data": {
                            "code": landing_page.code,
                            "title": landing_page.title,
                            "description": landing_page.description,
                            "product": ProductSerializer(
                                product, many=True, context={"request": request}
                            ).data,
                        },
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {"status": False, "message": "Landing page product not setup."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except LandingPageProduct.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Product ID doesn't match, Please use valid product id.",
                }
            )
        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# =========================
# LANDING ORDER (SAFE FINAL VERSION)
# =========================


@method_decorator(csrf_exempt, name='dispatch')
class LandingPageOrderAPI(APIView):
    permission_classes = [AllowAny]
    
    def get_customer_data(self, data):
        name = data.get("name")
        phone = normalize_bd_phone(data.get("phone"))
        whatsapp = data.get("whatsapp_number", "")
        if not name or not phone:
            raise ValueError("Name and phone are required")
        customer, created = Customer.objects.get_or_create(
            phone=phone,
            defaults={"name": name, "whatsapp": whatsapp}
        )
        return customer

    INVALID_DISTRICT_VALUES = ["", "জেলা নির্বাচন করুন", "district select", "select district", "n/a", "none"]

    def get_address(self, data):
        address = data.get("address")
        district = data.get("district")
        if not address:
            raise ValueError("Address is required")
        if not district or district.strip().lower() in self.INVALID_DISTRICT_VALUES:
            raise ValueError("Please select a valid district")
        return f"{address}, {district}"
    
    def get_product_object(self, id):
        try:
            variant = ProductVariant.objects.select_related("product").get(id=id)
            return variant
        except ProductVariant.DoesNotExist:
            raise ValueError("Variant not found")
    
    # ================= Corrected check_order_amount =================
    def check_order_amount(self, variant, product, data):
        unit_price = Decimal(str(data.get("unit_price")))
        subtotal = Decimal(str(data.get("subtotal")))
        district = data.get("district")
        delivery = Decimal(str(data.get("delivery")))
        total = Decimal(str(data.get("total")))

        # unit_price_expected = 0
        if variant:
            unit_price_expected = variant.discount_price or variant.price
        else:
            unit_price_expected = product.discount_price or product.price

        if unit_price != unit_price_expected:
            raise ValueError("Unit price doesn't match with product price")

        district_lower = district.lower().strip()
        if district_lower == "dhaka" and delivery != Decimal("60"):
            raise ValueError("Delivery charge for Dhaka should be 60")
        elif district_lower == "chattogram" and delivery != Decimal("120"):
            raise ValueError("Delivery charge for outside Chattogram should be 120")
        elif district_lower not in ["dhaka", "chattogram"] and delivery != Decimal("150"):
            raise ValueError("Delivery charge for outside Dhaka and Chattogram should be 150")

        quantity = int(data.get("quantity", 1))
        subtotal_expected = unit_price_expected * quantity
        if subtotal != subtotal_expected:
            raise ValueError("Subtotal doesn't match with product price")
        total_expected = subtotal_expected + delivery
        if total != total_expected:
            raise ValueError("Total doesn't match with subtotal + delivery")
        # total_cost = subtotal_expected

        return total_expected, quantity, subtotal_expected, float(delivery)
    
    def post(self, request, *args, **kwargs):
        try:
            # --- IP / Device block check ---
            ip, user_agent, device_hash = get_client_identity(request)
            blocked = check_is_blocked(ip, device_hash)
            if blocked:
                return Response(
                    {"status": False, "message": "Apnar order ekhon accept kora jacche na. Onugroho kore amader shathe jogajog korun."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            with transaction.atomic():
                data = request.data
                print("data: ", data)
                # Payment validation ----
                payment_type = data.get("payment_type", "COD")
                payment_status = data.get("payment_status", "Unpaid")

                if payment_type not in [pt.value for pt in PAYMENT_TYPE]:
                    raise ValueError("Invalid payment type")
                if payment_status not in [ps.value for ps in PAYMENT_STATUS]:
                    raise ValueError("Invalid payment status")

                # Product Section---
                items = data.get("items")

                variant_id = data.get("variant_id")
                product_id = data.get("product_id")

                if variant_id:
                    variant = self.get_product_object(variant_id)
                    product = variant.product
                elif product_id:
                    product = get_object_or_404(Product, id=product_id)
                    variant = product.variants.filter(is_active=True).first() if product.has_variants else None
                    if product.has_variants and not variant:
                        raise ValueError("No active variant available for this product")

                # Customer Section---
                customer = self.get_customer_data(data)
                address = self.get_address(data)

                total_cost, quantity, subtotal, delivery = self.check_order_amount(variant, product, data)

                coupon_code = data.get("coupon_code")
                landing_page_code = data.get("landing_page_code")
                discount_amount = Decimal("0")
                applied_coupon = None

                if coupon_code:
                    applied_coupon = Coupon.objects.filter(code__iexact=coupon_code).first()
                    if not applied_coupon:
                        raise ValueError("Invalid coupon code.")

                    valid, reason = applied_coupon.is_currently_valid()
                    if not valid:
                        raise ValueError(reason)

                    landing_page = None
                    if landing_page_code:
                        landing_page = LandingPageProduct.objects.filter(code=landing_page_code).first()

                    scope_valid, scope_reason = applied_coupon.is_valid_for_scope(
                        landing_page=landing_page,
                        product_ids=[product.id] if not landing_page else None,
                    )
                    if not scope_valid:
                        raise ValueError(scope_reason)

                    condition_valid, condition_reason = applied_coupon.customer_meets_condition(customer.phone)
                    if not condition_valid:
                        raise ValueError(condition_reason)

                    if not applied_coupon.phone_can_use(customer.phone):
                        raise ValueError("You have already used this coupon.")

                    discount_amount = applied_coupon.calculate_discount(subtotal)

                final_total = total_cost - discount_amount

                recent_duplicate = Order.objects.filter(
                    customer=customer,
                    total_cost=final_total,
                    created_at__gte=timezone.now() - timedelta(seconds=30),
                ).first()

                if recent_duplicate:
                    return Response(
                        {"status": True, "message": "Order received successfully"},
                        status=status.HTTP_201_CREATED
                    )
                
                order = Order.objects.create(
                    customer=customer,
                    shipping_address=address,
                    note=data.get("note", ""),
                    shipping_total=delivery,
                    total_cost=final_total,
                    coupon=applied_coupon,
                    coupon_discount=discount_amount,
                    payment_type=payment_type,
                    payment_status=payment_status,
                    status=STATUS.NEW,
                    source=ORDER_SOURCE.LANDING_PAGE,
                    utm_source=data.get("utm_source"),
                    utm_medium=data.get("utm_medium"),
                    utm_campaign=data.get("utm_campaign"),
                    click_id=data.get("click_id"),
                    referrer=data.get("referrer"),
                    landing_url=data.get("landing_url"),
                )

                if applied_coupon:
                    CouponUsage.objects.create(
                        coupon=applied_coupon,
                        phone=customer.phone,
                        order=order,
                        discount_applied=discount_amount,
                    )

                # Create OrderItem
                unit_price = variant.discount_price or variant.price if variant else product.discount_price or product.price
                OrderItem.objects.create(
                    order=order,
                    variant=variant,
                    product=product,
                    quantity=quantity,
                    product_name=product.name,
                    sku=variant.sku if variant else product.sku,
                    price=unit_price,
                    discount_price=unit_price,
                    discount_total_price=unit_price * quantity,
                )

                # Inventory Deduction -----
                if variant:
                    variant.inventory_quantity -= quantity
                    variant.save()
                    product.inventory_quantity = sum(v.inventory_quantity for v in product.variants.filter(is_active=True))
                else:
                    if product.inventory_quantity < quantity:
                        raise ValueError(f"Not enough inventory for product {product.sku}")
                    product.inventory_quantity -= quantity
                product.save()

                record_order_track(order, request)

                return Response(
                    {"status": True, "message": "Order received successfully"},
                    status=status.HTTP_201_CREATED
                )
        except Exception as e:
            print("Error in LandingPageOrderAPI: ", str(e))
            return Response({"status": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class OrderCreateAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response(
            {"success": False, "message": "Get method not allowed!"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def amount_check(self, data: dict) -> dict:
        if Decimal(str(self.productTotal)) == Decimal(str(data.get("productTotal"))):
            return data
        raise Exception("Total product amount not same.")

    def create_order_item(self, order: object, products, amount):
        order_items = []
        for product in products:
            raw_id = product.get("id")
            try:
                product_id = int(raw_id)
            except (TypeError, ValueError):
                raise Exception(f"Invalid product id in order item: {raw_id!r}")

            prod = Product.objects.get(pk=product_id)
            quantity = int(product.get("quantity", 1))
            unit_price = Decimal(str(product.get("price", 0)))
            is_gift = product.get("product_type") == "FREE"

            order_item = OrderItem.objects.create(
                order=order,
                product=prod,
                quantity=quantity,
                price=Decimal("0") if is_gift else prod.price,
                discount_price=unit_price,
                snapshot={
                    "product_type": product.get("product_type"),
                    "reference_product": product.get("reference_product"),
                    "is_gift": is_gift,
                },
            )
            order_items.append(order_item)

            if prod.has_variants:
                variant = prod.variants.filter(is_active=True).first()
                if variant:
                    if variant.inventory_quantity < quantity:
                        raise Exception(f"Not enough inventory for {prod.name}")
                    variant.inventory_quantity -= quantity
                    variant.save()
                    prod.inventory_quantity = sum(
                        v.inventory_quantity for v in prod.variants.filter(is_active=True)
                    )
                    prod.save(update_fields=["inventory_quantity"])
            else:
                if prod.inventory_quantity < quantity:
                    raise Exception(f"Not enough inventory for {prod.name}")
                prod.inventory_quantity -= quantity
                prod.save(update_fields=["inventory_quantity"])

        return order_items

    def check_free_product(self, reference_product: int, product: object):
        reference = Product.objects.get(pk=reference_product)
        if not reference:
            return False
        for gift_product_object in reference.gift_product.filter(
            gift_type=PRODUCT_GIFT_TYPE.FREE
        ):
            if product == gift_product_object.gift_product:
                return True
        return False

    def get_product_and_verify(self, product_data: dict) -> object:
        products = []
        self.productTotal = 0
        for prod in product_data:
            raw_id = prod.get("id", None)
            if raw_id is None or str(raw_id).strip().lower() in ("undefined", "null", ""):
                raise Exception(f"Invalid product id received: {raw_id!r} for item '{prod.get('name', 'unknown')}'")

            try:
                product_id = int(raw_id)
            except (TypeError, ValueError):
                raise Exception(f"Product id must be numeric, got: {raw_id!r}")

            product = get_object_or_404(Product, pk=product_id)
            if not product:
                raise Exception("No Product Found.")

            product_type = prod.get("product_type")
            reference_product = prod.get("reference_product", None)

            if product_type == "FREE" and reference_product:
                if self.check_free_product(reference_product, product) is False:
                    raise Exception("Free Product not available.")
                products.append(product)
                # NOTE: FREE items don't add to productTotal — price is 0
            elif product.discount_price != float(prod.get("price")):
                raise Exception("Product price and given price are not same.")
            elif product.inventory_quantity < prod.get("quantity"):
                raise Exception("Product not available in our Inventory.")
            else:
                self.productTotal += Decimal(str(product.discount_price)) * Decimal(str(prod.get("quantity", 1)))
                products.append(product)
        return products

    def get_make_address(self, data):
        address = f"{data.get('address')}, {data.get('district')}"
        return address

    def get_customer(self, data):
        phone = normalize_bd_phone(data.get("phone"))
        if not phone:
            raise Exception("A valid Bangladeshi mobile number is required.")
        customer, created = Customer.objects.get_or_create(
            phone=phone, defaults={"name": data.get("name")}
        )
        return customer

    def post(self, request, *args, **kwargs):
        try:
            # --- IP / Device block check ---

            ip, user_agent, device_hash = get_client_identity(request)
            blocked = check_is_blocked(ip, device_hash)
            if blocked:
                return Response(
                    {"success": False, "message": "Apnar order ekhon accept kora jacche na. Onugroho kore amader shathe jogajog korun."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            with transaction.atomic():
                data = request.data
                self.handle_missing_field(data)

                otp_verified = None
                otp_required = bool(data.get("otp_required", False))

                if otp_required:
                    customer_data = data.get("customer", {})
                    phone = customer_data.get("phone", "").strip()
                    if not phone.startswith("88"):
                        phone = "88" + phone

                    otp_verified = OTPVerification.objects.filter(
                        phone=phone, is_verified=True
                    ).last()

                    if not otp_verified:
                        raise Exception("OTP not verified")
                    if otp_verified.is_expired():
                        raise Exception("OTP expired")

                customer = self.get_customer(data.get("customer", {}))
                address = self.get_make_address(data.get("customer", {}))
                products = self.get_product_and_verify(data.get("products", {}))
                amount = self.amount_check(data.get("amount", {}))

                coupon_code = data.get("coupon_code")
                landing_page_code = data.get("landing_page_code")
                discount_amount = Decimal("0")
                applied_coupon = None

                if coupon_code:
                    applied_coupon = Coupon.objects.filter(code__iexact=coupon_code).first()
                    if not applied_coupon:
                        raise Exception("Invalid coupon code.")

                    valid, reason = applied_coupon.is_currently_valid()
                    if not valid:
                        raise Exception(reason)

                    landing_page = None
                    if landing_page_code:
                        landing_page = LandingPageProduct.objects.filter(code=landing_page_code).first()

                    product_ids_in_cart = [p["id"] for p in products] if not landing_page else None
                    scope_valid, scope_reason = applied_coupon.is_valid_for_scope(
                        landing_page=landing_page, product_ids=product_ids_in_cart
                    )
                    if not scope_valid:
                        raise Exception(scope_reason)

                    condition_valid, condition_reason = applied_coupon.customer_meets_condition(customer.phone)
                    if not condition_valid:
                        raise Exception(condition_reason)

                    if not applied_coupon.phone_can_use(customer.phone):
                        raise Exception("You have already used this coupon.")

                    discount_amount = applied_coupon.calculate_discount(self.productTotal)

                metadata_payload = {
                    "source": "landing_page",
                    "district": data.get("customer", {}).get("district"),
                    "raw_products": data.get("products", []),
                    "raw_amount": data.get("amount", {}),
                    "note": data.get("note", ""),
                }

                recent_duplicate = Order.objects.filter(
                    customer=customer,
                    total_cost=amount.get("totalAmount"),
                    created_at__gte=timezone.now() - timedelta(seconds=30),
                ).first()

                if recent_duplicate:
                    return Response(
                        {"success": True, "message": "Order Created", "order_id": recent_duplicate.order_id},
                        status=status.HTTP_201_CREATED,
                    )
                
                delivery_charge = Decimal(str(amount.get("deliveryCharge", 0)))
                final_total = self.productTotal + delivery_charge - discount_amount

                order = Order.objects.create(
                    customer=customer,
                    shipping_address=address,
                    note=data.get("note", ""),
                    shipping_total=delivery_charge,
                    total_cost=final_total,
                    coupon=applied_coupon,
                    coupon_discount=discount_amount,
                    metadata=metadata_payload,
                    source=ORDER_SOURCE.LANDING_PAGE,
                    utm_source=data.get("utm_source"),
                    utm_medium=data.get("utm_medium"),
                    utm_campaign=data.get("utm_campaign"),
                    click_id=data.get("click_id"),
                    referrer=data.get("referrer"),
                    landing_url=data.get("landing_url"),
                )

                if applied_coupon:
                    CouponUsage.objects.create(
                        coupon=applied_coupon,
                        phone=customer.phone,
                        order=order,
                        discount_applied=discount_amount,
                    )

                order_item = self.create_order_item(
                    order, data.get("products", {}), amount
                )

                if otp_required and otp_verified:
                    otp_verified.delete()

                record_order_track(order, request)

                return Response(
                    {"success": True, "message": "Order Created", "order_id": order.order_id},
                    status=status.HTTP_201_CREATED,
                )
        except Exception as e:
            print("error: ", e)
            return Response(
                {"success": False, "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
    def verify_input_amount(self, data):
        if data:
            input_delivery_charge = data["deliveryCharge"]
            data["deliveryCharge"] = (
                "FREE" if input_delivery_charge == 0 else input_delivery_charge
            )
            required_fields = ["productTotal", "deliveryCharge", "totalAmount"]
            missing_fields = [field for field in required_fields if not data.get(field)]
            data["deliveryCharge"] = input_delivery_charge
            return missing_fields
        else:
            raise Exception("Customer amount must be set.")

    INVALID_DISTRICT_VALUES = ["", "জেলা নির্বাচন করুন", "district select", "select district", "n/a", "none"]

    def verify_input_customer(self, data):
        if data:
            required_fields = ["name", "phone", "address", "district"]
            missing_fields = [field for field in required_fields if not data.get(field)]
            district = (data.get("district") or "").strip().lower()
            if "district" not in missing_fields and district in self.INVALID_DISTRICT_VALUES:
                missing_fields.append("district")
            return missing_fields
        else:
            raise Exception("Customer data must be set.")

    def handle_missing_field(self, data):
        customer_missing_fields = self.verify_input_customer(data.get("customer", {}))
        if customer_missing_fields:
            raise Exception(
                f"The following fields must be filled: {', '.join(customer_missing_fields)}"
            )

        amount_missing_fields = self.verify_input_amount(data.get("amount", {}))
        if amount_missing_fields:
            raise Exception(
                f"The following fields must be set: {', '.join(amount_missing_fields)}"
            )
        
class ApplyCouponAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            code = (request.data.get("code") or "").strip()
            phone = normalize_bd_phone(request.data.get("phone") or "")
            subtotal = Decimal(str(request.data.get("subtotal", 0)))
            landing_page_code = request.data.get("landing_page_code")
            product_ids = request.data.get("product_ids") or []

            if not code:
                return Response({"status": False, "message": "Coupon code is required."}, status=400)
            if not phone:
                return Response({"status": False, "message": "Enter a valid phone number first."}, status=400)

            coupon = Coupon.objects.filter(code__iexact=code).first()
            if not coupon:
                return Response({"status": False, "message": "Invalid coupon code."}, status=404)

            valid, reason = coupon.is_currently_valid()
            if not valid:
                return Response({"status": False, "message": reason}, status=400)

            landing_page = None
            if landing_page_code:
                landing_page = LandingPageProduct.objects.filter(code=landing_page_code).first()

            scope_valid, scope_reason = coupon.is_valid_for_scope(
                landing_page=landing_page,
                product_ids=product_ids if not landing_page else None,
            )
            if not scope_valid:
                return Response({"status": False, "message": scope_reason}, status=400)

            condition_valid, condition_reason = coupon.customer_meets_condition(phone)
            if not condition_valid:
                return Response({"status": False, "message": condition_reason}, status=400)

            if not coupon.phone_can_use(phone):
                return Response({"status": False, "message": "You have already used this coupon."}, status=400)

            discount = coupon.calculate_discount(subtotal)
            if discount <= 0:
                return Response({"status": False, "message": f"Minimum order ৳{coupon.min_order_amount} required for this coupon."}, status=400)

            return Response({
                "status": True,
                "message": "Coupon applied successfully.",
                "data": {
                    "code": coupon.code,
                    "discount_amount": float(discount),
                    "new_total": float(subtotal - discount),
                }
            })
        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=500)
        
