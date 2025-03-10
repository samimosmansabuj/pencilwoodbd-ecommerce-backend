from django.core.files.storage import default_storage


def image_delete_os(picture):
    if picture and default_storage.exists(picture.name):
        default_storage.delete(picture.name)
        return True

def previous_image_delete_os(old_picture, new_picture):
    if old_picture and old_picture != new_picture and default_storage.exists(old_picture.name):
        default_storage.delete(old_picture.name)
        return True

