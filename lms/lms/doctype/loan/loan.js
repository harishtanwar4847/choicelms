// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan", {
  is_default: function (frm) {
    if (frm.doc.is_default == 0) {
      frm.set_value("custom_base_interest", 0);
      frm.set_value("custom_rebate_interest", 0);
    }
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
            // frappe.msgprint("hii,  whatsup");
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

        //   frm.add_custom_button(__("Check for shortfall"), function () {
        //     frappe.call({
        //       method: "lms.lms.doctype.loan.loan.check_single_loan_for_shortfall",
        //       freeze: true,
        //       args: {
        //         loan_name: frm.doc.name,
        //       },
        //     });
        //   });
      }
    });
    // frm.add_custom_button(__('Check Additional Interest'), function(){
    // 	// frappe.msgprint("hii,  whatsup");
    // 	frappe.prompt({
    // 		label: 'Date',
    // 		fieldname: 'date',
    // 		fieldtype: 'Date',
    // 		reqd: true
    // 	}, (values) => {

    // 		frappe.call({
    // 			method: 'lms.lms.doctype.loan.loan.check_for_additional_interest',
    // 			freeze: true,
    // 			args: {
    // 				loan_name: frm.doc.name,
    // 				input_date: values.date
    // 			}
    // 		})
    // 	})
    // });

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
