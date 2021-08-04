import re
from datetime import datetime

import frappe
import pandas as pd
import utils
from frappe.utils.pdf import get_pdf

import lms


@frappe.whitelist(allow_guest=True)
def approved_securities():
    filters = {"lender": "Choice Finserv"}
    approved_security_list = []
    approved_security_pdf_file_url = ""
    or_filters = ""
    approved_security_list = frappe.db.get_all(
        "Allowed Security",
        filters=filters,
        or_filters=or_filters,
        order_by="security_name asc",
        fields=[
            "isin",
            "security_name",
            "security_category",
            "eligible_percentage",
        ],
    )
    approved_security_list.sort(key=lambda item: (item["security_name"]).title())
    lt_list = []
    for list in approved_security_list:
        lt_list.append(list.values())
    df = pd.DataFrame(lt_list)
    df.columns = approved_security_list[0].keys()
    df.drop("eligible_percentage", inplace=True, axis=1)
    df.columns = pd.Series(df.columns.str.replace("_", " ")).str.title()
    df.index += 1
    approved_security_pdf_file = "{}-approved-securities.pdf".format(
        "Choice Finserv"
    ).replace(" ", "-")
    date_ = frappe.utils.now_datetime()
    formatted_date = lms.date_str_format(date=date_.day)
    curr_date = formatted_date + date_.strftime(" %B, %Y")
    approved_security_pdf_file_path = frappe.utils.get_files_path(
        approved_security_pdf_file
    )
    lender = frappe.get_doc("Lender", "Choice Finserv")
    las_settings = frappe.get_single("LAS Settings")
    logo_file_path_1 = lender.get_lender_logo_file()
    logo_file_path_2 = las_settings.get_spark_logo_file()
    approved_securities_template = lender.get_approved_securities_template()
    doc = {
        "column_name": df.columns,
        "rows": df.iterrows(),
        "date": curr_date,
        "logo_file_path_1": logo_file_path_1.file_url if logo_file_path_1 else "",
        "logo_file_path_2": logo_file_path_2.file_url if logo_file_path_2 else "",
    }
    agreement = frappe.render_template(
        approved_securities_template.get_content(), {"doc": doc}
    )
    pdf_file = open(approved_security_pdf_file_path, "wb")
    pdf = get_pdf(
        agreement,
        options={
            "margin-right": "0mm",
            "margin-left": "0mm",
            "page-size": "A4",
        },
    )
    pdf_file.write(pdf)
    pdf_file.close()
    approved_security_pdf_file_url = frappe.utils.get_url(
        "files/{}-approved-securities.pdf".format("Choice Finserv").replace(" ", "-")
    )
    return approved_security_pdf_file_url


def get_context(context):
    context.marginmax = frappe.get_all(
        "Margin Shortfall Action",
        fields=["*"],
        filters={"sell_off_deadline_eod": ("!=", 0)},
        order_by="creation",
    )[0]
    context.marginmax.sell_off_deadline_eod = datetime.strptime(
        "{}".format(context.marginmax.sell_off_deadline_eod), "%H"
    ).strftime("%I:%M %p")

    context.marginmin = frappe.get_all(
        "Margin Shortfall Action",
        fields=["*"],
        filters={"sell_off_after_hours": ("!=", 0)},
        order_by="creation",
    )[0]

    context.intrupto5 = frappe.get_all(
        "Interest Configuration",
        fields=["*"],
        filters={"from_amount": ("=", 0)},
        order_by="creation",
    )[0]

    context.lenderCharges = frappe.get_last_doc("Lender")

    context.approved_pdf = approved_securities()
