frappe.listview_settings["Security Details"] = {
  onload: function (listview) {
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
        callback: (res) => {
          window.open(res.message);
        },
      });
    });
  },
};
