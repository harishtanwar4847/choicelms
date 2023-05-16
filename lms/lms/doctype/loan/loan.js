// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan", {
  validate: function (frm) {
    if (
      frm.doc.wef_date != frm.doc.old_wef_date &&
      frm.doc.wef_date < frappe.datetime.now_date()
    ) {
      frappe.throw("W.e.f date should be Current date or Future date");
    }
  },
  is_default: function (frm) {
    if (frm.doc.is_default == 0) {
      frm.set_value("custom_base_interest", 0);
      frm.set_value("custom_rebate_interest", 0);
    } else {
      frm.set_df_property("custom_base_interest", "read_only", 1);
      frm.set_df_property("custom_rebate_interest", "read_only", 1);
    }
  },

  on_load: function (frm) {
    frappe.call({
      method: "lms.lms.doctype.loan.loan.check_for_topup_increase_loan",
      freeze: true,
      args: {
        loan_name: frm.doc.name,
      },
      callback: (res) => {
        if (res.message) {
          frm.set_df_property("is_default", "read_only", 1);
          frm.set_df_property("custom_base_interest", "read_only", 1);
          frm.set_df_property("custom_rebate_interest", "read_only", 1);
          frm.set_df_property("wef_date", "read_only", 1);
        }
      },
    });
  },

  refresh: function (frm) {
    frm.set_df_property("items", "read_only", 1);
    frm.attachments.parent.hide();
    frm
      .get_field("loan_agreement")
      .$input_wrapper.find("[data-action=clear_attachment]")
      .hide();
    frappe.db.get_single_value("LAS Settings", "debug_mode").then((res) => {
      if (res) {
        frm.add_custom_button(
          __("Virtual Interest"),
          function () {
            frappe.prompt(
              {
                label: "Date",
                fieldname: "date",
                fieldtype: "Date",
                reqd: true,
              },
              (values) => {
                frappe.call({
                  method: "lms.lms.doctype.loan.loan.daily_virtual_job",
                  freeze: true,
                  args: {
                    loan_name: frm.doc.name,
                    input_date: values.date,
                  },
                });
              }
            );
          },
          __("Interest Jobs")
        );
        frm.add_custom_button(
          __("Penal Interest"),
          function () {
            frappe.prompt(
              {
                label: "Date",
                fieldname: "date",
                fieldtype: "Date",
                reqd: true,
              },
              (values) => {
                frappe.call({
                  method: "lms.lms.doctype.loan.loan.daily_penal_job",
                  freeze: true,
                  args: {
                    loan_name: frm.doc.name,
                    input_date: values.date,
                  },
                });
              }
            );
          },
          __("Interest Jobs")
        );
        frm.add_custom_button(
          __("Additional Interest"),
          function () {
            frappe.prompt(
              {
                label: "Date",
                fieldname: "date",
                fieldtype: "Date",
                reqd: true,
              },
              (values) => {
                frappe.call({
                  method: "lms.lms.doctype.loan.loan.additional_interest_job",
                  freeze: true,
                  args: {
                    loan_name: frm.doc.name,
                    input_date: values.date,
                  },
                });
              }
            );
          },
          __("Interest Jobs")
        );

        frm.add_custom_button(
          __("Book Interest"),
          function () {
            frappe.prompt(
              {
                label: "Date",
                fieldname: "date",
                fieldtype: "Date",
                reqd: true,
              },
              (values) => {
                frappe.call({
                  method:
                    "lms.lms.doctype.loan.loan.book_virtual_interest_for_month",
                  freeze: true,
                  args: {
                    loan_name: frm.doc.name,
                    input_date: values.date,
                  },
                });
              }
            );
          },
          __("Interest Jobs")
        );
      }
    });

    // hiding loan item if pledged quantity is zero (0)
    cur_frm.doc.items.forEach((x) => {
      if (x.pledged_quantity <= 0) {
        $("[data-idx='" + x.idx + "']").hide();
      } else {
        $("[data-idx='" + x.idx + "']").show();
      }
    });
  },
});
