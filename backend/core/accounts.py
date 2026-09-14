"""Email-verified registration and Django's standard password recovery views."""
import hashlib
import time
import os
from datetime import timedelta
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetView
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.decorators.http import require_http_methods
from .models import AuthRateLimit


def limited(request, scope, limit=10):
    # Caddy overwrites X-Real-IP; this opt-in requires the private proxy topology.
    bucket = int(time.time()) // 900
    address = request.META.get('REMOTE_ADDR', 'unknown')
    if os.getenv('TRUST_HTTPS_PROXY', '0') == '1':
        address = request.META.get('HTTP_X_REAL_IP', address)
    key = hashlib.sha256(f'{scope}:{address}:{bucket}'.encode()).hexdigest()
    with transaction.atomic():
        row, _ = AuthRateLimit.objects.select_for_update().get_or_create(key=key,
            defaults={'expires_at': timezone.now() + timedelta(minutes=30)})
        row.count += 1
        row.save(update_fields=['count'])
        return row.count > limit


class RegistrationForm(UserCreationForm):
    email = forms.EmailField()

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('username', 'email')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email cannot be registered. Try account recovery.')
        return email


def send_activation(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f'{settings.PUBLIC_BASE_URL}/accounts/activate/{uid}/{token}/'
    send_mail('Activate your Marginalia account', f'Activate your account within one hour:\n{link}', settings.DEFAULT_FROM_EMAIL, [user.email])


class EmailForm(forms.Form):
    email = forms.EmailField()


@require_http_methods(['GET', 'POST'])
def resend_activation(request):
    if not settings.PUBLIC_REGISTRATION or not settings.EMAIL_HOST:
        return render(request, 'registration/form.html', {'title': 'Activation', 'message': 'Registration is not open yet.'})
    if request.method == 'POST' and limited(request, 'activation', 5):
        return HttpResponse('Please try again in 15 minutes.', status=429)
    form = EmailForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        for user in get_user_model().objects.filter(email__iexact=form.cleaned_data['email'], is_active=False, registration_pending=True):
            send_activation(user)
        return render(request, 'registration/form.html', {'title': 'Check your email', 'message': 'If a pending account matches that email, an activation link has been sent.'})
    return render(request, 'registration/form.html', {'title': 'Resend activation', 'form': form, 'submit': 'Send activation email'})


@require_http_methods(['GET', 'POST'])
def register(request):
    if not settings.PUBLIC_REGISTRATION or not settings.EMAIL_HOST:
        return render(request, 'registration/form.html', {'title': 'Registration', 'message': 'Registration is not open yet.'})
    if request.method == 'POST' and limited(request, 'register', 5):
        return HttpResponse('Please try again in 15 minutes.', status=429)
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save(commit=False)
            user.is_active = False
            user.registration_pending = True
            user.save()
            send_activation(user)
        return render(request, 'registration/form.html', {'title': 'Check your email', 'message': 'Follow the activation link to open your reading space.'})
    return render(request, 'registration/form.html', {'form': form, 'title': 'Create your reading space', 'submit': 'Create account'})


@require_http_methods(['GET', 'POST'])
def activate(request, uidb64, token):
    try:
        user = get_user_model().objects.get(pk=urlsafe_base64_decode(uidb64).decode(), is_active=False, registration_pending=True)
    except (ValueError, UnicodeDecodeError, get_user_model().DoesNotExist):
        user = None
    if not user or not default_token_generator.check_token(user, token):
        return render(request, 'registration/form.html', {'title': 'Link unavailable', 'message': 'This link has expired or has already been used.'}, status=400)
    if request.method == 'POST':
        user.is_active = True
        user.registration_pending = False
        user.save(update_fields=['is_active', 'registration_pending'])
        return redirect('/#/explore')
    return render(request, 'registration/form.html', {'title': 'Activate account', 'confirm': True, 'submit': 'Activate my account'})


class RecoveryView(PasswordResetView):
    template_name = 'registration/form.html'
    email_template_name = 'registration/password_reset_email.txt'
    subject_template_name = 'registration/password_reset_subject.txt'
    extra_context = {'title': 'Recover your account', 'submit': 'Send recovery email'}

    def dispatch(self, request, *args, **kwargs):
        if not settings.EMAIL_HOST:
            return render(request, self.template_name, {'title': 'Account recovery', 'message': 'Email recovery is not configured. Contact the app owner.'})
        if request.method == 'POST' and limited(request, 'recover', 5):
            return HttpResponse('Please try again in 15 minutes.', status=429)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        from urllib.parse import urlsplit
        base = urlsplit(settings.PUBLIC_BASE_URL)
        form.save(use_https=base.scheme == 'https', domain_override=base.netloc,
            email_template_name=self.email_template_name, subject_template_name=self.subject_template_name,
            from_email=settings.DEFAULT_FROM_EMAIL, request=self.request)
        return redirect('password_reset_done')
