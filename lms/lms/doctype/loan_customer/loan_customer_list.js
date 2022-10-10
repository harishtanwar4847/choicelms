// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// MIT License. See license.txt

// frappe.listview_settings["Loan Customer"] = {
//   onload: function (listview) {
//     var is_true = frappe.user_roles.find((role) => role === "Lender");
//     if (is_true || frappe.session.user == "Administrator") {
//

frappe.listview_settings["Loan Customer"] = {
  hide_name_column: true,
  refresh: function (listview) {
    var is_true = frappe.user_roles.find((role) => role === "Lender");
    if (is_true || frappe.session.user == "Administrator") {
      listview.page.add_inner_button(__("File Upload"), function () {
        let d = new frappe.ui.Dialog({
          title: "Enter details",
          fields: [
            {
              label: "Upload CSV",
              fieldname: "file",
              fieldtype: "Attach",
            },
          ],
          primary_action_label: "Submit",
          primary_action(values) {
            if (values.file.split(".")[1].toLowerCase() == "csv") {
              // pass
            } else {
              frappe.throw("Other than CSV file format not supported");
            }
            frappe.call({
              method: "lms.create_user_customer",
              args: {
                upload_file: values.file,
              },
              freeze: false,
            });
            d.hide();
          },
        });

        d.show();
      });
    }
  },
  onload: function (listview) {
    var is_true = frappe.user_roles.find((role) => role === "Lender");
    if (is_true || frappe.session.user == "Administrator") {
      listview.page.add_inner_button(
        __("Download Customer Template"),
        function () {
          frappe.call({
            method:
              "lms.lms.doctype.loan_customer.loan_customer.loan_customer_template",
            freeze: true,
            args: {
              doc_filters: frappe
                .get_user_settings("Loan Customer")
                ["List"].filters.map((filter) => filter.slice(1, 4)),
            },
            callback: (res) => {
              window.open(res.message);
            },
          });
        }
      );
    }
  },
};
