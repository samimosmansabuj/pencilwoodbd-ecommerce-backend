from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from product.models import Attribute, Tag
from product.serializers import AttributeSerializer, TagSerializer

class AttributeAPIViews(viewsets.ModelViewSet):
    queryset = Attribute.objects.prefetch_related("values").all()
    serializer_class = AttributeSerializer
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        try:
            attributes = Attribute.objects.prefetch_related("values").all()
            return Response(
                {"status": True, "data": AttributeSerializer(attributes, many=True).data},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

class TagAPIViews(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        try:
            q = request.query_params.get("q")
            if q:
                tags = Tag.objects.filter(name__icontains=q)[:5]
            else:
                tags = Tag.objects.all()[:5]
            return Response(
                {"status": True, "data": TagSerializer(tags, many=True).data},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        try:
            serializer = TagSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(
                    {"status": True, "message": "Tag created successfully", "data": serializer.data},
                    status=status.HTTP_201_CREATED
                )
            return Response({"status": False, "message": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)