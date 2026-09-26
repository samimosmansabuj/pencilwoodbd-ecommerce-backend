from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from django.views import View

from authentication.models import Customer
from .models import ActivityEvent, VisitorProfile, EVENT_TYPE


class CustomerActivityView(LoginRequiredMixin, View):

    login_url = "admin_login"

    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        events = (
            ActivityEvent.objects.filter(customer=customer)
            .select_related("product")
            .order_by("-created_at")
        )

        event_type = request.GET.get("event_type", "").strip()
        if event_type:
            events = events.filter(event_type=event_type)

        per_page = 30
        paginator = Paginator(events, per_page)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        sessions = VisitorProfile.objects.filter(customer=customer).order_by("-last_seen")

        context = {
            "customer": customer,
            "events": page_obj,
            "paginator": paginator,
            "sessions": sessions,
            "event_types": EVENT_TYPE.choices,
            "current_event_type": event_type,
        }

        if request.htmx:
            return render(request, "db_tracking/partial_activity_list.html", context)

        return render(request, "db_tracking/customer_activity.html", context)


class VisitorListView(LoginRequiredMixin, View):
    
    login_url = "admin_login"

    def get(self, request):
        visitors = VisitorProfile.objects.select_related("customer").order_by("-last_seen")

        guest_only = request.GET.get("guest_only") == "1"
        if guest_only:
            visitors = visitors.filter(customer__isnull=True)

        search = request.GET.get("q", "").strip()
        if search:
            visitors = visitors.filter(customer__name__icontains=search)

        paginator = Paginator(visitors, 30)
        page_obj = paginator.get_page(request.GET.get("page", 1))

        context = {
            "visitors": page_obj,
            "paginator": paginator,
            "guest_only": guest_only,
            "current_search": search,
        }

        if request.htmx:
            return render(request, "db_tracking/partial_visitor_list.html", context)

        return render(request, "db_tracking/visitor_list.html", context)
