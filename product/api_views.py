from rest_framework import views, status, permissions, viewsets
from .models import Category, ProductVariant
from rest_framework.response import Response
from .serializers import ProductSerializer, CategorySerializer
from site_app.models import LandingPageProduct
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from authentication.models import Customer
from order.models import Order, OrderItem
from product.models import Product
from django.db import transaction
from django.shortcuts import get_object_or_404
from decimal import Decimal
from pencilwoodbd.choices import STATUS, PAYMENT_TYPE, PAYMENT_STATUS, CATEGORY_PRODUCT_STATUS, DELIVERY_TYPE
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from django.db.models import Prefetch


class CategoryAPIViews(views.APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request, *args, **kwargs):
        try:
            category_id = request.query_params.get('category')
            if category_id:
                try:
                    category = Category.objects.get(id=category_id)
                    sub_category = category.children.all()
                    return Response(
                        {
                            "status": True,
                            "data": CategorySerializer(sub_category, many=True).data
                        }, status=status.HTTP_200_OK
                    )
                except Category.DoesNotExist:
                    return Response(
                        {
                            "status": False,
                            "message": "Category not found"
                        }, status=status.HTTP_404_NOT_FOUND
                    )
            categories = Category.objects.filter(parent__isnull=True)
            return Response(
                {
                    "status": True,
                    "data": CategorySerializer(categories, many=True, context={"request": request}).data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CradleProductViews(views.APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request, *args, **kwargs):
        try:
            landing_page = LandingPageProduct.objects.first()
            if landing_page:
                main = [landing_page.main_product] if landing_page.main_product else []
                many = list(landing_page.product.all())
                product = main + many
                return Response(
                    {
                        "status": True,
                        "data": ProductSerializer(product, many=True, context={"request": request}).data
                    }, status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {
                        "status": False,
                        "message": "Landing page product not setup."
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class LandingPageProductViews(views.APIView):
    permission_classes = [permissions.AllowAny]
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
                        "data": ProductSerializer(product, many=True, context={"request": request}).data
                    }, status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {
                        "status": False,
                        "message": "Landing page product not setup."
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        except LandingPageProduct.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Product ID doesn't match, Please use valid product id."
                }
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ================= Tissue Box Landing Order =================
@method_decorator(csrf_exempt, name='dispatch')
class LandingPageOrderAPI(views.APIView):
    permission_classes = [permissions.AllowAny]
    
    def get_customer_data(self, data):
        name = data.get("name")
        phone = data.get("phone")
        whatsapp = data.get("whatsapp_number", "")
        if not name or not phone:
            raise ValueError("Name and phone are required")
        customer, created = Customer.objects.get_or_create(
            phone=phone,
            defaults={"name": name, "whatsapp": whatsapp}
        )
        return customer

    def get_address(self, data):
        address = data.get("address")
        district = data.get("district")
        if not address:
            raise ValueError("Address is required")
        if not district:
            raise ValueError("District is required")
        return f"{address}, {district}"
    
    def get_product_object(self, id):
        try:
            variant = ProductVariant.objects.select_related("product").get(id=id)
            return variant
        except ProductVariant.DoesNotExist:
            raise ValueError("Variant not found")
    
    # ================= Corrected check_order_amount =================
    def check_order_amount(self, variant, product, data):
        unit_price = data.get("unit_price")
        subtotal = data.get("subtotal")
        district = data.get("district")
        delivery = data.get("delivery")
        total = data.get("total")

        unit_price_expected = 0
        if variant:
            unit_price_expected = variant.discount_price or variant.price
        else:
            unit_price_expected = product.discount_price or product.price

        if Decimal(str(unit_price)) != unit_price_expected:
            raise ValueError("Unit price doesn't match with product price")

        district_lower = district.lower().strip()
        if district_lower == "dhaka" and float(delivery) != 60:
            raise ValueError("Delivery charge for Dhaka should be 60")
        elif district_lower == "chattogram" and float(delivery) != 120:
            raise ValueError("Delivery charge for outside Chattogram should be 120")
        elif district_lower not in ["dhaka", "chattogram"] and float(delivery) != 150:
            raise ValueError("Delivery charge for outside Dhaka and Chattogram should be 150")

        quantity = int(data.get("quantity", 1))
        subtotal_expected = unit_price_expected * quantity
        if Decimal(str(subtotal)) != subtotal_expected:
            raise ValueError("Subtotal doesn't match with product price")
        total_expected = subtotal_expected + float(delivery)
        if Decimal(str(total)) != total_expected:
            raise ValueError("Total doesn't match with subtotal + delivery")
        total_cost = subtotal_expected

        return total_cost, quantity, subtotal_expected, float(delivery)
        
    
    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                data = request.data
                
                # Payment validation ----
                payment_type = data.get("payment_type", "COD")
                payment_status = data.get("payment_status", "Unpaid")

                if payment_type not in [pt.value for pt in PAYMENT_TYPE]:
                    raise ValueError("Invalid payment type")
                if payment_status not in [ps.value for ps in PAYMENT_STATUS]:
                    raise ValueError("Invalid payment status")


                # Product Section---
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
                
                total_cost, quantity, subtotal, delivery = self.check_order_amount(variant, product, data)


                # Customer Section---
                customer = self.get_customer_data(data)
                address = self.get_address(data)
                
                order = Order.objects.create(
                    customer=customer,
                    shipping_address=address,
                    note=data.get("note", ""),
                    shipping_total=delivery,
                    total_cost=total_cost,
                    payment_type=payment_type,        
                    payment_status=payment_status,    
                    status=STATUS.NEW  
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

                return Response(
                    {"status": True, "message": "Order received successfully"},
                    status=status.HTTP_201_CREATED
                )
        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)









class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "status": True,
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "data": data
        })

# ================= PROFESSIONAL GLOBAL CATEGORY API =================
class GlobalCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardPagination

    def get_queryset(self):
        queryset = Category.objects.filter(
            status=CATEGORY_PRODUCT_STATUS.ACTIVE
        )

        parent_id = self.request.query_params.get("parent_id")
        search = self.request.query_params.get("search")
        ordering = self.request.query_params.get("ordering", "sort_order")

        allowed_ordering = [
            "sort_order", "name", "-name",
            "created_at", "-created_at"
        ]

        if ordering not in allowed_ordering:
            ordering = "sort_order"

        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        else:
            queryset = queryset.filter(parent__isnull=True)

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by(ordering)

# ================= PROFESSIONAL GLOBAL PRODUCT API =================
class GlobalProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardPagination

    def get_queryset(self):
        queryset = Product.objects.filter(
            status=CATEGORY_PRODUCT_STATUS.ACTIVE
        ).select_related(
            "category"
        ).prefetch_related(
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.filter(is_active=True)
            )
        )

        category = self.request.query_params.get("category")
        search = self.request.query_params.get("search")
        min_price = self.request.query_params.get("min_price")
        max_price = self.request.query_params.get("max_price")
        ordering = self.request.query_params.get("ordering", "-created_at")

        allowed_ordering = [
            "price", "-price",
            "created_at", "-created_at",
            "name", "-name"
        ]

        if ordering not in allowed_ordering:
            ordering = "-created_at"

        if category:
            queryset = queryset.filter(category_id=category)

        if search:
            queryset = queryset.filter(name__icontains=search)

        if min_price:
            queryset = queryset.filter(price__gte=Decimal(min_price))

        if max_price:
            queryset = queryset.filter(price__lte=Decimal(max_price))

        return queryset.order_by(ordering)

