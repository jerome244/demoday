from django.contrib import admin
from .models import ParseResult

@admin.register(ParseResult)
class ParseResultAdmin(admin.ModelAdmin):
    list_display = ("id", "file_name", "language", "created_at")
    list_filter = ("language", "created_at")
    search_fields = ("file_name",)
