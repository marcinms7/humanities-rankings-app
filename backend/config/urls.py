from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from backend.core import views
from backend.core import accounts
from backend.core.thumbnails import thumbnail
from backend.core.operations import operations_status
from backend.core import recommendations
from backend.core.reading_calendar import reading_calendar
from backend.core.catalog_atlas import catalog_atlas
from backend.core.published_comparison import published_comparison
from backend.core import reading_insights
from backend.core import reading_tools
from backend.core import classical_education
from backend.core import discovery
from backend.core import reading_trails, reading_workflow, catalog_review, ranking_browse, book_workflow
from backend.core.saved_discovery import SavedDiscoveryFilterViewSet
from django.contrib.auth import views as auth_views

router = DefaultRouter()
for name, view, basename in [('works', views.WorkViewSet, 'work'), ('people', views.PersonViewSet, 'person'),
                             ('editions', views.EditionViewSet, 'edition'), ('rankings', views.RankingViewSet, 'ranking'),
                             ('library', views.LibraryViewSet, 'library'), ('plan', views.PlanViewSet, 'plan'),
                             ('saved-filters', SavedDiscoveryFilterViewSet, 'saved-filter')]:
    router.register(name, view, basename=basename)
urlpatterns = [path('media-preview/<int:size>/<path:filename>', thumbnail), path('admin/', admin.site.urls), path('api/session/', views.session_view), path('api/profile/', views.profile),
               path('api/export/', views.export_library), path('api/shared/<uuid:token>/', views.shared_list)]
urlpatterns += [
    path('api/operations/', operations_status),
    path('api/reading-calendar/', reading_calendar),
    path('api/catalog-atlas/', catalog_atlas),
    path('api/published-comparison/', published_comparison),
    path('api/recommendations/', recommendations.recommendations),
    path('api/recommendations/preferences/', recommendations.recommendation_preferences),
    path('api/recommendations/feedback/', recommendations.recommendation_feedback),
    path('api/today/', reading_workflow.today),
    path('api/today/progress/', reading_workflow.today_progress),
    path('api/plan/<int:pk>/progress/', reading_workflow.plan_progress),
    path('api/plan/carryover/', reading_workflow.carryover),
    path('api/reading-allocation/', book_workflow.reading_allocation),
    path('api/ranking-browse/<int:pk>/', ranking_browse.browse),
    path('api/catalog-review/', catalog_review.catalog_review_queue),
    path('api/catalog-review/batch/', catalog_review.catalog_review_batch),
    path('api/catalog-review/edition/', catalog_review.catalog_review_edition),
    path('api/catalog-review/history/', catalog_review.catalog_review_history),
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
urlpatterns += [path('api/', include(router.urls))]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += [re_path(r'^(?!api/|admin/|static/|media/|media-preview/)(?P<path>.*)$', views.app_index)]
