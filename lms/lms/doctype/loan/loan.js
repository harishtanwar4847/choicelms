// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Loan', {
	refresh: function(frm) {
		frm.add_custom_button(__('Daily Cron Job'), function(){
			// frappe.msgprint("hii,  whatsup");
			frappe.prompt({
				label: 'Date',
				fieldname: 'date',
				fieldtype: 'Date',
				reqd: true
			}, (values) => {

				frappe.call({
					method: 'lms.lms.doctype.loan.loan.daily_cron_job',
					freeze: true,
					args: {
						loan_name: frm.doc.name,
						input_date: values.date
					}
				})
			})
		});

		frm.add_custom_button(__('Monthly Cron Job'), function(){
			// frappe.msgprint("hii,  whatsup");
			frappe.prompt({
				label: 'Date',
				fieldname: 'date',
				fieldtype: 'Date',
				reqd: true
			}, (values) => {

				frappe.call({
					method: 'lms.lms.doctype.loan.loan.book_virtual_interest_for_month',
					freeze: true,
					args: {
						loan_name: frm.doc.name,
						input_date: values.date
					}
				})
			})
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
	}
});
