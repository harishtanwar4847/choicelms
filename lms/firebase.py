import frappe
import lms
import firebase_admin
from firebase_admin import credentials, messaging, exceptions
from os.path import isfile

class FirebaseAdmin():
	app = None

	def __init__(self):
		firebase_credentials_file_path = frappe.get_site_path('firebase.json')

		if not isfile(firebase_credentials_file_path):
			raise lms.FirebaseCredentialsFileNotFoundError('Firebase Credentials not found.')
		
		try:
			cred = credentials.Certificate(firebase_credentials_file_path)
			self.app = firebase_admin.initialize_app(cred)
		except ValueError as e:
			raise lms.InvalidFirebaseCredentialsError(str(e))
		
	def send_message(self, title, body, image=None, tokens=[], data=None):
		if not tokens:
			raise lms.FirebaseTokensNotProvidedError('Firebase tokens not provided.')
		notification = messaging.Notification(title, body, image)
		multicast_message = messaging.MulticastMessage(tokens, data, notification)
		try:
			messaging.send_multicast(multicast_message)
		except firebase_admin.exceptions.FirebaseError as e:
			raise lms.FirebaseError(str(e))

	def send_data(self, data, tokens=[]):
		if not data:
			raise lms.FirebaseDataNotProvidedError('Firebase data not provided.')
		multicast_message = messaging.MulticastMessage(tokens, data)
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

		
