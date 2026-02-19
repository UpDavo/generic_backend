import uuid
from django.db import models
from django.utils.timezone import now


class BaseModel(models.Model):
    external_id = models.UUIDField(unique=True, default=uuid.uuid4)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True)

    def delete(self, *args, **kwargs):
        self.deleted_at = now()

        super(BaseModel, self).save(*args, **kwargs)

    def hard_delete(self, *args, **kwargs):
        super(BaseModel, self).delete(*args, **kwargs)

    @classmethod
    def get_by_id(cls, id):
        return cls.objects.filter(id=id).first()

    @classmethod
    def get_by_external_id(cls, external_id):
        return cls.objects.filter(external_id=external_id).first()

    class Meta:
        abstract = True
