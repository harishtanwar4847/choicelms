// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// MIT License. See license.txt

frappe.listview_settings["Loan Customer"] = {
  onload: function (listview) {
    var is_true = frappe.user_roles.find((role) => role === "Lender");
    if (is_true || frappe.session.user == "Administrator") {
      listview.page.add_inner_button(
        __("Create User & Loan Customer"),
        function () {
          frappe.prompt(
            [
              {
                label: "Email",
                fieldname: "email",
                fieldtype: "Data",
                reqd: true,
              },
              {
                label: "First Name",
                fieldname: "first_name",
                fieldtype: "Data",
                reqd: true,
              },
              {
                label: "Last Name",
                fieldname: "last_name",
                fieldtype: "Data",
                reqd: true,
              },
              {
                label: "Phone",
                fieldname: "phone",
                fieldtype: "Data",
                reqd: true,
              },
            ],
            (values) => {
              frappe.call({
                method: "lms.create_user_customer",
                freeze: true,
                args: {
                  first_name: values.first_name,
                  last_name: values.last_name,
                  email: values.email,
                  mobile: values.phone,
                },
              });
            }
          );
        }
      );
    }
  },
};
