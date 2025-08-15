from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from .models import Project, Thread, Message

@require_POST
def upload_zip(request, project_id: int):
    project = get_object_or_404(Project, pk=project_id)
    zip_file = request.FILES.get("file")
    if not zip_file:
        return HttpResponseBadRequest("Missing file")
    count = project.ingest_zip(zip_file)
    return JsonResponse({"ingested": count})

def download_project(request, project_id: int):
    project = get_object_or_404(Project, pk=project_id)
    data = project.as_zip_bytes()
    resp = HttpResponse(data, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{project.name}.zip"'
    return resp

@require_POST
def thread_add_message(request, thread_id: int):
    thread = get_object_or_404(Thread, pk=thread_id)
    sender_id = request.POST.get("sender_id")
    content = request.POST.get("content", "")
    if not sender_id or not content:
        return HttpResponseBadRequest("sender_id and content are required.")
    sender = get_user_model().objects.get(pk=sender_id)
    msg = thread.add_message(sender=sender, content=content)
    return JsonResponse({"message_id": msg.pk})
