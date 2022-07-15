frappe.listview_settings["Client Summary"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(
          __("Update Client Summary"),
          function () {
            frappe.call({
              method:
                "lms.lms.doctype.client_summary.client_summary.client_summary",
              freeze: true,
            });
          }
        );
      }
    });
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(__("Generate Excel"), function () {
          frappe.call({
            method:
              "lms.lms.doctype.client_summary.client_summary.excel_generator",
            freeze: true,
            args: {
              doc_filters: frappe
                .get_user_settings("Client Summary")
                ["List"].filters.map((filter) => filter.slice(1, 4)),
            },
            callback: (res) => {
              window.open(res.message);
            },
          });
        });
      }
    });
  },
};
