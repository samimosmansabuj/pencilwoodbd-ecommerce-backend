from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.http import JsonResponse
from http import HTTPStatus
from django.db import transaction
from .models import Order, SteadFastWebhookLog, Shipment
import json
from django.shortcuts import redirect


from pencilwoodbd.choices import STATUS


# Logistic / Delivery Company API Integration Code==========================
@method_decorator(csrf_exempt, name="dispatch")
class SteadfastWebhookAPIView(View):
    def get_order(self, consignment_id):
        try:
            return self.get_shipment(consignment_id).order
        except Order.DoesNotExist:
            return None
    
    def get_shipment(self, consignment_id):
        try:
            return Shipment.objects.filter(tracking_number=str(consignment_id)).first()
        except Shipment.DoesNotExist:
            return None

    def order_validation(self, order, status_value, invoice, cod_amount):
        validation_invoice = order.tracking_ID == invoice
        validation_order_cod = float(order.due_amount) == cod_amount
        validation_order_status = True if status_value.lower() in ("delivered", "partial_delivered") and order.status != "Delivered" else \
                                  True if status_value == "pending" and order.status != "Parcel Created" else False
        if order and validation_order_status and (validation_invoice or validation_order_cod):
            return True
        return False

    def partial_workflow(self, data):
        try:
            status_value = data.get("status")
            consignment_id = data.get("consignment_id")
            
            order = self.get_order(consignment_id)
            shipment = self.get_shipment(consignment_id)
            
            shipment.status = status_value or shipment.status
            shipment.save(update_fields=["status"])
            
            status_map = {
                "pending": STATUS.SHIPPED,
                "delivered": STATUS.DELIVERED,
                "partial_delivered": STATUS.DELIVERED,
                "cancelled": STATUS.CANCELLED,
                "returned": STATUS.RETURNED,
            }
            mapped = status_map.get((status_value or "").lower())
            
            with transaction.atomic():
                if mapped:
                    Order.objects.filter(id=order.id).update(status=mapped, urgent=False)
        except:
            return None
    
    def create_log_entry(self, data, notification_type, account):
        SteadFastWebhookLog.objects.create(
            type=notification_type,
            account=account,
            payload=data,
            tracking_message=data.get("tracking_message", ""),
        )

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body.decode("utf-8"))
            notification_type = data.get("notification_type")
            account = request.GET.get("account", "pencilwood")
            self.create_log_entry(data, notification_type, account)
            if notification_type == "delivery_status":
                self.partial_workflow(data)
            return JsonResponse(
                {"status": "success", "message": "Webhook Received Successfully"},
                status=HTTPStatus.OK,
            )
        except json.JSONDecodeError:
            return JsonResponse(
                {"status": "error", "message": "Invalid JSON payload"},
                status=HTTPStatus.BAD_REQUEST,
            )
        except Exception as e:
            return JsonResponse(
                {"status": "error", "message": str(e)},
                status=HTTPStatus.BAD_REQUEST,
            )

    def get(self, request, *args, **kwargs):
        return JsonResponse(
            {"status": "error", "message": "Invalid Request Method"},
            status=HTTPStatus.METHOD_NOT_ALLOWED,
        )


