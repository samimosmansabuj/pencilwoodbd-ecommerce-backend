# product/forms.py
from django import forms
from .models import Product, ProductImage, ProductVideo, Category
from pencilwoodbd.choices import CATEGORY_PRODUCT_STATUS, PRODUCT_MEDIA_ROLE


class ProductForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        empty_label="Select Category",
        widget=forms.Select(attrs={"class": "form-control"})
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "category",
            "price",
            "discount_price",
            "inventory_quantity",
            "short_description",
            "details",
            "weight",
            "status",
            "seo",
            "metadata",
            "tags"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "price": forms.NumberInput(attrs={"class": "form-control"}),
            "discount_price": forms.NumberInput(attrs={"class": "form-control"}),
            "inventory_quantity": forms.NumberInput(attrs={"class": "form-control"}),
            "short_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "details": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "weight": forms.NumberInput(attrs={"class": "form-control", "step": "0.001"}),
            "status": forms.Select(choices=CATEGORY_PRODUCT_STATUS.choices, attrs={"class": "form-control"}),
            "seo": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "JSON format"}),
            "metadata": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "JSON format"}),
            "tags": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "List of tags"}),
        }


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "role", "position"]
        widgets = {
            "role": forms.Select(choices=PRODUCT_MEDIA_ROLE.choices, attrs={"class": "form-control"}),
            "position": forms.NumberInput(attrs={"class": "form-control"}),
        }


class ProductVideoForm(forms.ModelForm):
    class Meta:
        model = ProductVideo
        fields = ["video"]
        widgets = {
            "video": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }
