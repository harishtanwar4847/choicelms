# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json

import frappe
import requests
import utils
from frappe import _
from frappe.model.document import Document
from rsa import decrypt

import lms
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.collateral_ledger.collateral_ledger import CollateralLedger
from lms.lms.doctype.user_token.user_token import send_sms


class SellCollateralApplication(Document):
    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def before_insert(self):
        self.process_items()

    def before_save(self):
        self.process_items()
        self.process_sell_items()
        if self.status == "Rejected":
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Sell request rejected", fields=["*"]
            )
            message = fcm_notification.message.format(sell="sell")
            if self.instrument_type == "Mutual Fund":
                message = fcm_notification.message.format(sell="invoke")
                fcm_notification = fcm_notification.as_dict()
                fcm_notification["title"] = "Invoke request rejected"
            self.notify_customer(fcm_notification=fcm_notification, message=message)

    def process_items(self):
        self.total_collateral_value = 0
        loan = self.get_loan()
        self.actual_drawing_power = loan.actual_drawing_power
        self.instrument_type = loan.instrument_type
        self.scheme_type = loan.scheme_type
        self.lender = loan.lender
        self.customer = loan.customer
        if not self.customer_name:
            self.customer_name = loan.customer_name

        pending_unpledge_request_id = frappe.db.get_value(
            "Unpledge Application", {"loan": loan.name, "status": "Pending"}, "name"
        )
        if pending_unpledge_request_id:
            self.pending_unpledge_request_id = pending_unpledge_request_id
        else:
            self.pending_unpledge_request_id = ""

        if self.loan_margin_shortfall:
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", self.loan_margin_shortfall
            )
            if loan_margin_shortfall.status == "Request Pending":
                self.current_shortfall_amount = loan_margin_shortfall.shortfall
            elif loan_margin_shortfall.status == "Sell Triggered":
                self.initial_shortfall_amount = loan_margin_shortfall.shortfall
                loan_margin_shortfall.fill_items()
                self.current_shortfall_amount = loan_margin_shortfall.shortfall

        securities_list = [i.isin for i in self.items]

        query = """
            SELECT
                security_name, isin, price
            FROM
                `tabSecurity`
            WHERE
                instrument_type = '{}' and isin in {};
        """.format(
            loan.instrument_type, lms.convert_list_to_tuple_string(securities_list)
        )

        res_ = frappe.db.sql(query, as_dict=1)
        res = {i.isin: i for i in res_}

        for i in self.items:
            i.security_name = res.get(i.isin).security_name
            i.price = res.get(i.isin).price
            i.amount = i.quantity * i.price
            self.total_collateral_value += i.amount

    def process_sell_items(self):
        if self.status != "Pending":
            return

        applicaton_type = "sell" if self.instrument_type == "Shares" else "invoke"

        self.selling_collateral_value = 0

        price_map = {
            "{}{}".format(i.isin, i.folio if i.folio else ""): i.price
            for i in self.items
        }
        sell_quantity_map = {
            "{}{}".format(i.isin, i.folio if i.folio else ""): 0 for i in self.items
        }
        sell_requested_quantity_map = {
            "{}{}".format(i.isin, i.folio if i.folio else ""): i.quantity
            for i in self.items
        }

        msg = (
            "Can not sell {}(PSN: {}){} more than {}"
            if self.instrument_type == "Shares"
            else "Can not invoke {}(Lien Mark Number: {}){} more than {}"
        )

        for i in self.sell_items:
            isin_folio_combo = "{}{}".format(i.isin, i.folio if i.folio else "")
            if i.sell_quantity > i.quantity:
                frappe.throw(
                    msg.format(
                        i.isin,
                        i.psn,
                        "{}".format("-" + str(i.folio) if i.folio else ""),
                        i.quantity,
                    )
                )
            if self.instrument_type == "Mutual Fund":
                if sell_requested_quantity_map.get(isin_folio_combo) > i.sell_quantity:
                    frappe.throw(
                        "You need to {} all {} of isin {}{}".format(
                            applicaton_type,
                            sell_requested_quantity_map.get(isin_folio_combo),
                            i.isin,
                            "{}".format("-" + str(i.folio) if i.folio else ""),
                        )
                    )
            sell_quantity_map[isin_folio_combo] = (
                sell_quantity_map[isin_folio_combo] + i.sell_quantity
            )
            if self.instrument_type == "Shares":
                i.price = price_map.get(isin_folio_combo)
            else:
                i.price = (
                    price_map.get(isin_folio_combo)
                    if i.invoke_initiate_remarks == "SUCCESS"
                    else 0
                )
            self.selling_collateral_value += i.sell_quantity * i.price

        for i in self.items:
            isin_folio_combo = "{}{}".format(i.isin, i.folio if i.folio else "")
            if sell_quantity_map.get(isin_folio_combo) > i.quantity:
                frappe.throw(
                    "Can not {} {}{} more than {}".format(
                        applicaton_type,
                        i.isin,
                        "{}".format("-" + str(i.folio) if i.folio else ""),
                        i.quantity,
                    )
                )

    def before_submit(self):
        # check if all securities are sold
        sell_quantity_map = {
            "{}{}".format(i.isin, i.folio if i.folio else ""): 0 for i in self.items
        }

        applicaton_type = "sell" if self.instrument_type == "Shares" else "invoke"

        for i in self.sell_items:
            isin_folio_combo = "{}{}".format(i.isin, i.folio if i.folio else "")
            sell_quantity_map[isin_folio_combo] = (
                sell_quantity_map[isin_folio_combo] + i.sell_quantity
            )

        for i in self.items:
            isin_folio_combo = "{}{}".format(i.isin, i.folio if i.folio else "")
            if sell_quantity_map.get(isin_folio_combo) < i.quantity:
                frappe.throw(
                    "You need to {} all {} of isin {}{}".format(
                        applicaton_type,
                        i.quantity,
                        i.isin,
                        "{}".format("-" + str(i.folio) if i.folio else ""),
                    )
                )

        if self.lender_selling_amount <= 0:
            frappe.throw("Please fix the Lender Selling Amount.")

        loan_items = frappe.get_all(
            "Loan Item", filters={"parent": self.loan}, fields=["*"]
        )
        for i in loan_items:
            for j in self.sell_items:
                if (
                    str(i["isin"]) + str(i["folio"] if i["folio"] else "")
                    == str(j.isin) + str(j.folio if j.folio else "")
                    and i["pledged_quantity"] < j.sell_quantity
                ):
                    frappe.throw(
                        "Sufficient quantity not available for ISIN {sell_isin},\nCurrent Quantity= {loan_qty} Requested {applicaton_type} Quantity {sell_quantity}\nPlease Reject this Application".format(
                            sell_isin=j.isin,
                            applicaton_type=applicaton_type.title(),
                            loan_qty=i["pledged_quantity"],
                            sell_quantity=j.sell_quantity,
                        )
                    )

    def on_update(self):
        las_settings = frappe.get_single("LAS Settings")

        if self.status == "Rejected":
            if self.instrument_type == "Mutual Fund":
                msg = frappe.get_doc(
                    "Spark SMS Notification", "Invoke request"
                ).message.format(link=las_settings.my_securities)
                # msg = "Dear Customer,\nSorry! Your invoke request was turned down due to technical reasons. You can reach out via the 'Contact Us' section of the app or please try again later using this link- {link} -Spark Loans".format(
                #     link=las_settings.my_securities
                # )

            else:
                msg = frappe.get_doc(
                    "Spark SMS Notification", "Sell Request Turn Down"
                ).message

                # msg = "Dear Customer,\nSorry! Your sell collateral request was turned down due to technical reasons. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"

            receiver_list = [str(self.get_customer().phone)]
            if self.get_customer().get_kyc().mob_num:
                receiver_list.append(str(self.get_customer().get_kyc().mob_num))
            if self.get_customer().get_kyc().choice_mob_no:
                receiver_list.append(str(self.get_customer().get_kyc().choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

            # msg = frappe.get_doc("Spark SMS Notification","TopUp rejected").message

            # lms.send_sms_notification(customer=self.get_customer(),msg=msg)
            # msg = "Dear Customer,\nSorry! Your {} request was turned down due to technical reasons. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans".format(
            #     msg_type
            # )

        if self.loan_margin_shortfall:
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", self.loan_margin_shortfall
            )
            if loan_margin_shortfall.status == "Request Pending":
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

    def on_submit(self):
        las_settings = frappe.get_single("LAS Settings")
        for i in self.sell_items:
            if i.sell_quantity > 0:
                collateral_ledger_data = {
                    "pledgor_boid": i.pledgor_boid,
                    "pledgee_boid": i.pledgee_boid,
                    "prf": i.get("prf"),
                }
                collateral_ledger_input = {
                    "doctype": "Sell Collateral Application",
                    "docname": self.name,
                    "request_type": "Sell Collateral",
                    "isin": i.get("isin"),
                    "quantity": i.get("sell_quantity"),
                    "price": i.get("price"),
                    "security_name": i.get("security_name"),
                    "security_category": i.get("security_category"),
                    "psn": i.get("psn"),
                    "loan_name": self.loan,
                    "lender_approval_status": "Approved",
                    "data": collateral_ledger_data,
                    "amc_code": i.get("amc_code"),
                    "folio": i.get("folio"),
                    "scheme_code": i.get("scheme_code"),
                }
                CollateralLedger.create_entry(**collateral_ledger_input)

        loan = self.get_loan()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)

        lender = self.get_lender()

        loan.create_loan_transaction(
            transaction_type="Sell Collateral",
            amount=self.lender_selling_amount,
            approve=True,
            loan_margin_shortfall_name=self.loan_margin_shortfall,
        )

        if self.instrument_type == "Shares":
            dp_reimburse_sell_charges = lender.dp_reimburse_sell_charges
            sell_charges = lender.sell_collateral_charges

            if lender.dp_reimburse_sell_charge_type == "Fix":
                total_dp_reimburse_sell_charges = (
                    len(self.items) * dp_reimburse_sell_charges
                )
            elif lender.dp_reimburse_sell_charge_type == "Percentage":
                amount = len(self.items) * dp_reimburse_sell_charges / 100
                total_dp_reimburse_sell_charges = loan.validate_loan_charges_amount(
                    lender,
                    amount,
                    "dp_reimburse_sell_minimum_amount",
                    "dp_reimburse_sell_maximum_amount",
                )

            if lender.sell_collateral_charge_type == "Fix":
                sell_collateral_charges = sell_charges
            elif lender.sell_collateral_charge_type == "Percentage":
                amount = self.lender_selling_amount * sell_charges / 100
                sell_collateral_charges = loan.validate_loan_charges_amount(
                    lender,
                    amount,
                    "sell_collateral_minimum_amount",
                    "sell_collateral_maximum_amount",
                )
            # DP Reimbursement(Sell) Charges
            # Sell Collateral Charges
            if total_dp_reimburse_sell_charges > 0:
                total_dp_reimburse_sell_charges_reference = (
                    loan.create_loan_transaction(
                        transaction_type="DP Reimbursement(Sell) Charges",
                        amount=total_dp_reimburse_sell_charges,
                        approve=True,
                        loan_margin_shortfall_name=self.loan_margin_shortfall,
                    )
                )

            if sell_collateral_charges > 0:
                sell_collateral_charges_reference = loan.create_loan_transaction(
                    transaction_type="Sell Collateral Charges",
                    amount=sell_collateral_charges,
                    approve=True,
                    loan_margin_shortfall_name=self.loan_margin_shortfall,
                )

        else:
            # invoke charges - Mutual Fund
            invoke_charges = lender.invoke_initiate_charges

            if lender.invoke_initiate_charge_type == "Fix":
                invoke_charges = invoke_charges
            elif lender.invoke_initiate_charge_type == "Percentage":
                amount = self.lender_selling_amount * invoke_charges / 100
                invoke_charges = loan.validate_loan_charges_amount(
                    lender,
                    amount,
                    "invoke_initiate_charges_minimum_amount",
                    "invoke_initiate_charges_maximum_amount",
                )

            if invoke_charges > 0:
                invoke_charges_reference = loan.create_loan_transaction(
                    transaction_type="Invocation Charges",
                    amount=invoke_charges,
                    approve=True,
                    gst_percent=0,
                    loan_margin_shortfall_name=self.loan_margin_shortfall,
                )

        user_roles = frappe.db.get_values(
            "Has Role", {"parent": self.owner, "parenttype": "User"}, ["role"]
        )
        if not user_roles:
            frappe.throw(_("Invalid User"))
        user_roles = [role[0] for role in user_roles]

        email_subject = "Sale Triggered Completion"
        application_type = "sell collateral"
        if loan.instrument_type == "Mutual Fund":
            email_subject = "MF Sale Triggered Completion"
            application_type = "invoke"

        if "Loan customer" not in user_roles and self.loan_margin_shortfall:
            doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
            doc["sell_triggered_completion"] = {"loan": self.loan}

            frappe.enqueue_doc("Notification", email_subject, method="send", doc=doc)
            msg = frappe.get_doc(
                "Spark SMS Notification", "Sale triggerred completed"
            ).message.format(msg_type[0], self.loan, msg_type[1])
            # msg = "Dear Customer,\n{} initiated by the lending partner for your loan account  {} is now completed .The {} proceeds have been credited to your loan account and collateral value updated. Please check the app for details. Spark Loans".format(
            #     msg_type[0], self.loan, msg_type[1]
            # )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Sale triggerred completed", fields=["*"]
            )
            message = fcm_notification.message.format(
                Sale="Sale of securities", loan=self.loan
            )
            if self.instrument_type == "Mutual Fund":
                message = fcm_notification.message.format(Sale="Invoke", loan=self.loan)
                fcm_notification = fcm_notification.as_dict()
                fcm_notification["title"] = "Invoke triggerred completed "
        else:
            msg_type = "sell collateral"
            if loan.instrument_type == "Mutual Fund":
                msg_type = "invoke"

            msg = frappe.get_doc(
                "Spark SMS Notification", "Sell request executed"
            ).message.format(application_type)
            # msg = "Dear Customer,\nCongratulations! Your {} request has been successfully executed and sale proceeds credited to your loan account. Kindly check the app for details -Spark Loans".format(
            #     application_type
            # )

            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Sell request executed", fields=["*"]
            )
            message = fcm_notification.message.format(sell="sell", sale="sale")
            if self.instrument_type == "Mutual Fund":
                message = fcm_notification.message.format(sell="invoke", sale="invoke")
                fcm_notification = fcm_notification.as_dict()
                fcm_notification["title"] = "Invoke request executed"
        if msg:
            # lms.send_sms_notification(customer=self.get_customer,msg=msg)
            receiver_list = [str(self.get_customer().phone)]
            if self.get_customer().get_kyc().mob_num:
                receiver_list.append(str(self.get_customer().get_kyc().mob_num))
            if self.get_customer().get_kyc().choice_mob_no:
                receiver_list.append(str(self.get_customer().get_kyc().choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        self.notify_customer(fcm_notification=fcm_notification, message=message)

    def validate(self):
        for i, item in enumerate(
            sorted(self.items, key=lambda item: item.security_name), start=1
        ):
            item.idx = i

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def notify_customer(self, fcm_notification={}, message=""):
        doc = self.get_customer().get_kyc().as_dict()
        doc["sell_collateral_application"] = {"status": self.status}
        email_subject = "Sell Collateral Application"
        if self.instrument_type == "Mutual Fund":
            email_subject = "Invoke Application"
        frappe.enqueue_doc("Notification", email_subject, method="send", doc=doc)

        if fcm_notification:
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                message=message,
                loan=self.loan,
                customer=self.get_customer(),
            )


@frappe.whitelist()
def get_collateral_details(sell_collateral_application_name):
    doc = frappe.get_doc(
        "Sell Collateral Application", sell_collateral_application_name
    )
    loan = doc.get_loan()
    isin_list = [i.isin for i in doc.items]
    folio_clause = (
        " and cl.folio IN {}".format(
            lms.convert_list_to_tuple_string([i.folio for i in doc.items])
        )
        if doc.instrument_type == "Mutual Fund"
        else ""
    )
    return loan.get_collateral_list(
        group_by_psn=True,
        where_clause="and cl.isin IN {}{}".format(
            lms.convert_list_to_tuple_string(isin_list), folio_clause
        ),
        having_clause=" HAVING quantity > 0",
    )


@frappe.whitelist()
def validate_invoc(sell_collateral_application_name):
    try:
        try:
            sell_collateral_application_doc = frappe.get_doc(
                "Sell Collateral Application", sell_collateral_application_name
            )
        except frappe.DoesNotExistError as e:
            raise utils.exceptions.APIException(str(e))
        collateral_ledger = frappe.get_last_doc(
            "Collateral Ledger", filters={"loan": sell_collateral_application_doc.loan}
        )
        customer = frappe.get_doc(
            "Loan Customer", sell_collateral_application_doc.customer
        )
        user_kyc = lms.__user_kyc(customer.user)

        if (
            customer.mycams_email_id
            and sell_collateral_application_doc.instrument_type == "Mutual Fund"
        ):
            try:
                # create payload
                datetime_signature = lms.create_signature_mycams()
                las_settings = frappe.get_single("LAS Settings")
                headers = {
                    "Content-Type": "application/json",
                    "clientid": las_settings.client_id,
                    "datetimestamp": datetime_signature[0],
                    "signature": datetime_signature[1],
                    "subclientid": "",
                }
                url = las_settings.invoke_api
                data = {
                    "invocvalidate": {
                        "reqrefno": sell_collateral_application_doc.name,
                        "lienrefno": collateral_ledger.prf,
                        "pan": user_kyc.pan_no,
                        "regemailid": customer.mycams_email_id,
                        "clientid": las_settings.client_id,
                        "requestip": "103.19.132.194",
                        "schemedetails": [],
                    }
                }
                for i in sell_collateral_application_doc.sell_items:
                    schemedetails = (
                        {
                            "amccode": i.amc_code,
                            "folio": i.folio,
                            "schemecode": i.scheme_code,
                            "schemename": i.security_name,
                            "isinno": i.isin,
                            "schemetype": sell_collateral_application_doc.scheme_type,
                            "schemecategory": i.security_category,
                            "lienunit": i.quantity,
                            "invocationunit": i.sell_quantity,
                            "lienmarkno": i.psn,
                        },
                    )
                    data["invocvalidate"]["schemedetails"].append(schemedetails[0])

                lms.create_log(
                    {
                        "json_payload": data,
                        "timestamp": str(frappe.utils.now_datetime()),
                    },
                    "invoke_validate_request",
                )
                encrypted_data = lms.AESCBC(
                    las_settings.encryption_key, las_settings.iv
                ).encrypt(json.dumps(data))

                req_data = {"req": str(encrypted_data)}

                resp = requests.post(
                    url=url, headers=headers, data=json.dumps(req_data)
                ).text

                encrypted_response = (
                    json.loads(resp).get("res").replace("-", "+").replace("_", "/")
                )
                decrypted_response = lms.AESCBC(
                    las_settings.decryption_key, las_settings.iv
                ).decrypt(encrypted_response)
                dict_decrypted_response = json.loads(decrypted_response)

                lms.create_log(
                    {
                        "encrypted_request": encrypted_data,
                        "encrypred_response": json.loads(resp).get("res"),
                        "decrypted_response": dict_decrypted_response,
                    },
                    "invoke_validate_response",
                )

                if dict_decrypted_response.get("invocvalidate"):
                    sell_collateral_application_doc.validate_message = (
                        dict_decrypted_response.get("invocvalidate").get("message")
                    )
                    sell_collateral_application_doc.invoctoken = (
                        dict_decrypted_response.get("invocvalidate").get("invoctoken")
                    )

                    schemedetails_res = dict_decrypted_response.get(
                        "invocvalidate"
                    ).get("schemedetails")
                    isin_details = {}

                    for i in schemedetails_res:
                        isin_details["{}{}".format(i.get("isinno"), i.get("folio"))] = i

                    for i in sell_collateral_application_doc.sell_items:
                        isin_folio_combo = "{}{}".format(i.get("isin"), i.get("folio"))
                        if isin_folio_combo in isin_details:
                            i.invoke_validate_remarks = isin_details.get(
                                isin_folio_combo
                            ).get("remarks")

                    if (
                        dict_decrypted_response.get("invocvalidate").get("message")
                        == "SUCCESS"
                    ):
                        sell_collateral_application_doc.is_validated = True
                else:
                    sell_collateral_application_doc.validate_message = (
                        dict_decrypted_response.get("status")[0].get("error")
                    )

                sell_collateral_application_doc.save(ignore_permissions=True)
                frappe.db.commit()

            except requests.RequestException as e:
                raise utils.exceptions.APIException(str(e))
        else:
            frappe.throw(frappe._("Mycams Email ID is missing"))
    except utils.exceptions.APIException as e:
        frappe.log_error(
            title="Invocation - Validate - Error",
            message=frappe.get_traceback()
            + "\n\nInvocation - Validate Details:\n"
            + str(sell_collateral_application_name),
        )


@frappe.whitelist()
def initiate_invoc(sell_collateral_application_name):
    try:
        try:
            sell_collateral_application_doc = frappe.get_doc(
                "Sell Collateral Application", sell_collateral_application_name
            )
        except frappe.DoesNotExistError as e:
            raise utils.exceptions.APIException(str(e))
        collateral_ledger = frappe.get_last_doc(
            "Collateral Ledger", filters={"loan": sell_collateral_application_doc.loan}
        )
        customer = frappe.get_doc(
            "Loan Customer", sell_collateral_application_doc.customer
        )
        user_kyc = lms.__user_kyc(customer.user)

        if (
            customer.mycams_email_id
            and sell_collateral_application_doc.instrument_type == "Mutual Fund"
        ):
            try:
                # create payload
                datetime_signature = lms.create_signature_mycams()
                las_settings = frappe.get_single("LAS Settings")
                headers = {
                    "Content-Type": "application/json",
                    "clientid": las_settings.client_id,
                    "datetimestamp": datetime_signature[0],
                    "signature": datetime_signature[1],
                    "subclientid": "",
                }
                url = las_settings.invoke_api
                data = {
                    "invocinitiate": {
                        "reqrefno": sell_collateral_application_doc.name,
                        "invoctoken": sell_collateral_application_doc.invoctoken,
                        "lienrefno": collateral_ledger.prf,
                        "pan": user_kyc.pan_no,
                        "regemailid": customer.mycams_email_id,
                        "clientid": las_settings.client_id,
                        "requestip": "103.19.132.194",
                        "schemedetails": [],
                    }
                }
                for i in sell_collateral_application_doc.sell_items:
                    schemedetails = (
                        {
                            "amccode": i.amc_code,
                            "folio": i.folio,
                            "schemecode": i.scheme_code,
                            "schemename": i.security_name,
                            "isinno": i.isin,
                            "schemetype": sell_collateral_application_doc.scheme_type,
                            "schemecategory": i.security_category,
                            "lienunit": i.quantity,
                            "invocationunit": i.sell_quantity,
                            "lienmarkno": i.psn,
                        },
                    )
                    data["invocinitiate"]["schemedetails"].append(schemedetails[0])

                lms.create_log(
                    {
                        "json_payload": data,
                        "timestamp": str(frappe.utils.now_datetime()),
                    },
                    "invoke_initiate_request",
                )
                encrypted_data = lms.AESCBC(
                    las_settings.encryption_key, las_settings.iv
                ).encrypt(json.dumps(data))

                req_data = {"req": str(encrypted_data)}

                resp = requests.post(
                    url=url, headers=headers, data=json.dumps(req_data)
                ).text

                encrypted_response = (
                    json.loads(resp).get("res").replace("-", "+").replace("_", "/")
                )
                decrypted_response = lms.AESCBC(
                    las_settings.decryption_key, las_settings.iv
                ).decrypt(encrypted_response)
                dict_decrypted_response = json.loads(decrypted_response)

                lms.create_log(
                    {
                        "encrypted_request": encrypted_data,
                        "encrypred_response": json.loads(resp).get("res"),
                        "decrypted_response": dict_decrypted_response,
                    },
                    "invoke_initiate_response",
                )

                if dict_decrypted_response.get("invocinitiate"):
                    sell_collateral_application_doc.initiate_message = (
                        dict_decrypted_response.get("invocinitiate").get("message")
                    )

                    isin_details = {}
                    schemedetails_res = dict_decrypted_response.get(
                        "invocinitiate"
                    ).get("schemedetails")

                    for i in schemedetails_res:
                        isin_details["{}{}".format(i.get("isinno"), i.get("folio"))] = i

                    for i in sell_collateral_application_doc.sell_items:
                        isin_folio_combo = "{}{}".format(i.get("isin"), i.get("folio"))
                        if isin_folio_combo in isin_details:
                            i.invoke_initiate_remarks = isin_details.get(
                                isin_folio_combo
                            ).get("remarks")

                            old_psn = i.psn
                            i.psn = isin_details.get(isin_folio_combo).get("invocrefno")
                            new_psn = isin_details.get(isin_folio_combo).get(
                                "invocrefno"
                            )
                            if old_psn != new_psn:
                                frappe.db.sql(
                                    """
                                    update `tabCollateral Ledger`
                                    set psn = '{psn}'
                                    where loan = '{loan}' and isin = '{isin}' and folio = '{folio}'
                                    """.format(
                                        psn=new_psn,
                                        isin=i.get("isin"),
                                        loan=sell_collateral_application_doc.loan,
                                        folio=i.get("folio"),
                                    )
                                )

                    if (
                        dict_decrypted_response.get("invocinitiate").get("message")
                        == "SUCCESS"
                    ) or (
                        dict_decrypted_response.get("invocinitiate").get("message")
                        == "PARTIAL FAILURE"
                    ):
                        sell_collateral_application_doc.is_initiated = True

                else:
                    sell_collateral_application_doc.initiate_message = (
                        dict_decrypted_response.get("status")[0].get("error")
                    )

                sell_collateral_application_doc.save(ignore_permissions=True)
                frappe.db.commit()

            except requests.RequestException as e:
                raise utils.exceptions.APIException(str(e))
        else:
            frappe.throw(frappe._("Mycams Email ID is missing"))
    except utils.exceptions.APIException as e:
        frappe.log_error(
            title="Invocation - Initiate - Error",
            message=frappe.get_traceback()
            + "\n\nInvocation - Initiate Details:\n"
            + str(sell_collateral_application_name),
        )
