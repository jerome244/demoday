# community/views.py

# --- standard library ---
import hashlib
import io
import json
import re
import zipfile

# --- third-party ---
import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

# --- Django ---
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

# --- local ---
from .formatters import format_for_path
from .linters import lint_for_path
from .models import Message, Project, ProjectFile, Thread
from .parsing import build_project_summary, parse_project_files
from importlib import import_module


_GITHUB_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?(?:/|$)"
)

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

    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")
        sender_id = payload.get("sender_id", sender_id)
        content = payload.get("content", content)

    if not sender_id or not content:
        return HttpResponseBadRequest("sender_id and content are required.")

    sender = get_user_model().objects.get(pk=sender_id)
    msg = thread.add_message(sender=sender, content=content.strip())
    return JsonResponse({"message_id": msg.pk})

def _etag_for_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def project_file_detail(request, project_id: int, path: str):
    """
    GET   -> return file content (and ETag)
             query: ?lint=1  -> include diagnostics for current content
    PUT   -> replace entire content (JSON: {"content": "..."}), supports If-Match
    PATCH -> same as PUT

    Query flags for PUT/PATCH:
      ?format=1   -> auto-format based on file type (e.g. Black for .py)
      ?preview=1  -> return formatted/diagnosed text WITHOUT saving
      ?lint=1     -> include diagnostics in response
    """
    project = get_object_or_404(Project, pk=project_id)
    try:
        pf = ProjectFile.objects.get(project=project, path=path)
    except ProjectFile.DoesNotExist:
        return HttpResponseBadRequest("File not found")

    if request.method == "GET":
        etag = _etag_for_text(pf.content)
        data = {"project_id": project.id, "path": pf.path, "content": pf.content}
        if request.GET.get("lint") in ("1", "true", "yes", "on"):
            data["diagnostics"] = lint_for_path(path, pf.content)
        resp = JsonResponse(data)
        resp["ETag"] = etag
        return resp

    # PUT/PATCH: write new content
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    if "content" not in payload or not isinstance(payload["content"], str):
        return HttpResponseBadRequest("Missing or invalid 'content'")

    # Optional optimistic concurrency
    if_match = request.headers.get("If-Match")
    if if_match:
        current = _etag_for_text(pf.content)
        if if_match != current:
            resp = JsonResponse({"detail": "ETag mismatch; file changed."}, status=412)
            resp["ETag"] = current
            return resp

    # Normalize content (ensure single trailing newline)
    new_content = (payload["content"] or "").rstrip("\n") + "\n"

    # Optional size guard:
    # if len(new_content.encode("utf-8")) > 2_000_000:
    #     return HttpResponseBadRequest("File too large")

    # Flags
    autoformat = request.GET.get("format") in ("1", "true", "yes", "on")
    preview    = request.GET.get("preview") in ("1", "true", "yes", "on")
    want_lint  = request.GET.get("lint") in ("1", "true", "yes", "on")

    tool = None
    if autoformat:
        new_content, tool = format_for_path(path, new_content)

    diagnostics = lint_for_path(path, new_content) if want_lint else []

    if preview:
        # don't persist; show how it would look
        etag = _etag_for_text(new_content)
        resp = JsonResponse({
            "project_id": project.id,
            "path": pf.path,
            "formatted": new_content,
            "tool": tool or "none",
            "preview": True,
            "diagnostics": diagnostics,
        })
        resp["ETag"] = etag
        return resp

    # Persist
    pf.content = new_content
    pf.save(update_fields=["content"])

    etag = _etag_for_text(pf.content)
    resp = JsonResponse({
        "project_id": project.id,
        "path": pf.path,
        "content": pf.content,
        "saved": True,
        "tool": tool or "none",
        "diagnostics": diagnostics,
    })
    resp["ETag"] = etag
    return resp

@require_GET
def project_files_bulk(request, project_id: int):
    """GET /projects/<id>/files/bulk/?paths=a.py,b/c.py"""
    project = get_object_or_404(Project, pk=project_id)
    raw = request.GET.get("paths", "")
    paths = [p for p in (s.strip() for s in raw.split(",")) if p]
    if not paths:
        return HttpResponseBadRequest("Missing 'paths' query parameter")

    files = ProjectFile.objects.filter(project=project, path__in=paths)
    by_path = {pf.path: pf for pf in files}
    result = {p: {"found": False, "content": ""} for p in paths}
    for p in paths:
        if p in by_path:
            result[p] = {"found": True, "content": by_path[p].content}
    return JsonResponse({"project_id": project.id, "files": result})


