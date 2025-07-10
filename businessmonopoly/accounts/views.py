from django.urls import reverse_lazy
from django.views.generic import CreateView
from main.forms import CustomUserCreationForm  # импорт формы из main


class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'main/signup.html'  # указываем правильный путь к шаблону

