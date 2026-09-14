from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from backend.core import views
from backend.core import accounts
from backend.core import reading_insights
from backend.core import reading_tools
from backend.core import classical_education
from backend.core import discovery
from backend.core import reading_trails
from django.contrib.auth import views as auth_views

router = DefaultRouter()
for name, view, basename in [('works', views.WorkViewSet, 'work'), ('people', views.PersonViewSet, 'person'),
                             ('editions', views.EditionViewSet, 'edition'), ('rankings', views.RankingViewSet, 'ranking'),
                             ('library', views.LibraryViewSet, 'library'), ('plan', views.PlanViewSet, 'plan')]:
    router.register(name, view, basename=basename)
urlpatterns = [path('admin/', admin.site.urls), path('api/session/', views.session_view), path('api/profile/', views.profile),
               path('api/export/', views.export_library), path('api/shared/<uuid:token>/', views.shared_list), path('api/', include(router.urls))]
urlpatterns += [
    path('api/reading-trails/', reading_trails.trails),
    path('api/personal-discovery/', reading_trails.personal_discovery),
    path('api/source-explorer/', discovery.source_explorer),
    path('api/works/<int:pk>/placements/', discovery.placements),
    path('api/classical-education/', classical_education.syllabus),
    path('api/read-next/', reading_tools.shortlist),
    path('api/read-next/plan/', reading_tools.send_shortlist),
    path('api/annual-reading/', reading_tools.annual_reading),
    path('api/reading-insights/', reading_insights.insights),
    path('api/collection-overlap/', reading_insights.overlap),
    path('api/collection-context/', reading_insights.collection_context),
    path('health/live/', views.health_live), path('health/ready/', views.health_ready),
    path('accounts/register/', accounts.register),
    path('accounts/resend-activation/', accounts.resend_activation),
    path('accounts/activate/<uidb64>/<token>/', accounts.activate),
    path('accounts/password-reset/', accounts.RecoveryView.as_view(), name='password_reset'),
    path('accounts/password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/form.html', extra_context={'title': 'Check your email', 'message': 'If an active account matches that email, a recovery link has been sent.'}), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/form.html'), name='password_reset_confirm'),
    path('accounts/reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/form.html', extra_context={'title': 'Password updated', 'message': 'Return to the app and sign in with your new password.'}), name='password_reset_complete'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += [re_path(r'^(?!api/|admin/|static/|media/)(?P<path>.*)$', views.app_index)]
