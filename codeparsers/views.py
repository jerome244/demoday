import json, zipfile, posixpath, traceback
from io import BytesIO
from django.http import JsonResponse, HttpResponseBadRequest
from django.views import View
from .dispatcher import parse_code
from .models import ParseResult
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .graph import build_project_graph
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse, HttpResponseBadRequest
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

@method_decorator(csrf_exempt, name="dispatch")
class ParseAPI(View):
    """
    POST JSON body:
    {
      "language": "python|c|css|html|js",
      "file_name": "example.py",
      "file_content": "...",
      "all_files": {"styles.css": "..."}   # optional
      "save": true                         # optional: persist to DB
    }
    """
    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8"))
            language = payload["language"]
            file_name = payload["file_name"]
            file_content = payload["file_content"]
            all_files = payload.get("all_files") or {}
            save = bool(payload.get("save", False))
        except Exception as exc:
            return HttpResponseBadRequest(f"Invalid JSON: {exc}")

        try:
            result = parse_code(language, file_name, file_content, all_files)
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))

        response = {"result": result}
        if save:
            pr = ParseResult.objects.create(
                file_name=file_name,
                language=language.lower(),
                data=result,
            )
            response["id"] = pr.id
        return JsonResponse(response)

@method_decorator(csrf_exempt, name="dispatch")
class ParseZipAPI(APIView):
    """
    POST multipart/form-data with a "file" field (zip).
    Returns:
      {
        "global": {...},
        "files":  {...},
        "sources": {...}
      }
    """
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [AllowAny]

    MAX_FILE_CHARS = 200_000     # per-file cap
    MAX_TOTAL_CHARS = 2_000_000  # total cap

    @staticmethod
    def _norm(path: str) -> str:
        # normalize to forward slashes, strip leading ./ and redundant segments
        return posixpath.normpath(path).lstrip("./")

    def post(self, request, *args, **kwargs):
        up = request.FILES.get("file")
        if not up:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Robust read (UploadedFile may be in-memory or temp file)
        try:
            # IMPORTANT: read the stream once, then wrap in BytesIO for zipfile
            raw_bytes = up.read()
        except Exception as e:
            return Response({"detail": f"upload read error: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        files: dict[str, str] = {}
        total_chars = 0

        try:
            with zipfile.ZipFile(BytesIO(raw_bytes)) as z:
                for name in z.namelist():
                    # skip directories and macOS metadata
                    if name.endswith("/") or name.startswith("__MACOSX/"):
                        continue

                    try:
                        with z.open(name) as fp:
                            raw = fp.read()
                    except Exception as e:
                        # Skip unreadable member but keep going
                        continue

                    # decode text (skip binaries)
                    text = None
                    for enc in ("utf-8", "utf-16", "latin-1"):
                        try:
                            text = raw.decode(enc)
                            break
                        except UnicodeDecodeError:
                            continue
                    if text is None:
                        continue

                    # enforce caps
                    text = text[: self.MAX_FILE_CHARS]
                    remain = self.MAX_TOTAL_CHARS - total_chars
                    if remain <= 0:
                        break
                    if len(text) > remain:
                        text = text[:remain]

                    if not text:
                        continue

                    files[self._norm(name)] = text
                    total_chars += len(text)

                    if total_chars >= self.MAX_TOTAL_CHARS:
                        break

        except zipfile.BadZipFile:
            return Response({"detail": "invalid zip"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Unexpected zip handling error
            traceback.print_exc()
            return Response({"detail": f"zip processing error: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        if not files:
            return Response({"detail": "zip empty or no text files found"}, status=status.HTTP_400_BAD_REQUEST)

        # Build the cross-file graph — protect this too
        try:
            global_results, file_results = build_project_graph(files)
        except Exception as e:
            traceback.print_exc()
            return Response({"detail": f"graph build error: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"global": global_results, "files": file_results, "sources": files},
            status=status.HTTP_200_OK,
        )
class GraphView(TemplateView):
    template_name = "codeparsers/graph_view.html"
    