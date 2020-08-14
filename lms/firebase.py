import frappe
import lms
import firebase_admin
from firebase_admin import credentials
from os.path import isfile

class FirebaseAdmin():
	app = None

	def __init__(self):
		firebase_credentials_file_path = frappe.get_site_path('firebase.json')

		if not isfile(firebase_credentials_file_path):
			raise lms.FirebaseCredentialsFileNotFoundError
		
		try:
			cred = credentials.Certificate(firebase_credentials_file_path)
			self.app = firebase_admin.initialize_app(cred)
		except ValueError as e:
			raise lms.InvalidFirebaseCredentialsError(str(e))
		

	def __del__(self):
		if self.app:
			firebase_admin.delete_app(self.app)
			self.app = None

		
