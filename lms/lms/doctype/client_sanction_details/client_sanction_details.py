# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import datetime

import frappe
import numpy as np
import pandas as pd
from frappe.model.document import Document

import lms


class ClientSanctionDetails(Document):
    pass


@frappe.whitelist()
def excel_generator(doc_filters):
    client_sanctioned_details_doc = frappe.get_all(
        "Client Sanction Details",
        filters=doc_filters,
        fields=[
            "client_code",
            "loan_no",
            "client_name",
            "pan_no",
            "start_date",
            "end_date",
            "sanctioned_amount",
            "roi",
            "sanction_date",
        ],
    )
    if client_sanctioned_details_doc == []:
        frappe.throw(("Record does not exist"))

    final = pd.DataFrame(
        [c.values() for c in client_sanctioned_details_doc], index=None
    )
    # final=final.set_index(['client_code', 'loan_no','client_name','pan_no'],drop = False)
    # final = final.set_index(['client_code', 'loan_no','client_name','pan_no','start_date'])
    final.columns = client_sanctioned_details_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    final.sort_values("Client Code", inplace=True)

    # final.set_index(['loan_no','client_name','pan_no','sanctioned_amount','pledged_value','drawing_power','loan_balance','adp_shortfall','roi_','client_demat_acc','customer_contact_no','loan_expiry_date','dpd'])
    # report = final.groupby(['']).apply(lambda sub_df:  sub_df.pivot_table(index=['customer','customer_name','transaction_type'], values=['amount'],aggfunc=np.sum, margins=True,margins_name= 'TOTAL'))
    # report.loc[('', 'Grand Total','',''), :] = report[report.index.get_level_values(1) != 'TOTAL'].sum()
    # report=report.reset_index(level=0,drop=True)
    # final
    # report=report.reset_index(level=0,drop=True)
    # final.to_excel("Client_Sanction_Details.xlsx", index=False)
    # final.loc[final['Client Code'].duplicated(), 'Client Code'] = ""
    # final.loc[final['Loan No'].duplicated(), 'Loan No'] = ""
    # final.loc[final['Client Name'].duplicated(), 'Client Name'] = ""
    # final.loc[final['Pan No'].duplicated(), 'Pan No'] = ""
    final.loc[final["Client Code"].duplicated(), "Client Code"] = ""
    final.loc[final["Loan No"].duplicated(), "Loan No"] = ""
    final.loc[final["Client Name"].duplicated(), "Client Name"] = ""
    final.loc[final["Pan No"].duplicated(), "Pan No"] = ""

    # final.loc[(final['Client Code'].duplicated() & final['Loan No'].duplicated()), ['Client Code','Loan No']] = ''
    # final.loc[(final['Client Code'].duplicated() & final['Client Name'].duplicated()), ['Client Code','Client Name']] = ''
    # final.loc[(final['Client Code'].duplicated() & final['Pan No'].duplicated()), ['Client Code','Pan No']] = ''
    print(final)
    file_name = "client_santion_details_{}".format(frappe.utils.now_datetime())
    return lms.download_file(
        dataframe=final, file_name=file_name, file_extention="xlsx"
    )
