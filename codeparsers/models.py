from django.db import models

class ParseResult(models.Model):
    file_name = models.CharField(max_length=255)
    language = models.CharField(max_length=20, db_index=True)
    data = models.JSONField()  # Requires Django 3.1+
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.language}:{self.file_name}"
