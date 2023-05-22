// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.listview_settings["Allowed Security"] = {
  hide_name_column: true,
  refresh: function (listview) {
    listview.page.add_inner_button(__("Upload CSV"), function () {
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
          if (values.file.split(".").slice(-1)[0].toLowerCase() != "csv") {
            frappe.throw("Other than CSV file format not supported");
          }
          frappe.call({
            method:
              "lms.lms.doctype.allowed_security.allowed_security.update_mycams_scheme_bulk",
            args: {
              upload_file: values.file,
            },
            freeze: true,
          });
          d.hide();
        },
      });

      d.show();
    });
  },
};
