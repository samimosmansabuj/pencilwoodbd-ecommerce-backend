from http import HTTPStatus
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.generic import CreateView, UpdateView, DeleteView, ListView
from order.models import Order
from product.models import Product, Category
from authentication.models import CustomUser
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.models import LogEntry
from django.utils.timezone import now
from django.views import View
from pencilwoodbd.choices import USER_TYPE
from django.db import transaction
from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS

@login_required(login_url='admin_login')
def dashboard(request):
    return render(request, "dashboard.html")


class UserLoginView(View):
    def get(self, request):
        print("request.user: ", request.user)
        if request.user.is_authenticated:
            return redirect('dashboard')
        return render(request, 'db_auth/login.html')
    
    def post(self, request):
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            user = authenticate(username=email, password=password)
            if user is not None and user.user_type in (USER_TYPE.ADMIN, USER_TYPE.SUPER_ADMIN, USER_TYPE.STAFF):
                login(request, user)
                return redirect('dashboard')
            else:
                return render(request, 'db_auth/login.html', {'error': 'Invalid credentials or insufficient permissions.'})
        except CustomUser.DoesNotExist:
            return render(request, 'db_auth/login.html', {'error': 'User does not exist.'})

def logout_view(request):
    logout(request)
    return redirect('admin_login')









@login_required(login_url='admin_login')
def product_list(request):
    products = Product.objects.all()
    return render(request, "db_product/product_list.html", {"products": products})

@login_required(login_url='admin_login')
def add_product(request):
    return render(request, "db_product/add_product.html")

@login_required(login_url='admin_login')
def add_category(request):
    if request.method == "POST":
        Category.objects.create(
            name=request.POST.get("name"),
            slug=request.POST.get("slug"),
            parent=request.POST.get("parent"),
            status=request.POST.get("status"),
            image=request.FILES.get("image"),
        )
        return JsonResponse({"message": "Category added successfully"})
    return render(request, "db_category/add_category.html")

# @login_required(login_url='admin_login')
class CategoryView(View):
    def get(self, request):
        categories = Category.objects.all()
        return render(request, "db_category/category_list.html", {"categories": categories})
    
    def post(self, request):
        try:
            with transaction.atomic():
                data = request.POST

                if data.get("category_id"):
                    category = Category.objects.get(id=data.get("category_id"))
                    category.name = data.get("category_title")
                    category.description = data.get("category_description")
                    category.save()
                    return JsonResponse({
                        "status": True,
                        "message": "Category updated successfully"
                    }, status=HTTPStatus.OK)
                
                if data.get("category_title") == "":
                    return JsonResponse({
                        "status": False,
                        "message": "Category title is required"
                    }, status=HTTPStatus.BAD_REQUEST)
                if data.get("category_description") == "":
                    return JsonResponse({
                        "status": False,
                        "message": "Category description is required"
                    }, status=HTTPStatus.BAD_REQUEST)
                Category.objects.create(
                    name=data.get("category_title"),
                    description=data.get("category_description"),
                    status=CATEGORY_PRODUCT_STATUS.ACTIVE,
                )
                return JsonResponse({
                    "status": True,
                    "message": "Category added successfully"
                }, status=HTTPStatus.CREATED)
        except Exception as e:
            print("Exception", e)
            return JsonResponse({
                "status": False,
                "message": str(e)
            }, status=HTTPStatus.BAD_REQUEST)

@login_required(login_url='admin_login')
def get_category(request, id):
    try:
        category = get_object_or_404(Category, id=id)
        return JsonResponse({
            "status": True,
            "category": {
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "status": category.status
            }
        }, status=HTTPStatus.OK)
    except Exception as e:
        print("Exception", e)
        return JsonResponse({
            "status": False,
            "message": str(e)
        }, status=HTTPStatus.BAD_REQUEST)

