from rest_framework_simplejwt.tokens import AccessToken


def authenticate_client(client, user):
    """Attach a short-lived bearer token to a DRF APIClient."""
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client
