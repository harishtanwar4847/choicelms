import frappe


def execute():
    sms_settings = frappe.get_single("SMS Settings")

    sms_settings.sms_gateway_url = "https://apps.vibgyortel.in/client/api/sendmessage"
    sms_settings.message_parameter = "sms"
    sms_settings.receiver_parameter = "mobiles"
    sms_settings.parameters = []

    sms_settings.append(
        "parameters", {"parameter": "apikey", "value": "3a48e2d603d37b69"}
    )
    sms_settings.append("parameters", {"parameter": "unicode", "value": "yes"})
    sms_settings.save()
    frappe.db.commit()
