from django.shortcuts import render
from django.views.generic import CreateView, DetailView, UpdateView, DeleteView, ListView
from .forms import ProductForm, CategoryForm
from product.models import Product, Category
from django.urls import reverse_lazy


def login(request):
    return render(request, 'user/login.html')

def index(request):
    return render(request, 'home/index.html')


def product_list(request):
    return render(request, 'product/list.html')




class ProductListView(ListView):
    model = Product
    form_class = ProductForm
    template_name = 'product/list.html'
    context_object_name = 'products'

class ProductCreateView(CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'product/product_form.html'
    success_url = reverse_lazy('product_list')

class ProductUpdateView(UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'product/product_form.html'
    context_object_name = 'product'
    success_url = reverse_lazy('product_list')

class ProductDeleteView(DeleteView):
    model = Product
    context_object_name = 'product'
    success_url = reverse_lazy('product_list')




class CategoryListView(ListView):
    model = Category
    form_class = CategoryForm
    template_name = 'category/list.html'
    context_object_name = 'categories'

class CategoryCreateView(CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'category/category_form.html'
    success_url = reverse_lazy('category_list')

class CategoryUpdateView(UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'category/category_form.html'
    context_object_name = 'object'
    success_url = reverse_lazy('category_list')

class CategoryDeleteView(DeleteView):
    model = Category
    context_object_name = 'object'
    success_url = reverse_lazy('category_list')
    template_name = 'category/category_confirm_delete.html'



