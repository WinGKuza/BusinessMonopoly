from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView
from .forms import CustomUserCreationForm
from django.shortcuts import render, redirect
from games.forms import GameCreateForm



def create_game(request):
    if request.method == 'POST':
        form = GameCreateForm(request.POST)
        if form.is_valid():
            game = form.save(commit=False)
            game.creator = request.user  # чтобы установить создателя
            game.save()
            return redirect('game_detail', game_id=game.id)
    else:
        form = GameCreateForm()
    return render(request, 'main/create_game.html', {'form': form})


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