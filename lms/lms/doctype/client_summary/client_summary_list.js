frappe.listview_settings["Client Summary"] = {
  onload: function (listview) {
    listview.page.add_inner_button(__("Generate Excel"), function () {
      frappe.call({
        method: "lms.lms.doctype.client_summary.client_summary.excel_generator",
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
  },
};
