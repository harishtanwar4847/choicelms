frappe.listview_settings["Security Transaction"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(
          __("Update Security Transaction"),
          function () {
            frappe.call({
              method:
                "lms.lms.doctype.security_transaction.security_transaction.security_transaction",
              freeze: true,
            });
          }
        );
        frappe.db.get_single_value("LAS Settings").then((res) => {
          if (res) {
            listview.page.add_inner_button(__("Generate Excel"), function () {
              frappe.call({
                method:
                  "lms.lms.doctype.security_transaction.security_transaction.excel_generator",
                freeze: true,
                args: {
                  doc_filters: frappe
                    .get_user_settings("Security Transaction")
                    ["List"].filters.map((filter) => filter.slice(1, 4)),
                },
                callback: (res) => {
                  window.open(res.message);
                },
              });
            });
          }
        });
      }
    });
  },
};
