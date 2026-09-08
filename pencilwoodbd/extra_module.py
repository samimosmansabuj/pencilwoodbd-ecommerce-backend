from django.core.files.storage import default_storage
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys
import json
from decimal import Decimal, InvalidOperation

def image_delete_os(picture):
    if picture and default_storage.exists(picture.name):
        default_storage.delete(picture.name)
        return True

def previous_image_delete_os(old_picture, new_picture):
    if old_picture and old_picture != new_picture and default_storage.exists(old_picture.name):
        default_storage.delete(old_picture.name)
        return True

def resize_to_fixed(image_file, size=(1600, 600)):
    """Crop+resize any uploaded image to an exact fixed size (cover-fit, like CSS object-fit:cover)."""
    if not image_file:
        return image_file

    img = Image.open(image_file)
    img = img.convert("RGB")

    target_w, target_h = size
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))

    img = img.resize(size, Image.LANCZOS)

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=88)
    buffer.seek(0)

    return InMemoryUploadedFile(
        buffer, "ImageField",
        f"{image_file.name.rsplit('.', 1)[0]}.jpg",
        "image/jpeg", sys.getsizeof(buffer), None
    )

def parse_decimal(value, default=Decimal("0")):
    if value is None or str(value).strip() == "":
        return default
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return default


def parse_int(value, default=0):
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "on", "yes")


def parse_delivery_charge_payload(request):
    delivery_charge_cost = parse_decimal(request.POST.get("delivery_charge_cost"), default=None)

    raw = request.POST.get("delivery_charge_json", "").strip()
    if not raw:
        return None, False, delivery_charge_cost

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, False, delivery_charge_cost

    mode = payload.get("mode", "none")
    if mode == "none":
        return None, False, delivery_charge_cost

    area_and_charge = {}
    for key, value in payload.items():
        if key == "mode":
            continue
        parsed = parse_decimal(value, default=None)
        if parsed is not None:
            area_and_charge[key] = str(parsed)

    if not area_and_charge:
        return None, False, delivery_charge_cost

    return area_and_charge, True, delivery_charge_cost
