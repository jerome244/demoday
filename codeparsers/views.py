import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views import View
from .parsers import parse_code
from .models import ParseResult

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