def _user_in_project(user, project: Project) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return user == project.creator or project.participants.filter(pk=user.pk).exists()

def _get_or_create_project_chat(project: Project) -> Thread:
    """
    Create or fetch the single chat thread for this project.
    We key by a deterministic title; avoids DB schema changes.
    """
    title = f"project:{project.pk}:chat"
    thread, created = Thread.objects.get_or_create(title=title)
    # Ensure membership: creator + participants
    needed_user_ids = list(project.participants.values_list("id", flat=True)) + [project.creator_id]
    thread.participants.add(*needed_user_ids)
    return thread

@require_GET
def project_chat_info(request, project_id: int):
    """
    Return the chat thread for the project and basic metadata.
    """
    project = get_object_or_404(Project, pk=project_id)
    if not _user_in_project(request.user, project):
        return HttpResponseForbidden("Not allowed")

    thread = _get_or_create_project_chat(project)
    return JsonResponse({
        "project_id": project.id,
        "thread_id": thread.id,
        "title": thread.title,
        "participants": list(thread.participants.values("id", "username", "name")),
    })

@require_GET
def project_chat_messages(request, project_id: int):
    """
    Paginated list of messages for the project's chat.
    GET params: page (default 1), per_page (default 30), after_id (optional)
    """
    project = get_object_or_404(Project, pk=project_id)
    if not _user_in_project(request.user, project):
        return HttpResponseForbidden("Not allowed")

    thread = _get_or_create_project_chat(project)

    qs = thread.messages.select_related("sender").order_by("-timestamp")

    # Optional incremental fetch: messages with id > after_id (useful for polling)
    after_id = request.GET.get("after_id")
    if after_id:
        try:
            qs = qs.filter(id__gt=int(after_id)).order_by("id")
        except ValueError:
            return HttpResponseBadRequest("after_id must be an integer")
        # When after_id is used, skip pagination and return latest chunk
        results = [{
            "id": m.id,
            "sender_id": m.sender_id,
            "sender": (m.sender.name or m.sender.username),
            "content": m.content,
            "timestamp": m.timestamp.isoformat(),
            "likes": m.likes.count(),
        } for m in qs[:200]]
        return JsonResponse({"thread_id": thread.id, "results": results})

    # Standard pagination
    page = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", 30))
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    return JsonResponse({
        "thread_id": thread.id,
        "count": paginator.count,
        "num_pages": paginator.num_pages,
        "page": page_obj.number,
        "results": [{
            "id": m.id,
            "sender_id": m.sender_id,
            "sender": (m.sender.name or m.sender.username),
            "content": m.content,
            "timestamp": m.timestamp.isoformat(),
            "likes": m.likes.count(),
        } for m in page_obj.object_list]
    })

@require_POST
def project_chat_post(request, project_id: int):
    """
    Add a message to the project's chat.
    POST form or JSON: sender_id, content
    """
    project = get_object_or_404(Project, pk=project_id)
    thread = _get_or_create_project_chat(project)

    # Accept either form-encoded or JSON
    sender_id = request.POST.get("sender_id")
    content = request.POST.get("content")
    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")
        sender_id = payload.get("sender_id", sender_id)
        content = payload.get("content", content)

    if not sender_id or not content:
        return HttpResponseBadRequest("sender_id and content are required.")

    content = content.strip()
    if not content:
        return HttpResponseBadRequest("content cannot be empty")

    User = get_user_model()
    try:
        sender = User.objects.get(pk=sender_id)
    except User.DoesNotExist:
        return HttpResponseBadRequest("Invalid sender_id")

    if not _user_in_project(sender, project):
        return HttpResponseForbidden("Sender not in project")

    # Persist
    msg = thread.add_message(sender=sender, content=content)

    # Fan-out to the project's WebSocket group (non-blocking fail-safe)
    try:
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                f"projectchat_{project.id}",
                {
                    "type": "chat.message",  # maps to chat_message() in your consumer
                    "id": msg.id,
                    "sender_id": sender.id,
                    "sender": (sender.name or sender.username),
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "likes": 0,
                },
            )
    except Exception:
        # Don’t break the HTTP flow if WS infra is down
        pass

    # decide status
    is_json = bool(request.content_type and "application/json" in request.content_type)
    status_code = 200 if (is_json or request.user.is_authenticated) else 201

    return JsonResponse(
        {
            "message_id": msg.pk,
            "timestamp": msg.timestamp.isoformat(),
            "sender": (sender.name or sender.username),
            "content": msg.content,
        },
        status=status_code,
    )



