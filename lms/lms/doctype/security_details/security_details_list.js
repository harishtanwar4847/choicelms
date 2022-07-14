frappe.listview_settings["Security Details"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(
          __("Update Security Details"),
          function () {
            frappe.call({
              method:
                "lms.lms.doctype.security_details.security_details.security_details",
              freeze: true,
            });
          }
        );
        frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
          if (res) {
            listview.page.add_inner_button(__("Generate Excel"), function () {
              frappe.call({
                method:
                  "lms.lms.doctype.security_details.security_details.excel_generator",
                freeze: true,
                args: {
                  doc_filters: frappe
                    .get_user_settings("Security Details")
                    ["List"].filters.map((filter) => filter.slice(1, 4)),
                },
              });
            });
          }
        });
      }
    });
  },
};
