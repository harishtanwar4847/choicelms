from datetime import datetime, timedelta

import frappe

from lms import send_spark_push_notification
from lms.lms.doctype.user_token.user_token import send_sms


def execute():
    try:
        loans = frappe.get_all("Loan", fields=["*"])
        for loan in loans:
            customer = frappe.get_doc("Loan Customer", loan.customer)
            print(
                "Loan name : {},, Loan expiry : {} ".format(loan.name, loan.expiry_date)
            )
            month_to_expiry = loan.expiry_date - timedelta(days=30)
            curr_date = frappe.utils.now_datetime().date()
            if curr_date < loan.expiry_date and curr_date >= month_to_expiry:
                print("Inside if loan name :", loan.name)
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
                print("Renewal doc name :", renewal_doc.name)
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

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._(
                "Loan Renewal Application  - Patch for application creation error"
            ),
        )