# ================= ENTERPRISE GLOBAL ORDER CREATE API =================
@method_decorator(csrf_exempt, name='dispatch')
class GlobalOrderCreateApi(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            with transaction.atomic():

                data = request.data
                request_id = data.get("request_id")

                # -------- IDEMPOTENCY CHECK --------
                if request_id and Order.objects.filter(metadata__request_id=request_id).exists():
                    return Response(
                        {"status": False, "message": "Duplicate order submission"},
                        status=400
                    )

                # -------- CUSTOMER --------
                name = data.get("name")
                phone = data.get("phone")
                address = data.get("address")
                district = data.get("district")

                if not all([name, phone, address, district]):
                    raise ValueError("Missing required customer fields")

                customer, _ = Customer.objects.get_or_create(
                    phone=phone,
                    defaults={"name": name}
                )

                full_address = f"{address}, {district}"
                delivery_type = data.get("delivery_type", DELIVERY_TYPE.HOME_DELIVERY)


                order = Order.objects.create(
                    customer=customer,
                    shipping_address=full_address,
                    payment_type=data.get("payment_type", PAYMENT_TYPE.COD),
                    payment_status=PAYMENT_STATUS.Unpaid,
                    status=STATUS.NEW,
                    metadata={"request_id": request_id},
                    delivery_type=delivery_type,
                )

                items = data.get("items", [])
                if not items:
                    raise ValueError("Order must contain at least one item")

                subtotal = Decimal("0")

                # -------- ITEM PROCESS --------
                for item in items:
                    quantity = int(item.get("quantity", 1))
                    if item.get("variant_id"):
                        variant = ProductVariant.objects.select_for_update().select_related("product").get(id=item["variant_id"])
                        product = variant.product

                        if variant.inventory_quantity < quantity:
                            raise ValueError("Insufficient stock")

                        unit_price = variant.discount_price or variant.price
                        variant.inventory_quantity -= quantity
                        variant.save()

                        product.inventory_quantity = sum(
                            v.inventory_quantity for v in product.variants.filter(is_active=True)
                        )
                        product.save(update_fields=["inventory_quantity"])
                    else:
                        product_id = item.get("product_id")
                        if not product_id:
                            raise ValueError("product id required if no variant id")

                        product = Product.objects.select_for_update().get(id=product_id)

                        if product.inventory_quantity < quantity:
                            raise ValueError("Insufficient stock")

                        unit_price = product.discount_price or product.price
                        product.inventory_quantity -= quantity
                        product.save(update_fields=["inventory_quantity"])
                        variant = None

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        variant=variant,
                        quantity=quantity,
                        price=unit_price,
                        discount_price=unit_price,
                        discount_total_price=unit_price * quantity
                    )

                    subtotal += unit_price * quantity


                # -------- UPDATE ORDER METADATA WITH VARIANT SIZE --------
                order_items_data = [
                    {
                        "product_id": item.product.id,
                        "product_name": item.product_name,
                        "variant_id": item.variant.id if item.variant else None,
                        "variant": item.variant.attributes if item.variant else None,
                        "sku": item.sku,
                        "quantity": item.quantity,
                        "price": str(item.price),
                        "discount_price": str(item.discount_price),
                        "discount_total_price": str(item.discount_total_price),
                    }
                    for item in order.order_items.all()
                ]

                order.metadata["items"] = order_items_data
                order.save(update_fields=["metadata"])
                # -------- OPTIONAL TAX --------
                tax_total = Decimal("0")
                if data.get("apply_tax"):
                    tax_percentage = Decimal(str(data.get("tax_percentage", 0)))
                    tax_total = (subtotal * tax_percentage) / 100
                    order.tax_total = tax_total

                # -------- DELIVERY --------
                delivery_charge = Decimal("0")

                if order.delivery_type == DELIVERY_TYPE.HOME_DELIVERY:
                    district_lower = district.lower()
                    delivery_charge = Decimal("60") if district_lower == "dhaka" else Decimal("130")

                order.shipping_total = delivery_charge

                # -------- OPTIONAL COUPON --------
                if data.get("coupon_code"):
                    discount_amount = subtotal * Decimal("0.10")  # Example 10%
                    subtotal -= discount_amount
                    order.promotions_applied = {
                        "coupon": data.get("coupon_code"),
                        "discount": str(discount_amount)
                    }

                # -------- FINAL TOTAL --------
                order.total_cost = subtotal + tax_total + delivery_charge
                order.save()

                return Response(
                    {
                        "status": True,
                        "message": "Order created successfully",
                        "order_id": order.order_id,
                        "total": order.total_cost
                    },
                    status=201
                )

        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=400
            )
        





# class TagAPIViews(views.APIView):
#     permission_classes = [permissions.AllowAny]
    
#     def get(self, request, *args, **kwargs):
#         try:
#             q = request.query_params.get('q')
#             if q:
#                 try:
#                     tags = Tag.objects.filter(name__icontains=q)
#                     print("Tags: ", tags)
#                     return Response(
#                         {
#                             "status": True,
#                             "data": TagSerializer(tags, many=True).data
#                         }, status=status.HTTP_200_OK
#                     )
#                 except Tag.DoesNotExist:
#                     return Response(
#                         {
#                             "status": False,
#                             "message": "Tag not found"
#                         }, status=status.HTTP_404_NOT_FOUND
#                     )
#             tags = Tag.objects.all()
#             return Response(
#                 {
#                     "status": True,
#                     "data": TagSerializer(tags, many=True).data
#                 }, status=status.HTTP_200_OK
#             )
#         except Exception as e:
#             return Response(
#                 {
#                     "status": False,
#                     "message": str(e)
#                 }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
    
#     def post(self, request, *args, **kwargs):
#         try:
#             serializer = TagSerializer(data=request.data)
#             if serializer.is_valid():
#                 serializer.save()
#                 return Response(
#                     {
#                         "status": True,
#                         "message": "Tag created successfully",
#                         "data": serializer.data
#                     }, status=status.HTTP_201_CREATED
#                 )
#             return Response(
#                 {
#                     "status": False,
#                     "message": serializer.errors
#                 }, status=status.HTTP_400_BAD_REQUEST
#             )
#         except Exception as e:
#             return Response(
#                 {
#                     "status": False,
#                     "message": str(e)
#                 }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