def _parse_github_url(url: str):
    m = _GITHUB_RE.match(url or "")
    if not m:
        return None, None
    return m.group("owner"), m.group("repo")


def _zip_strip_top(zip_bytes: bytes) -> bytes:
    """
    Repack a zip so files are at the root (GitHub zipballs have <repo>-<sha>/).
    """
    src = zipfile.ZipFile(io.BytesIO(zip_bytes))
    out_buf = io.BytesIO()
    dst = zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED)

    names = src.namelist()
    if not names:
        src.close(); dst.close()
        return out_buf.getvalue()

    top_prefix = names[0].split("/")[0]  # e.g., repo-<sha>
    prefix = f"{top_prefix}/"

    for name in names:
        if name.endswith("/"):
            continue
        if name.startswith(prefix):
            rel = name[len(prefix):]  # drop <repo>-<sha>/
            dst.writestr(rel, src.read(name))

    dst.close()
    src.close()
    return out_buf.getvalue()


def _zip_only_subdir(zip_bytes: bytes, subdir: str) -> bytes:
    """
    GitHub zipballs have a dynamic top-level folder: <repo>-<sha>/
    This filters to a given subdir inside that, and rewrites paths to be relative
    to the subdir root.
    """
    src = zipfile.ZipFile(io.BytesIO(zip_bytes))
    out_buf = io.BytesIO()
    dst = zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED)

    # Normalize subdir (no leading slash)
    subdir = subdir.strip("/")

    # The top-level prefix varies – detect from first item
    # and then join with subdir to match entries.
    names = src.namelist()
    if not names:
        src.close(); dst.close()
        return out_buf.getvalue()
    top_prefix = names[0].split("/")[0]  # e.g., repo-<sha>
    wanted_prefix = f"{top_prefix}/{subdir}/"

    for name in names:
        if not name.endswith("/") and name.startswith(wanted_prefix):
            rel = name[len(wanted_prefix):]  # strip top/subdir prefixes
            data = src.read(name)
            zi = zipfile.ZipInfo(rel)
            dst.writestr(zi, data)

    dst.close()
    src.close()
    return out_buf.getvalue()



@csrf_exempt
@require_POST
def project_import_github(request, project_id: int):
    """
    POST JSON: {
      "repo_url": "https://github.com/owner/repo",
      "ref": "main",            # optional
      "subdir": "app",          # optional
      "token": "<gh_token>"     # optional, overrides settings.GITHUB_TOKEN
    }
    """
    project = get_object_or_404(Project, pk=project_id)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    repo_url = (payload.get("repo_url", "") or "").strip()
    ref = (payload.get("ref") or "").strip()
    subdir = (payload.get("subdir") or "").strip()
    token = payload.get("token") or getattr(settings, "GITHUB_TOKEN", "")

    owner, repo = _parse_github_url(repo_url)
    if not owner or not repo:
        return JsonResponse({"detail": "repo_url must be a valid GitHub repo URL"}, status=400)

    # GitHub zipball URL; ref optional
    zip_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"
    if ref:
        zip_url += f"/{ref}"

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    MAX_BYTES = 100 * 1024 * 1024
    try:
        r = requests.get(zip_url, headers=headers, stream=True, timeout=30)
    except requests.RequestException as e:
        return JsonResponse({"detail": f"Failed to reach GitHub: {e}"}, status=400)

    if r.status_code == 404:
        return JsonResponse({"detail": "Repository or ref not found"}, status=400)
    if r.status_code in (401, 403):
        return JsonResponse({"detail": "Unauthorized to access repository"}, status=403)
    if r.status_code >= 400:
        return JsonResponse({"detail": f"GitHub error: {r.status_code}"}, status=400)

    buf = io.BytesIO()
    total = 0
    for chunk in r.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_BYTES:
            return JsonResponse({"detail": "Zip too large"}, status=400)
        buf.write(chunk)
    zip_bytes = buf.getvalue()

    if subdir:
        zip_bytes = _zip_only_subdir(zip_bytes, subdir)
    else:
        zip_bytes = _zip_strip_top(zip_bytes)

    count = project.ingest_zip(io.BytesIO(zip_bytes))
    return JsonResponse(
        {
            "project_id": project.id,
            "imported_files": count,
            "owner": owner,
            "repo": repo,
            "ref": ref or "default",
        },
        status=200,
    )



