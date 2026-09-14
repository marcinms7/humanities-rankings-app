"""Shared records are archived, never physically deleted through the ORM."""
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import Person, Work, Edition, Tag, Ranking, RankingEntry, ResearchSource, RankingRevision


@receiver(pre_delete)
def protect_shared_records(sender, instance, **kwargs):
    protected = sender in {Person, Work, Edition, Tag, ResearchSource}
    if sender is Ranking:
        protected = instance.origin != 'personal'
    elif sender in {RankingEntry, RankingRevision}:
        protected = instance.ranking.origin != 'personal'
    if protected:
        raise ProtectedError('Shared catalog and research records cannot be deleted. Archive the record instead.', [instance])
