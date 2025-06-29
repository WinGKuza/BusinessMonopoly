from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView
from .forms import CustomUserCreationForm


class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')  # После регистрации перенаправляем на страницу входа
    template_name = 'main/signup.html'

def index(request):
    return render(request, 'main/index.html')


def about(request):
    return render(request, 'main/about.html')


def registration(request):
    return render(request, 'main/login.html')