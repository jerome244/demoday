from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

class BlockAwareTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        if getattr(self.user, "blocked", False):
            raise AuthenticationFailed("User is blocked.")
        return data

class BlockAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = BlockAwareTokenObtainPairSerializer
