# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
from datetime import datetime, timedelta

import frappe
import requests
import utils
from frappe import _
from frappe.model.document import Document
from num2words import num2words

import lms
from lms.exceptions import PledgeSetupFailureException
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.collateral_ledger.collateral_ledger import CollateralLedger
from lms.lms.doctype.user_token.user_token import send_sms


class LoanApplication(Document):
    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def esign_request(self, increase_loan):
        try:
            customer = self.get_customer()
            user = frappe.get_doc("User", customer.user)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            lender = self.get_lender()
            diff = self.drawing_power
            logo_file_path_1 = lender.get_lender_logo_file()
            logo_file_path_2 = lender.get_lender_address_file()
            if self.loan:
                loan = self.get_loan()
                # increased_sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                #     (self.total_collateral_value + loan.total_collateral_value)
                #     * self.allowable_ltv
                #     / 100
                # )
                actual_dp = 0
                for i in loan.items:
                    i.amount = i.price * i.pledged_quantity
                    i.eligible_amount = ((i.eligible_percentage or 0) / 100) * i.amount
                    actual_dp += i.eligible_amount
                drawing_power = 0
                for i in self.items:
                    i.amount = i.price * i.pledged_quantity
                    dp = ((i.eligible_percentage or 0) / 100) * i.amount
                    i.eligibile_amount = dp
                    drawing_power += dp
                increased_sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                    actual_dp + drawing_power
                )
                new_increased_sanctioned_limit = (
                    increased_sanctioned_limit
                    if increased_sanctioned_limit < lender.maximum_sanctioned_limit
                    else lender.maximum_sanctioned_limit
                )
                frappe.db.set_value(
                    self.doctype,
                    self.name,
                    "increased_sanctioned_limit",
                    new_increased_sanctioned_limit,
                    update_modified=False,
                )
                diff = new_increased_sanctioned_limit - loan.sanctioned_limit

            if user_kyc.address_details:
                address_details = frappe.get_doc(
                    "Customer Address Details", user_kyc.address_details
                )
                address = (
                    (
                        (str(address_details.perm_line1) + ", ")
                        if address_details.perm_line1
                        else ""
                    )
                    + (
                        (str(address_details.perm_line2) + ", ")
                        if address_details.perm_line2
                        else ""
                    )
                    + (
                        (str(address_details.perm_line3) + ", ")
                        if address_details.perm_line3
                        else ""
                    )
                    + str(address_details.perm_city)
                    + ", "
                    + str(address_details.perm_dist)
                    + ", "
                    + str(address_details.perm_state)
                    + ", "
                    + str(address_details.perm_country)
                    + ", "
                    + str(address_details.perm_pin)
                )
            else:
                address = ""

            if user_kyc.address_details:
                address_details = frappe.get_doc(
                    "Customer Address Details", user_kyc.address_details
                )

                line1 = str(address_details.perm_line1)
                if line1:
                    addline1 = "{},<br/>".format(line1)
                else:
                    addline1 = ""

                line2 = str(address_details.perm_line2)
                if line2:
                    addline2 = "{},<br/>".format(line2)
                else:
                    addline2 = ""

                line3 = str(address_details.perm_line3)
                if line3:
                    addline3 = "{},<br/>".format(line3)
                else:
                    addline3 = ""

                perm_city = str(address_details.perm_city)
                perm_dist = str(address_details.perm_dist)
                perm_state = str(address_details.perm_state)
                perm_pin = str(address_details.perm_pin)

            else:
                address_details = ""

            interest_config = frappe.get_value(
                "Interest Configuration",
                {
                    "to_amount": [
                        ">=",
                        lms.validate_rupees(
                            float(
                                new_increased_sanctioned_limit
                                if self.loan and not self.loan_margin_shortfall
                                else self.drawing_power
                            )
                        ),
                    ],
                },
                order_by="to_amount asc",
            )

            int_config = frappe.get_doc("Interest Configuration", interest_config)
            roi_ = round((self.base_interest * 12), 2)
            charges = lms.charges_for_apr(
                lender.name,
                lms.validate_rupees(float(diff)),
            )
            # apr = lms.calculate_apr(
            #     self.name,
            #     roi_,
            #     12,
            #     int(
            #         lms.validate_rupees(
            #             float(
            #                 new_increased_sanctioned_limit
            #                 if self.loan and not self.loan_margin_shortfall
            #                 else self.drawing_power
            #             )
            #         )
            #     ),
            #     charges.get("total"),
            # )
            annual_default_interest = lender.default_interest * 12
            sanctionlimit = (
                new_increased_sanctioned_limit
                if self.loan and not self.loan_margin_shortfall
                else self.drawing_power
            )
            interest_charges_in_amount = int(
                lms.validate_rupees(float(sanctionlimit))
            ) * (roi_ / 100)
            interest_per_month = float(interest_charges_in_amount / 12)
            final_payment = float(interest_per_month) + sanctionlimit
            apr = lms.calculate_irr(
                name_=self.name,
                sanction_limit=float(sanctionlimit),
                interest_per_month=interest_per_month,
                final_payment=final_payment,
                charges=charges.get("total"),
            )

            doc = {
                "esign_date": frappe.utils.now_datetime().strftime("%d-%m-%Y"),
                "loan_account_number": loan.name if self.loan else "",
                "loan_application_number": self.name,
                "borrower_name": customer.full_name,
                "borrower_address": address,
                "addline1": addline1,
                "addline2": addline2,
                "addline3": addline3,
                "city": perm_city,
                "district": perm_dist,
                "state": perm_state,
                "pincode": perm_pin,
                # "sanctioned_amount": frappe.utils.fmt_money(float(self.drawing_power)),
                "logo_file_path_1": logo_file_path_1.file_url
                if logo_file_path_1
                else "",
                "logo_file_path_2": logo_file_path_2.file_url
                if logo_file_path_2
                else "",
                "sanctioned_amount": frappe.utils.fmt_money(
                    float(
                        new_increased_sanctioned_limit
                        if self.loan and not self.loan_margin_shortfall
                        else self.drawing_power
                    )
                ),
                "sanctioned_amount_in_words": lms.number_to_word(
                    lms.validate_rupees(
                        float(
                            new_increased_sanctioned_limit
                            if self.loan and not self.loan_margin_shortfall
                            else self.drawing_power,
                        )
                    )
                ).title(),
                "roi": roi_,
                "apr": apr,
                "documentation_charges_kfs": frappe.utils.fmt_money(
                    charges.get("documentation_charges")
                ),
                "processing_charges_kfs": frappe.utils.fmt_money(
                    charges.get("processing_fees")
                ),
                "net_disbursed_amount": frappe.utils.fmt_money(
                    float(sanctionlimit) - charges.get("total")
                ),
                "total_amount_to_be_paid": frappe.utils.fmt_money(
                    float(sanctionlimit)
                    + charges.get("total")
                    + interest_charges_in_amount
                ),
                "loan_application_no": self.name,
                "rate_of_interest": lender.rate_of_interest,
                "rebate_interest": self.rebate_interest,
                "default_interest": annual_default_interest,
                "rebait_threshold": lender.rebait_threshold,
                "penal_charges": lender.renewal_penal_interest
                if lender.renewal_penal_interest
                else "",
                "documentation_charges_kfs": frappe.utils.fmt_money(
                    charges.get("documentation_charges")
                ),
                "processing_charges_kfs": frappe.utils.fmt_money(
                    charges.get("processing_fees")
                ),
                "interest_charges_in_amount": frappe.utils.fmt_money(
                    interest_charges_in_amount
                ),
                "interest_per_month": frappe.utils.fmt_money(interest_per_month),
                "final_payment": frappe.utils.fmt_money(final_payment),
                "renewal_charges": lms.validate_rupees(lender.renewal_charges)
                if lender.renewal_charge_type == "Fix"
                else lms.validate_percent(lender.renewal_charges),
                "renewal_charge_type": lender.renewal_charge_type,
                "renewal_charge_in_words": lms.number_to_word(
                    lms.validate_rupees(lender.renewal_charges)
                ).title()
                if lender.renewal_charge_type == "Fix"
                else "",
                "renewal_min_amt": lms.validate_rupees(lender.renewal_minimum_amount),
                "renewal_max_amt": lms.validate_rupees(lender.renewal_maximum_amount),
                "documentation_charge": lms.validate_rupees(
                    lender.documentation_charges
                )
                if lender.documentation_charge_type == "Fix"
                else lms.validate_percent(lender.documentation_charges),
                "documentation_charge_type": lender.documentation_charge_type,
                "documentation_charge_in_words": lms.number_to_word(
                    lms.validate_rupees(lender.documentation_charges)
                ).title()
                if lender.documentation_charge_type == "Fix"
                else "",
                "documentation_min_amt": lms.validate_rupees(
                    lender.lender_documentation_minimum_amount
                ),
                "documentation_max_amt": lms.validate_rupees(
                    lender.lender_documentation_maximum_amount
                ),
                "lender_processing_fees_type": lender.lender_processing_fees_type,
                "processing_charge": lms.validate_rupees(lender.lender_processing_fees)
                if lender.lender_processing_fees_type == "Fix"
                else lms.validate_percent(lender.lender_processing_fees),
                "processing_charge_in_words": lms.number_to_word(
                    lms.validate_rupees(lender.lender_processing_fees)
                ).title()
                if lender.lender_processing_fees_type == "Fix"
                else "",
                "processing_min_amt": lms.validate_rupees(
                    lender.lender_processing_minimum_amount
                ),
                "processing_max_amt": lms.validate_rupees(
                    lender.lender_processing_maximum_amount
                ),
                # "stamp_duty_charges": int(lender.lender_stamp_duty_minimum_amount),
                "transaction_charges_per_request": lms.validate_rupees(
                    lender.transaction_charges_per_request
                ),
                "security_selling_share": lender.security_selling_share,
                "cic_charges": lms.validate_rupees(lender.cic_charges),
                "total_pages": lender.total_pages,
                "lien_initiate_charge_type": lender.lien_initiate_charge_type,
                "invoke_initiate_charge_type": lender.invoke_initiate_charge_type,
                "revoke_initiate_charge_type": lender.revoke_initiate_charge_type,
                "lien_initiate_charge_minimum_amount": lms.validate_rupees(
                    lender.lien_initiate_charge_minimum_amount
                ),
                "lien_initiate_charge_maximum_amount": lms.validate_rupees(
                    lender.lien_initiate_charge_maximum_amount
                ),
                "lien_initiate_charges": lms.validate_rupees(
                    lender.lien_initiate_charges
                )
                if lender.lien_initiate_charge_type == "Fix"
                else lms.validate_percent(lender.lien_initiate_charges),
                "invoke_initiate_charges_minimum_amount": lms.validate_rupees(
                    lender.invoke_initiate_charges_minimum_amount
                ),
                "invoke_initiate_charges_maximum_amount": lms.validate_rupees(
                    lender.invoke_initiate_charges_maximum_amount
                ),
                "invoke_initiate_charges": lms.validate_rupees(
                    lender.invoke_initiate_charges
                )
                if lender.invoke_initiate_charge_type == "Fix"
                else lms.validate_percent(lender.invoke_initiate_charges),
                "revoke_initiate_charges_minimum_amount": lms.validate_rupees(
                    lender.revoke_initiate_charges_minimum_amount
                ),
                "revoke_initiate_charges_maximum_amount": lms.validate_rupees(
                    lender.revoke_initiate_charges_maximum_amount
                ),
                "revoke_initiate_charges": lms.validate_rupees(
                    lender.revoke_initiate_charges
                )
                if lender.revoke_initiate_charge_type == "Fix"
                else lms.validate_percent(lender.revoke_initiate_charges),
            }

            if increase_loan:
                doc["old_sanctioned_amount"] = frappe.utils.fmt_money(
                    loan.sanctioned_limit
                )
                doc["old_sanctioned_amount_in_words"] = lms.number_to_word(
                    lms.validate_rupees(loan.sanctioned_limit)
                ).title()
                agreement_template = lender.get_loan_enhancement_agreement_template()
                loan_agreement_file = "loan-enhancement-aggrement.pdf"
                coordinates = lender.enhancement_coordinates.split(",")
                esign_page = lender.enhancement_esign_page
            else:
                agreement_template = lender.get_loan_agreement_template()
                loan_agreement_file = "loan-aggrement.pdf"
                coordinates = lender.coordinates.split(",")
                esign_page = lender.esign_page

            agreement = frappe.render_template(
                agreement_template.get_content(), {"doc": doc}
            )

            # from frappe.utils.pdf import get_pdf

            agreement_pdf = lms.get_pdf(agreement)
            las_settings = frappe.get_single("LAS Settings")
            headers = {"userId": las_settings.choice_user_id}
            files = {"file": (loan_agreement_file, agreement_pdf)}

            return {
                "file_upload_url": "{}{}".format(
                    las_settings.esign_host, las_settings.esign_upload_file_uri
                ),
                "headers": headers,
                "files": files,
                "esign_url_dict": {
                    "x": coordinates[0],
                    "y": coordinates[1],
                    "page_number": esign_page,
                },
                "esign_url": "{}{}".format(
                    las_settings.esign_host, las_settings.esign_request_uri
                ),
            }
        except Exception:
            frappe.log_error(
                title="Esign Request Loan Doc",
                message=frappe.get_traceback() + "\n\nLoan name \n" + str(self.name),
            )

    def after_insert(self):
        user_roles = frappe.db.get_values(
            "Has Role", {"parent": frappe.session.user, "parenttype": "User"}, ["role"]
        )
        user_role = []
        for i in list(user_roles):
            user_role.append(i[0])
        if "Loan Customer" not in user_role:
            self.is_offline_loan = 1
            self.status = "Executing pledge"
            self.workflow_state = "Executing pledge"
            self.pledge_status = "Success"
            instrument_type = []
            pledged_total = 0
            eligible_percent = 0
            total_collateral = 0
            isin = [i.isin for i in self.items]
            allowed_securities = lms.get_allowed_securities(
                isin, self.lender, self.instrument_type
            )
            for i in self.items:
                security = allowed_securities.get(i.isin)
                i.security_category = security.security_category
                i.eligible_percentage = security.eligible_percentage
                i.amc_code = security.amc_code
                i.pledge_status = "Success"
                i.lender_approval_status = "Approved"
                i.requested_quantity = i.pledged_quantity
                i.amc_code = security.amc_code
                eligible_percent += i.eligible_percentage
                i.amount = i.price * i.pledged_quantity
                i.eligible_amount = (
                    round(i.pledged_quantity, 3)
                    * i.price
                    * security.eligible_percentage
                ) / 100
                pledged_total += i.amount

                i.type = security.scheme_type if security.scheme_type else "Shares"

                if i.lender_approval_status == "Approved":
                    i.pledge_executed = 1
                    total_collateral += i.amount
                instrument_type.append(i.type)
            if len(set(instrument_type)) == 1 and (
                "Equity" in set(instrument_type) or "Debt" in set(instrument_type)
            ):
                self.scheme_type = instrument_type[0]

            self.allowable_ltv = float(eligible_percent / len(self.items))
            self.total_collateral_value = total_collateral
            self.pledged_total_collateral_value = pledged_total
            self.save(ignore_permissions=True)
            frappe.db.commit()

            self.status = "Pledge executed"
            self.workflow_state = "Pledge executed"
            self.save(ignore_permissions=True)
            frappe.db.commit()

            for i in self.items:
                # i.date_of_pledge = frappe.utils.now_datetime().strftime("%d-%m-%Y")
                collateral_ledger_data = {
                    "prf": i.prf_number,
                    "date_of_pledge": i.date_of_pledge,
                    # "expiry": self.expiry_date,
                    "pledgor_boid": self.pledgor_boid,
                    "pledgee_boid": self.pledgee_boid,
                    "amc_code": i.amc_code,
                    "folio": i.folio,
                    "scheme_code": i.scheme_code,
                }
                collateral_ledger_input = {
                    "doctype": "Loan Application",
                    "docname": self.name,
                    "request_type": "Pledge",
                    "isin": i.isin,
                    "quantity": i.pledged_quantity,
                    "price": i.price,
                    "security_name": i.security_name,
                    "security_category": i.security_category,
                    "data": collateral_ledger_data,
                    "psn": i.psn,
                    "requested_quantity": i.requested_quantity,
                    "scheme_code": i.scheme_code,
                    "folio": i.folio,
                    "amc_code": i.amc_code,
                }
                CollateralLedger.create_entry(**collateral_ledger_input)
            self.save(ignore_permissions=True)
            frappe.db.commit()

        else:
            if self.instrument_type == "Mutual Fund":
                drawing_power_mf = (
                    self.increased_sanctioned_limit
                    if self.application_type == "Increase Loan"
                    else self.drawing_power
                )
                if drawing_power_mf < self.minimum_sanctioned_limit:
                    self.remarks = "Rejected due to min/max range"
                    self.status = "Rejected"
                    self.workflow_state = "Rejected"
                    self.save(ignore_permissions=True)
                    frappe.db.commit()
                    doc = frappe.get_doc(
                        "User KYC", self.get_customer().choice_kyc
                    ).as_dict()
                    doc["minimum_sanctioned_limit"] = self.minimum_sanctioned_limit
                    doc["maximum_sanctioned_limit"] = self.maximum_sanctioned_limit
                    # send sms/email/fcm to user for rejection of loan application
                    frappe.enqueue_doc(
                        "Notification",
                        "Lien not Approved by lender",
                        method="send",
                        doc=doc,
                    )
                    msg = """Dear Customer,
Sorry! Your loan application was turned down since the requested loan amount is not in the range of lender's minimum sanction limit (Rs.{}) and maximum sanction limit (Rs.{}) criteria. We regret the inconvenience caused. Please try again with the expected criteria or reach out via the 'Contact Us' section of the app- {link} -Spark Loans""".format(
                        self.minimum_sanctioned_limit,
                        self.maximum_sanctioned_limit,
                        link=las_settings.app_login_dashboard,
                    )
                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification", "Lien unsuccessful", fields=["*"]
                    )
                    fcm_message = fcm_notification.message.format(
                        minimum_sanctioned_limit=self.minimum_sanctioned_limit,
                        maximum_sanctioned_limit=self.maximum_sanctioned_limit,
                    )
                    receiver_list = [str(self.get_customer().phone)]
                    if doc.mob_num:
                        receiver_list.append(str(doc.mob_num))
                    if doc.choice_mob_no:
                        receiver_list.append(str(doc.choice_mob_no))

                    receiver_list = list(set(receiver_list))
                    frappe.enqueue(
                        method=send_sms, receiver_list=receiver_list, msg=msg
                    )

                    lms.send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        message=fcm_message,
                        customer=self.get_customer(),
                    )

                elif drawing_power_mf >= self.minimum_sanctioned_limit:
                    customer = self.get_customer()
                    frappe.session.user = "Administrator"
                    user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
                    las_settings = frappe.get_single("LAS Settings")
                    self.status = "Executing pledge"
                    self.workflow_state = "Executing pledge"
                    self.total_collateral_value = 0
                    self.save(ignore_permissions=True)
                    frappe.db.commit()
                    lien_ref_no = self.items[0].get("prf_number")
                    schemedetails = []
                    for i in self.items:
                        item = {
                            "amccode": i.get("amc_code"),
                            "amcname": i.get("amc_name"),
                            "folio": i.get("folio"),
                            "schemecode": i.get("scheme_code"),
                            "schemename": i.get("security_name"),
                            "isinno": i.get("isin"),
                            "schemetype": i.get("type"),
                            "schemecategory": "O",
                            "lienunit": str(round(i.get("requested_quantity"), 3)),
                            "lienapprovedunit": str(
                                round(i.get("pledged_quantity"), 3)
                            ),
                            "lienmarkno": "",
                            "sanctionedamount": "",
                        }
                        schemedetails.append(item)

                    data = {
                        "initiatereq": [
                            {
                                "lienrefno": lien_ref_no,
                                "errorcode": "",
                                "error": "",
                                "sucessflag": "Y",
                                "failurereason": "",
                                "loginemail": customer.mycams_email_id,
                                "netbankingemail": customer.user,
                                "clientid": las_settings.client_id,
                                "clientname": las_settings.client_name,
                                "subclientid": "",
                                "pan": user_kyc.pan_no,
                                "bankschemetype": self.scheme_type,
                                "bankrefno": las_settings.bank_reference_no,
                                "bankname": las_settings.bank_name,
                                "branchname": "Mumbai",
                                "address1": "Address1",
                                "address2": "Address2",
                                "address3": "Address3",
                                "city": "Mumbai",
                                "state": "MH",
                                "country": "india",
                                "pincode": "400706",
                                "phoneoff": "02212345678",
                                "phoneres": "02221345678",
                                "faxno": "02231245678",
                                "faxres": "1357",
                                "requestip": "",
                                "addinfo1": self.name,
                                "addinfo2": customer.name,
                                "addinfo3": customer.full_name,
                                "addinfo4": "4",
                                "addinfo5": "5",
                                "markid": "",
                                "verifyid": "",
                                "approveid": "",
                            }
                        ],
                        "schemedetails": schemedetails,
                    }

                    encrypted_data = lms.AESCBC(
                        las_settings.encryption_key, las_settings.iv
                    ).encrypt(json.dumps(data))

                    url = las_settings.lien_initiate_api
                    datetime_signature = lms.create_signature_mycams()
                    headers = {
                        "Content-Type": "application/json",
                        "clientid": las_settings.client_id,
                        "datetimestamp": datetime_signature[0],
                        "signature": datetime_signature[1],
                    }

                    response = requests.post(
                        url=url, headers=headers, data=encrypted_data
                    )
                    encrypted_response = response.text.replace("-", "+").replace(
                        "_", "/"
                    )
                    decrypted_data = lms.AESCBC(
                        las_settings.decryption_key, las_settings.iv
                    ).decrypt(encrypted_response)
                    decrypted_json = json.loads(decrypted_data)

                    lms.create_log(
                        {
                            "Customer name": customer.full_name,
                            "json_payload": data,
                            "encrypted_request": encrypted_data,
                            "decrypted_json": decrypted_json,
                        },
                        "lien_initiate_request",
                    )

                    schemedetails = decrypted_json.get("schemedetails", None)
                    isin_details = {}

                    if schemedetails and "Success" in [
                        i["remarks"].title() for i in schemedetails
                    ]:
                        total_successfull_lien = 0
                        total_collateral_value = 0
                        for i in schemedetails:
                            isin_details[
                                str(i.get("isinno"))
                                + str(i.get("folio"))
                                + str(i.get("date_of_pledge"))
                            ] = i
                        for i in self.items:
                            isin_folio_combo = (
                                str(i.get("isin"))
                                + str(i.get("folio"))
                                + str(i.get("date_of_pledge"))
                            )
                            if isin_folio_combo in isin_details:
                                cur = isin_details.get(isin_folio_combo)
                                frappe.log_error(
                                    "{}\n{}".format(str(isin_folio_combo), str(cur))
                                )
                                i.pledge_executed = 1
                                i.pledge_status = (
                                    "Success"
                                    if cur.get("remarks").title() == "Success"
                                    else "Failure"
                                )
                                if i.pledge_status == "Success":
                                    total_successfull_lien += 1
                                    i.lender_approval_status = "Approved"
                                else:
                                    i.lender_approval_status = "Rejected"
                                collateral_ledger_data = {
                                    "prf": i.get("prf_number"),
                                    "expiry": self.expiry_date,
                                }
                                collateral_ledger_input = {
                                    "doctype": "Loan Application",
                                    "docname": self.name,
                                    "request_type": "Pledge",
                                    "isin": i.get("isin"),
                                    "quantity": i.get("pledged_quantity"),
                                    "price": i.get("price"),
                                    "security_name": i.get("security_name"),
                                    "security_category": i.get("security_category"),
                                    "data": collateral_ledger_data,
                                    "psn": cur.get("lienmarkno"),
                                    "requested_quantity": i.get("requested_quantity"),
                                    "scheme_code": i.get("scheme_code"),
                                    "folio": i.get("folio"),
                                    "amc_code": i.get("amc_code"),
                                }
                                CollateralLedger.create_entry(**collateral_ledger_input)
                        pledge_securities = 0
                        self.status = "Pledge executed"
                        if total_successfull_lien == len(self.items):
                            self.pledge_status = "Success"
                            pledge_securities = 1
                        elif total_successfull_lien == 0:
                            self.status = "Pledge Failure"
                            self.pledge_status = "Failure"
                        else:
                            self.pledge_status = "Partial Success"
                            pledge_securities = 1
                        self.workflow_state = "Pledge executed"
                        self.total_collateral_value = round(total_collateral_value, 2)
                        drawing_power = 0
                        for i in self.items:
                            i.amount = i.price * i.pledged_quantity
                            dp = (i.eligible_percentage / 100) * i.amount
                            i.eligibile_amount = dp
                            # self.total_collateral_value += i.amount
                            drawing_power += dp

                        drawing_power = round(
                            lms.round_down_amount_to_nearest_thousand(drawing_power),
                            2,
                        )
                        if not customer.pledge_securities:
                            customer.pledge_securities = pledge_securities
                            customer.save(ignore_permissions=True)

                    else:
                        if schemedetails:
                            isin_folio_combo = (
                                str(i.get("isin"))
                                + str(i.get("folio"))
                                + str(i.get("date"))
                            )
                            for i in schemedetails:
                                isin_details[isin_folio_combo] = i
                            for i in self.items:
                                if isin_folio_combo in isin_details:
                                    i.pledge_executed = 1
                                    i.pledge_status = "Failure"
                                    i.lender_approval_status = "Rejected"

                        self.status = "Pledge Failure"
                        self.pledge_status = "Failure"
                        self.workflow_state = "Pledge executed"

                    self.save(ignore_permissions=True)
                    frappe.db.commit()

    def before_save(self):
        lender = self.get_lender()
        if self.instrument_type != "Mutual Fund" and not self.pledgee_boid:
            self.pledgee_boid = lender.demat_account_number
        if self.instrument_type == "Shares" and not self.pledgor_boid:
            frappe.throw("Pledgor BOID can not be empty for LAS")

        if self.lender_esigned_document and self.status in ["Esign Done", "Approved"]:
            file_name = frappe.db.get_value(
                "File", {"file_url": self.lender_esigned_document}
            )
            file_ = frappe.get_doc("File", file_name)
            if file_.is_private:
                file_.is_private = 0
                file_.save(ignore_permissions=True)
                frappe.db.commit()
                file_.reload()
            self.lender_esigned_document = file_.file_url

        if self.is_offline_loan:
            pending_loan_application = frappe.get_all(
                "Loan Application",
                filters={
                    "customer": self.customer,
                    "status": ["Not IN", ["Approved", "Rejected"]],
                },
            )
            if pending_loan_application:
                frappe.throw(
                    (
                        """Loan Application for this customer id {} is pending .""".format(
                            self.customer
                        )
                    )
                )
            existing_new_loan_app = frappe.db.count(
                "Loan Application",
                {"customer": self.customer, "application_type": "New Loan"},
            )
            if existing_new_loan_app > 1:
                frappe.throw(
                    ("""Loan Application for {} already exists""".format(self.customer))
                )
            if (
                self.application_type in ["Increase Loan", "Margin Shortfall"]
                and not self.loan
            ):
                frappe.throw("Loan name is required")

            if (
                self.application_type == "Margin Shortfall"
                and not self.loan_margin_shortfall
            ):
                frappe.throw("Loan Margin Shortfall Name is required")

            if not self.lender or self.lender != "Choice Finserv":
                frappe.throw("Lender required")

            if not self.instrument_type or self.instrument_type not in [
                "Shares",
                "Mutual Fund",
            ]:
                frappe.throw("Instrument Type required")

            if self.instrument_type == "Mutual Fund" and (
                not self.scheme_type or self.scheme_type not in ["Equity", "Debt"]
            ):
                frappe.throw("Scheme Type required")

            for i in self.items:
                if i.date_of_pledge and i.date_of_pledge >= self.expiry_date:
                    frappe.throw("Date of pledge should be less than expiry date")

        user_roles = frappe.db.get_values(
            "Has Role", {"parent": frappe.session.user, "parenttype": "User"}, ["role"]
        )
        user_role = []
        for i in list(user_roles):
            user_role.append(i[0])
        self.minimum_sanctioned_limit = lender.minimum_sanctioned_limit
        self.maximum_sanctioned_limit = lender.maximum_sanctioned_limit

        if (
            self.status == "Approved"
            and not self.lender_esigned_document
            and not self.loan_margin_shortfall
            and self.application_type != "Pledge More"
        ):
            frappe.throw("Please upload Lender Esigned Document")
        elif self.status == "Approved":
            if "Loan Customer" in user_role:
                current = frappe.utils.now_datetime()
                expiry = frappe.utils.add_years(current, 1) - timedelta(days=1)
                self.expiry_date = datetime.strftime(expiry, "%Y-%m-%d")

            customer = self.get_customer()
            if self.instrument_type == "Mutual Fund" and not customer.mycams_email_id:
                frappe.throw("Please add MyCAMS Email ID in Customer details.")

        elif self.status == "Pledge accepted by Lender":
            if (
                self.base_interest <= 0
                and self.application_type == "New Loan"
                or self.rebate_interest <= 0
                and self.application_type == "New Loan"
            ):
                frappe.throw(
                    "Base interest and Rebate Interest should be greater than 0"
                )
            if self.pledge_status == "Failure":
                frappe.throw("Sorry! Pledge for this Loan Application is failed.")

            total_approved = 0
            total_collateral_value = 0

            for i in self.items:
                if i.get("pledge_status") == "Failure" and i.lender_approval_status in [
                    "Approved",
                    "Rejected",
                ]:
                    frappe.throw(
                        "Pledge failed for ISIN - {}, can't Approve or Reject".format(
                            i.isin
                        )
                    )

                elif i.get("pledge_status") == "Success":
                    if i.lender_approval_status == "Pledge Failure":
                        frappe.throw(
                            "Already pledge success for {}, not allowed to set Pledge Failure.".format(
                                i.isin
                            )
                        )

                    elif i.lender_approval_status == "":
                        frappe.throw("Please Approve/Reject {}".format(i.isin))

                    if i.lender_approval_status == "Approved":
                        total_approved += 1
                        total_collateral_value += i.amount

            if total_approved == 0:
                frappe.throw(
                    "Please Approve atleast one item or Reject the Loan Application"
                )

            # TODO : manage loan application and its item's as per lender approval
            self.total_collateral_value = round(total_collateral_value, 2)
            # if self.instrument_type == "Shares":
            #     drawing_power = round(
            #         lms.round_down_amount_to_nearest_thousand(
            #             (self.allowable_ltv / 100) * self.total_collateral_value
            #         ),
            #         2,
            #     )
            # else:
            drawing_power = 0
            for i in self.items:
                i.amount = i.price * i.pledged_quantity
                dp = (i.eligible_percentage / 100) * i.amount
                i.eligible_amount = dp
                # self.total_collateral_value += i.amount
                drawing_power += dp

            drawing_power = round(
                lms.round_down_amount_to_nearest_thousand(drawing_power),
                2,
            )

            self.drawing_power = (
                drawing_power
                if drawing_power < self.maximum_sanctioned_limit
                else self.maximum_sanctioned_limit
            )
            # Updating actual drawing power
            self.actual_drawing_power = drawing_power

            # TODO : if increase loan drawing power is less than 10k the loan application wont be proceed
            # loan_total_collateral_value = 0
            # if self.loan:
            #     loan_total_collateral_value = frappe.get_doc(
            #         "Loan", self.loan
            #     ).total_collateral_value

            # Use increased sanctioned limit field for this validation
            # if self.instrument_type == "Shares":
            #     drawing_power = round(
            #         lms.round_down_amount_to_nearest_thousand(
            #             (self.total_collateral_value + loan_total_collateral_value)
            #             * (self.allowable_ltv / 100)
            #         ),
            #         2,
            #     )
            # else:
            drawing_power = 0
            for i in self.items:
                i.amount = i.price * i.pledged_quantity
                dp = (i.eligible_percentage / 100) * i.amount
                i.eligible_amount = dp
                # self.total_collateral_value += i.amount
                drawing_power += dp

            drawing_power = round(
                lms.round_down_amount_to_nearest_thousand(drawing_power),
                2,
            )
            self.sanction_letter()

            if self.application_type in ["New Loan", "Increase Loan"]:
                if drawing_power < self.minimum_sanctioned_limit:
                    frappe.throw(
                        "Sorry! This Loan Application can not be Approved as its Drawing power is less than Minimum Sanctioned Limit."
                    )

        if self.status == "Pledge executed":
            total_collateral_value = 0

            drawing_power = 0
            for i in self.items:
                # i.date_of_pledge = frappe.utils.now_datetime().strftime("%d-%m-%Y")
                if i.pledge_status == "Success" or i.pledge_status == "":
                    if (
                        i.lender_approval_status == "Approved"
                        or i.lender_approval_status == ""
                    ):
                        i.amount = i.price * i.pledged_quantity
                        dp = (i.eligible_percentage / 100) * i.amount
                        i.eligible_amount = dp
                        # self.total_collateral_value += i.amount
                        drawing_power += dp
                        total_collateral_value += i.amount
                        # if self.instrument_type == "Shares":
                        #     drawing_power = round(
                        #         lms.round_down_amount_to_nearest_thousand(
                        #             (self.allowable_ltv / 100)
                        #             * self.total_collateral_value
                        #         ),
                        #         2,
                        #     )
                        # else:
                        # for i in self.items:

                        drawing_power = round(
                            lms.round_down_amount_to_nearest_thousand(drawing_power),
                            2,
                        )
                    self.drawing_power = (
                        drawing_power
                        if drawing_power < self.maximum_sanctioned_limit
                        else self.maximum_sanctioned_limit
                    )
            self.total_collateral_value = round(total_collateral_value, 2)

        # On loan application rejection mark lender approvel status as rejected in loan application items
        if self.status == "Rejected":
            for i in self.items:
                i.lender_approval_status = "Rejected"

        self.total_collateral_value_str = lms.amount_formatter(
            self.total_collateral_value
        )
        self.drawing_power_str = lms.amount_formatter(self.drawing_power)
        self.pledged_total_collateral_value_str = lms.amount_formatter(
            self.pledged_total_collateral_value
        )
        if (
            self.application_type
            in ["Increase Loan", "Pledge More", "Margin Shortfall"]
            and self.status == "Approved"
        ):
            renewal_list = frappe.get_all(
                "Spark Loan Renewal Application",
                filters={
                    "loan": self.loan,
                    "status": ["Not IN", ["Approved", "Rejected"]],
                },
                fields=["name"],
            )
            if renewal_list:
                renewal_doc = frappe.get_doc(
                    "Spark Loan Renewal Application", renewal_list[0].name
                )
                renewal_doc.status = "Rejected"
                renewal_doc.workflow_state = "Rejected"
                renewal_doc.remarks = (
                    "Rejected due to Approval of Top-up/Increase Loan Application"
                )
                renewal_doc.save(ignore_permissions=True)
                frappe.db.commit()

        interest_configuration = frappe.db.get_value(
            "Interest Configuration",
            {
                "lender": self.lender,
                "from_amount": [
                    "<=",
                    self.drawing_power
                    if self.application_type != "Increase Loan"
                    else self.increased_sanctioned_limit,
                ],
                "to_amount": [
                    ">=",
                    self.drawing_power
                    if self.application_type != "Increase Loan"
                    else self.increased_sanctioned_limit,
                ],
            },
            ["name", "base_interest", "rebait_interest"],
            as_dict=1,
        )
        if self.is_default == 1:
            self.custom_base_interest = interest_configuration["base_interest"]
            self.custom_rebate_interest = interest_configuration["rebait_interest"]

        if (
            self.custom_base_interest != self.base_interest
            or self.custom_rebate_interest != self.rebate_interest
        ):
            self.base_interest = self.custom_base_interest
            self.rebate_interest = self.custom_rebate_interest

    def on_update(self):
        if self.status == "Approved":
            customer = self.get_customer()

            if not self.loan:
                loan = self.create_loan()
                frappe.db.set_value(
                    "Sanction Letter and CIAL Log", self.sl_entries, "loan", loan.name
                )
                if not self.is_offline_loan and self.lender_esigned_document:
                    self.sanction_letter(check=loan.name)
            else:
                loan = self.update_existing_loan()
                if not self.is_offline_loan and self.lender_esigned_document:
                    # signed_doc = lms.pdf_editor(
                    #     self.lender_esigned_document,
                    #     pdf_doc_name,
                    # )
                    # self.lender_esigned_document = signed_doc
                    # frappe.db.set_value(
                    #     self.doctype, self.name, "lender_esigned_document", signed_doc
                    # )

                    self.sanction_letter(check=loan.name)
            frappe.db.commit()
            if self.application_type in ["New Loan", "Increase Loan"]:

                date = frappe.utils.now_datetime().date()
                lms.client_sanction_details(loan, date)

            if not self.loan:
                # new loan agreement mapping
                self.map_loan_agreement_file(loan)
            elif (
                self.loan
                and self.lender_esigned_document
                and not self.loan_margin_shortfall
            ):
                # increase loan agreement mapping
                self.map_loan_agreement_file(loan, increase_loan=True)

            if self.loan_margin_shortfall:
                # if shortfall is not recoverd then margin shortfall status will change from request pending to pending
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", self.loan_margin_shortfall
                )
                under_process_la = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": self.loan,
                        "status": [
                            "not IN",
                            ["Approved", "Rejected", "Pledge Failure"],
                        ],
                        "pledge_status": ["!=", "Failure"],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_loan_transaction = frappe.get_all(
                    "Loan Transaction",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "razorpay_event": [
                            "not in",
                            ["", "Failed", "Payment Cancelled"],
                        ],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_sell_collateral_application = frappe.get_all(
                    "Sell Collateral Application",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )

                if (
                    (
                        not pending_loan_transaction
                        and not pending_sell_collateral_application
                        and not under_process_la
                    )
                    and loan_margin_shortfall.status == "Request Pending"
                    and loan_margin_shortfall.shortfall_percentage > 0
                ):
                    loan_margin_shortfall.status = "Pending"
                    loan_margin_shortfall.save(ignore_permissions=True)
                    frappe.db.commit()
            self.notify_customer()

        elif self.status == "Pledge accepted by Lender":
            approved_isin_list = []
            rejected_isin_list = []
            for i in self.items:
                # i.date_of_pledge = frappe.utils.now_datetime().strftime("%d-%m-%Y")
                if i.lender_approval_status == "Approved":
                    approved_isin_list.append(i.isin)
                elif i.lender_approval_status == "Rejected":
                    rejected_isin_list.append(i.isin)

            if len(approved_isin_list) > 0:
                self.update_collateral_ledger(
                    {"lender_approval_status": "Approved"},
                    "application_doctype = 'Loan Application' and application_name = '{}' and isin IN {}".format(
                        self.name, lms.convert_list_to_tuple_string(approved_isin_list)
                    ),
                )

            if len(rejected_isin_list) > 0:
                self.update_collateral_ledger(
                    {"lender_approval_status": "Rejected"},
                    "application_doctype = 'Loan Application' and application_name = '{}' and isin IN {}".format(
                        self.name, lms.convert_list_to_tuple_string(rejected_isin_list)
                    ),
                )
            try:
                fa = FirebaseAdmin()
                fa.send_data(
                    data={
                        "event": "Esign Pending",
                    },
                    tokens=lms.get_firebase_tokens(self.get_customer().user),
                )
            except Exception:
                pass
            finally:
                fa.delete_app()
            if self.notification_sent == 0:
                self.notify_customer()

        elif self.status == "Rejected":
            if self.loan_margin_shortfall:
                # if shortfall is not recoverd then margin shortfall status will change from request pending to pending
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", self.loan_margin_shortfall
                )
                under_process_la = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": self.loan,
                        "status": [
                            "not IN",
                            ["Approved", "Rejected", "Pledge Failure"],
                        ],
                        "pledge_status": ["!=", "Failure"],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_loan_transaction = frappe.get_all(
                    "Loan Transaction",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "razorpay_event": [
                            "not in",
                            ["", "Failed", "Payment Cancelled"],
                        ],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_sell_collateral_application = frappe.get_all(
                    "Sell Collateral Application",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )

                if (
                    (
                        not pending_loan_transaction
                        and not pending_sell_collateral_application
                        and not under_process_la
                    )
                    and loan_margin_shortfall.status == "Request Pending"
                    and loan_margin_shortfall.shortfall_percentage > 0
                ):
                    loan_margin_shortfall.status = "Pending"
                    loan_margin_shortfall.save(ignore_permissions=True)
                    frappe.db.commit()

            if not self.loan and not self.loan_margin_shortfall:
                customer = self.get_customer()
                if customer.pledge_securities:
                    customer.pledge_securities = 0
                    customer.save(ignore_permissions=True)
                    frappe.db.commit()

            # On loan application rejection mark lender approvel status as rejected in collateral ledger as well 23-09-2021 Poonam
            loan_application_isin_list = [i.isin for i in self.items]

            self.update_collateral_ledger(
                {"lender_approval_status": "Rejected"},
                "application_doctype = 'Loan Application' and application_name = '{}' and isin IN {}".format(
                    self.name,
                    lms.convert_list_to_tuple_string(loan_application_isin_list),
                ),
            )
            self.notify_customer()

    def create_loan(self):
        items = []

        for item in self.items:
            psn_no = frappe.get_all(
                "Collateral Ledger",
                fields="*",
                filters={
                    "application_name": self.name,
                    "request_type": "Pledge",
                    "isin": item.isin,
                },
            )
            psn_no[0].psn
            if item.lender_approval_status == "Approved":
                temp = frappe.get_doc(
                    {
                        "doctype": "Loan Item",
                        "isin": item.isin,
                        "security_name": item.security_name,
                        "security_category": item.security_category,
                        "pledged_quantity": item.pledged_quantity,
                        "price": item.price,
                        "amount": item.amount,
                        "eligible_percentage": item.eligible_percentage,
                        "eligible_amount": item.eligible_amount,
                        "folio": item.folio,
                        "amc_code": item.amc_code,
                        "amc_name": item.amc_name,
                        "scheme_code": item.scheme_code,
                        "type": item.type,
                        "folio": item.folio,
                        "psn": psn_no[0].psn
                        if self.instrument_type == "Mutual Fund"
                        else "",
                    }
                )

                items.append(temp)

        loan = frappe.get_doc(
            {
                "doctype": "Loan",
                "total_collateral_value": self.total_collateral_value,
                "drawing_power": self.drawing_power,
                "sanctioned_limit": self.drawing_power,
                "expiry_date": self.expiry_date,
                # "allowable_ltv": self.allowable_ltv,
                "customer": self.customer,
                "customer_name": self.customer_name,
                "lender": self.lender,
                "items": items,
                "is_eligible_for_interest": 1,
                "instrument_type": self.instrument_type,
                "scheme_type": self.scheme_type,
                "is_default": self.is_default,
                "base_interest": self.base_interest,
                "rebate_interest": self.rebate_interest,
                "sl_cial_entries": self.sl_entries,
                "old_interest": self.base_interest,
                "old_rebate_interest": self.rebate_interest,
                "custom_base_interest": self.base_interest,
                "custom_rebate_interest": self.rebate_interest,
                "wef_date": frappe.utils.now_datetime().date(),
                "old_wef_date": frappe.utils.now_datetime().date(),
            }
        )
        loan.insert(ignore_permissions=True)
        loan.create_loan_charges()

        sl_cial_doc = frappe.get_doc(
            {"doctype": "Sanction Letter and CIAL Log", "loan": loan.name}
        ).insert(ignore_permissions=True)

        loan.sl_cial_entries = sl_cial_doc.name

        # File code here #S

        customer = frappe.get_doc("Loan Customer", self.customer)
        if not customer.loan_open:
            customer.loan_open = 1
            customer.save(ignore_permissions=True)

        self.update_collateral_ledger(
            {"loan": loan.name},
            "application_doctype = 'Loan Application' and application_name = '{}'".format(
                self.name,
            ),
        )

        loan.reload()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)

        return loan

    def map_loan_agreement_file(self, loan, increase_loan=False):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.lender_esigned_document}
        )

        loan_agreement = frappe.get_doc("File", file_name)

        event = "New loan"
        if increase_loan:
            loan_agreement_file_name = "{}-loan-enhancement-aggrement.pdf".format(
                loan.name
            )
            event = "Increase loan"
        else:
            loan_agreement_file_name = "{}-loan-aggrement.pdf".format(loan.name)

        # frappe.db.begin()
        loan_agreement_file = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": loan_agreement_file_name,
                "content": loan_agreement.get_content(),
                "attached_to_doctype": "Loan",
                "attached_to_name": loan.name,
                "attached_to_field": "loan_agreement",
                "folder": "Home",
                "is_private": 0,
            }
        )
        loan_agreement_file.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.db.set_value(
            "Loan",
            loan.name,
            "loan_agreement",
            loan_agreement_file.file_url,
            update_modified=False,
        )
        # save loan sanction history
        loan.save_loan_sanction_history(loan_agreement_file.name, event)

    def update_existing_loan(self):
        self.update_collateral_ledger(
            {"loan": self.loan},
            "application_doctype = 'Loan Application' and application_name = '{}'".format(
                self.name
            ),
        )

        loan = frappe.get_doc("Loan", self.loan)
        loan.update_items()
        loan.fill_items()

        # custom to default and wef date future
        # -> no change

        # default to custom and wef date future
        # -> old base and old rebate

        # default to custom and wef date = current date
        # -> no change

        # custom to default and wef date = current date
        # -> base interest and rebate interest
        wef_date = loan.wef_date

        if type(wef_date) is str:
            wef_date = datetime.strptime(str(wef_date), "%Y-%m-%d").date()
        if wef_date <= frappe.utils.now_datetime().date():
            loan.base_interest = self.base_interest
            loan.rebate_interest = self.rebate_interest
        else:
            loan.old_interest = self.base_interest
            loan.old_rebate_interest = self.rebate_interest

        drawing_power = 0
        for i in loan.items:
            i.amount = i.price * i.pledged_quantity
            i.eligible_amount = (i.eligible_percentage / 100) * i.amount
            self.total_collateral_value += i.amount
            drawing_power += i.eligible_amount

        loan.drawing_power = round(drawing_power, 2)
        loan.save(ignore_permissions=True)

        if self.application_type == "Increase Loan":
            # apply processing fees on new sanctioned limit(loan application drawing power)
            # apply renewal charges on existing loan sanctioned limit
            self.apply_renewal_charges(loan)
            loan.reload()
            # TODO : manage expiry date
            loan.expiry_date = self.expiry_date

            loan.sanctioned_limit = (
                self.maximum_sanctioned_limit
                if self.increased_sanctioned_limit > self.maximum_sanctioned_limit
                else self.increased_sanctioned_limit
            )
            loan.save(ignore_permissions=True)
            frappe.db.commit()
            loan.check_for_shortfall(on_approval=True)

        if self.application_type in ["Margin Shortfall", "Pledge More"]:
            if loan.drawing_power > loan.sanctioned_limit:
                loan.drawing_power = loan.sanctioned_limit

            loan.save(ignore_permissions=True)
            if self.loan_margin_shortfall:
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", self.loan_margin_shortfall
                )
                loan_margin_shortfall.fill_items()
                # if not loan_margin_shortfall.margin_shortfall_action:
                if loan_margin_shortfall.shortfall_percentage == 0:
                    loan_margin_shortfall.status = "Pledged Securities"
                    loan_margin_shortfall.action_time = frappe.utils.now_datetime()
                loan_margin_shortfall.save(ignore_permissions=True)
        frappe.db.commit()
        return loan

    def apply_renewal_charges(self, loan):
        lender = loan.get_lender()

        # renewal charges
        import calendar

        # new sanctioned_limit > old sanctioned_limit
        # -> apply processing fee on (new - old)
        # -> apply renewal on loan sanctioned
        # new sanctioned_limit < old sanctioned_limit
        # -> no processing fee
        # -> renewal on new sanctioned
        # new sanctioned_limit = old sanctioned_limit
        # -> no processing fee
        # -> renewal on new sanctioned
        # new sanctioned limit = lms.round_down_amount_to_nearest_thousand((new total coll + old total coll) / 2)
        new_sanctioned_limit = self.increased_sanctioned_limit
        renewal_sanctioned_limit, processing_sanctioned_limit = (
            (loan.sanctioned_limit, (new_sanctioned_limit - loan.sanctioned_limit))
            if new_sanctioned_limit > loan.sanctioned_limit
            else (new_sanctioned_limit, 0)
        )
        date = frappe.utils.now_datetime()
        days_in_year = 366 if calendar.isleap(date.year) else 365
        renewal_charges = lender.renewal_charges
        if lender.renewal_charge_type == "Percentage":
            la_expiry_date = (
                (datetime.strptime(self.expiry_date, "%Y-%m-%d")).date()
                if type(self.expiry_date) == str
                else self.expiry_date
            )
            loan_expiry_date = loan.expiry_date + timedelta(days=1)
            days_left_to_expiry = (la_expiry_date - loan_expiry_date).days + 1

            amount = (
                (renewal_charges / 100)
                * renewal_sanctioned_limit
                / days_in_year
                * days_left_to_expiry
            )
            renewal_charges = loan.validate_loan_charges_amount(
                lender, amount, "renewal_minimum_amount", "renewal_maximum_amount"
            )
        if renewal_charges > 0:
            loan.create_loan_transaction(
                "Account Renewal Charges", renewal_charges, approve=True
            )

        # Processing fees
        processing_fees = lender.lender_processing_fees
        if lender.lender_processing_fees_type == "Percentage":
            days_left_to_expiry = days_in_year

            amount = (
                (processing_fees / 100)
                * processing_sanctioned_limit
                / days_in_year
                * days_left_to_expiry
            )
            processing_fees = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_processing_minimum_amount",
                "lender_processing_maximum_amount",
            )

        if processing_fees > 0 and processing_sanctioned_limit > 0:
            loan.create_loan_transaction(
                "Processing Fees",
                processing_fees,
                approve=True,
            )

        # Stamp Duty
        stamp_duty = lender.stamp_duty
        if lender.stamp_duty_type == "Percentage":
            amount = (stamp_duty / 100) * self.drawing_power
            stamp_duty = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_stamp_duty_minimum_amount",
                "lender_stamp_duty_maximum_amount",
            )

        if stamp_duty > 0:
            loan.create_loan_transaction(
                "Stamp Duty",
                stamp_duty,
                approve=True,
            )

        # Documentation Charges
        documentation_charges = lender.documentation_charges
        if lender.documentation_charge_type == "Percentage":
            amount = (documentation_charges / 100) * self.drawing_power
            documentation_charges = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_documentation_minimum_amount",
                "lender_documentation_maximum_amount",
            )

        if documentation_charges > 0:
            loan.create_loan_transaction(
                "Documentation Charges",
                documentation_charges,
                approve=True,
            )

        # Mortgage Charges
        mortgage_charges = lender.mortgage_charges
        if lender.mortgage_charge_type == "Percentage":
            amount = (mortgage_charges / 100) * self.drawing_power
            mortgage_charges = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_mortgage_minimum_amount",
                "lender_mortgage_maximum_amount",
            )

        if mortgage_charges > 0:
            loan.create_loan_transaction(
                "Mortgage Charges",
                mortgage_charges,
                approve=True,
            )
        frappe.db.commit()

    def update_collateral_ledger(self, set_values={}, where=""):
        try:
            set_values_str = ""
            last_col = sorted(set_values.keys())[-1]
            if len(set_values.keys()) == len(set_values.values()):
                for col, val in set_values.items():
                    set_values_str += "{} = '{}'".format(col, val)
                    if len(set_values.keys()) > 0 and col != last_col:
                        set_values_str += ", "

            sql = """update `tabCollateral Ledger` set {} """.format(set_values_str)

            if len(where) > 0:
                sql += " where {}".format(where)

            frappe.db.sql(sql)
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nLoan Application : {}".format(self.name),
                title=(_("Update Collateral Ledger failed in Loan application")),
            )

    # hit pledge request as per batch items
    def pledge_request(self, security_list):
        try:
            las_settings = frappe.get_single("LAS Settings")
            API_URL = "{}{}".format(
                las_settings.cdsl_host, las_settings.pledge_setup_uri
            )

            prf_number = lms.random_token(length=12)
            securities_array = []
            for i in self.items:
                if i.isin in security_list:
                    # set prf_number to LA item
                    i.prf_number = prf_number
                    j = {
                        "ISIN": i.isin,
                        "Quantity": str(float(i.pledged_quantity)),
                        "Value": str(float(i.price)),
                    }
                    securities_array.append(j)
            self.save(ignore_permissions=True)

            payload = {
                "PledgorBOID": self.pledgor_boid,
                "PledgeeBOID": self.pledgee_boid,
                "PRFNumber": prf_number,
                "ExpiryDate": self.expiry_date.strftime("%d%m%Y"),
                "ReasonCode": "06",
                "ISINDTLS": securities_array,
            }
            headers = las_settings.cdsl_headers()

            res = requests.get(API_URL, headers=headers, json=payload)
            data = res.json()
            log = {
                "url": API_URL,
                "headers": headers,
                "request": payload,
                "response": data,
            }

            lms.create_log(log, "pledge_request_log")
            return {"url": API_URL, "headers": headers, "payload": payload}
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nPledge Details:\n{security_list}".format(
                    security_list=security_list
                ),
                title="Pledge Request Error",
            )

    # dummy pledge response for pledge
    def dummy_pledge_response(self, security_list):
        import random

        error_flag = 0
        # error_flag = bool(random.getrandbits(1))
        if error_flag:
            return {
                "Success": False,
                "PledgeSetupResponse": {
                    "ErrorId": "ERR007",
                    "ErrorMessage": "Invalid Pledgor BOID.",
                },
            }
        else:
            ISINstatusDtls = []
            flag = 0
            for item in security_list:
                # flag = bool(random.getrandbits(1))
                error_code = ["CIF3065-F", "PLD0152-E", "PLD0125-F"]
                ISINstatusDtls_item = {
                    "ISIN": item.get("ISIN"),
                    "PSN": "" if flag else lms.random_token(7, is_numeric=True),
                    "ErrorCode": random.choice(error_code) if flag else "",
                }
                ISINstatusDtls.append(ISINstatusDtls_item)
            return {
                "Success": True,
                "PledgeSetupResponse": {"ISINstatusDtls": ISINstatusDtls},
            }

    # handle pledge response(process loan application items)
    def process(self, security_list, pledge_response):
        isin_details_ = pledge_response.get("PledgeSetupResponse").get("ISINstatusDtls")

        total_successful_pledge = 0
        if isin_details_:
            isin_details = {}
            for i in isin_details_:
                isin_details[i.get("ISIN")] = i

            total_collateral_value = 0
            for i in self.items:
                if i.get("isin") in security_list:
                    cur = isin_details.get(i.get("isin"))

                    i.pledge_executed = 1

                    success = len(cur.get("PSN")) > 0

                    if success:
                        # TODO : manage individual LA item pledge status
                        i.pledge_status = "Success"
                        total_collateral_value += i.amount
                        total_successful_pledge += 1
                        collateral_ledger_data = {
                            "prf": i.get("prf_number"),
                            "expiry": self.expiry_date,
                            "pledgor_boid": self.pledgor_boid,
                            "pledgee_boid": self.pledgee_boid,
                        }
                        collateral_ledger_input = {
                            "doctype": "Loan Application",
                            "docname": self.name,
                            "request_type": "Pledge",
                            "isin": i.get("isin"),
                            "quantity": i.get("pledged_quantity"),
                            "price": i.get("price"),
                            "security_name": i.get("security_name"),
                            "security_category": i.get("security_category"),
                            "data": collateral_ledger_data,
                            "psn": cur.get("PSN"),
                        }
                        CollateralLedger.create_entry(**collateral_ledger_input)
                    else:
                        i.pledge_status = "Failure"
                        i.lender_approval_status = "Pledge Failure"

            self.total_collateral_value += total_collateral_value
        else:
            ErrorId = pledge_response.get("PledgeSetupResponse").get("ErrorId")
            for i in self.items:
                if i.get("isin") in security_list:
                    i.error_code = ErrorId
                    i.pledge_executed = 1
                    i.pledge_status = "Failure"
                    i.lender_approval_status = "Pledge Failure"

        self.save(ignore_permissions=True)
        return total_successful_pledge

    def notify_customer(self):
        las_settings = frappe.get_single("LAS Settings")
        msg_type = "pledge"
        if self.instrument_type == "Mutual Fund":
            msg_type = "lien"
        customer = self.get_customer()
        doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
        doc["loan_application"] = {
            "status": self.status,
            "pledge_status": self.pledge_status,
            "current_total_collateral_value": self.total_collateral_value_str,
            "requested_total_collateral_value": self.pledged_total_collateral_value_str,
            "drawing_power": self.drawing_power_str,
        }
        doc["margin_shortfall"] = self.loan_margin_shortfall
        email_subject = "Loan Application"
        if self.instrument_type == "Mutual Fund":
            email_subject = "MF Loan Application"
        if (
            self.status
            in [
                "Pledge Failure",
                "Pledge accepted by Lender",
                "Rejected",
            ]
            and not self.remarks
        ):
            if not self.is_offline_loan:
                if self.loan and not self.loan_margin_shortfall:
                    frappe.enqueue_doc(
                        "Notification",
                        "Increase Loan Application",
                        method="send",
                        doc=doc,
                    )
                else:
                    frappe.enqueue_doc(
                        "Notification",
                        email_subject,
                        method="send",
                        doc=doc,
                    )
        elif self.status in ["Approved"]:
            if self.loan and not self.loan_margin_shortfall:
                loan_email_message = frappe.db.sql(
                    "select message from `tabNotification` where name ='Increase Loan Application Approved';"
                )[0][0]
                loan_email_message = loan_email_message.replace(
                    "fullname", doc.fullname
                )
                loan_email_message = loan_email_message.replace(
                    "fullname", doc.fullname
                )
                loan_email_message = loan_email_message.replace(
                    "logo_file",
                    frappe.utils.get_url("/assets/lms/mail_images/logo.png"),
                )
                loan_email_message = loan_email_message.replace(
                    "fb_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png"),
                )
                loan_email_message = loan_email_message.replace(
                    "inst_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png"),
                )
                loan_email_message = loan_email_message.replace(
                    "lin_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/lin-icon.png"),
                )
                attachments = ""
                if not self.is_offline_loan:
                    attachments = self.create_attachment()
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[customer.user],
                    sender=None,
                    subject="Increase Loan Application",
                    message=loan_email_message,
                    attachments=attachments,
                )

            else:
                loan_email_message = frappe.db.sql(
                    "select message from `tabNotification` where name ='Loan Application Approved';"
                )[0][0]
                loan_email_message = loan_email_message.replace(
                    "fullname", doc.fullname
                )
                loan_email_message = loan_email_message.replace(
                    "fullname", doc.fullname
                )
                loan_email_message = loan_email_message.replace(
                    "logo_file",
                    frappe.utils.get_url("/assets/lms/mail_images/logo.png"),
                )
                loan_email_message = loan_email_message.replace(
                    "fb_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png"),
                )
                loan_email_message = loan_email_message.replace(
                    "inst_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png"),
                )
                loan_email_message = loan_email_message.replace(
                    "lin_icon",
                    frappe.utils.get_url("/assets/lms/mail_images/lin-icon.png"),
                )
                attachments = ""
                if not self.loan_margin_shortfall and not self.is_offline_loan:
                    attachments = self.create_attachment()
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[customer.user],
                    sender=None,
                    subject=email_subject,
                    message=loan_email_message,
                    attachments=attachments,
                )

        msg = ""
        fcm_notification = {}
        fcm_message = ""
        if doc.get("loan_application").get("status") == "Pledge Failure":
            if not self.is_offline_loan:
                msg, fcm_title = (
                    (
                        "Dear Customer,\nSorry! Your Increase loan application was turned down since the {} was not successful due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app -Spark Loans".format(
                            msg_type
                        ),
                        "Increase loan application rejected",
                    )
                    if self.loan and not self.loan_margin_shortfall
                    else (
                        "Dear Customer,\nSorry! Your loan application was turned down since the {} was not successful due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans".format(
                            msg_type
                        ),
                        "Pledge rejected",
                    )
                )

                if self.instrument_type == "Mutual Fund":
                    msg, fcm_title = (
                        "Dear Customer,\nSorry! Your loan application was turned down since the {} was not successful due to technical reasons. We regret the inconvenience caused. Please try again after a while, or reach out via the 'Contact Us' section of the app- {link} -Spark Loans".format(
                            msg_type, link=las_settings.contact_us
                        ),
                        "Pledge rejected",
                    )

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", fcm_title, fields=["*"]
                )
                fcm_message = fcm_notification.message.format(pledge="pledge")
                if self.instrument_type == "Mututal Fund":
                    fcm_message = fcm_notification.message.format(pledge="lien")
                    if fcm_title == "Pledge rejected":  # can be refactored
                        fcm_notification = fcm_notification.as_dict()
                        fcm_notification["title"] = "Lien rejected"

        elif (
            doc.get("loan_application").get("status") == "Pledge accepted by Lender"
            and not self.loan_margin_shortfall
        ):
            if not self.is_offline_loan:
                msg, fcm_title = (
                    (
                        'Dear Customer,\nCongratulations! Your Increase loan application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under "Contact Us" on the app -Spark Loans',
                        "Increase loan application accepted",
                    )
                    if self.loan and not self.loan_margin_shortfall
                    else (
                        'Dear Customer,\nCongratulations! Your loan application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under "Contact Us" on the app -Spark Loans',
                        "Pledge accepted",
                    )
                )
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", fcm_title, fields=["*"]
                )

                if self.instrument_type == "Mutual Fund":
                    if fcm_title == "Pledge accepted":
                        fcm_notification = fcm_notification.as_dict()
                        fcm_notification["title"] = "Lien accepted"
                self.db_set("notification_sent", 1)

        elif (
            doc.get("loan_application").get("status") == "Approved"
            and not self.loan_margin_shortfall
        ):
            msg, fcm_title = (
                (
                    # frappe.get_doc(
                    #     "Spark SMS Notification", "Increase loan application approved"
                    # ).message,
                    "Dear Customer,\nCongratulations! Your loan limit has been successfully increased. Kindly check the app. You may now withdraw funds as per your convenience. -Spark Loans",
                    "Increase loan application approved",
                )
                if self.loan and not self.loan_margin_shortfall
                else (
                    # frappe.get_doc("Spark SMS Notification", "Loan approved").message,
                    "Dear Customer,\nCongratulations! Your loan account is open. Kindly check the app. You may now withdraw funds as per your convenience. -Spark Loans",
                    "Loan approved",
                )
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", fcm_title, fields=["*"]
            )

        elif (
            doc.get("loan_application").get("status") == "Rejected"
            and not self.loan_margin_shortfall
            and not self.remarks
        ):
            if not self.is_offline_loan:
                msg, fcm_title = (
                    (
                        "Dear Customer,\nSorry! Your Increase loan application was turned down due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans",
                        "Increase loan application turned down",
                    )
                    if self.loan and not self.loan_margin_shortfall
                    else (
                        "Dear Customer,\nSorry! Your loan application was turned down due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans",
                        "Loan rejected",
                    )
                )
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification", fcm_title, fields=["*"]
                )

        elif (
            doc.get("loan_application").get("status") == "Esign Done"
            and self.lender_esigned_document == None
            and not self.loan_margin_shortfall
            and not self.is_offline_loan
        ):
            msg = "Dear Customer,\nYour E-sign process is completed. You shall soon receive a confirmation of loan approval. Thank you for your patience. - Spark Loans"

            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "E-signing was successful", fields=["*"]
            )

        msg_type = "pledge"
        if self.instrument_type == "Mutual Fund":
            msg_type = "lien"
        if not self.is_offline_loan and (
            (
                (self.pledge_status == "Partial Success")
                or (self.total_collateral_value < self.pledged_total_collateral_value)
            )
            and doc.get("loan_application").get("status") == "Pledge accepted by Lender"
            and not self.loan_margin_shortfall
        ):
            msg = "Dear Customer,\nCongratulations! Your {} request was successfully considered and was partially accepted for Rs. {} due to technical reasons. You can find the details on the app dashboard. Please e-sign the loan agreement to avail loan instantly. Proceed now:{link} -Spark Loans".format(
                msg_type,
                self.total_collateral_value_str,
                link=las_settings.app_login_dashboard,
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Increase loan application partially accepted"
                if self.loan
                else "Pledge partially accepted",
                fields=["*"],
            )
            if fcm_notification.title == "Pledge partially accepted":
                fcm_message = fcm_notification.message.format(
                    pledge="pledge",
                    total_collateral_value_str=self.total_collateral_value_str,
                )
                if self.instrument_type == "Mutual Fund":
                    fcm_message = fcm_notification.message.format(
                        pledge="lien",
                        total_collateral_value_str=self.total_collateral_value_str,
                    )
                    fcm_notification = fcm_notification.as_dict()
                    fcm_notification["title"] = "Lien partially accepted"
            else:
                fcm_message = fcm_notification.message.format(
                    pledge="pledge",
                    total_collateral_value_str=self.total_collateral_value_str,
                )

        if msg:
            # lms.send_sms(customer=str(self.get_customer().phone), msg=msg)
            receiver_list = [str(self.get_customer().phone)]
            if doc.mob_num:
                receiver_list.append(str(doc.mob_num))
            if doc.choice_mob_no:
                receiver_list.append(str(doc.choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        if fcm_notification:
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                message=fcm_message,
                loan=self.loan,
                customer=self.get_customer(),
            )

    def validate(self):
        for i, item in enumerate(
            sorted(self.items, key=lambda item: item.security_name), start=1
        ):
            item.idx = i

    def sanction_letter(self, check=None):
        try:
            customer = self.get_customer()
            user = frappe.get_doc("User", customer.user)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            lender = self.get_lender()
            logo_file_path_1 = lender.get_lender_logo_file()
            logo_file_path_2 = lender.get_lender_address_file()
            if user_kyc.address_details:
                address_details = frappe.get_doc(
                    "Customer Address Details", user_kyc.address_details
                )

                line1 = str(address_details.perm_line1)
                if line1:
                    addline1 = "{},<br/>".format(line1)
                else:
                    addline1 = ""

                line2 = str(address_details.perm_line2)
                if line2:
                    addline2 = "{},<br/>".format(line2)
                else:
                    addline2 = ""

                line3 = str(address_details.perm_line3)
                if line3:
                    addline3 = "{},<br/>".format(line3)
                else:
                    addline3 = ""

                perm_city = str(address_details.perm_city)
                perm_dist = str(address_details.perm_dist)
                perm_state = str(address_details.perm_state)
                perm_pin = str(address_details.perm_pin)

            else:
                address_details = ""

            diff = self.drawing_power
            if self.loan:
                loan = self.get_loan()
                # increased_sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                #     (self.total_collateral_value + loan.total_collateral_value)
                #     * self.allowable_ltv
                #     / 100
                # )
                actual_dp = 0
                for i in loan.items:
                    i.amount = i.price * i.pledged_quantity
                    i.eligible_amount = ((i.eligible_percentage or 0) / 100) * i.amount
                    actual_dp += i.eligible_amount
                drawing_power = 0
                for i in self.items:
                    i.amount = i.price * i.pledged_quantity
                    dp = ((i.eligible_percentage or 0) / 100) * i.amount
                    i.eligibile_amount = dp
                    drawing_power += dp
                increased_sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                    actual_dp + drawing_power
                )
                new_increased_sanctioned_limit = (
                    increased_sanctioned_limit
                    if increased_sanctioned_limit < lender.maximum_sanctioned_limit
                    else lender.maximum_sanctioned_limit
                )
                self.increased_sanctioned_limit = new_increased_sanctioned_limit
                diff = self.increased_sanctioned_limit - loan.sanctioned_limit
            interest_config = frappe.get_value(
                "Interest Configuration",
                {
                    "to_amount": [
                        ">=",
                        lms.validate_rupees(
                            float(
                                self.increased_sanctioned_limit
                                if self.increased_sanctioned_limit
                                else self.drawing_power
                            )
                        ),
                    ],
                },
                order_by="to_amount asc",
            )

            int_config = frappe.get_doc("Interest Configuration", interest_config)
            # sanctionlimit = (
            #     new_increased_sanctioned_limit
            #     if self.loan and not self.loan_margin_shortfall
            #     else self.drawing_power
            # )
            roi_ = round((self.base_interest * 12), 2)
            charges = lms.charges_for_apr(
                lender.name,
                lms.validate_rupees(float(diff)),
            )
            interest_charges_in_amount = int(
                lms.validate_rupees(
                    float(
                        self.increased_sanctioned_limit
                        if self.increased_sanctioned_limit
                        else self.drawing_power
                    )
                )
            ) * (roi_ / 100)
            # apr = lms.calculate_apr(
            #     self.name,
            #     roi_,
            #     12,
            #     int(
            #         lms.validate_rupees(
            #             float(
            #                 self.increased_sanctioned_limit
            #                 if self.increased_sanctioned_limit
            #                 else self.drawing_power
            #             )
            #         )
            #     ),
            #     charges.get("total"),
            # )
            interest_per_month = float(interest_charges_in_amount / 12)
            final_payment = float(interest_per_month) + (
                self.increased_sanctioned_limit
                if self.increased_sanctioned_limit
                else self.drawing_power
            )
            apr = lms.calculate_irr(
                name_=self.name,
                sanction_limit=float(
                    self.increased_sanctioned_limit
                    if self.increased_sanctioned_limit
                    else self.drawing_power
                ),
                interest_per_month=interest_per_month,
                final_payment=final_payment,
                charges=charges.get("total"),
            )

            loan_name = ""
            if not check and self.loan:
                loan_name = loan.name
            elif check:
                loan_name = check
            annual_default_interest = lender.default_interest * 12
            if self.status != "Approved":
                doc = {
                    "esign_date": "",
                    "loan_account_number": loan_name,
                    "loan_application_no": self.name,
                    "borrower_name": customer.full_name,
                    "addline1": addline1,
                    "addline2": addline2,
                    "addline3": addline3,
                    "city": perm_city,
                    "district": perm_dist,
                    "state": perm_state,
                    "pincode": perm_pin,
                    # "sanctioned_amount": frappe.utils.fmt_money(float(self.drawing_power)),
                    "logo_file_path_1": logo_file_path_1.file_url
                    if logo_file_path_1
                    else "",
                    "logo_file_path_2": logo_file_path_2.file_url
                    if logo_file_path_2
                    else "",
                    "sanctioned_amount": frappe.utils.fmt_money(
                        self.increased_sanctioned_limit
                        if self.increased_sanctioned_limit
                        else self.drawing_power
                    ),
                    "sanctioned_amount_in_words": lms.number_to_word(
                        lms.validate_rupees(
                            float(
                                self.increased_sanctioned_limit
                                if self.increased_sanctioned_limit
                                else self.drawing_power
                            )
                        )
                    ).title(),
                    "roi": roi_,
                    "apr": apr,
                    "documentation_charges_kfs": frappe.utils.fmt_money(
                        charges.get("documentation_charges")
                    ),
                    "processing_charges_kfs": frappe.utils.fmt_money(
                        charges.get("processing_fees")
                    ),
                    "net_disbursed_amount": frappe.utils.fmt_money(
                        float(
                            self.increased_sanctioned_limit
                            if self.increased_sanctioned_limit
                            else self.drawing_power
                        )
                        - charges.get("total")
                    ),
                    "total_amount_to_be_paid": frappe.utils.fmt_money(
                        float(
                            self.increased_sanctioned_limit
                            if self.increased_sanctioned_limit
                            else self.drawing_power
                        )
                        + charges.get("total")
                        + interest_charges_in_amount
                    ),
                    "loan_application_no": self.name,
                    "rate_of_interest": lender.rate_of_interest,
                    "rebate_interest": self.rebate_interest,
                    "default_interest": annual_default_interest,
                    "rebait_threshold": lender.rebait_threshold,
                    "penal_charges": lender.renewal_penal_interest
                    if lender.renewal_penal_interest
                    else "",
                    "interest_charges_in_amount": frappe.utils.fmt_money(
                        interest_charges_in_amount
                    ),
                    "interest_per_month": frappe.utils.fmt_money(interest_per_month),
                    "final_payment": frappe.utils.fmt_money(final_payment),
                    "renewal_charges": lms.validate_rupees(lender.renewal_charges)
                    if lender.renewal_charge_type == "Fix"
                    else lms.validate_percent(lender.renewal_charges),
                    "renewal_charge_type": lender.renewal_charge_type,
                    "renewal_charge_in_words": lms.number_to_word(
                        lms.validate_rupees(lender.renewal_charges)
                    ).title()
                    if lender.renewal_charge_type == "Fix"
                    else "",
                    "renewal_min_amt": lms.validate_rupees(
                        lender.renewal_minimum_amount
                    ),
                    "renewal_max_amt": lms.validate_rupees(
                        lender.renewal_maximum_amount
                    ),
                    "documentation_charge": lms.validate_rupees(
                        lender.documentation_charges
                    )
                    if lender.documentation_charge_type == "Fix"
                    else lms.validate_percent(lender.documentation_charges),
                    "documentation_charge_type": lender.documentation_charge_type,
                    "documentation_charge_in_words": lms.number_to_word(
                        lms.validate_rupees(lender.documentation_charges)
                    ).title()
                    if lender.documentation_charge_type == "Fix"
                    else "",
                    "documentation_min_amt": lms.validate_rupees(
                        lender.lender_documentation_minimum_amount
                    ),
                    "documentation_max_amt": lms.validate_rupees(
                        lender.lender_documentation_maximum_amount
                    ),
                    "lender_processing_fees_type": lender.lender_processing_fees_type,
                    "processing_charge": lms.validate_rupees(
                        lender.lender_processing_fees
                    )
                    if lender.lender_processing_fees_type == "Fix"
                    else lms.validate_percent(lender.lender_processing_fees),
                    "processing_charge_in_words": lms.number_to_word(
                        lms.validate_rupees(lender.lender_processing_fees)
                    ).title()
                    if lender.lender_processing_fees_type == "Fix"
                    else "",
                    "processing_min_amt": lms.validate_rupees(
                        lender.lender_processing_minimum_amount
                    ),
                    "processing_max_amt": lms.validate_rupees(
                        lender.lender_processing_maximum_amount
                    ),
                    # "stamp_duty_charges": int(lender.lender_stamp_duty_minimum_amount),
                    "transaction_charges_per_request": lms.validate_rupees(
                        lender.transaction_charges_per_request
                    ),
                    "security_selling_share": lender.security_selling_share,
                    "cic_charges": lms.validate_rupees(lender.cic_charges),
                    "total_pages": lender.total_pages,
                    "lien_initiate_charge_type": lender.lien_initiate_charge_type,
                    "invoke_initiate_charge_type": lender.invoke_initiate_charge_type,
                    "revoke_initiate_charge_type": lender.revoke_initiate_charge_type,
                    "lien_initiate_charge_minimum_amount": lms.validate_rupees(
                        lender.lien_initiate_charge_minimum_amount
                    ),
                    "lien_initiate_charge_maximum_amount": lms.validate_rupees(
                        lender.lien_initiate_charge_maximum_amount
                    ),
                    "lien_initiate_charges": lms.validate_rupees(
                        lender.lien_initiate_charges
                    )
                    if lender.lien_initiate_charge_type == "Fix"
                    else lms.validate_percent(lender.lien_initiate_charges),
                    "invoke_initiate_charges_minimum_amount": lms.validate_rupees(
                        lender.invoke_initiate_charges_minimum_amount
                    ),
                    "invoke_initiate_charges_maximum_amount": lms.validate_rupees(
                        lender.invoke_initiate_charges_maximum_amount
                    ),
                    "invoke_initiate_charges": lms.validate_rupees(
                        lender.invoke_initiate_charges
                    )
                    if lender.invoke_initiate_charge_type == "Fix"
                    else lms.validate_percent(lender.invoke_initiate_charges),
                    "revoke_initiate_charges_minimum_amount": lms.validate_rupees(
                        lender.revoke_initiate_charges_minimum_amount
                    ),
                    "revoke_initiate_charges_maximum_amount": lms.validate_rupees(
                        lender.revoke_initiate_charges_maximum_amount
                    ),
                    "revoke_initiate_charges": lms.validate_rupees(
                        lender.revoke_initiate_charges
                    )
                    if lender.revoke_initiate_charge_type == "Fix"
                    else lms.validate_percent(lender.revoke_initiate_charges),
                }
                # doc_d = str(frappe.utils.now_datetime())
                # doc_da = doc_d.replace(" ","_")
                # doc_date = doc_da.replace(".",":")
                sanctioned_letter_pdf_file = "{}-{}-sanctioned_letter.pdf".format(
                    self.name, frappe.utils.now_datetime()
                )
                sll_name = sanctioned_letter_pdf_file

                sanctioned_leter_pdf_file_path = frappe.utils.get_files_path(
                    sanctioned_letter_pdf_file
                )
                sanction_letter_template = lender.get_sanction_letter_template()

                s_letter = frappe.render_template(
                    sanction_letter_template.get_content(), {"doc": doc}
                )

                pdf_file = open(sanctioned_leter_pdf_file_path, "wb")

                # /from frappe.utils.pdf import get_pdf

                pdf = lms.get_pdf(s_letter)

                pdf_file.write(pdf)
                pdf_file.close()
                sL_letter = frappe.utils.get_url(
                    "files/{}".format(sanctioned_letter_pdf_file)
                )
            if not check:
                if self.application_type == "New Loan" and not self.sl_entries:
                    sl = frappe.get_doc(
                        dict(
                            doctype="Sanction Letter and CIAL Log",
                            loan_application=self.name,
                        ),
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()
                    self.sl_entries = sl.name
                    sanction_letter_table = frappe.get_all(
                        "Sanction Letter Entries",
                        filters={"loan_application_no": self.name},
                        fields=["*"],
                    )
                    if not sanction_letter_table:
                        sll = frappe.get_doc(
                            {
                                "doctype": "Sanction Letter Entries",
                                "parent": sl.name,
                                "parentfield": "sl_table",
                                "parenttype": "Sanction Letter and CIAL Log",
                                "sanction_letter": sL_letter,
                                "loan_application_no": self.name,
                                "date_of_acceptance": frappe.utils.now_datetime().date(),
                                "base_interest": self.base_interest,
                                "rebate_interest": self.rebate_interest,
                            }
                        ).insert(ignore_permissions=True)
                        frappe.db.commit()
                elif self.application_type != "New Loan" and not self.sl_entries:
                    sl = frappe.get_all(
                        "Sanction Letter and CIAL Log",
                        filters={"loan": self.loan},
                        fields=["*"],
                    )
                    if sl:
                        self.sl_entries = sl[0].name
                    else:
                        sl = [
                            frappe.get_doc(
                                dict(
                                    doctype="Sanction Letter and CIAL Log",
                                    loan_application=self.name,
                                ),
                            ).insert(ignore_permissions=True)
                        ]
                        frappe.db.commit()
                        self.sl_entries = sl[0].name

                    sanction_letter_table = frappe.get_all(
                        "Sanction Letter Entries",
                        filters={"loan_application_no": self.name},
                        fields=["*"],
                    )
                    if not sanction_letter_table:
                        sll = frappe.get_doc(
                            {
                                "doctype": "Sanction Letter Entries",
                                "parent": sl[0].name,
                                "parentfield": "sl_table",
                                "parenttype": "Sanction Letter and CIAL Log",
                                "sanction_letter": sL_letter,
                                "loan_application_no": self.name,
                                "date_of_acceptance": frappe.utils.now_datetime().date(),
                                "base_interest": self.base_interest,
                                "rebate_interest": self.rebate_interest,
                            }
                        ).insert(ignore_permissions=True)
                        frappe.db.commit()
                elif self.sl_entries and self.status != "Approved":
                    sl = frappe.get_doc("Sanction Letter and CIAL Log", self.sl_entries)
                    ssl = frappe.get_all(
                        "Sanction Letter Entries",
                        filters={
                            "loan_application_no": self.name,
                            "parent": self.sl_entries,
                        },
                        fields=["*"],
                    )
                    if ssl:
                        sel = frappe.get_doc("Sanction Letter Entries", ssl[0].name)
                        sel.sanction_letter = sL_letter
                        sel.save(ignore_permissions=True)
                        frappe.db.commit()

            if self.status == "Approved":
                import os

                from PyPDF2 import PdfReader, PdfWriter

                lender_esign_file = self.lender_esigned_document
                if self.lender_esigned_document:
                    lfile_name = lender_esign_file.split("files/", 1)
                    l_file = lfile_name[1]
                    pdf_file_path = frappe.utils.get_files_path(
                        l_file,
                    )
                    file_base_name = pdf_file_path.replace(".pdf", "")
                    reader = PdfReader(pdf_file_path)
                    pages = [
                        23,
                        24,
                        25,
                        26,
                        27,
                        28,
                        29,
                        30,
                    ]  # page 1, 3, 5
                    pdfWriter = PdfWriter()
                    for page_num in pages:
                        pdfWriter.add_page(reader.pages[page_num])
                    sanction_letter_esign = "Sanction_letter_{0}.pdf".format(self.name)
                    sanction_letter_esign_path = frappe.utils.get_files_path(
                        sanction_letter_esign
                    )
                    if os.path.exists(sanction_letter_esign_path):
                        os.remove(sanction_letter_esign_path)
                    sanction_letter_esign_document = frappe.utils.get_url(
                        "files/{}".format(sanction_letter_esign)
                    )
                    sanction_letter_esign = frappe.utils.get_files_path(
                        sanction_letter_esign
                    )

                    with open(sanction_letter_esign, "wb") as f:
                        pdfWriter.write(f)
                        f.close()
                    sl = frappe.get_all(
                        "Sanction Letter Entries",
                        filters={"loan_application_no": self.name},
                        fields=["*"],
                    )
                    loan_name = ""
                    if not check and self.loan:
                        loan_name = loan.name
                    elif check:
                        loan_name = check
                    frappe.db.set_value(
                        "Sanction Letter and CIAL Log",
                        self.sl_entries,
                        "loan",
                        loan_name,
                    )
                    if sl:
                        sll = frappe.get_doc("Sanction Letter Entries", sl[0].name)
                        sll.sanction_letter = sanction_letter_esign_document
                        sll.save()
                        frappe.db.commit()
            return
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nLoan Application : {}".format(self.name),
                title=(_("Sanction Letter failed in Loan application")),
            )

    def create_attachment(self):
        try:
            attachments = []
            doc_name = self.lender_esigned_document
            fname = doc_name.split("files/", 1)
            file_ = fname[1].split(".", 1)
            file_name = file_[0]
            log_file = frappe.utils.get_files_path("{}.pdf".format(file_name))
            with open(log_file, "rb") as fileobj:
                filedata = fileobj.read()

            sanction_letter = {"fname": fname[1], "fcontent": filedata}
            attachments.append(sanction_letter)

            return attachments
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nLoan Application : {}".format(self.name),
                title=(_("Create attachment failed in Loan application")),
            )


