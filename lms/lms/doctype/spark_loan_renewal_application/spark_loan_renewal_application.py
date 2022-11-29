# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import datetime, time, timedelta

import frappe
import pandas as pd
from frappe import _
from frappe.model.document import Document

import lms
from lms import send_spark_push_notification
from lms.lms.doctype.user_token.user_token import send_sms


class SparkLoanRenewalApplication(Document):
    def before_save(self):
        loan = frappe.get_doc("Loan", self.loan)
        msg = ""
        if self.status == "Approved" and not self.expiry_date:
            if not self.lender_esigned_document:
                frappe.throw(_("Please upload Lender esigned document."))
            else:
                expiry = frappe.utils.now_datetime().date() + timedelta(days=365)
                self.expiry_date = expiry - timedelta(days=1)
                loan.expiry_date = expiry - timedelta(days=1)
                loan.save(ignore_permissions=True)
                frappe.db.commit()
        if self.status == "Rejected" and not self.remarks:
            frappe.throw(_("Remarks field cannot be empty."))
        try:
            loan = frappe.get_doc("Loan", self.loan)
            customer = frappe.get_doc("Loan Customer", self.customer)

            doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            doc["loan_renewal_application"] = {
                "status": self.status,
            }

            if self.status in [
                "Loan Renewal accepted by Lender",
                "Esign Done",
                "Approved",
                "Rejected",
            ]:
                frappe.enqueue_doc(
                    "Notification", "Loan Renewal Application", method="send", doc=doc
                )

            if self.status == "Loan Renewal accepted by Lender":
                msg = 'Dear Customer,\nCongratulations! Your loan renewal application has been accepted.\nKindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement.\nFor any help on e-sign, please view our tutorial videos or reach out to us under "Contact Us" on the app\n-Spark Loans'
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal accepted",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )

            elif self.status == "Esign Done":
                msg = "Dear Customer,\nYour E-sign process is completed. You shall soon receive a confirmation of loan renew approval.\nThank you for your patience.\n-Spark Loans"

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal E-signing was successful",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )

            elif self.status == "Approved":
                expiry = frappe.utils.now_datetime().date() + timedelta(days=365)
                self.expiry_date = expiry
                loan.expiry_date = expiry
                loan.save(ignore_permissions=True)
                frappe.db.commit()
                msg = "Dear Customer,\nCongratulations! Your loan renewal process is completed. Kindly check the app.\n-Spark Loans"

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal approved",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )

            elif self.status == "Rejected":
                msg = "Dear Customer,\nSorry! Your loan renewal application was turned down. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app.\n-SparkLoans"

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal rejected",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )
                if (
                    loan.expiry_date > frappe.utils.now_datetime.date()
                    and self.remarks
                    != "Rejected due to Approval of Top-up/Increase Loan Application"
                ):
                    self.tnc_complete = 0
                    self.updated_kyc_status = ""
                    kyc_doc = frappe.get_doc("User KYC", self.new_kyc_name)
                    kyc_doc.updated_kyc = 0
                    kyc_doc.save(ignore_pernissions=True)
                    frappe.get_doc(
                        dict(
                            doctype="Spark Loan Renewal Application",
                            loan=loan.name,
                            lender=loan.lender,
                            old_kyc_name=customer.choice_kyc,
                            total_collateral_value=loan.total_collateral_value,
                            sanctioned_limit=loan.sanctioned_limit,
                            drawing_power=loan.drawing_power,
                            customer=customer.name,
                            customer_name=customer.full_name,
                        )
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()
                if loan.expiry_date < frappe.utils.now_datetime.date():
                    renewal_list_expiring = frappe.get_all(
                        "Spark Loan Renewal Application",
                        filters={"loan": loan.name},
                        fields=["*"],
                    )
                    status_list = [i["status"] for i in renewal_list_expiring]
                    if status_list.count("Rejected") >= 2:
                        self.is_expired = 1

            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=_("Loan Renewal Application - Customer Notification "),
            )


