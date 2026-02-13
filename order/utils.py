from marketing.models import EmailConfig
from pencilwoodbd.choices import EmailConfigMailType, EmailConfigServerType, USER_TYPE
from smtplib import SMTP, SMTP_SSL
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from authentication.models import CustomUser
from django.shortcuts import get_object_or_404
from site_app.models import DeliveryOption
import requests


class OrderConfirmatinoEmailSend:
    def __init__(self, order, email) -> None:
        self.order = order
        self.email = email

    def order_confirmation_mail_send(self):
        email_server = EmailConfig.objects.filter(mail_type=EmailConfigMailType.NO_REPLY, is_active=True).first()
        if email_server.server_type == EmailConfigServerType.SMTP:
            subject = f"Successfully Confirm Your Order #{self.order.order_id}!"
            html_body = self.get_dynamical_block_update(email_server)

            mime_msg = MIMEMultipart('alternative')
            mime_msg['Subject'] = str(Header(subject, 'utf-8'))
            mime_msg['From'] = formataddr((email_server.name, email_server.email))
            mime_msg['To'] = self.email
            mime_msg["Reply-To"] = formataddr(("Samim Osman", email_server.reply_to))
            mime_msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            server = SMTP(host=email_server.host, port=email_server.port)
            server.starttls()
            server.login(email_server.host_user, email_server.host_password)
            print("server login: ", server)
            server.sendmail(
                from_addr=email_server.email, to_addrs=self.email, msg=mime_msg.as_string()
            )
            server.quit()
            return True
        return True
    
    def order_items_template(self):
        order_items_html = ""
        for item in self.order.order_items.all():
            order_items_html += f"""
                <tr>
                    <td style='padding:10px;'>{item.product.name}</td>
                    <td style='padding:10px;'>{item.quantity}</td>
                    <td style='padding:10px;'>৳{item.discount_price}</td>
                </tr>
            """
        return order_items_html
    
    def get_dynamical_block_update(self, email_server):
        user = get_object_or_404(CustomUser, email=self.email, user_type=USER_TYPE.CUSTOMER)
        if user:
            user = user.customer_profile
        order = self.order
        order_items = self.order_items_template()
        msg_body = f"""<!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Order Confirmation</title>
        </head>
        <body style="margin:0; padding:0; font-family:Arial, Helvetica, sans-serif; background-color:#f4f4f4;">
            <div style="max-width:600px; margin:20px auto; background:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1);">

                <!-- Header -->
                <div style="background:#177484; padding:20px; color:#ffffff; text-align:center;">
                    <h2 style="margin:0; font-size:24px;">Order Confirmation</h2>
                    <p style="margin:5px 0 0;">Thank you for shopping with us!</p>
                </div>

                <!-- Greeting -->
                <div style="padding:20px;">
                    <p style="font-size:16px; margin:0 0 10px;">Dear {user.full_name},</p>
                    <p style="font-size:15px; line-height:1.6; color:#333333;">
                        We’re happy to let you know that your order has been successfully placed.  
                        Below are the details of your order:
                    </p>

                    <!-- Order Info -->
                    <div style="background:#f9f9f9; padding:15px; border-left:4px solid #177484; margin:20px 0; border-radius:5px;">
                        <p style="margin:5px 0; font-size:15px;"><strong>Order ID:</strong> #{order.order_id}</p>
                        <p style="margin:5px 0; font-size:15px;"><strong>Order Date:</strong> {order.placed_at.strftime("%d %B %Y")}</p>
                        <p style="margin:5px 0; font-size:15px;"><strong>Total Amount:</strong> ৳ <span style="text-decoration:line-through; color:#888;">{order.get_current_total }</span> <span style="color:#d32f2f; font-weight:bold; margin-left:5px;">{ order.get_discount_total }</span> ({order.get_discount_percentage}% OFF)</p>
                        <p style="margin:5px 0; font-size:15px;"><strong>Payment Method:</strong> {order.payment_status}</p>
                    </div>

                    <!-- Items Table (Optional)
                    Add if you have order items -->
                    
                    <h3 style="font-size:18px; margin-bottom:10px;">Order Items</h3>
                    <table width="100%" style="border-collapse:collapse;">
                        <tr style="background:#f1f1f1;">
                            <th style="padding:10px; text-align:left;">Product</th>
                            <th style="padding:10px; text-align:left;">Qty</th>
                            <th style="padding:10px; text-align:left;">Price</th>
                        </tr>
                        {order_items}
                    </table>
                    

                    <p style="font-size:15px; margin-top:20px; color:#333;">
                        You will receive another email when your order is shipped.
                    </p>

                    <p style="font-size:15px; margin-top:25px;">
                        If you have any questions, feel free to reply to this email.
                    </p>

                    <p style="font-size:16px; margin-top:20px;"><strong>Best regards,</strong><br>Your Company Team</p>
                </div>

                <!-- Footer -->
                <div style="background:#eeeeee; padding:15px; text-align:center; font-size:12px; color:#555;">
                    &copy; {order.placed_at.year} Your Company. All rights reserved.
                </div>

            </div>
        </body>
        </html>"""

        return msg_body



class SteadFastOrderCreateAPI:
    def __init__(self, id):
        self.id = id
    
    def get_steadfast_credentials(self):
        try:
            steadfast = get_object_or_404(DeliveryOption, id=self.id)
            return steadfast
        except DeliveryOption.DoesNotExist:
            return None

    def create_order(self, order_data):
        url = f"{self.get_steadfast_credentials().api_url}/create_order"
        headers = {
            "Content-Type": "application/json",
            "Api-Key": self.get_steadfast_credentials().api_key,
            "Secret-Key": self.get_steadfast_credentials().secret_key
        }
        response = requests.post(url, headers=headers, json=order_data)
        response.raise_for_status()
        return response.json()

    def delivery_status_checking(self, consignment_id):
        steadfast = self.get_steadfast_credentials()
        url = f"{steadfast.api_url}/status_by_cid/{consignment_id}"
        headers = {
            "Content-Type": "application/json",
            "Api-Key": steadfast.api_key,
            "Secret-Key": steadfast.secret_key
        }
        response = requests.get(url=url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
        # data = response.json()
        # if "delivery_status" not in data:
        #     raise ValueError("Invalid response structure")
        # return True, data.get("delivery_status")