@login_required(login_url='admin_login')
def delete_category(request, id):
    if request.method == "DELETE":
        try:
            category = get_object_or_404(Category, id=id)
            category.delete()
            return JsonResponse({
                "status": True,
                "message": "Category deleted successfully"
            }, status=HTTPStatus.OK)
        except Exception as e:
            print("Exception", e)
            return JsonResponse({
                "status": False,
                "message": str(e)
            }, status=HTTPStatus.BAD_REQUEST)
    return JsonResponse({
        "status": False,
        "message": "Invalid request"
    }, status=HTTPStatus.BAD_REQUEST)


class OrderView(View):
    def get(self, request):
        # if not request.user.is_authenticated:
        #     return redirect('product_landing_page')
        # elif request.user.user_type not in [USER_TYPE.ADMIN, USER_TYPE.STAFF, USER_TYPE.SUPER_ADMIN]:
        #     return redirect('product_landing_page')
        
        orders = Order.objects.all()
        return render(request, "db_order/order_list.html", {"orders": orders})
    
    def post(self, request):
        if not request.user.is_authenticated:
            return redirect('product_landing_page')
        elif request.user.user_type not in [USER_TYPE.ADMIN, USER_TYPE.STAFF, USER_TYPE.SUPER_ADMIN]:
            return redirect('product_landing_page')
        
        try:
            with transaction.atomic():
                data = request.POST

                if data.get("order_id"):
                    order = Order.objects.get(id=data.get("order_id"))
                    order.name = data.get("order_title")
                    order.description = data.get("order_description")
                    order.save()
                    return JsonResponse({
                        "status": True,
                        "message": "Order updated successfully"
                    }, status=HTTPStatus.OK)
                
                if data.get("order_title") == "":
                    return JsonResponse({
                        "status": False,
                        "message": "Order title is required"
                    }, status=HTTPStatus.BAD_REQUEST)
                if data.get("order_description") == "":
                    return JsonResponse({
                        "status": False,
                        "message": "Order description is required"
                    }, status=HTTPStatus.BAD_REQUEST)
                Order.objects.create(
                    name=data.get("order_title"),
                    description=data.get("order_description"),
                    status=ORDER_STATUS.ACTIVE,
                )
                return JsonResponse({
                    "status": True,
                    "message": "Order added successfully"
                }, status=HTTPStatus.CREATED)
        except Exception as e:
            print("Exception", e)
            return JsonResponse({
                "status": False,
                "message": str(e)
            }, status=HTTPStatus.BAD_REQUEST)

class OrderDetailView(View):
    def get(self, request, id):
        if not request.user.is_authenticated:
            return redirect('product_landing_page')
        elif request.user.user_type not in [USER_TYPE.ADMIN, USER_TYPE.STAFF, USER_TYPE.SUPER_ADMIN]:
            return redirect('product_landing_page')
        
        order = self.get_order(id)
        return render(request, "db_order/order_detail.html", {"order": order})

    def get_order(self, id):
        return get_object_or_404(Order, id=id)

    def generate_unique_username(self, name):
        base = slugify(name) or "user"
        username = base
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{username}-{counter}"
            counter += 1
        return username

    def update_customer_profile(self, data, profile):
        profile.full_name = data.get("full_name", profile.full_name)
        profile.phone = data.get("phone", profile.phone)
        if data.get("email"):
            if profile.user:
                profile.user.email = data.get("email", profile.user.email)
                profile.user.save()
            else:
                user = CustomUser.objects.create(
                    email=data.get("email"),
                    full_name=profile.full_name,
                    username=self.generate_unique_username(profile.full_name)
                )
                profile.user = user
        profile.save()
        return True
    
    def update_order_object(self, data, order):
        if data.get("delivery_date"):
            order.delivery_date = data.get("delivery_date", order.delivery_date)
        order.shipping_address = data.get("shipping_address", order.shipping_address)
        order.payment_status = data.get("payment_status", order.payment_status)
        order.order_status = data.get("order_status", order.order_status)
        order.save()
        return True

    def post(self, request, id):
        if not request.user.is_authenticated:
            return redirect('product_landing_page')
        elif request.user.user_type not in [USER_TYPE.ADMIN, USER_TYPE.STAFF, USER_TYPE.SUPER_ADMIN]:
            return redirect('product_landing_page')
        
        if request.POST.get("_method") == "PATCH":
            return self.patch(request, id)
        return JsonResponse({"error": "Invalid request"}, status=400)

    def patch(self, request, id):
        order = self.get_order(id)
        
        data = request.POST
        print("data: ", data)
        if order:
            try:
                with transaction.atomic():
                    profile = order.customer
                    self.update_customer_profile(data, profile)
                    self.update_order_object(data, order)
                    return JsonResponse(
                        {
                            "success": True,
                            "message": "Order updated successfully"
                        }, status=200
                    )
                
            except Exception as e:
                print("error: ", e)
                return JsonResponse(
                    {
                        "success": False,
                        "message": str(e)
                    }
                )

    def dispatch(self, request, *args, **kwargs):
        if request.method.lower() == "patch":
            return self.patch(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)





