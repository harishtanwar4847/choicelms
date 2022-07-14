frappe.listview_settings["Client Sanction Details"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(__("Generate Excel"), function () {
          frappe.call({
            method:
              "lms.lms.doctype.client_sanction_details.client_sanction_details.excel_generator",
            freeze: true,
            args: {
              doc_filters: frappe
                .get_user_settings("Client Sanction Details")
                ["List"].filters.map((filter) => filter.slice(1, 4)),
            },
          });
        });
      }
    });
  },
};
