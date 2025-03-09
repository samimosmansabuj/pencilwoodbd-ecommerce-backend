from rest_framework import viewsets
from django.shortcuts import get_object_or_404
from django.http import Http404
from rest_framework import permissions, status, generics
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
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



class CustomModelViewSet(viewsets.ModelViewSet):
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            'status': True,
            'count': len(response.data),
            # 'count': len(response.data) if isinstance(response.data, list) else response.data.get('count', 0),
            'data': response.data
        }, status=status.HTTP_200_OK)
    
    def handle_exception(self, exc):
        if isinstance(exc, Http404):
            return Response({
                'status': False,
                'message': f'No {self.queryset.model().display_name} matches the given query.'
            }, status=status.HTTP_404_NOT_FOUND)
        return super().handle_exception(exc)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response({
                'status': True,
                'message': f"{self.queryset.model().display_name} Successfully Created!",
                'data': serializer.data
            }, status=status.HTTP_201_CREATED, headers=headers)
        else:
            error_json = {kay : str(value[0]) for kay, value in serializer.errors.items()}
            return Response({
                'status': False,
                'message': f'{self.queryset.model().display_name} Creation Failed!',
                'error': error_json
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            'status': True,
            'data': response.data
        }, status=status.HTTP_200_OK)
    
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            'status': True,
            'message': f'{self.queryset.model().display_name} Successfully Updated!',
            'data': response.data
        }, status=status.HTTP_200_OK)
    
    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        return Response({
            'status': True,
            'message': f'{self.queryset.model().display_name} Successfully Deleted!'
        }, status=status.HTTP_200_OK)

class HomeSliderViewSet(CustomModelViewSet):
    queryset = HomeSlider.objects.all()
    serializer_class = HomeSliderSerializer
    search_fields = ['title', 'url']
    filterset_fields = ['is_active']

class NewsFeedViewSet(CustomModelViewSet):
    queryset = NewsFeed.objects.all()
    serializer_class = NewsFeedSerializer
    search_fields = ['news', 'url']
    filterset_fields = ['is_active']

class SocialLinkViewSet(CustomModelViewSet):
    queryset = SocialLink.objects.all()
    serializer_class = SocialLinkSerializer
    search_fiels = ['name', 'url', 'icon']
    filterset_fields = ['is_active']

class FooterTagLinkViewSet(CustomModelViewSet):
    queryset = FooterTagLink.objects.all()
    serializer_class = FooterTagLinkSerializer
    search_fiels = ['name', 'url']
    filterset_fields = ['is_active']

class FAQListViewSet(CustomModelViewSet):
    queryset = FAQ_List.objects.all()
    serializer_class = FAQListSerializer
    search_fiels = ['question', 'answer']
    filterset_fields = ['is_active']
    



class BaseRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    permission_classes = [AdminCreationPermision]
    
    def get_object(self):
        return self.queryset.first()
    
    def hanlde_no_content(self, message):
        return Response({
            'status': False,
            'message': message
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.hanlde_no_content(f"No {self.model_name} Found!")
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
                'message': f'{self.model_name} Successfully Updated!',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'error': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.hanlde_no_content(f"No {self.model_name} Found!")
        return self.handle_object_update(request, data)

    def patch(self, request, *args, **kwargs):
        data = self.get_object()
        if not data:
            return self.handle_no_content(f"No {self.model_name} Found!")
        return self.handle_object_update(request, data)






# =================================About Us Start===============================
class AboutUsView(generics.RetrieveUpdateAPIView):
    queryset = AboutUs.objects.all()
    serializer_class = AboutUsSerializer
    permission_classes = [AdminCreationPermision]
    model_name = "About Us Content"
    

class AboutWhyChooseUsViewSet(viewsets.ModelViewSet):
    queryset = About_WhyChooseUs.objects.all()
    serializer_class = AboutWhyChooseUsSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

# =================================About Us Start===============================



# =================================Site Content Start===============================
class SiteContentView(BaseRetrieveUpdateView):
    queryset = SiteContent.objects.all()
    serializer_class = SiteContentSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    model_name = "Site Content"
    
# =================================Site Content Start===============================
# =================================Site Color Start===============================
class SiteColorSectionView(BaseRetrieveUpdateView):
    queryset = SiteColorSection.objects.all()
    serializer_class = SiteColorSectionSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    model_name = "Site Color Content"
    
# =================================Site Color Start===============================
# =================================Contact Information Start===============================
class ContactInformationView(generics.RetrieveUpdateAPIView):
    queryset = ContactInformation.objects.all()
    serializer_class = ContactInformationSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    model_name = "Contact Information Content"

# =================================Contact Information Start===============================
# =================================Refund Policy Start===============================
class RefundPolicyView(generics.RetrieveUpdateAPIView):
    serializer_class = RefundPolicySerializer
    permission_classes = [AdminCreationPermision]
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    model_name = "Refund Policy Content"

# =================================Refund Policy Start===============================
# =================================Terms & Condition Start===============================
class TermsAndConditionView(generics.RetrieveUpdateAPIView):
    serializer_class = TermsAndConditionSerializer
    permission_classes = [AdminCreationPermision]
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    model_name = "Temrs & Condition Content"

# =================================Terms & Condition Start===============================
# =================================Privacy Policy Start===============================
class PrivacyPolicyView(generics.RetrieveUpdateAPIView):
    serializer_class = PrivacyPolicySerializer
    permission_classes = [AdminCreationPermision]
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
    model_name = "Privacy Policy Content"

# =================================Privacy Policy Start===============================


