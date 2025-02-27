# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json

import frappe
import requests
import utils
from frappe.model.document import Document

import lms
from lms.lms.doctype.collateral_ledger.collateral_ledger import CollateralLedger
from lms.lms.doctype.user_token.user_token import send_sms


class UnpledgeApplication(Document):
    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def before_insert(self):
        self.process_items()
        user_roles = frappe.db.get_values(
            "Has Role", {"parent": frappe.session.user, "parenttype": "User"}, ["role"]
        )
        user_role = []
        for i in list(user_roles):
            user_role.append(i[0])
        if "Loan Customer" not in user_role:
            loan = self.get_loan()
            self.instrument_type = loan.instrument_type
            if self.instrument_type == "Mutual Fund":
                self.scheme_type = loan.scheme_type

    def before_save(self):
        isin = [i.isin for i in self.items]
        allowed_securities = lms.get_allowed_securities(
            isin, self.lender, self.instrument_type
        )
        for i in self.items:
            security = allowed_securities.get(i.isin)
            i.eligible_percentage = security.eligible_percentage
            i.security_category = security.security_category
        loan = self.get_loan()
        self.actual_drawing_power = loan.actual_drawing_power
        loan_margin_shortfall = frappe.get_all(
            "Loan Margin Shortfall",
            {"loan": self.loan, "status": "Pending"},
            page_length=1,
        )
        if self.status == "Rejected" and not loan_margin_shortfall:
            self.notify_customer()
        else:
            self.process_items()
            self.process_sell_items()

    def process_items(self):
        self.total_collateral_value = 0
        loan = self.get_loan()
        self.instrument_type = loan.instrument_type
        self.scheme_type = loan.scheme_type
        self.lender = loan.lender
        self.customer = loan.customer
        if not self.customer_name:
            self.customer_name = loan.customer_name

        pending_sell_request_id = frappe.db.get_value(
            "Sell Collateral Application",
            {"loan": loan.name, "status": "Pending"},
            "name",
        )
        if pending_sell_request_id:
            self.pending_sell_request_id = pending_sell_request_id
        else:
            self.pending_sell_request_id = ""

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

        self.unpledge_collateral_value = 0

        application_type = "unpledge" if self.instrument_type == "Shares" else "revoke"

        price_map = {
            "{}{}{}".format(
                i.isin,
                "{}".format("-" + str(i.folio) if i.folio else ""),
                i.psn if self.instrument_type == "Mutual Fund" else "",
            ): i.price
            for i in self.items
        }
        unpledge_quantity_map = {
            "{}{}{}".format(
                i.isin,
                "{}".format("-" + str(i.folio) if i.folio else ""),
                i.psn if self.instrument_type == "Mutual Fund" else "",
            ): 0
            for i in self.items
        }

        unpledge_requested_quantity_map = {
            "{}{}{}".format(
                i.isin,
                "{}".format("-" + str(i.folio) if i.folio else ""),
                i.psn if self.instrument_type == "Mutual Fund" else "",
            ): i.quantity
            for i in self.items
        }

        msg = (
            "Can not unpledge {}(PSN: {}){} more than {}"
            if self.instrument_type == "Shares"
            else "Can not revoke {}(Lien Mark Number: {}){} more than {}"
        )

        for i in self.unpledge_items:
            isin_folio_combo = "{}{}{}".format(
                i.isin,
                "{}".format("-" + str(i.folio) if i.folio else ""),
                i.psn if self.instrument_type == "Mutual Fund" else "",
            )
            if i.unpledge_quantity > i.quantity:
                frappe.throw(
                    msg.format(
                        i.isin,
                        i.psn,
                        "{}".format("-" + str(i.folio) if i.folio else ""),
                        i.quantity,
                    )
                )
            if self.instrument_type == "Mutual Fund":
                lms.create_log(
                    {
                        "isin_folio_combo": isin_folio_combo,
                        "unpledge_quantity_map": unpledge_quantity_map,
                        "unpledge_requested_quantity_map": unpledge_requested_quantity_map,
                        "i.unpledge_quantity": i.unpledge_quantity,
                        "unpledge_requested_quantity_map.get(isin_folio_combo)": unpledge_requested_quantity_map.get(
                            isin_folio_combo
                        ),
                    },
                    "checking",
                )
                if (
                    unpledge_requested_quantity_map.get(isin_folio_combo)
                    > i.unpledge_quantity
                ):
                    frappe.throw(
                        "You need to {} all {} of isin {}".format(
                            application_type,
                            unpledge_requested_quantity_map.get(isin_folio_combo),
                            isin_folio_combo,
                        )
                    )
            unpledge_quantity_map[isin_folio_combo] = (
                unpledge_quantity_map[isin_folio_combo] + i.unpledge_quantity
            )

            if self.instrument_type == "Shares":
                i.price = price_map.get(isin_folio_combo)
            else:
                i.price = (
                    price_map.get(isin_folio_combo)
                    if i.revoke_initiate_remarks == "SUCCESS"
                    else 0
                )
            self.unpledge_collateral_value += i.unpledge_quantity * i.price

        for i in self.items:
            isin_folio_combo = "{}{}{}".format(
                i.isin,
                "{}".format("-" + str(i.folio) if i.folio else ""),
                i.psn if self.instrument_type == "Mutual Fund" else "",
            )
            if unpledge_quantity_map.get(isin_folio_combo) > i.quantity:
                frappe.throw(
                    "Can not {} {} more than {}".format(
                        application_type, isin_folio_combo, i.quantity
                    )
                )

    def before_submit(self):
        # check if all securities are sold
        unpledge_quantity_map = {
            "{}{}{}".format(
                i.isin,
                "{}".format("-" + str(i.folio) if i.folio else ""),
                i.psn if self.instrument_type == "Mutual Fund" else "",
            ): 0
            for i in self.items
        }

        application_type = "unpledge" if self.instrument_type == "Shares" else "revoke"

        if len(self.unpledge_items):
            for i in self.unpledge_items:
                isin_folio_combo = "{}{}{}".format(
                    i.isin,
                    "{}".format("-" + str(i.folio) if i.folio else ""),
                    i.psn if self.instrument_type == "Mutual Fund" else "",
                )
                unpledge_quantity_map[isin_folio_combo] = (
                    unpledge_quantity_map[isin_folio_combo] + i.unpledge_quantity
                )
        if len(self.unpledge_items) == 0:
            frappe.throw("Please add items to {}".format(application_type))

        for i in self.items:
            isin_folio_combo = "{}{}{}".format(
                i.isin,
                "{}".format("-" + str(i.folio) if i.folio else ""),
                i.psn if self.instrument_type == "Mutual Fund" else "",
            )
            if unpledge_quantity_map.get(isin_folio_combo) < i.quantity:
                frappe.throw(
                    "You need to {} all {} of isin {}".format(
                        application_type, i.quantity, isin_folio_combo
                    )
                )

        loan_items = frappe.get_all(
            "Loan Item", filters={"parent": self.loan}, fields=["*"]
        )
        for i in loan_items:
            for j in self.unpledge_items:
                if (
                    str(i["isin"]) + str(i["folio"] if i["folio"] else "")
                    == str(j.isin) + str(j.folio if j.folio else "")
                    and i["pledged_quantity"] < j.unpledge_quantity
                ):
                    frappe.throw(
                        "Sufficient quantity not available for ISIN {unpledge_isin},\nCurrent Quantity= {loan_qty} Requested {application_type} Quantity {unpledge_quantity}\nPlease Reject this Application".format(
                            unpledge_isin=j.isin,
                            application_type=application_type.title(),
                            loan_qty=i["pledged_quantity"],
                            unpledge_quantity=j.unpledge_quantity,
                        )
                    )

    def on_submit(self):
        for i in self.unpledge_items:
            if i.unpledge_quantity > 0:
                collateral_ledger_data = {
                    "pledgor_boid": i.pledgor_boid,
                    "pledgee_boid": i.pledgee_boid,
                    "prf": i.get("prf"),
                }
                collateral_ledger_input = {
                    "doctype": "Unpledge Application",
                    "docname": self.name,
                    "request_type": "Unpledge",
                    "isin": i.get("isin"),
                    "quantity": i.get("unpledge_quantity"),
                    "price": i.get("price"),
                    "security_name": i.get("security_name"),
                    "security_category": i.get("security_category"),
                    "psn": i.get("new_psn") if i.get("new_psn") else i.get("psn"),
                    "loan_name": self.loan,
                    "lender_approval_status": "Approved",
                    "data": collateral_ledger_data,
                    "scheme_code": i.get("scheme_code"),
                    "folio": i.get("folio"),
                    "amc_code": i.get("amc_code"),
                }
                CollateralLedger.create_entry(**collateral_ledger_input)

        loan = self.get_loan()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)

        lender = self.get_lender()
        if self.instrument_type == "Shares":
            dp_reimburse_unpledge_charges = lender.dp_reimburse_unpledge_charges
            if lender.dp_reimburse_unpledge_charge_type == "Fix":
                total_dp_reimburse_unpledge_charges = (
                    len(self.items) * dp_reimburse_unpledge_charges
                )
            elif lender.dp_reimburse_unpledge_charge_type == "Percentage":
                amount = len(self.items) * dp_reimburse_unpledge_charges / 100
                total_dp_reimburse_unpledge_charges = loan.validate_loan_charges_amount(
                    lender,
                    amount,
                    "dp_reimburse_unpledge_minimum_amount",
                    "dp_reimburse_unpledge_maximum_amount",
                )

            if total_dp_reimburse_unpledge_charges > 0:
                loan.create_loan_transaction(
                    transaction_type="DP Reimbursement(Unpledge) Charges",
                    amount=total_dp_reimburse_unpledge_charges,
                    approve=True,
                )

        else:
            # revoke charges - Mutual Fund
            for i in range(self.successfull_request_count):
                revoke_charges = lender.revoke_initiate_charges

                if lender.revoke_initiate_charge_type == "Fix":
                    revoke_charges = revoke_charges
                elif lender.revoke_initiate_charge_type == "Percentage":
                    amount = self.unpledge_collateral_value * revoke_charges / 100
                    revoke_charges = loan.validate_loan_charges_amount(
                        lender,
                        amount,
                        "revoke_initiate_charges_minimum_amount",
                        "revoke_initiate_charges_maximum_amount",
                    )

                if revoke_charges > 0:
                    loan.create_loan_transaction(
                        transaction_type="Revocation Charges",
                        amount=revoke_charges,
                        approve=True,
                    )

        self.notify_customer()

    def notify_customer(self, check=None):
        las_settings = frappe.get_single("LAS Settings")
        msg = ""
        fcm_notification = {}

        msg_type = "unpledge"
        email_subject = "Unpledge Application"
        if self.instrument_type == "Mutual Fund":
            msg_type = "revoke"
            email_subject = "Revoke Application"

        if self.status in ["Approved", "Rejected"]:
            customer = self.get_loan().get_customer()
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            doc = user_kyc.as_dict()
            doc["unpledge_application"] = {"status": self.status}
            frappe.enqueue_doc("Notification", email_subject, method="send", doc=doc)
            if self.status == "Approved":
                # mutual fund sms changes
                # msg = frappe.get_doc(
                #     "Spark SMS Notification", "Unpledge application accepted"
                # ).message.format(msg_type)
                msg = "Dear Customer,\nCongratulations! Your {} request has been successfully executed. Kindly check the app now. -Spark Loans".format(
                    msg_type
                )
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Unpledge application accepted",
                    fields=["*"],
                )
                message = fcm_notification.message.format(unpledge="unpledge")
                if self.instrument_type == "Mutual Fund":
                    message = fcm_notification.message.format(unpledge="revoke")
                    fcm_notification = fcm_notification.as_dict()
                    fcm_notification["title"] = "Revoke application accepted"
            elif self.status == "Rejected":
                if check == True:
                    # msg = frappe.get_doc(
                    #     "Spark SMS Notification", "Rejected"
                    # ).message.format(msg_type=msg_type)
                    msg = """Your {msg_type} request was rejected. There is a margin shortfall. You can send another {msg_type} request when there is no margin shortfall.""".format(
                        msg_type=msg_type
                    )
                else:
                    # mutual fund sms changes
                    if self.instrument_type == "Mutual Fund":
                        # msg = (
                        #     "Spark SMS Notification",
                        #     "Unpledge application rejected",
                        # ).message.format(msg_type, link=las_settings.my_securities)
                        msg = "Dear Customer,\nSorry! Your {} application was turned down due to technical reasons. You can reach out via the 'Contact Us' section of the app or please try again later using this link- {link} -Spark Loans".format(
                            msg_type, link=las_settings.my_securities
                        )
                    else:
                        msg = "Dear Customer,\nSorry! Your {} application was turned down due to technical reasons. Please try again after sometime or reach us through 'Contact Us' on the app  -Spark Loans".format(
                            msg_type
                        )

                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Unpledge application rejected",
                        fields=["*"],
                    )
                    message = fcm_notification.message.format(unpledge="unpledge")
                    if self.instrument_type == "Mutual Fund":
                        message = fcm_notification.message.format(unpledge="revoke")
                        fcm_notification = fcm_notification.as_dict()
                        fcm_notification["title"] = "Revoke application rejected"

            receiver_list = [str(customer.phone)]
            if user_kyc.mob_num:
                receiver_list.append(str(user_kyc.mob_num))
            if user_kyc.choice_mob_no:
                receiver_list.append(str(user_kyc.choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        if fcm_notification:
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                message=message,
                loan=self.loan,
                customer=customer,
            )

    def validate(self):
        for i, item in enumerate(
            sorted(self.items, key=lambda item: item.security_name), start=1
        ):
            item.idx = i

    def unpledge_with_margin_shortfall(self):
        loan_margin_shortfall = frappe.get_all(
            "Loan Margin Shortfall",
            {"loan": self.loan, "status": "Pending"},
            page_length=1,
        )

        if self.status == "Pending" and loan_margin_shortfall:
            self.status = "Rejected"
            self.workflow_state = "Rejected"
            check = True
            self.save(ignore_permissions=True)
            frappe.db.commit()
            self.notify_customer(check)

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)


