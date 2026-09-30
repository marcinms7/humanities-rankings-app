"""Permission-scoped entry point for bounded ranking pages."""
from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes

from .ranking_queries import browse_page, position_map


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def browse(request, pk):
    from .views import ranking_queryset
    ranking = get_object_or_404(ranking_queryset(request.user), pk=pk)
    return browse_page(ranking, request)