@frappe.whitelist()
def check_for_pledge_failure(la_name):
    la = frappe.get_doc("Loan Application", la_name)
    count_items = len(la.items)
    count = 0
    status = ""
    for i in la.items:
        if i.pledge_status == "Failure":
            count += 1
    if count_items == count:
        status = "Pledge Failure"
    return status


def check_for_pledge(loan_application_doc):
    # TODO : Workers assigned for this cron can be set in las and we can apply (fetch records)limit as per no. of workers assigned
    # frappe.db.begin()
    loan_application_doc.status = "Executing pledge"
    loan_application_doc.workflow_state = "Executing pledge"
    loan_application_doc.total_collateral_value = 0
    loan_application_doc.save(ignore_permissions=True)
    frappe.db.commit()

    customer = loan_application_doc.get_customer()
    count_la_items = frappe.db.count(
        "Loan Application Item", {"parent": loan_application_doc.name}
    )
    no_of_batches = 1
    if count_la_items > 10:
        import math

        no_of_batches = math.ceil(count_la_items / 10)

    # loop as per no of batches
    start = 0
    page_length = 10
    total_successful_pledge = 0
    for b_no in range(no_of_batches):
        # frappe.db.begin()
        # fetch loan application items
        if b_no > 0:
            start += page_length

        la_items = frappe.get_all(
            "Loan Application Item",
            fields="*",
            filters={"parent": loan_application_doc.name},
            start=start,
            page_length=page_length,
        )
        la_items_list = [item.isin for item in la_items]
        # TODO : generate prf number and assign to items in batch
        pledge_request = loan_application_doc.pledge_request(la_items_list)
        # TODO : pledge request hit for all batches
        debug_mode = frappe.db.get_single_value("LAS Settings", "debug_mode")
        if debug_mode:
            data = loan_application_doc.dummy_pledge_response(
                pledge_request.get("payload").get("ISINDTLS")
            )
        else:
            try:
                res = requests.post(
                    pledge_request.get("url"),
                    headers=pledge_request.get("headers"),
                    json=pledge_request.get("payload"),
                )
                data = res.json()

                #     # Pledge LOG
                log = {
                    "url": pledge_request.get("url"),
                    "headers": pledge_request.get("headers"),
                    "request": pledge_request.get("payload"),
                    "response": data,
                }

                lms.create_log(log, "pledge_log")

            except requests.RequestException:
                frappe.log_error(
                    title="Pledge Setup API Error",
                    message=frappe.get_traceback()
                    + "\n\n Loan application name - {}".format(
                        loan_application_doc.name
                    ),
                )

        # TODO : process loan application items in batches
        total_successful_pledge_count = loan_application_doc.process(
            la_items_list, data
        )
        total_successful_pledge += total_successful_pledge_count
        frappe.db.commit()

    # frappe.db.begin()
    # manage loan application doc pledge status
    loan_application_doc.status = "Pledge executed"
    pledge_securities = 0
    if total_successful_pledge == len(loan_application_doc.items):
        loan_application_doc.pledge_status = "Success"
        pledge_securities = 1
    elif total_successful_pledge == 0:
        loan_application_doc.reload()
        loan_application_doc.status = "Pledge Failure"
        loan_application_doc.pledge_status = "Failure"
    else:
        loan_application_doc.pledge_status = "Partial Success"
        pledge_securities = 1
    # TODO : once done with all batches, mark LA as Pledge executed
    loan_application_doc.workflow_state = "Pledge executed"

    # TODO : process loan application(handle collateral and eligible amount)
    # loan_application_doc.reload()
    loan_application_doc.total_collateral_value = round(
        loan_application_doc.total_collateral_value, 2
    )
    drawing_power = 0
    for i in loan_application_doc.items:
        i.amount = i.price * i.pledged_quantity
        dp = (i.eligible_percentage / 100) * i.amount
        drawing_power += dp
    loan_application_doc.drawing_power = round(
        lms.round_down_amount_to_nearest_thousand(drawing_power),
        2,
    )

    loan_application_doc.save(ignore_permissions=True)

    if not customer.pledge_securities:
        customer.pledge_securities = pledge_securities
        customer.save(ignore_permissions=True)

    frappe.db.commit()