@frappe.whitelist()
def get_collateral_details(unpledge_application_name):
    doc = frappe.get_doc("Unpledge Application", unpledge_application_name)
    loan = doc.get_loan()
    isin_list = [i.isin for i in doc.items]
    folio_clause = (
        " and cl.folio IN {}".format(
            lms.convert_list_to_tuple_string([i.folio for i in doc.items])
        )
        if doc.instrument_type == "Mutual Fund"
        else ""
    )
    psn = (
        " and cl.psn IN {}".format(
            lms.convert_list_to_tuple_string([i.psn for i in doc.items])
        )
        if doc.instrument_type == "Mutual Fund"
        else ""
    )
    return loan.get_collateral_list(
        group_by_psn=True,
        where_clause="and cl.isin IN {}{}{psn}".format(
            lms.convert_list_to_tuple_string(isin_list),
            folio_clause,
            psn=psn,
        ),
        having_clause=" HAVING quantity > 0",
    )


@frappe.whitelist()
def validate_revoc(unpledge_application_name):
    try:
        try:
            unpledge_application_doc = frappe.get_doc(
                "Unpledge Application", unpledge_application_name
            )
        except frappe.DoesNotExistError as e:
            raise utils.exceptions.APIException(str(e))
        customer = frappe.get_doc("Loan Customer", unpledge_application_doc.customer)
        user_kyc = lms.__user_kyc(customer.user)

        if (
            customer.mycams_email_id
            and unpledge_application_doc.instrument_type == "Mutual Fund"
        ):
            success = []
            prf_list = []
            revoc_response_list = []
            token_dict = dict()

            for i in unpledge_application_doc.unpledge_items:
                prf = frappe.get_all(
                    "Unpledge Application Unpledged Item",
                    filters={
                        "parent": unpledge_application_doc.name,
                        "prf": i.prf,
                    },
                    fields=["*"],
                )
                if i.prf not in prf_list:
                    try:
                        datetime_signature = lms.create_signature_mycams()
                        las_settings = frappe.get_single("LAS Settings")
                        headers = {
                            "Content-Type": "application/json",
                            "clientid": las_settings.client_id,
                            "datetimestamp": datetime_signature[0],
                            "signature": datetime_signature[1],
                            "subclientid": "",
                        }
                        url = las_settings.revoke_api
                        data = {
                            "revocvalidate": {
                                "reqrefno": "{}_{}".format(
                                    unpledge_application_doc.name,
                                    frappe.utils.now_datetime().strftime(
                                        "%Y-%m-%d %H:%M:%S.%f"
                                    ),
                                ),
                                "lienrefno": i.prf,
                                "pan": user_kyc.pan_no,
                                "regemailid": customer.mycams_email_id,
                                "clientid": las_settings.client_id,
                                "requestip": "",
                                "schemedetails": [],
                            }
                        }
                        for i in prf:
                            schemedetails = (
                                {
                                    "amccode": i.amc_code,
                                    "folio": i.folio,
                                    "schemecode": i.scheme_code,
                                    "schemename": i.security_name,
                                    "isinno": i.isin,
                                    "schemetype": unpledge_application_doc.scheme_type,
                                    "schemecategory": i.security_category,
                                    "lienunit": i.quantity,
                                    "revocationunit": i.unpledge_quantity,
                                    "lienmarkno": i.psn,
                                },
                            )
                            data["revocvalidate"]["schemedetails"].append(
                                schemedetails[0]
                            )

                        encrypted_data = lms.AESCBC(
                            las_settings.encryption_key, las_settings.iv
                        ).encrypt(json.dumps(data))
                        req_data = {"req": str(encrypted_data)}
                        resp = requests.post(
                            url=url, headers=headers, data=json.dumps(req_data)
                        ).text
                        encrypted_response = (
                            json.loads(resp)
                            .get("res")
                            .replace("-", "+")
                            .replace("_", "/")
                        )
                        decrypted_response = lms.AESCBC(
                            las_settings.decryption_key, las_settings.iv
                        ).decrypt(encrypted_response)
                        dict_decrypted_response = json.loads(decrypted_response)

                        lms.create_log(
                            {
                                "json_payload": data,
                                "encrypted_request": encrypted_data,
                                "encrypred_response": json.loads(resp).get("res"),
                                "decrypted_response": dict_decrypted_response,
                            },
                            "revoke_validate",
                        )
                        if dict_decrypted_response.get("revocvalidate"):
                            unpledge_application_doc.validate_message = (
                                dict_decrypted_response.get("revocvalidate").get(
                                    "message"
                                )
                            )

                            isin_details = {}
                            schemedetails_res = dict_decrypted_response.get(
                                "revocvalidate"
                            ).get("schemedetails")

                            for i in schemedetails_res:
                                isin_details[
                                    "{}{}{}".format(
                                        i.get("isinno"),
                                        i.get("folio"),
                                        i.get("lienmarkno"),
                                    )
                                ] = i
                            for i in unpledge_application_doc.unpledge_items:
                                isin_folio_combo = "{}{}{}".format(
                                    i.get("isin"), i.get("folio"), i.get("psn")
                                )

                                if isin_folio_combo in isin_details:
                                    i.revoke_validate_remarks = isin_details.get(
                                        isin_folio_combo
                                    ).get("remarks")
                                    i.revoc_token = dict_decrypted_response.get(
                                        "revocvalidate"
                                    ).get("revoctoken")
                                    i.revoc_ref_no = dict_decrypted_response.get(
                                        "revocvalidate"
                                    ).get("reqrefno")

                            success.append(
                                dict_decrypted_response.get("revocvalidate").get(
                                    "message"
                                )
                            )
                            token_dict.update(
                                {
                                    str(
                                        dict_decrypted_response.get(
                                            "revocvalidate"
                                        ).get("reqrefno")
                                    ): str(
                                        dict_decrypted_response.get(
                                            "revocvalidate"
                                        ).get("revoctoken")
                                    )
                                }
                            )
                            unpledge_application_doc.refno = (
                                dict_decrypted_response.get("revocvalidate").get(
                                    "revoctoken"
                                )
                            )
                            if "FAILURE" not in success:
                                unpledge_application_doc.is_validated = True
                            elif "FAILURE" in success and "SUCCESS" in success:
                                unpledge_application_doc.is_validated = True
                                unpledge_application_doc.validate_message = (
                                    "Partial Success"
                                )
                            unpledge_application_doc.save(ignore_permissions=True)
                            frappe.db.commit()
                            schemedetails_res_res = dict_decrypted_response.get(
                                "revocvalidate"
                            ).get("schemedetails")
                            for i in schemedetails_res_res:
                                revoc_response_list.append(
                                    {
                                        "{}{}{}".format(
                                            i.get("isinno"),
                                            i.get("folio"),
                                            i.get("lienmarkno"),
                                        ): {
                                            "revoc_token": dict_decrypted_response.get(
                                                "revocvalidate"
                                            ).get("revoctoken"),
                                            "revoc_ref_no": dict_decrypted_response.get(
                                                "revocvalidate"
                                            ).get("reqrefno"),
                                        }
                                    }
                                )

                        else:
                            frappe.db.sql(
                                """update `tabUnpledge Application` set validate_message = '{message}' where name ='{name}'""".format(
                                    message=dict_decrypted_response.get("status")[
                                        0
                                    ].get("error"),
                                    name=unpledge_application_doc.name,
                                )
                            )
                            frappe.db.commit()

                        prf_list.append(prf[0].prf)
                    except requests.RequestException as e:
                        raise utils.exceptions.APIException(str(e))

        else:
            frappe.throw(frappe._("Mycams Email ID is missing"))
    except utils.exceptions.APIException as e:
        frappe.log_error(
            title="Revocation - Validate - Error",
            message=frappe.get_traceback()
            + "\n\nRevocation - Validate Details:\n"
            + str(unpledge_application_name),
        )