@frappe.whitelist()
def customer_reminder(doc_name):
    try:
        renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc_name)
        loan = frappe.get_doc("Loan", renewal_doc.loan)
        customer = frappe.get_doc("Loan Customer", renewal_doc.customer)

        doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
        doc["loan_renewal_application"] = {"status": renewal_doc.status}

        if renewal_doc.status == "Pending":
            kyc_doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            email_expiry = frappe.db.sql(
                "select message from `tabNotification` where name='Loan Renewal Reminder';"
            )[0][0]
            email_expiry = email_expiry.replace("expiry_date", str(loan.expiry_date))
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[customer.user],
                sender=None,
                subject="Loan Renewal Reminder",
                message=email_expiry,
                queue="short",
                delayed=False,
                job_name="Loan Renewal Reminder",
            )
            msg = "Dear Customer,\nYour expiry date is due on {}.\nPlease renew your loan before it expires.\n-Spark Loans"
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Loan Renewal Reminder",
                fields=["*"],
            )
            send_spark_push_notification(
                fcm_notification=fcm_notification,
                loan=loan.name,
                customer=customer,
            )
            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(
                    method=send_sms,
                    receiver_list=receiver_list,
                    msg=msg.format(loan.expiry_date),
                )
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("Loan Renewal Application - Notify Customer"),
        )


