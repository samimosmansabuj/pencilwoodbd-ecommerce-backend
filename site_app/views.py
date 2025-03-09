from rest_framework import viewsets
from django.shortcuts import get_object_or_404
from django.http import Http404
from rest_framework import permissions, status, generics
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    HomeSlider, SiteContent, SiteColorSection, NewsFeed, SocialLink, FooterTagLink, 
    AboutUs, About_WhyChooseUs, ContactInformation, RefundPolicy, TermsAndCondition, 
    PrivacyPolicy, FAQ_List
)
from .serializers import (
    HomeSliderSerializer, SiteContentSerializer, SiteColorSectionSerializer, 
    NewsFeedSerializer, SocialLinkSerializer, FooterTagLinkSerializer, AboutUsSerializer, 
    AboutWhyChooseUsSerializer, ContactInformationSerializer, RefundPolicySerializer, 
    TermsAndConditionSerializer, PrivacyPolicySerializer, FAQListSerializer
)

class CustomPagenumberpagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def paginate_queryset(self, queryset, request, view=None):
        all_items = request.query_params.get('all', 'false').lower() == 'true'
        page_size = request.query_params.get(self.page_size_query_param)
        if all_items or (page_size and page_size.isdigit() and int(page_size) == 0):
            self.all_data = queryset
            return None
        return super().paginate_queryset(queryset, request, view)
    
    def get_paginated_response(self, data):
        return Response(
            {
                'status': True,
                'count': self.page.paginator.count,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'data': data
            }, status=status.HTTP_200_OK
        )

class AdminCreationPermision(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.user_type in {'Admin', 'Super Admin', 'Staff'}



class HomeSliderViewSet(viewsets.ModelViewSet):
    queryset = HomeSlider.objects.all()
    serializer_class = HomeSliderSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    filter_backends = [DjangoFilterBackend]
    search_fields = ['title', 'image_url', 'url']
    filterset_fields = ['is_active']
    pagination_class = None
    
    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        return Response({
            'status': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response({
                'status': True,
                'message': 'Slider Successfully Created!',
                'data': serializer.data
            }, status=status.HTTP_201_CREATED, headers=headers)
        else:
            error_dict = serializer.errors
            error_json = {kay: str(value[0]) for kay, value in error_dict.items()}
            return Response({
                'status': False,
                'message': 'Slider creation failed!',
                'data': error_json
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            'status': True,
            'message': 'Slider Successfully Updated!',
            'data': response.data
        }, status=status.HTTP_200_OK)
    
    def handle_exception(self, exc):
        if isinstance(exc, Http404):
            return Response({
                'status': False,
                'message': 'No Slider matches the given query.'
            }, status=status.HTTP_404_NOT_FOUND)
        return super().handle_exception(exc)
    
    def retrieve(self, request, *args, **kwargs):
        queryset = HomeSlider.objects.all()
        obj = get_object_or_404(queryset, pk=kwargs.get('pk'))
        serializer = self.get_serializer(obj)
        return Response({
            'status': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        return Response({
            'status': True,
            'message': 'Slider Successfully Deleted!',
        }, status=status.HTTP_200_OK)

















class NewsFeedViewSet(viewsets.ModelViewSet):
    queryset = NewsFeed.objects.all()
    serializer_class = NewsFeedSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

class SocialLinkViewSet(viewsets.ModelViewSet):
    queryset = SocialLink.objects.all()
    serializer_class = SocialLinkSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

class FooterTagLinkViewSet(viewsets.ModelViewSet):
    queryset = FooterTagLink.objects.all()
    serializer_class = FooterTagLinkSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

class FAQListViewSet(viewsets.ModelViewSet):
    queryset = FAQ_List.objects.all()
    serializer_class = FAQListSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]








# =================================Site Content Start===============================
class SiteContentView(generics.RetrieveUpdateAPIView):
    serializer_class = SiteContentSerializer
    permission_classes = [AdminCreationPermision]
    
    def get_object(self):
        return SiteContent.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'data' : "No Site Content Found!"
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return Response({
            'status': True,
            'data': self.get_serializer(data).data
        }, status=status.HTTP_200_OK)
    
    def handle_object_update(self, request, data):
        serializer = self.get_serializer(data, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

    def patch(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

# =================================Site Content Start===============================


# =================================Site Color Start===============================
class SiteColorSectionView(generics.RetrieveUpdateAPIView):
    serializer_class = SiteColorSectionSerializer
    permission_classes = [AdminCreationPermision]
    
    def get_object(self):
        return SiteColorSection.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'data' : "No Site Color Content Found!"
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return Response({
            'status': True,
            'data': self.get_serializer(data).data
        }, status=status.HTTP_200_OK)
    
    def handle_object_update(self, request, data):
        serializer = self.get_serializer(data, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

    def patch(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

# =================================Site Color Start===============================


# =================================About Us Start===============================
class AboutUsView(generics.RetrieveUpdateAPIView):
    serializer_class = AboutUsSerializer
    permission_classes = [AdminCreationPermision]
    
    def get_object(self):
        return AboutUs.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'data' : "No About Us Content Found!"
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return Response({
            'status': True,
            'data': self.get_serializer(data).data
        }, status=status.HTTP_200_OK)
    
    def handle_object_update(self, request, data):
        serializer = self.get_serializer(data, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

    def patch(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)


class AboutWhyChooseUsViewSet(viewsets.ModelViewSet):
    queryset = About_WhyChooseUs.objects.all()
    serializer_class = AboutWhyChooseUsSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

# =================================About Us Start===============================

# =================================Contact Information Start===============================
class ContactInformationView(generics.RetrieveUpdateAPIView):
    serializer_class = ContactInformationSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    
    def get_object(self):
        return ContactInformation.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'data' : "No Contact Information Found!"
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return Response({
            'status': True,
            'data': self.get_serializer(data).data
        }, status=status.HTTP_200_OK)
    
    def handle_object_update(self, request, data):
        serializer = self.get_serializer(data, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

    def patch(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

# =================================Contact Information Start===============================

# =================================Refund Policy Start===============================
class RefundPolicyView(generics.RetrieveUpdateAPIView):
    serializer_class = RefundPolicySerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    
    def get_object(self):
        return RefundPolicy.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'data' : "No Refund Policy Content Found!"
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return Response({
            'status': True,
            'data': self.get_serializer(data).data
        }, status=status.HTTP_200_OK)
    
    def handle_object_update(self, request, data):
        serializer = self.get_serializer(data, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

    def patch(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

# =================================Refund Policy Start===============================

# =================================Terms & Condition Start===============================
class TermsAndConditionView(generics.RetrieveUpdateAPIView):
    serializer_class = TermsAndConditionSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    
    def get_object(self):
        return TermsAndCondition.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'data' : "No Terms & Condition Content Found!"
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return Response({
            'status': True,
            'data': self.get_serializer(data).data
        }, status=status.HTTP_200_OK)
    
    def handle_object_update(self, request, data):
        serializer = self.get_serializer(data, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

    def patch(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

# =================================Terms & Condition Start===============================

# =================================Privacy Policy Start===============================
class PrivacyPolicyView(generics.RetrieveUpdateAPIView):
    serializer_class = PrivacyPolicySerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    
    def get_object(self):
        return PrivacyPolicy.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'data' : "No Privacy Policy Content Found!"
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return Response({
            'status': True,
            'data': self.get_serializer(data).data
        }, status=status.HTTP_200_OK)
    
    def handle_object_update(self, request, data):
        serializer = self.get_serializer(data, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'data': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

    def patch(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content()
        return self.handle_object_update(request, data)

# =================================Privacy Policy Start===============================


