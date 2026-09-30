from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (User, Person, Work, Edition, Tag, Ranking, RankingEntry, RankingRevision, ResearchSource,
                     RankingPreference, LibraryItem, PlanItem)

admin.site.site_header = 'Marginalia · Administration'
admin.site.register(User, UserAdmin)
admin.site.register([RankingPreference, LibraryItem])


@admin.register(PlanItem)
class PlanItemAdmin(admin.ModelAdmin):
    """Use the planner's validated progress/carryover flows for private writes.

    A generic admin form bypasses allocation snapshots, preview signatures and
    protected reading history. Keep this view available for inspection only.
    """
    list_display = ['user', 'work', 'month', 'pages', 'pages_read', 'carried_pages', 'locked']
    list_filter = ['month', 'locked']
    search_fields = ['work__title', 'user__username']
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

class ArchiveOnlyAdmin(admin.ModelAdmin):
    list_filter = ['is_archived']

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register([Person, Work, Edition, Tag], ArchiveOnlyAdmin)

class EntryInline(admin.TabularInline):
    model = RankingEntry
    extra = 0
    can_delete = False

@admin.register(Ranking)
class RankingAdmin(ArchiveOnlyAdmin):
    list_display = ['title', 'origin', 'status', 'is_archived', 'last_researched_at', 'updated_at']
    list_filter = ['origin', 'domain', 'status', 'is_archived']
    search_fields = ['title']
    inlines = [EntryInline]
    readonly_fields = ['created_at', 'updated_at', 'share_token', 'revision']

    def save_model(self, request, obj, form, change):
        from .views import ensure_revision
        if change:
            previous = Ranking.objects.select_for_update().get(pk=obj.pk)
            ensure_revision(previous)
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        from .views import save_revision
        super().save_related(request, form, formsets, change)
        save_revision(form.instance, 'Updated through administration' if change else 'Created through administration', initial=not change)

@admin.register(ResearchSource)
class ResearchSourceAdmin(ArchiveOnlyAdmin):
    list_display = ['source_id', 'title', 'ranking', 'family', 'eligible', 'is_archived']
    list_filter = ['ranking', 'family', 'eligible', 'is_archived']
    search_fields = ['title', 'evidence']

@admin.register(RankingRevision)
class RevisionAdmin(admin.ModelAdmin):
    readonly_fields = ['ranking', 'number', 'created_at', 'note', 'snapshot']
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