@require_GET
def project_graph(request, project_id: int):
    project = get_object_or_404(Project, pk=project_id)
    files = {pf.path: pf.content for pf in ProjectFile.objects.filter(project=project)}

    # Try to use codeparsers.parsers.parse_project if it exists / is monkeypatched
    try:
        cp = import_module("codeparsers.parsers")
        parse_project_fn = getattr(cp, "parse_project", None)
    except Exception:
        parse_project_fn = None

    try:
        if callable(parse_project_fn):
            graph = parse_project_fn(files)  # tests may monkeypatch this
            if not isinstance(graph, dict) or "nodes" not in graph or "edges" not in graph:
                graph = {"nodes": [], "edges": []}
        else:
            # Fall back to your local project parser, but be resilient to bad files
            try:
                graph = parse_project_files(files)
            except Exception:
                graph = {"nodes": [], "edges": []}
    except Exception:
        graph = {"nodes": [], "edges": []}

    return JsonResponse({"project_id": project.id, "graph": graph})

@require_GET
def project_file_tree(request, project_id: int):
    project = get_object_or_404(Project, pk=project_id)
    # (optional) enforce access: if not _user_in_project(request.user, project): return HttpResponseForbidden("Not allowed")

    paths = list(ProjectFile.objects.filter(project=project).values_list("path", flat=True))

    # Build a nested tree from paths
    root = {"name": "", "type": "dir", "children": {}}

    for p in paths:
        parts = p.split("/")
        node = root
        for i, part in enumerate(parts):
            is_file = (i == len(parts) - 1)
            bucket = node["children"]
            if part not in bucket:
                bucket[part] = {"name": part, "type": "file" if is_file else "dir", "children": {} if not is_file else None}
            node = bucket[part]

    def to_list(n):
        if n["type"] == "file":
            return {"name": n["name"], "type": "file"}
        children = [to_list(c) for c in n["children"].values()]
        # sort dirs first, then files, alpha
        children.sort(key=lambda x: (x["type"] != "dir", x["name"]))
        return {"name": n["name"] or "/", "type": "dir", "children": children}

    tree = to_list(root)
    return JsonResponse({"project_id": project.id, "tree": tree, "total_files": len(paths)})



# community/views.py (near your existing project_summary)
from collections import Counter  # keep this single import

def _language_from_path(path: str) -> str:
    ext = (path.rsplit(".", 1)[-1] if "." in path else "").lower()
    return {
        "py": "python",
        "js": "javascript",
        "html": "html",
        "htm": "html",
        "css": "css",
    }.get(ext, ext or "unknown")

def _count_lines(text: str) -> int:
    if not text:
        return 0
    # count lines like editors do: splitlines then len
    return len(text.splitlines())

@require_GET
def project_summary(request, project_id: int):
    project = get_object_or_404(Project, pk=project_id)
    files_qs = ProjectFile.objects.filter(project=project).values_list("path", "content")

    file_paths = []
    total_lines = 0
    lang_counts = Counter()

    for path, content in files_qs:
        file_paths.append(path)
        lang_counts[_language_from_path(path)] += 1
        total_lines += _count_lines(content or "")

    # keep your original, parser-driven summary
    files_map = {pf.path: pf.content for pf in ProjectFile.objects.filter(project=project)}
    summary = build_project_summary(files_map)

    return JsonResponse({
        "project_id": project.id,
        "summary": summary,                     # original payload
        "file_paths": file_paths,               # new: stable list of paths
        "languages": dict(lang_counts),         # new: language histogram
        "totals": {"files": len(file_paths), "lines": total_lines},  # new: rollups
    })

