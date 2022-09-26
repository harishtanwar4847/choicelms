frappe.listview_settings["Security Exposure Summary"] = {
  onload: function (listview) {
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
  },
};
