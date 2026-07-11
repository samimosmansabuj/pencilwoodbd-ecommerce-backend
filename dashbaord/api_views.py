from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from product.models import Attribute
from product.serializers import AttributeSerializer

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