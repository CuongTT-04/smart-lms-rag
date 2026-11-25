from django.core.signals import request_finished
from django.db import close_old_connections
from apps.users.authentication import issue_access_token


def authenticate_client(client, user):
    """Attach a short-lived bearer token to a DRF APIClient."""
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_access_token(user)}")
    return client


def close_response(response):
    """Close a streaming test response without letting request_finished drop TestCase atomics."""
    connected = request_finished.disconnect(close_old_connections)
    try:
        response.close()
    finally:
        if connected:
            request_finished.connect(close_old_connections)
