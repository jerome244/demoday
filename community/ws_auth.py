# community/ws_auth.py
import urllib.parse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from channels.middleware import BaseMiddleware
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

class JwtQueryAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = dict(urllib.parse.parse_qsl(scope.get("query_string", b"").decode()))
        raw = None
        if "token" in query:
            raw = f"Bearer {query['token']}"
        else:
            # Sec-WebSocket-Protocol isn’t great for auth; try headers
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization")
            raw = auth.decode() if auth else None

        scope["user"] = AnonymousUser()
        if raw:
            try:
                user_auth = JWTAuthentication()
                validated = user_auth.get_validated_token(raw.split()[-1])
                user = await _get_user(await _get_user_id_from_token(validated))
                if user:
                    scope["user"] = user
            except InvalidToken:
                pass

        return await super().__call__(scope, receive, send)

async def _get_user_id_from_token(token):
    # SimpleJWT typically stores user id under 'user_id'
    return token.get("user_id")

async def _get_user(user_id):
    if not user_id:
        return None
    User = get_user_model()
    try:
        return await User.objects.aget(pk=user_id)
    except User.DoesNotExist:
        return None