@frappe.whitelist()
def loan_renewal_cron():
    try:
        # Renewal Doc creation and 1st reminder
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            renewal_doc_list = frappe.get_all(
                "Spark Loan Renewal Application",
                filters={"loan": loan.name, "status": ["!=", "Rejected"]},
                fields=["name"],
            )
            for i in renewal_doc_list:
                if (
                    loan.expiry_date < frappe.utils.now_datetime().date()
                    and i.is_expired == 0
                ):
                    doc = frappe.get_doc("Spark Loan Renewal Application", i.name)
                    doc.is_expired = 1
                    doc.save(ignore_permissions=True)
                    frappe.db.commit()

            existing_renewal_doc_list = frappe.get_all(
                "Spark Loan Renewal Application",
                filters={"loan": loan.name, "status": "Pending"},
                fields=["*"],
            )
            customer = frappe.get_doc("Loan Customer", loan.customer)
            expiry_date = frappe.utils.now_datetime().date() + timedelta(days=31)
            if (
                loan.expiry_date == expiry_date
                and loan.total_collateral_value > 0
                and len(loan.items) > 0
            ):
                renewal_doc = frappe.get_doc(
                    dict(
                        doctype="Spark Loan Renewal Application",
                        loan=loan.name,
                        lender=loan.lender,
                        old_kyc_name=customer.choice_kyc,
                        total_collateral_value=loan.total_collateral_value,
                        sanctioned_limit=loan.sanctioned_limit,
                        drawing_power=loan.drawing_power,
                        customer=customer.name,
                        customer_name=customer.full_name,
                    )
                ).insert(ignore_permissions=True)
                frappe.db.commit()
                email_expiry = frappe.db.sql(
                    "select message from `tabNotification` where name='Loan Renewal Reminder';"
                )[0][0]
                email_expiry = email_expiry.replace(
                    "expiry_date", str(loan.expiry_date)
                )
                frappe.enqueue(
                    method=frappe.sendmail,
                    recipients=[customer.user],
                    subject="Loan Renewal Reminder",
                    message=email_expiry,
                    queue="short",
                    job_name="Loan Renewal Reminder",
                )
                msg = "Dear Customer,\nYour expiry date is due on {}.\nPlease renew your loan before it expires.\n-Spark Loans"
                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal Reminder",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )
                if msg:
                    receiver_list = [str(customer.phone)]
                    if customer.get_kyc().mob_num:
                        receiver_list.append(str(customer.get_kyc().mob_num))
                    if customer.get_kyc().choice_mob_no:
                        receiver_list.append(str(customer.get_kyc().choice_mob_no))

                    receiver_list = list(set(receiver_list))
                    frappe.enqueue(
                        method=send_sms,
                        receiver_list=receiver_list,
                        msg=msg.format(loan.expiry_date),
                    )

                renewal_doc.reminder = 1
                renewal_doc.save(ignore_permissions=True)
                frappe.db.commit()

            elif loan.expiry_date == frappe.utils.now_datetime().date() + timedelta(
                days=19
            ):
                for doc in existing_renewal_doc_list:
                    if doc.reminders == 1:
                        email_expiry = frappe.db.sql(
                            "select message from `tabNotification` where name='Loan Renewal Reminder';"
                        )[0][0]
                        email_expiry = email_expiry.replace(
                            "expiry_date", str(loan.expiry_date)
                        )
                        frappe.enqueue(
                            method=frappe.sendmail,
                            recipients=[customer.user],
                            sender=None,
                            subject="Loan Renewal Reminder",
                            message=email_expiry,
                            queue="short",
                            delayed=False,
                            job_name="Loan Renewal Reminder",
                        )
                        msg = "Dear Customer,\nYour expiry date is due on {}.\nPlease renew your loan before it expires.\n-Spark Loans"
                        fcm_notification = frappe.get_doc(
                            "Spark Push Notification",
                            "Loan Renewal Reminder",
                            fields=["*"],
                        )
                        send_spark_push_notification(
                            fcm_notification=fcm_notification,
                            loan=loan.name,
                            customer=customer,
                        )
                        if msg:
                            receiver_list = [str(customer.phone)]
                            if customer.get_kyc().mob_num:
                                receiver_list.append(str(customer.get_kyc().mob_num))
                            if customer.get_kyc().choice_mob_no:
                                receiver_list.append(
                                    str(customer.get_kyc().choice_mob_no)
                                )

                            receiver_list = list(set(receiver_list))

                            frappe.enqueue(
                                method=send_sms,
                                receiver_list=receiver_list,
                                msg=msg.format(loan.expiry_date),
                            )

                        renewal_doc.reminder = 2
                        renewal_doc.save(ignore_permissions=True)
                        frappe.db.commit()

            elif loan.expiry_date == frappe.utils.now_datetime().date() + timedelta(
                days=9
            ):
                for doc in existing_renewal_doc_list:
                    if doc.reminders == 2:
                        email_expiry = frappe.db.sql(
                            "select message from `tabNotification` where name='Loan Renewal Reminder';"
                        )[0][0]
                        email_expiry = email_expiry.replace(
                            "expiry_date", str(loan.expiry_date)
                        )
                        frappe.enqueue(
                            method=frappe.sendmail,
                            recipients=[customer.user],
                            sender=None,
                            subject="Loan Renewal Reminder",
                            message=email_expiry,
                            queue="short",
                            delayed=False,
                            job_name="Loan Renewal Reminder",
                        )
                        msg = "Dear Customer,\nYour expiry date is due on {}.\nPlease renew your loan before it expires.\n-Spark Loans"
                        fcm_notification = frappe.get_doc(
                            "Spark Push Notification",
                            "Loan Renewal Reminder",
                            fields=["*"],
                        )
                        send_spark_push_notification(
                            fcm_notification=fcm_notification,
                            loan=loan.name,
                            customer=customer,
                        )
                        if msg:
                            receiver_list = [str(customer.phone)]
                            if customer.get_kyc().mob_num:
                                receiver_list.append(str(customer.get_kyc().mob_num))
                            if customer.get_kyc().choice_mob_no:
                                receiver_list.append(
                                    str(customer.get_kyc().choice_mob_no)
                                )

                            receiver_list = list(set(receiver_list))

                            frappe.enqueue(
                                method=send_sms,
                                receiver_list=receiver_list,
                                msg=msg.format(loan.expiry_date),
                            )

                        renewal_doc.reminder = 3
                        renewal_doc.save(ignore_permissions=True)
                        frappe.db.commit()

            elif loan.expiry_date == frappe.utils.now_datetime().date() + timedelta(
                days=2
            ):
                for doc in existing_renewal_doc_list:
                    if doc.reminders == 3:
                        email_expiry = frappe.db.sql(
                            "select message from `tabNotification` where name='Loan Renewal Reminder';"
                        )[0][0]
                        email_expiry = email_expiry.replace(
                            "expiry_date", str(loan.expiry_date)
                        )
                        frappe.enqueue(
                            method=frappe.sendmail,
                            recipients=[customer.user],
                            sender=None,
                            subject="Loan Renewal Reminder",
                            message=email_expiry,
                            queue="short",
                            delayed=False,
                            job_name="Loan Renewal Reminder",
                        )
                        msg = "Dear Customer,\nYour expiry date is due on {}.\nPlease renew your loan before it expires.\n-Spark Loans"
                        fcm_notification = frappe.get_doc(
                            "Spark Push Notification",
                            "Loan Renewal Reminder",
                            fields=["*"],
                        )
                        send_spark_push_notification(
                            fcm_notification=fcm_notification,
                            loan=loan.name,
                            customer=customer,
                        )
                        if msg:
                            receiver_list = [str(customer.phone)]
                            if customer.get_kyc().mob_num:
                                receiver_list.append(str(customer.get_kyc().mob_num))
                            if customer.get_kyc().choice_mob_no:
                                receiver_list.append(
                                    str(customer.get_kyc().choice_mob_no)
                                )

                            receiver_list = list(set(receiver_list))

                            frappe.enqueue(
                                method=send_sms,
                                receiver_list=receiver_list,
                                msg=msg.format(loan.expiry_date),
                            )

                        renewal_doc.reminder = 4
                        renewal_doc.save(ignore_permissions=True)
                        frappe.db.commit()
        frappe.enqueue(
            method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.renewal_penal_interest",
            queue="long",
            job_name="Renewal Penal Interest",
        )
        frappe.enqueue(
            method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.renewal_timer",
            queue="long",
            job_name="Renewal Time Remaining Addition",
        )

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("Loan Renewal Application  - Cron Function"),
        )


