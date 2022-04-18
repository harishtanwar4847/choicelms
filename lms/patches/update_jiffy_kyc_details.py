from datetime import datetime

import frappe

from lms.user import request_choice_kyc


def execute():
    frappe.reload_doc("Lms", "DocType", "User KYC")
    frappe.reload_doc("Lms", "DocType", "User Bank Account")

    user_kyc_list = frappe.get_all("User KYC", fields=["*"])
    for kyc in user_kyc_list:
        try:
            res_json = request_choice_kyc({"pan_no": kyc.pan_no})

            # update kyc details
            frappe.db.sql(
                """Update `tabUser KYC` set kyc_type = "CHOICE", investor_name='{}', first_name='{}', middle_name='{}', last_name='{}', email_id='{}', date_of_birth='{}', father_name='{}', mother_name='{}', address='{}', permanant_address1='{}',                 permanant_address2='{}', permanant_address3='{}', per_city='{}', per_state='{}', per_pincode='{}', current_address1='{}', current_address2=' {}', current_address3='{}', curr_city='{}', curr_state='{}', curr_pincode='{}', address_city='{}', address_state='{}', address_pincode='{}',city='{}', state='{}', pincode='{}', address_proof_type='{}', same_as_current_address={}, mobile_number='{}', choice_client_id='{}', pan_no='{}' where name='{}'""".format(
                    res_json["investorName"],
                    res_json["firstName"],
                    res_json["middleName"],
                    res_json["lastName"],
                    res_json["emailId"],
                    datetime.strptime(
                        res_json["dateOfBirth"], "%Y-%m-%dT%H:%M:%S.%f%z"
                    ).strftime("%Y-%m-%d"),
                    res_json["fatherName"],
                    res_json["motherName"],
                    "".join(
                        [
                            res_json["permanantAddress1"],
                            res_json["permanantAddress2"],
                            res_json["permanantAddress3"],
                            res_json["perCity"],
                            " ",
                            res_json["perState"],
                            " ",
                            res_json["perPincode"],
                        ]
                    ),
                    res_json["permanantAddress1"],
                    res_json["permanantAddress2"],
                    res_json["permanantAddress3"],
                    res_json["perCity"],
                    res_json["perState"],
                    res_json["perPincode"],
                    res_json["currentAddress1"],
                    res_json["currentAddress2"],
                    res_json["currentAddress3"],
                    res_json["currCity"],
                    res_json["currState"],
                    res_json["currPincode"],
                    res_json["addressCity"],
                    res_json["addressState"],
                    res_json["addressPinCode"],
                    res_json["city"],
                    res_json["state"],
                    res_json["pinCode"],
                    res_json["addressProofType"],
                    1 if res_json["sameAsCurrentAddress"] == "true" else 0,
                    res_json["mobileNum"],
                    res_json["clientId"],
                    res_json["panNum"],
                    kyc.name,
                )
            )

            if res_json["banks"]:
                for bank in res_json["banks"]:
                    user_bank_acc_name = frappe.db.get_value(
                        "User Bank Account",
                        {"parent": kyc.name, "account_number": bank["accountNumber"]},
                    )
                    if user_bank_acc_name:
                        frappe.db.sql(
                            """Update `tabUser Bank Account` set is_default={}, account_type='{}', cancel_cheque_file_name='{}', ifsc='{}', micr='{}', branch='{}', bank='{}', bank_address='{}', contact='{}', city='{}', district='{}', state='{}', bank_mode='{}', bank_code='{}', bank_zip_code='{}', address_state='{}', account_number='{}' where name='{}' and parent='{}' and account_number='{}'""".format(
                                1 if bank["defaultBank"] == "Y" else 0,
                                bank["accountType"],
                                bank["cancelChequeFileName"],
                                bank["ifsc"],
                                bank["micr"],
                                bank["branch"],
                                bank["bank"],
                                bank["bankAddress"],
                                bank["contact"],
                                bank["city"],
                                bank["district"],
                                bank["state"],
                                bank["bankMode"],
                                bank["bankcode"],
                                bank["bankZipCode"],
                                bank["addressState"],
                                bank["accountNumber"],
                                user_bank_acc_name,
                                kyc.name,
                                bank["accountNumber"],
                            )
                        )
            frappe.db.commit()
        except:
            pass
