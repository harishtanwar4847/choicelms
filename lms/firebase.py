from os.path import isfile

import firebase_admin
import frappe
from firebase_admin import credentials, exceptions, messaging

import lms


class FirebaseAdmin:
    app = None

    def __init__(self):
        firebase_credentials_file_path = frappe.get_site_path("firebase.json")

        if not isfile(firebase_credentials_file_path):
            raise lms.FirebaseCredentialsFileNotFoundError(
                "Firebase Credentials not found."
            )

        try:
            cred = credentials.Certificate(firebase_credentials_file_path)
            self.app = firebase_admin.initialize_app(cred)
        except ValueError as e:
            raise lms.InvalidFirebaseCredentialsError(str(e))

    def send_message(self, title, body, image=None, tokens=[], data=None):
        if not tokens:
            raise lms.FirebaseTokensNotProvidedError("Firebase tokens not provided.")
        notification = messaging.Notification(title, body, image)
        multicast_message = messaging.MulticastMessage(tokens, data, notification)
        try:
            messaging.send_multicast(multicast_message)
        except firebase_admin.exceptions.FirebaseError as e:
            raise lms.FirebaseError(str(e))

    def send_data(self, data, tokens=[]):
        if not data:
            raise lms.FirebaseDataNotProvidedError("Firebase data not provided.")
        multicast_message = messaging.MulticastMessage(tokens, data)
        try:
            messaging.send_multicast(multicast_message)
        except firebase_admin.exceptions.FirebaseError as e:
            raise lms.FirebaseError(str(e))

    def send_android_message(
        self,
        title,
        body,
        image=None,
        tokens=[],
        data=None,
        priority="normal",
        collapse_key="com.sparktechnologies.sparkloans",
        channel_id="channel_ID_1",
        sound="default",
    ):
        if not tokens:
            raise lms.FirebaseTokensNotProvidedError("Firebase tokens not provided.")

        notification = messaging.Notification(title, body, image)

        android_notification = messaging.AndroidNotification(
            title=title,
            body=body,
            channel_id=channel_id,
            priority=priority,
            icon=None,
            color=None,
            sound=sound,
            tag=None,
            click_action=None,
            body_loc_key=None,
            body_loc_args=None,
            title_loc_key=None,
            title_loc_args=None,
            image=None,
            ticker=None,
            sticky=None,
            event_timestamp=None,
            local_only=None,
            vibrate_timings_millis=None,
            default_vibrate_timings=None,
            default_sound=None,
            light_settings=None,
            default_light_settings=None,
            visibility=None,
            notification_count=None,
        )

        # Android notification
        android = messaging.AndroidConfig(
            collapse_key=collapse_key,
            priority=priority,
            notification=android_notification,
        )
        # IOS notification
        sound = messaging.CriticalSound(name=sound, volume=1.0)
        alert = messaging.ApsAlert(title=title, body=body)
        aps = messaging.Aps(alert=alert, content_available=True, sound=sound)
        payload = messaging.APNSPayload(aps=aps)
        headers = {
            "apns-push-type": "background",
            "apns-priority": "5",
            "apns-topic": "io.flutter.plugins.firebase.messaging",
        }
        apns = messaging.APNSConfig(payload=payload, headers=headers, fcm_options=None)
        multicast_message = messaging.MulticastMessage(
            tokens=tokens,
            data=data,
            notification=notification,
            android=android,
            apns=apns,
            webpush=None,
            fcm_options=None,
        )
        try:
            messaging.send_multicast(multicast_message)
        except firebase_admin.exceptions.FirebaseError as e:
            raise lms.FirebaseError(str(e))

    def delete_app(self):
        if self.app:
            firebase_admin.delete_app(self.app)
            self.app = None

    def __del__(self):
        self.delete_app()