@frappe.whitelist()
def renewal_penal_interest():
    loans = frappe.get_all("Loan", fields=["*"])
    for loan in loans:
        existing_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": ["not IN", ["Rejected", "Pending"]]},
            fields=["*"],
        )
        pending_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": "Pending"},
            fields=["*"],
        )
        customer = frappe.get_doc("Loan Customer", loan.customer)
        user_kyc = frappe.get_all(
            "User KYC",
            filters={
                "user": customer.user,
                "updated_kyc": 1,
                "kyc_status": ["IN", ["Approved", "Pending"]],
            },
            fields=["*"],
        )
        user_kyc_approved = frappe.get_all(
            "User KYC",
            filters={
                "user": customer.user,
                "updated_kyc": 1,
                "kyc_status": "Approved",
            },
            fields=["*"],
        )
        applications = []

        current_date = frappe.utils.now_datetime().date()
        greater_than_7 = loan.expiry_date + timedelta(days=7)
        if greater_than_7 > current_date and loan.expiry_date < current_date:
            if (not existing_renewal_doc_list and not user_kyc) or (
                user_kyc_approved and pending_renewal_doc_list
            ):
                top_up_application = frappe.get_all(
                    "Top up Application",
                    filters={
                        "loan": loan.name,
                        "status": ["IN", ["Pending", "Esign Done"]],
                    },
                    fields=["name"],
                )
                for i in top_up_application:
                    applications.append(i)
                loan_application = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": loan.name,
                        "application_type": [
                            "IN",
                            ["Increase Loan", "Pledge More", "Margin Shortfall"],
                        ],
                    },
                    fields=["name"],
                )
                for i in loan_application:
                    applications.append(i)
                if not top_up_application:
                    if not loan_application:
                        current_year = frappe.utils.now_datetime().strftime("%Y")
                        current_year = int(current_year)
                        if (
                            (current_year % 400 == 0)
                            or (current_year % 100 != 0)
                            and (current_year % 4 == 0)
                        ):
                            no_of_days = 366
                        # Else it is not a leap year
                        else:
                            no_of_days = 365
                        renewal_penal_interest = frappe.get_doc("Lender", loan.lender)
                        daily_penal_interest = (
                            float(renewal_penal_interest.renewal_penal_interest)
                            / no_of_days
                        )
                        amount = loan.balance * (daily_penal_interest / 100)
                        penal_interest_transaction = frappe.get_doc(
                            {
                                "doctype": "Loan Transaction",
                                "loan": loan.name,
                                "lender": loan.lender,
                                "transaction_type": "Penal Interest",
                                "record_type": "DR",
                                "amount": round(amount, 2),
                                "unpaid_interest": round(amount, 2),
                                "time": current_date,
                            }
                        )
                        penal_interest_transaction.insert(ignore_permissions=True)
                        penal_interest_transaction.transaction_id = (
                            penal_interest_transaction.name
                        )
                        penal_interest_transaction.status = "Approved"
                        penal_interest_transaction.workflow_state = "Approved"
                        penal_interest_transaction.docstatus = 1
                        penal_interest_transaction.save(ignore_permissions=True)
                        frappe.db.commit()

        pending_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": "Pending"},
            fields=["*"],
        )
        is_expired_date = loan.expiry_date + timedelta(days=7)
        if pending_renewal_doc_list:
            for renewal_doc in pending_renewal_doc_list:
                if (
                    not user_kyc
                    and is_expired_date < frappe.utils.now_datetime().date()
                ):
                    doc = frappe.get_doc(
                        "Spark Loan Renewal Application", renewal_doc.name
                    )
                    doc.status = "Rejected"
                    doc.workflow_state = "Rejected"
                    doc.remarks = "Is Expired"
                    doc.save(ignore_permissions=True)
                    frappe.db.commit()


