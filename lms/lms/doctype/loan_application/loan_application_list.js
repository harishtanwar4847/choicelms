// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.listview_settings["Loan Application"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(__("Process Pledge"), function () {
          frappe.call({
            method:
              "lms.lms.doctype.loan_application.loan_application.process_pledge",
            freeze: true,
          });
        });
      }
    });
  },
  hide_name_column: true, // hide the last column which shows the `name`
};
