from django import forms
from product.models import Product, Category, ProductImage
from order.models import Order, Address

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ['street_01', 'street_02', 'upazila', 'post_office', 'post_code', 'district', 'country']
        widgets = {
            'street_01': forms.TextInput(attrs={'class': 'form-control', 'id': 'Street01'}),
            'street_02': forms.TextInput(attrs={'class': 'form-control', 'id': 'Street02'}),
            'post_office': forms.TextInput(attrs={'class': 'form-control', 'id': 'PostOffice'}),
            'post_code': forms.TextInput(attrs={'class': 'form-control', 'id': 'PostCode'}),
            'upazila': forms.TextInput(attrs={'class': 'form-control', 'id': 'Upazila'}),
            'district': forms.TextInput(attrs={'class': 'form-control', 'id': 'District'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'id': 'Country'}),
        }

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'
        exclude = ['customer']
        widgets = {
            # 'customer': forms.Select(attrs={'class': 'form-control', 'id': 'Customer'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'id': 'Name'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'id': 'PhoneNumber'}),
            
            'payment_type': forms.Select(attrs={'class': 'form-control', 'id': 'PaymentType'}),
            'payment_partial': forms.CheckboxInput(attrs={'id': 'PaymentPartial'}),
            'payment_status': forms.Select(attrs={'class': 'form-control', 'id': 'PaymentStatus'}),
            
            'status': forms.Select(attrs={'class': 'form-control', 'id': 'Status'}),
            'tracking_id': forms.TextInput(attrs={'class': 'form-control', 'id': 'Tracking ID'}),
            'delivery_by': forms.TextInput(attrs={'class': 'form-control', 'id': 'Delivery By'}),
            
            'total_cost': forms.NumberInput(attrs={'class': 'form-control', 'id': 'TotalCost'}),
            'shipping_charge': forms.NumberInput(attrs={'class': 'form-control', 'id': 'ShippingCharge'}),
        }
    
    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     if self.instance and self.instance.customer:
    #         self.fields['customer'] = forms.CharField(
    #             initial=self.instance.customer, disabled=True, required=False
    #         )
        


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

