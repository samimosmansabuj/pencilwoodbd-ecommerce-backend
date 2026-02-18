from rest_framework import views, status, permissions
from .models import Category
from rest_framework.response import Response
from .serializers import ProductSerializer, CategorySerializer
from site_app.models import LandingPageProduct
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from authentication.models import Customer
from order.models import Order, OrderItem
from product.models import Product
from django.db import transaction

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
            product = Product.objects.get(id=id)
            return product
        except Product.DoesNotExist:
            raise ValueError("Product not found")
    
    def check_order_amount(self, product, data):
        unit_price = data.get("unit_price")
        subtotal = data.get("subtotal")
        district = data.get("district")
        delivery = data.get("delivery")
        total = data.get("total")
        
        if product.discount_price and product.discount_price != unit_price:
            raise ValueError("Unit price doesn't match with product price")
        
        if district == "dhaka" and delivery != 60:
            raise ValueError("Delivery charge for Dhaka should be 60")
        elif district == "chattogram" and delivery != 120:
            raise ValueError("Delivery charge for outside Chittagong should be 120")
        elif district not in ["chattogram", "dhaka"] and delivery != 150:
            raise ValueError("Delivery charge for outside Dhaka and Chittagong should be 150")
        
        if subtotal != product.discount_price * int(data.get("quantity", 1)):
            raise ValueError("Subtotal doesn't match with product price")
        if total != subtotal + delivery:
            raise ValueError("Total doesn't match with subtotal + delivery")
        
        quantity = int(data.get("quantity", 1))
        total_cost = product.discount_price * quantity
        return total_cost, quantity, subtotal, delivery
    
    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                data = request.data
                
                # Product Section---
                product = self.get_product_object(data.get("product_id"))
                total_cost, quantity, subtotal, delivery = self.check_order_amount(product, data)

                # Customer Section---
                customer = self.get_customer_data(data)
                address = self.get_address(data)
                
                order = Order.objects.create(
                    customer=customer,
                    shipping_address=address,
                    note=data.get("note", ""),
                    shipping_total=delivery,
                    total_cost=total_cost
                )

                # Create OrderItem
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    price=product.price,
                    discount_price=product.discount_price if product.discount_price else product.price,
                    discount_total_price=product.discount_price * quantity if product.discount_price else product.price * quantity
                )

                return Response(
                    {"status": True, "message": "Order received successfully"},
                    status=status.HTTP_201_CREATED
                )
        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
