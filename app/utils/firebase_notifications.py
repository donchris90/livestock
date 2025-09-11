import json
import google.auth.transport.requests
from google.oauth2 import service_account
import requests

# 🔑 Path to your downloaded service account file
SERVICE_ACCOUNT_FILE = "afriklivestock-firebase-adminsdk-fbsvc-a27d6e3eec.json"
PROJECT_ID = "afriklivestock"  # Firebase project ID


def get_access_token():
    """Get OAuth2 access token using service account"""
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


def send_fcm_notification(token=None, topic=None, title="", body="", product_url=None, admin_message=None):
    """
    Send FCM notification to a specific device token or topic.

    Parameters:
    - token: individual device token for single user
    - topic: topic name (e.g., 'all_users') for broadcast
    - title: notification title
    - body: notification body
    - product_url: optional URL for product notifications
    - admin_message: optional admin message for general announcements
    """

    if not token and not topic:
        raise ValueError("You must provide either a token or a topic")

    access_token = get_access_token()
    url = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Build the message payload
    message_payload = {
        "notification": {"title": title, "body": body},
        "data": {}
    }

    # Add custom data if provided
    if product_url:
        message_payload["data"]["product_url"] = product_url
    if admin_message:
        message_payload["data"]["admin_message"] = admin_message

    # Decide target: token or topic
    if token:
        message_payload["token"] = token
    else:
        message_payload["topic"] = topic

    payload = {"message": message_payload}

    response = requests.post(url, headers=headers, json=payload)
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        print("FCM send error:", e, response.text)
    return response.json()
