from django.shortcuts import render, redirect
from django.views.generic import CreateView, UpdateView, DeleteView, ListView
from .forms import ProductForm, CategoryForm, OrderForm, AddressForm, AdminAuthenticationForm
from order.models import Order
from product.models import Product, Category
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.models import LogEntry
from django.utils.timezone import now

def logout_view(request):
    logout(request)
    return redirect('login')

class AdminLoginView(LoginView):
    template_name = 'user/login.html'
    form_class = AdminAuthenticationForm

@login_required()
def index(request):
    recent_activities = LogEntry.objects.filter(action_time__date=now().date()).order_by('-action_time')[:5]
    order = Order.objects.all().order_by('-created_at')
    return render(request, 'home/index.html', {'recent_activities': recent_activities, 'order': order})





# =============================Order Section Start==============================
class OrdertListView(LoginRequiredMixin, ListView):
    model = Order
    form_class = OrderForm
    template_name = 'order/list.html'
    context_object_name = 'orders'

# class OrderCreateView(CreateView):
#     model = Order
#     form_class = OrderForm
#     template_name = 'order/order_form.html'
#     success_url = reverse_lazy('product_list')

class OrderUpdateView(LoginRequiredMixin, UpdateView):
    model = Order
    form_class = OrderForm
    template_name = 'order/order_form.html'
    context_object_name = 'order'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.get_object()
        context['address_form'] = AddressForm(instance=order.address if order.address else None)
        return context
    
    def form_valid(self, form):
        order = form.save(commit=False)
        address_form = AddressForm(self.request.POST, instance=order.address if order.address else None)
        if address_form.is_valid():
            address = address_form.save()
            order.address = address
            order.save()
            messages.success(self.request, "Order and Address updated successfully!")
            return redirect(self.request.META['HTTP_REFERER'])
        else:
            return self.render_to_response(self.get_context_data(form=form, address_form=address_form))

class OrderDeleteView(LoginRequiredMixin, DeleteView):
    model = Order
    context_object_name = 'order'
    success_url = reverse_lazy('product_list')

# =============================Order Section End==============================




# =============================Product Section Start==============================
class ProductListView(LoginRequiredMixin, ListView):
    model = Product
    form_class = ProductForm
    template_name = 'product/list.html'
    context_object_name = 'products'

class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'product/product_form.html'
    success_url = reverse_lazy('product_list')

class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'product/product_form.html'
    context_object_name = 'product'
    success_url = reverse_lazy('product_list')

class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product
    context_object_name = 'product'
    success_url = reverse_lazy('product_list')

# =============================Product Section End==============================



# =============================Category Section Start==============================
class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    form_class = CategoryForm
    template_name = 'category/list.html'
    context_object_name = 'categories'

class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'category/category_form.html'
    success_url = reverse_lazy('category_list')

class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'category/category_form.html'
    context_object_name = 'object'
    success_url = reverse_lazy('category_list')

class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    context_object_name = 'object'
    success_url = reverse_lazy('category_list')
    template_name = 'category/category_confirm_delete.html'

# =============================Category Section End==============================


