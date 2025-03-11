from django import forms
from product.models import Product, Category, ProductImage

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['title', 'image', 'details']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'id': 'title'}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'id': 'image'}),
            'details': forms.Textarea(attrs={'class': 'form-control', 'id': 'details'}),
        }

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['category', 'name', 'short_description', 'details', 'variation', 'stock', 'current_price', 'discount_price']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control', 'id': 'category'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'id': 'inputName'}),
            'short_description': forms.Textarea(attrs={'class': 'form-control', 'id': 'inputShortDescriptino'}),
            'details': forms.Textarea(attrs={'class': 'form-control', 'id': 'details'}),
            'variation': forms.TextInput(attrs={'class': 'form-control', 'id': 'inputVariation'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'id': 'inputStock'}),
            'current_price': forms.NumberInput(attrs={'class': 'form-control', 'id': 'inputCurrentPrice'}),
            'discount_price': forms.NumberInput(attrs={'class': 'form-control', 'id': 'inputDiscountPrice'}),
        }


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['product', 'image']

