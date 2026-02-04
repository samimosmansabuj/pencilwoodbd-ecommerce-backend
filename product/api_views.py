from rest_framework import views, status, permissions
from .models import Category
from rest_framework.response import Response
from .serializers import ProductSerializer
from site_app.models import LandingPageProduct

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

class ProductViews(views.APIView):
    permission_classes = [permissions.AllowAny]
    def get(self, request, *args, **kwargs):
        try:
            landing_page = LandingPageProduct.objects.first()
            if landing_page:
                main = [landing_page.main_product] if landing_page.main_product else []
                many = list(landing_page.product.all())
                product = main + many
                # product = landing_page.product.all()
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
