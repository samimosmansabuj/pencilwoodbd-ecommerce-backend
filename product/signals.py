from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from .models import Product, AddToCart
from authentication.models import Customer

@receiver(user_logged_in)
def migrate_cart_to_user(sender, request, user, **kwargs):
    if not request or not hasattr(request, 'session'):
        return
    
    session_cart = request.session.get('cart', {})
    if session_cart:
        customer, created = Customer.objects.get_or_create(user=user, defaults={"name": user.email, "email": user.email})
        
        for product_id, item in session_cart.items():
            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                continue
            
            existing_cart_item = AddToCart.objects.filter(customer=customer, product=product).first()
            if existing_cart_item:
                existing_cart_item.quantity += item['quantity']
                existing_cart_item.save()
            else:
                AddToCart.objects.create(customer=customer, product=product, quantity=item['quantity'])
            
            request.session['cart'] = {}
            request.session.modified = True