def only_pdf_upload(doc, method):
    try:
        if doc.attached_to_doctype == "Loan Application":
            if doc.file_name.split(".")[-1].lower() != "pdf":
                frappe.throw("Kindly upload PDF files only.")
    except Exception:
        frappe.log_error(
            title="only_pdf_upload",
            message=frappe.get_traceback() + "\n\nLoan name \n" + str(doc.name),
        )


@frappe.whitelist()
def actions_on_isin(loan_application):
    loan_application = json.loads(loan_application)
    loan_application_doc = frappe.get_doc("Loan Application", loan_application["name"])
    if loan_application_doc.status == "Pledge executed":
        total_collateral_value = 0
        drawing_power = 0
        for i in loan_application["items"]:
            if i["pledge_status"] == "Success" or i["pledge_status"] == "":
                if (
                    i["lender_approval_status"] == "Approved"
                    or i["lender_approval_status"] == ""
                ):
                    total_collateral_value += i["amount"]
                    total_collateral_value = round(total_collateral_value, 2)
                    drawing_power = 0
                    for i in loan_application["items"]:
                        i["amount"] = i["price"] * i["pledged_quantity"]
                        dp = (i["eligible_percentage"] / 100) * i["amount"]
                        drawing_power += dp

                    drawing_power = round(
                        lms.round_down_amount_to_nearest_thousand(drawing_power),
                        2,
                    )

        response = {
            "total_collateral_value": total_collateral_value,
            "drawing_power": drawing_power,
            "total_collateral_value_str": lms.amount_formatter(total_collateral_value),
            "drawing_power_str": lms.amount_formatter(drawing_power),
            "pledged_total_collateral_value_str": lms.amount_formatter(
                loan_application["pledged_total_collateral_value"]
            ),
        }
        return response


@frappe.whitelist()
def process_pledge():
    from frappe import utils

    current_hour = int(utils.nowtime().split(":")[0])
    las_settings = frappe.get_single("LAS Settings")
    if (
        las_settings.scheduler_from_time
        <= current_hour
        < las_settings.scheduler_to_time
    ):
        loan_applications = frappe.get_all(
            "Loan Application",
            filters={"status": "Waiting to be pledged", "instrument_type": "Shares"},
            order_by="creation asc",
        )

        if loan_applications:
            for loan_application in loan_applications:
                loan_application_doc = frappe.get_doc(
                    "Loan Application", loan_application.name
                )
                la_name = int(loan_application.name[2:])
                queue = "default" if (la_name % 2) == 0 else "short"
                frappe.enqueue(
                    method="lms.lms.doctype.loan_application.loan_application.check_for_pledge",
                    job_name="{} - Loan Application Pledge".format(
                        loan_application.name
                    ),
                    loan_application_doc=loan_application_doc,
                    queue=queue,
                )
