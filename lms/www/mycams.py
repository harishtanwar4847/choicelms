import json

import frappe
import utils

import lms


def get_context(context):
    user = lms.__user()
    user_kyc = lms.__user_kyc(user.name)
    customer = lms.__customer(user.name)

    cart = frappe.get_doc("Cart", str(frappe.form_dict.cart_name))
    if not cart:
        return utils.respondNotFound(message=frappe._("Cart not found."))
    if cart.customer != customer.name:
        return utils.respondForbidden(message=frappe._("Please use your own cart."))

    if customer.cams_email_id and cart.instrument_type == "Mutual Fund":
        # create payload
        datetime_signature = lms.create_signature_mycams()
        las_settings = frappe.get_single("LAS Settings")

        data = {
            "loginemail": customer.cams_email_id,  # mandatory
            "netbankingemail": customer.cams_email_id,  # mandatory
            "clientid": las_settings.client_id,  # mandatory
            "clientname": las_settings.client_name,  # mandatory
            "pan": user_kyc.pan_no,  # mandatory
            "bankschemetype": cart.scheme_type,  # mandatory
            "requestip": "",
            "bankrefno": las_settings.bank_reference_no,  # mandatory
            "bankname": las_settings.bank_name,  # mandatory
            "branchname": "Mumbai",
            "address1": "Address1",
            "address2": "Address2",
            "address3": "Address3",
            "city": "Mumbai",
            "state": "MH",
            "country": "India",
            "pincode": "400706",
            "phoneoff": "02212345678",
            "phoneres": "02221345678",
            "faxno": "02231245678",
            "faxres": "1357",
            "addinfo1": cart.name,
            "addinfo2": cart.customer,
            "addinfo3": cart.customer_name,
            "addinfo4": "4",
            "addinfo5": "5",
            "mobile": customer.phone,
            "requesterid": customer.name,
            "ipaddress": "103.19.132.194",
            "requestresponse": "1",
            "sessionid": datetime_signature[0],  # mandatory
            "executiondate": datetime_signature[0],  # mandatory
            "signature": datetime_signature[1],  # mandatory
            "requestername": customer.full_name,
            "deviceid": "chrome",
            "osid": "Windows",
            "url": frappe.utils.get_url(),
            "redirecturl": frappe.utils.get_url(
                "/api/method/lms.decrypt_lien_marking_response"
            ),  # mandatory
            "markid": "mark12",
            "verifyid": "verify12",
            "approveid": "appro12",
        }

        encrypted_data = lms.AESCBC(
            las_settings.encryption_key, las_settings.iv
        ).encrypt(json.dumps(data))
        lms.create_log(
            {
                "Customer name": customer.full_name,
                "json_payload": data,
                "encrypted_request": encrypted_data,
            },
            "lien_marking_request",
        )

    context.encrypted = encrypted_data