# # =============================Order Section Start==============================
# class OrdertListView(LoginRequiredMixin, ListView):
#     model = Order
#     form_class = OrderForm
#     template_name = 'order/list.html'
#     context_object_name = 'orders'

# # class OrderCreateView(CreateView):
# #     model = Order
# #     form_class = OrderForm
# #     template_name = 'order/order_form.html'
# #     success_url = reverse_lazy('product_list')

# class OrderUpdateView(LoginRequiredMixin, UpdateView):
#     model = Order
#     form_class = OrderForm
#     template_name = 'order/order_form.html'
#     context_object_name = 'order'
    
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         order = self.get_object()
#         context['address_form'] = AddressForm(instance=order.address if order.address else None)
#         return context
    
#     def form_valid(self, form):
#         order = form.save(commit=False)
#         address_form = AddressForm(self.request.POST, instance=order.address if order.address else None)
#         if address_form.is_valid():
#             address = address_form.save()
#             order.address = address
#             order.save()
#             messages.success(self.request, "Order and Address updated successfully!")
#             return redirect(self.request.META['HTTP_REFERER'])
#         else:
#             return self.render_to_response(self.get_context_data(form=form, address_form=address_form))

# class OrderDeleteView(LoginRequiredMixin, DeleteView):
#     model = Order
#     context_object_name = 'order'
#     success_url = reverse_lazy('product_list')

# # =============================Order Section End==============================




# # =============================Product Section Start==============================
# class ProductListView(LoginRequiredMixin, ListView):
#     model = Product
#     form_class = ProductForm
#     template_name = 'product/list.html'
#     context_object_name = 'products'

# class ProductCreateView(LoginRequiredMixin, CreateView):
#     model = Product
#     form_class = ProductForm
#     template_name = 'product/product_form.html'
#     success_url = reverse_lazy('product_list')

# class ProductUpdateView(LoginRequiredMixin, UpdateView):
#     model = Product
#     form_class = ProductForm
#     template_name = 'product/product_form.html'
#     context_object_name = 'product'
#     success_url = reverse_lazy('product_list')

# class ProductDeleteView(LoginRequiredMixin, DeleteView):
#     model = Product
#     context_object_name = 'product'
#     success_url = reverse_lazy('product_list')

# # =============================Product Section End==============================



# # =============================Category Section Start==============================
# class CategoryListView(LoginRequiredMixin, ListView):
#     model = Category
#     form_class = CategoryForm
#     template_name = 'category/list.html'
#     context_object_name = 'categories'

# class CategoryCreateView(LoginRequiredMixin, CreateView):
#     model = Category
#     form_class = CategoryForm
#     template_name = 'category/category_form.html'
#     success_url = reverse_lazy('category_list')

# class CategoryUpdateView(LoginRequiredMixin, UpdateView):
#     model = Category
#     form_class = CategoryForm
#     template_name = 'category/category_form.html'
#     context_object_name = 'object'
#     success_url = reverse_lazy('category_list')

# class CategoryDeleteView(LoginRequiredMixin, DeleteView):
#     model = Category
#     context_object_name = 'object'
#     success_url = reverse_lazy('category_list')
#     template_name = 'category/category_confirm_delete.html'

# # =============================Category Section End==============================


