from contextvars import ContextVar

actor = ContextVar('notification_actor', default=None)


class NotificationActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # DRF authenticates later; evaluate its JWT authenticator for event attribution.
        from rest_framework_simplejwt.authentication import JWTAuthentication
        user = getattr(request, 'user', None)
        try:
            result = JWTAuthentication().authenticate(request)
            if result:
                user = result[0]
        except Exception:
            user = None  # The view still returns its normal authentication error.
        token = actor.set(user if user and user.is_authenticated else None)
        try:
            return self.get_response(request)
        finally:
            actor.reset(token)

