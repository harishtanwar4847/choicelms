frappe.listview_settings["Loan Transaction"] = {
  onload: function (listview) {
    listview.page.add_inner_button(__("Settle Payment"), function () {
      frappe.prompt(
        {
          label: "Date",
          fieldname: "date",
          fieldtype: "Date",
          reqd: true,
        },
        (values) => {
          frappe.call({
            method:
              "lms.lms.doctype.loan_transaction.loan_transaction.settlement_recon_api",
            args: {
              input_date: values.date,
            },
          });
        }
      );
    });
  },
};
