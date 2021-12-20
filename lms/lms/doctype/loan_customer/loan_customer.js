// Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Customer", {
  refresh: function (frm) {
    if (!frm.doc.is_email_verified) {
      frm.add_custom_button("Resend Verification Email", () => {
        console.log(frm.doc.user);
        frappe.call({
          type: "POST",
          method: "lms.auth.request_verification_email",
          args: { email: frm.doc.user },
        });
      });
    }
  },
});
