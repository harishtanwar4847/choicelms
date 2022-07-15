frappe.listview_settings["Interest Calculation"] = {
  onload: function (listview) {
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        listview.page.add_inner_button(
          __("Update Interest Calculation"),
          function () {
            frappe.call({
              method:
                "lms.lms.doctype.interest_calculation.interest_calculation.interest_calculation_enqueue",
              freeze: true,
            });
          }
        );
        frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
          if (res) {
            listview.page.add_inner_button(__("Generate Excel"), function () {
              frappe.call({
                method:
                  "lms.lms.doctype.interest_calculation.interest_calculation.excel_generator",
                freeze: true,
                args: {
                  doc_filters: frappe
                    .get_user_settings("Interest Calculation")
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
  hide_name_column: true,
};
