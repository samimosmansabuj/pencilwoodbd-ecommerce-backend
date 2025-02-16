from django.utils.deprecation import MiddlewareMixin
from .models import Product, AddToCart
from authentication.models import Customer

class MirgateCartMiddleware(MiddlewareMixin):
    def process_request(self, request):
        session_cart = request.session.get('cart', {})
        # print(session_cart)
        if request.user.is_authenticated and 'cart' in request.session:
            print('authenticated')
            self.migrate_cart_to_user(request)
    
    def migrate_cart_to_user(self, request):
            session_cart = request.session.get('cart', {})
            print(session_cart)
            if session_cart:
                customer, created = Customer.objects.get_or_create(
                    user=request.user,
                    defaults={"name": request.user.email, "email": request.user.email}
                )
                
                for product_id, item in session_cart.items():
                    try:
                        product = Product.objects.get(id=product_id)
                    except Product.DoesNotExist:
                        continue
                    
                    existing_cart_item = AddToCart.objects.filter(customer=customer, product=product).first()
                    if existing_cart_item:
                        existing_cart_item.quantity == item['quantity']
                        existing_cart_item.save()
                    else:
                        AddToCart.objects.create(customer=customer, product=product, quantity=item['quantity'])
                    
                    request.session['cart'] = {}
                    request.session.modified = True


