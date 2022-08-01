// Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Spark Email Campaign", {
  refresh: function (frm, cdt, cdn) {
    $("div.grid-heading-row span.hidden-xs").html("Level");
    if (frm.doc.sender_email.length > 0) {
      $(".grid-add-row").hide();
    }
  },
  sender_email_on_form_rendered(frm, cdt, cdn) {
    frm.fields_dict["sender_email"].grid.wrapper.find(".grid-shortcuts").hide();
    if (frm.doc.sender_email.length >= 1) {
      console.log("efgh");
      $(".grid-add-row").hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-delete-row")
        .hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-insert-row-below")
        .hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-insert-row")
        .hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-duplicate-row")
        .hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-append-row")
        .hide();
    }
  },
});

frappe.ui.form.on("User Email", {
  sender_email_add(frm, cdt, cdn) {
    console.log(frm.doc);
    if (frm.doc.sender_email.length >= 1) {
      $(".grid-add-row").hide();
    }
    if (frm.doc.sender_email.length > 1) {
      frappe.msgprint(__("Maximum 1 levels allowed"));
    }
  },
});

// frappe.ui.form.on("Customer Email", {
//   // customer_selection: function (frm)  {
//     if (customer_selection == "Selected Customer") {
//         console.log("hiiiii")
//         frappe.db.get_list("Loan Customer", function () {
//         var tabletransfer = frappe.db.get_list("Loan Customer");
//         console.log(tabletransfer)
//         // $.each(tabletransfer.customer_email, function (index, row) {
//         //   if (row.pledged_quantity > 0) {
//         //     var d = frm.add_child("customer_email");
//         //     d.customer_id = row.name;
//         //     frm.refresh_field("customer_email");
//         //   }
//         // });
//       });
//     }
//   // }
// });