@frappe.whitelist()
def renewal_timer(loan_renewal_name):
    try:
        if loan_renewal_name:
            renewal_doc = frappe.get_doc(
                "Spark Loan Renewal Application", loan_renewal_name
            )
            loan = frappe.get_doc("Loan", renewal_doc.loan)
            customer = frappe.get_doc("Loan Customer", loan.customer)
            loan_expiry = datetime.combine(loan.expiry_date, time.min)
            user_kyc = frappe.get_all(
                "User KYC",
                filters={
                    "user": customer.user,
                    "updated_kyc": 1,
                },
                fields=["*"],
            )
            top_up_application = frappe.get_all(
                "Top up Application",
                filters={"loan": loan.name, "status": "Pending"},
                fields=["name"],
            )

            loan_application = frappe.get_all(
                "Loan Application",
                filters={
                    "loan": loan.name,
                    "application_type": [
                        "IN",
                        ["Increase Loan", "Pledge More", "Margin Shortfall"],
                    ],
                },
                fields=["name"],
            )
            if top_up_application or loan_application:
                renewal_doc.action_status = "Pending"
                renewal_doc.save(ignore_permissions=True)
                frappe.db.commit()
            else:
                renewal_doc.action_status = ""
                renewal_doc.save(ignore_permissions=True)
                frappe.db.commit()
            date_7after_expiry = loan_expiry + timedelta(days=7)
            if (
                frappe.utils.now_datetime().date() > loan.expiry_date
                and frappe.utils.now_datetime().date()
                < (loan.expiry_date + timedelta(days=7))
                and renewal_doc.status not in ["Approved", "Rejected"]
                and user_kyc
            ):
                seconds = abs(
                    date_7after_expiry - frappe.utils.now_datetime()
                ).total_seconds()
                renewal_timer = lms.convert_sec_to_hh_mm_ss(seconds, is_for_days=True)
                renewal_doc.time_remaining = renewal_timer
                renewal_doc.save(ignore_permissions=True)
                frappe.db.commit()

        else:
            loans = frappe.get_all("Loan", fields=["*"])
            for loan in loans:
                customer = frappe.get_doc("Loan Customer", loan.customer)
                user_kyc = frappe.get_all(
                    "User KYC",
                    filters={
                        "user": customer.user,
                        "updated_kyc": 1,
                    },
                    fields=["*"],
                )
                top_up_application = frappe.get_all(
                    "Top up Application",
                    filters={"loan": loan.name, "status": "Pending"},
                    fields=["name"],
                )

                loan_application = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": loan.name,
                        "application_type": [
                            "IN",
                            ["Increase Loan", "Pledge More", "Margin Shortfall"],
                        ],
                    },
                    fields=["name"],
                )

                renewal_doc_list = frappe.get_all(
                    "Spark Loan Renewal Application",
                    filters={
                        "loan": loan.name,
                        "status": ["NOT IN", ["Approved", "Rejected"]],
                    },
                    fields=["*"],
                )
                if renewal_doc_list:
                    renewal_doc = frappe.get_doc(
                        "Spark Loan Renewal Application", renewal_doc_list[0].name
                    )

                if top_up_application or loan_application:
                    if renewal_doc_list:
                        renewal_doc.action_status = "Pending"
                        renewal_doc.save(ignore_permissions=True)
                        frappe.db.commit()
                else:
                    if renewal_doc_list:
                        renewal_doc.action_status = ""
                        renewal_doc.save(ignore_permissions=True)
                        frappe.db.commit()

                # loan_expiry = pd.Timestamp(loan.expiry_date)
                loan_expiry = datetime.combine(loan.expiry_date, time.min)
                date_7after_expiry = loan_expiry + timedelta(days=7)
                if (
                    frappe.utils.now_datetime().date() > loan.expiry_date
                    and renewal_doc_list
                    and user_kyc
                ):
                    seconds = abs(
                        date_7after_expiry - frappe.utils.now_datetime()
                    ).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )
                    if renewal_doc_list:
                        renewal_doc.time_remaining = renewal_timer
                        renewal_doc.save(ignore_permissions=True)
                        frappe.db.commit()

                user_kyc_pending = frappe.get_all(
                    "User KYC",
                    filters={
                        "user": customer.user,
                        "updated_kyc": 1,
                        "kyc_status": "Pending",
                    },
                    fields=["*"],
                )
                renewal_doc_pending_list = frappe.get_all(
                    "Spark Loan Renewal Application",
                    filters={"loan": loan.name, "status": "Pending"},
                    fields=["*"],
                )
                if renewal_doc_pending_list:
                    renewal_doc = frappe.get_doc(
                        "Spark Loan Renewal Application",
                        renewal_doc_pending_list[0].name,
                    )

                if (
                    frappe.utils.now_datetime().date()
                    > (loan.expiry_date + timedelta(days=7))
                    and user_kyc_pending
                    and renewal_doc_pending_list
                ):
                    seconds = abs(
                        (date_7after_expiry + timedelta(days=7))
                        - frappe.utils.now_datetime()
                    ).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )
                    if renewal_doc_list:
                        renewal_doc.time_remaining = renewal_timer
                        renewal_doc.save(ignore_permissions=True)
                        frappe.db.commit()

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("Loan Renewal Application  - Timer Function"),
        )
