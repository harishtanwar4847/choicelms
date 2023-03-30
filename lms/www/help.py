from datetime import datetime
from warnings import filters

import frappe
import pandas as pd

import lms

# from frappe.utils.pdf import get_pdf


@frappe.whitelist(allow_guest=True)
def approved_securities(instrument_type):
    approved_security_list = []
    approved_security_pdf_file_url = ""
    # approved_security_list = frappe.db.get_all(
    #     "Allowed Security",
    #     order_by="security_name asc",
    #     filters={"instrument_type":"Mutual Fund"},
    #     fields=[
    #         "isin",
    #         "security_name",
    #         "security_category",
    #         "eligible_percentage",
    #         "lender",
    #     ],
    # )
    approved_security_list = frappe.db.sql(
        """
        select alsc.isin,alsc.security_name,alsc.category_name as security_category,alsc.eligible_percentage,alsc.lender  from `tabAllowed Security` alsc  where instrument_type = "{}" order by security_name asc
        """.format(
            instrument_type
        ),
        as_dict=True,
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
    if instrument_type == "Shares":
        approved_security_pdf_file = "approved-securities.pdf"
    else:
        approved_security_pdf_file = "approved-securities-mf.pdf"

    date_ = frappe.utils.now_datetime()
    formatted_date = lms.date_str_format(date=date_.day)
    curr_date = formatted_date + date_.strftime(" %B, %Y")
    approved_security_pdf_file_path = frappe.utils.get_files_path(
        approved_security_pdf_file
    )
    las_settings = frappe.get_single("LAS Settings")
    logo_file_path_2 = las_settings.get_spark_logo_file()
    approved_securities_template = las_settings.get_approved_securities_template()
    doc = {
        "column_name": df.columns,
        "rows": df.iterrows(),
        "date": curr_date,
        "logo_file_path_2": logo_file_path_2.file_url if logo_file_path_2 else "",
    }
    agreement = frappe.render_template(
        approved_securities_template.get_content(), {"doc": doc}
    )
    pdf_file = open(approved_security_pdf_file_path, "wb")
    pdf = lms.get_pdf(
        agreement,
        options={
            "margin-right": "0mm",
            "margin-left": "0mm",
            "page-size": "A4",
        },
    )
    pdf_file.write(pdf)
    pdf_file.close()
    if instrument_type == "Shares":
        approved_security_pdf_file_url = frappe.utils.get_url(
            "files/approved-securities.pdf"
        )
    else:
        approved_security_pdf_file_url = frappe.utils.get_url(
            "files/approved-securities-mf.pdf"
        )
    return approved_security_pdf_file_url


@frappe.whitelist(allow_guest=True)
def lenders():
    lender_list = []
    lender_pdf_file_url = ""
    lender_list = frappe.db.get_all(
        "Lender",
        order_by="creation asc",
        fields=[
            "full_name",
            "logo_file_1",
        ],
    )
    lt_list = []
    for list in lender_list:
        lt_list.append(list.values())
    df = pd.DataFrame(lt_list)
    df.columns = lender_list[0].keys()
    df.columns = pd.Series(df.columns.str.replace("_", " ")).str.title()
    df.index += 1
    lender_pdf_file = "Lender.pdf"
    date_ = frappe.utils.now_datetime()
    formatted_date = lms.date_str_format(date=date_.day)
    curr_date = formatted_date + date_.strftime(" %B, %Y")
    lender_pdf_file_path = frappe.utils.get_files_path(lender_pdf_file)

    lender = frappe.get_doc("LAS Settings")
    las_settings = frappe.get_single("LAS Settings")
    logo_file_path_2 = las_settings.get_spark_logo_file()
    lender_template = lender.get_lender_template()
    doc1 = {
        "column_name": df.columns,
        "rows": df.iterrows(),
        "date": curr_date,
        "logo_file_path_2": logo_file_path_2.file_url if logo_file_path_2 else "",
    }
    agreement = frappe.render_template(lender_template.get_content(), {"doc": doc1})

    pdf_file = open(lender_pdf_file_path, "wb")
    pdf = lms.get_pdf(
        agreement,
        options={
            "margin-right": "0mm",
            "margin-left": "0mm",
            "page-size": "A4",
        },
    )
    pdf_file.write(pdf)
    pdf_file.close()
    lender_pdf_file_url = frappe.utils.get_url("files/Lender.pdf")
    return lender_pdf_file_url


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

    context.interestupto5 = frappe.get_all(
        "Interest Configuration",
        fields=["*"],
        filters={"from_amount": ("=", 0)},
        order_by="creation",
    )[0]

    context.lenderCharges = frappe.get_last_doc("Lender")
    context.approved_pdf_shares = approved_securities(instrument_type="Shares")
    context.approved_pdf_mf = approved_securities(instrument_type="Mutual Fund")

    context.lender_pdf = lenders()
