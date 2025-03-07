from rest_framework import viewsets
from rest_framework import permissions, status, generics
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser
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




class SiteContentView(generics.RetrieveUpdateAPIView):
    serializer_class = SiteContentSerializer
    permission_classes = [AdminCreationPermision]
    
    def get_object(self):
        return SiteContent.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'message': 'No Site Content Found!'
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        site_content = self.get_object()
        if not site_content:
            return self.handle_no_content()

        return Response({
                'status': True,
                'data': self.get_serializer(site_content).data
            }, status=status.HTTP_200_OK)
    
    def content_update(self, site_content, request):
        serializer = self.get_serializer(site_content, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'message': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
    
    def patch(self, request, *args, **kwargs):
        site_content = self.get_object()
        if not site_content:
            return self.handle_no_content()
        return self.content_update(site_content, request)
    
    def put(self, request, *args, **kwargs):
        site_content = self.get_object()
        if not site_content:
            return self.handle_no_content()
        return self.content_update(site_content, request)

class SiteColorSectionView(generics.RetrieveUpdateAPIView):
    serializer_class = SiteColorSectionSerializer
    permission_classes = [AdminCreationPermision]
    
    def get_object(self):
        return SiteColorSection.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'message': 'No Site Content Found!'
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        site_content = self.get_object()
        if not site_content:
            return self.handle_no_content()
        return Response({
                'status': True,
                'data': self.get_serializer(site_content).data
            }, status=status.HTTP_200_OK)
    
    def content_update(self, site_content, request):
        serializer = self.get_serializer(site_content, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'message': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
    
    def patch(self, request, *args, **kwargs):
        site_content = self.get_object()
        if not site_content:
            return self.handle_no_content()
        return self.content_update(site_content, request)
    
    def put(self, request, *args, **kwargs):
        site_content = self.get_object()
        if not site_content:
            return self.handle_no_content()
        return self.content_update(site_content, request)


class AboutUsView(generics.RetrieveUpdateAPIView):
    serializer_class = AboutUsSerializer
    permission_classes = [AdminCreationPermision]
    
    def get_object(self):
        return AboutUs.objects.all().first()
    
    def handle_no_content(self):
        return Response({
            'status': False,
            'message': 'No Site Content Found!'
        }, status=status.HTTP_404_NOT_FOUND)
    
    def get(self, request, *args, **kwargs):
        site_content = self.get_object()
        if not site_content:
            return self.handle_no_content()
        return Response({
                'status': True,
                'data': self.get_serializer(site_content).data
            }, status=status.HTTP_200_OK)
    
    def content_update(self, site_content, request):
        serializer = self.get_serializer(site_content, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'status': False,
                'message': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
    
    def patch(self, request, *args, **kwargs):
        site_content = self.get_object()
        if not site_content:
            return self.handle_no_content()
        return self.content_update(site_content, request)
    
    def put(self, request, *args, **kwargs):
        site_content = self.get_object()
        if not site_content:
            return self.handle_no_content()
        return self.content_update(site_content, request)




class AboutWhyChooseUsViewSet(viewsets.ModelViewSet):
    queryset = About_WhyChooseUs.objects.all()
    serializer_class = AboutWhyChooseUsSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

class ContactInformationViewSet(viewsets.ModelViewSet):
    queryset = ContactInformation.objects.all()
    serializer_class = ContactInformationSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

class RefundPolicyViewSet(viewsets.ModelViewSet):
    queryset = RefundPolicy.objects.all()
    serializer_class = RefundPolicySerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

class TermsAndConditionViewSet(viewsets.ModelViewSet):
    queryset = TermsAndCondition.objects.all()
    serializer_class = TermsAndConditionSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

class PrivacyPolicyViewSet(viewsets.ModelViewSet):
    queryset = PrivacyPolicy.objects.all()
    serializer_class = PrivacyPolicySerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]

class FAQListViewSet(viewsets.ModelViewSet):
    queryset = FAQ_List.objects.all()
    serializer_class = FAQListSerializer
    permission_classes = [AdminCreationPermision]
    parser_classes = [MultiPartParser]
