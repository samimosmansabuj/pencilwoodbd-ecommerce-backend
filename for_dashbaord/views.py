from django.shortcuts import render

def index(request):
    return render(request, 'home/index.html')


def product_list(request):
    return render(request, 'product/list.html')