@frappe.whitelist()
def initiate_revoc(unpledge_application_name):
    try:
        try:
            unpledge_application_doc = frappe.get_doc(
                "Unpledge Application", unpledge_application_name
            )
        except frappe.DoesNotExistError as e:
            raise utils.exceptions.APIException(str(e))
        customer = frappe.get_doc("Loan Customer", unpledge_application_doc.customer)
        user_kyc = lms.__user_kyc(customer.user)

        if (
            customer.mycams_email_id
            and unpledge_application_doc.instrument_type == "Mutual Fund"
        ):
            prf_list = []
            for i in unpledge_application_doc.unpledge_items:
                prf = frappe.get_all(
                    "Unpledge Application Unpledged Item",
                    filters={
                        "parent": unpledge_application_doc.name,
                        "prf": i.prf,
                        "revoke_validate_remarks": "SUCCESS",
                    },
                    fields=["*"],
                )
                if i.prf not in prf_list:
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
                        url = las_settings.revoke_api
                        data = {
                            "revocinitiate": {
                                "reqrefno": i.revoc_ref_no,
                                "revoctoken": i.revoc_token,
                                "lienrefno": i.prf,
                                "pan": user_kyc.pan_no,
                                "regemailid": customer.mycams_email_id,
                                "clientid": las_settings.client_id,
                                "requestip": "",
                                "schemedetails": [],
                            }
                        }
                        for i in prf:
                            schemedetails = (
                                {
                                    "amccode": i.amc_code,
                                    "folio": i.folio,
                                    "schemecode": i.scheme_code,
                                    "schemename": i.security_name,
                                    "isinno": i.isin,
                                    "schemetype": unpledge_application_doc.scheme_type,
                                    "schemecategory": i.security_category,
                                    "lienunit": i.quantity,
                                    "revocationunit": i.unpledge_quantity,
                                    "lienmarkno": i.psn,
                                },
                            )
                            data["revocinitiate"]["schemedetails"].append(
                                schemedetails[0]
                            )

                        encrypted_data = lms.AESCBC(
                            las_settings.encryption_key, las_settings.iv
                        ).encrypt(json.dumps(data))

                        req_data = {"req": str(encrypted_data)}

                        resp = requests.post(
                            url=url, headers=headers, data=json.dumps(req_data)
                        ).text

                        encrypted_response = (
                            json.loads(resp)
                            .get("res")
                            .replace("-", "+")
                            .replace("_", "/")
                        )
                        decrypted_response = lms.AESCBC(
                            las_settings.decryption_key, las_settings.iv
                        ).decrypt(encrypted_response)
                        dict_decrypted_response = json.loads(decrypted_response)

                        lms.create_log(
                            {
                                "json_payload": data,
                                "encrypted_request": encrypted_data,
                                "encrypred_response": json.loads(resp).get("res"),
                                "decrypted_response": dict_decrypted_response,
                            },
                            "revoke_initiate",
                        )

                        if dict_decrypted_response.get("revocinitiate"):
                            unpledge_application_doc.initiate_message = (
                                dict_decrypted_response.get("revocinitiate").get(
                                    "message"
                                )
                            )

                            schemedetails_res = dict_decrypted_response.get(
                                "revocinitiate"
                            ).get("schemedetails")
                            isin_details = {}
                            for i in schemedetails_res:
                                isin_details[
                                    "{}{}{}".format(
                                        i.get("isinno"),
                                        i.get("folio"),
                                        i.get("lienmarkno"),
                                    )
                                ] = i

                            for i in unpledge_application_doc.unpledge_items:
                                isin_folio_combo = "{}{}{}".format(
                                    i.get("isin"), i.get("folio"), i.get("psn")
                                )
                                if isin_folio_combo in isin_details:
                                    i.revoke_initiate_remarks = (
                                        isin_details.get(isin_folio_combo).get(
                                            "remarks"
                                        )
                                        if isin_details.get(isin_folio_combo).get(
                                            "remarks"
                                        )
                                        else "FAILURE"
                                    )

                                    old_psn = i.psn
                                    new_psn = isin_details.get(isin_folio_combo).get(
                                        "revoc_refno"
                                    )
                                    if (
                                        old_psn != new_psn
                                        and isin_details.get(isin_folio_combo).get(
                                            "remarks"
                                        )
                                        == "SUCCESS"
                                    ):
                                        frappe.db.sql(
                                            """
                                            update `tabCollateral Ledger`
                                            set psn = '{psn}'
                                            where loan = '{loan}' and isin = '{isin}' and folio = '{folio}' and psn = '{old_psn}'
                                            """.format(
                                                psn=new_psn,
                                                isin=i.get("isin"),
                                                loan=unpledge_application_doc.loan,
                                                folio=i.get("folio"),
                                                old_psn=old_psn,
                                            )
                                        )
                                        i.new_psn = new_psn

                            if (
                                dict_decrypted_response.get("revocinitiate").get(
                                    "message"
                                )
                                == "SUCCESS"
                            ) or (
                                dict_decrypted_response.get("revocinitiate").get(
                                    "message"
                                )
                                == "PARTIAL FAILURE"
                            ):
                                unpledge_application_doc.is_initiated = True
                                unpledge_application_doc.successfull_request_count += 1
                        else:
                            unpledge_application_doc.initiate_message = (
                                dict_decrypted_response.get("status")[0].get("error")
                            )

                        unpledge_application_doc.save(ignore_permissions=True)
                        frappe.db.commit()
                        prf_list.append(prf[0].prf)

                    except requests.RequestException as e:
                        raise utils.exceptions.APIException(str(e))
        else:
            frappe.throw(frappe._("Mycams Email ID is missing"))
    except utils.exceptions.APIException as e:
        frappe.log_error(
            title="Revocation - Initiate - Error",
            message=frappe.get_traceback()
            + "\n\nRevocation - Initiate Details:\n"
            + str(unpledge_application_name),
        )
