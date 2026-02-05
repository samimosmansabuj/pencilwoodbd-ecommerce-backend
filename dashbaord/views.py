from http import HTTPStatus
from urllib.parse import urlparse
from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect, HttpResponseRedirect, JsonResponse
from django.views.generic import CreateView, UpdateView, DeleteView, ListView
from order.models import Order
from product.models import Product, Category, ProductImage, ProductVideo
from authentication.models import CustomUser
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.models import LogEntry
from django.utils.timezone import now
from django.views import View
from pencilwoodbd.choices import USER_TYPE, STATUS
from django.db import transaction
from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS
from product.forms import ProductForm,ProductImageForm, ProductVideoForm
from django.forms import modelformset_factory
from django.utils.text import slugify
from django.contrib.auth.mixins import LoginRequiredMixin


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








# ------------------Product--------
@login_required(login_url='admin_login')
def product_list(request):
    products = Product.objects.all()
    return render(request, "db_product/product_list.html", {"products": products})

@login_required(login_url='admin_login')
def add_product(request):
    ImageFormSet = modelformset_factory(ProductImage, form=ProductImageForm, extra=3, can_delete=True)
    VideoFormSet = modelformset_factory(ProductVideo, form=ProductVideoForm, extra=1, can_delete=True)

    if request.method == "POST":
        product_form = ProductForm(request.POST)
        image_formset = ImageFormSet(request.POST, request.FILES, queryset=ProductImage.objects.none())
        video_formset = VideoFormSet(request.POST, request.FILES, queryset=ProductVideo.objects.none())

        if product_form.is_valid() and image_formset.is_valid() and video_formset.is_valid():
            try:
                with transaction.atomic():
                    product = product_form.save()

                    # Images
                    for img_form in image_formset.cleaned_data:
                        if img_form and not img_form.get("DELETE", False):
                            ProductImage.objects.create(
                                product=product,
                                image=img_form.get("image"),
                                role=img_form.get("role", "gallery"),
                                position=img_form.get("position", 0)
                            )

                    # Video
                    for vid_form in video_formset.cleaned_data:
                        if vid_form and vid_form.get("video"):
                            ProductVideo.objects.create(
                                product=product,
                                video=vid_form.get("video")
                            )

                    messages.success(request, "Product added successfully!")
                    return redirect("product_list")
            except Exception as e:
                messages.error(request, f"Error saving product: {e}")
        else:
            messages.error(request, "Please correct the errors below.")

    else:
        product_form = ProductForm()
        image_formset = ImageFormSet(queryset=ProductImage.objects.none())
        video_formset = VideoFormSet(queryset=ProductVideo.objects.none())

    return render(request, "db_product/add_product.html", {
        "product_form": product_form,
        "image_formset": image_formset,
        "video_formset": video_formset
    })


@login_required(login_url='admin_login')
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)

    ImageFormSet = modelformset_factory(
        ProductImage,
        form=ProductImageForm,
        extra=0,
        can_delete=True
    )

    VideoFormSet = modelformset_factory(
        ProductVideo,
        form=ProductVideoForm,
        extra=0,
        can_delete=True
    )

    if request.method == "POST":
        product_form = ProductForm(request.POST, instance=product)

        image_formset = ImageFormSet(
            request.POST,
            request.FILES,
            queryset=ProductImage.objects.filter(product=product)
        )

        video_formset = VideoFormSet(
            request.POST,
            request.FILES,
            queryset=ProductVideo.objects.filter(product=product)
        )

        if product_form.is_valid() and image_formset.is_valid() and video_formset.is_valid():
            try:
                with transaction.atomic():
                    product_form.save()

                    # images
                    for form in image_formset:
                        if form.cleaned_data.get("DELETE"):
                            if form.instance.pk:
                                form.instance.delete()
                        else:
                            img = form.save(commit=False)
                            img.product = product
                            img.save()

                    # videos
                    for form in video_formset:
                        if form.cleaned_data.get("DELETE"):
                            if form.instance.pk:
                                form.instance.delete()
                        else:
                            vid = form.save(commit=False)
                            vid.product = product
                            vid.save()

                    messages.success(request, "Product updated successfully")
                    return redirect("product_list")

            except Exception as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Please fix the errors below")

    else:
        product_form = ProductForm(instance=product)
        image_formset = ImageFormSet(queryset=ProductImage.objects.filter(product=product))
        video_formset = VideoFormSet(queryset=ProductVideo.objects.filter(product=product))

    return render(request, "db_product/add_product.html", {
        "product_form": product_form,
        "image_formset": image_formset,
        "video_formset": video_formset,
        "is_update": True,
        "product": product
    })


