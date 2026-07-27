from django.core.files.storage import default_storage
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys

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