from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Project

@receiver(post_save, sender=Project)
def add_creator_as_participant(sender, instance: Project, created: bool, **kwargs):
    if created:
        instance.participants.add(instance.creator)
