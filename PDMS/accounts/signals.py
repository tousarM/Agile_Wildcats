from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile

@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, **kwargs):
    profile, _ = Profile.objects.get_or_create(
        user=instance,
        defaults={"email": instance.email},
    )

    if instance.email and profile.email != instance.email:
        profile.email = instance.email
        profile.save(update_fields=["email"])
