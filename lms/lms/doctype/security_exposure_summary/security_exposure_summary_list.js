frappe.listview_settings["Security Exposure Summary"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(
          __("Update Security Exposure Summary"),
          function () {
            frappe.call({
              method:
                "lms.lms.doctype.security_exposure_summary.security_exposure_summary.security_exposure_summary",
              freeze: true,
            });
          }
        );
        frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
          if (res) {
            listview.page.add_inner_button(__("Generate Excel"), function () {
              frappe.call({
                method:
                  "lms.lms.doctype.security_exposure_summary.security_exposure_summary.excel_generator",
                freeze: true,
                args: {
                  doc_filters: frappe
                    .get_user_settings("Security Exposure Summary")
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