@login_required(login_url='admin_login')
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()
        messages.success(request, "Product deleted successfully!")
        return redirect("product_list")
    return redirect("product_list")  # fallback


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



# ------------------Order section CBV-------------
class OrderView(LoginRequiredMixin, View):
    login_url = 'admin_login'
    
    def get(self, request):
        # if not request.user.is_authenticated:
        #     return redirect('product_landing_page')
        # elif request.user.user_type not in [USER_TYPE.ADMIN, USER_TYPE.STAFF, USER_TYPE.SUPER_ADMIN]:
        #     return redirect('product_landing_page')
        
        orders = Order.objects.all()
        return render(request, "db_order/order_list.html", {"orders": orders})
    
    def post(self, request):
        print("request.POST: ", request.POST)
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
                    status=STATUS.Pending,
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

class OrderDetailView(LoginRequiredMixin, View):
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



# ------------------Order section FBV-------------

@login_required(login_url='admin_login')
def update_order(request, order_id):
    if request.method != "POST" or request.POST.get("_method") != "PATCH":
        return JsonResponse({"success": False, "message": "Invalid request"}, status=400)

    if request.user.user_type not in [USER_TYPE.ADMIN, USER_TYPE.STAFF, USER_TYPE.SUPER_ADMIN]:
        return JsonResponse({"success": False, "message": "Permission denied"}, status=403)

    order = get_object_or_404(Order, id=order_id)
    data = request.POST

    def generate_unique_username(name):
        base = slugify(name) or "user"
        username = base
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{base}-{counter}"
            counter += 1
        return username

    try:
        with transaction.atomic():
            # Update customer profile
            profile = order.customer
            profile.name = data.get("full_name", profile.name)
            profile.phone = data.get("phone", profile.phone)
            email = data.get("email")
            if email:
                if profile.user:
                    profile.user.email = email
                    profile.user.save()
                else:
                    user = CustomUser.objects.create(
                        email=email,
                        username=generate_unique_username(profile.name),
                        user_type=USER_TYPE.CUSTOMER
                    )
                    profile.user = user
            profile.save()

            # Update order
            if data.get("delivery_date"):
                order.delivery_date = data.get("delivery_date")
            order.shipping_address = data.get("shipping_address", order.shipping_address)
            order.payment_status = data.get("payment_status", order.payment_status)
            order.status = data.get("order_status", order.status)
            order.save()

            return JsonResponse({"success": True, "message": "Order updated successfully"}, status=200)

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)

class OrderDeleteView(LoginRequiredMixin, DeleteView):
    model = Order
    success_url = reverse_lazy("order_list")
    login_url = 'admin_login'
    
    def post(self, request, *args: str, **kwargs) -> HttpResponse:
        try:
            order = get_object_or_404(Order, pk=kwargs.get("pk"))
            order.delete()
            messages.success(request, "Order deleted successfully!")
        except:
            messages.error(request, "Order does not exist.")
        return redirect(self.success_url)

# class RedirectView(View):
#     permanent = False
#     url = None
#     pattern_name = None
#     query_string = False

#     def get_redirect_url(self, *args, **kwargs):
#         if self.url:
#             url = self.url % kwargs
#         elif self.pattern_name:
#             url = reverse(self.pattern_name, args=args, kwargs=kwargs)
#         else:
#             return None

#         args = self.request.META.get("QUERY_STRING", "")
#         if args and self.query_string:
#             if urlparse(url).query:
#                 url = f"{url}&{args}"
#             else:
#                 url = f"{url}?{args}"
#         return url

#     def get(self, request, *args, **kwargs):
#         url = self.get_redirect_url(*args, **kwargs)
#         if url:
#             if self.permanent:
#                 return HttpResponsePermanentRedirect(url)
#             else:
#                 return HttpResponseRedirect(url)
#         else:
#             response = HttpResponseGone()
#             log_response("Gone: %s", request.path, response=response, request=request)
#             return response

#     def head(self, request, *args, **kwargs):
#         return self.get(request, *args, **kwargs)

#     def post(self, request, *args, **kwargs):
#         return self.get(request, *args, **kwargs)

#     def options(self, request, *args, **kwargs):
#         return self.get(request, *args, **kwargs)

#     def delete(self, request, *args, **kwargs):
#         return self.get(request, *args, **kwargs)

