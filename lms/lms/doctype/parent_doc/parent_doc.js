// Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Parent Doc", {
  //refresh: function(frm) {
  //frappe.msgprint(("hello world from refresh event"))
  //}
  //onload: function(frm) {
  //frappe.msgprint(("hello world from 'onload' event"))
  //}
  //validate: function(frm) {
  //frappe.msgprint(("hello world from 'validate' event"))
  //}
  //validate: function(frm) {
  //frappe.throw(("hello world from 'validate' event"))
  //}
  //before_save: function(frm) {
  //frappe.throw(("hello world from 'before_save' event"))
  //}
  //after_save: function(frm) {
  //frappe.throw(("hello world from 'after_save' event"))
  //}
  //enable: function(frm) {
  //frappe.throw(("hello world from 'enable' event"))
  //},
  //age: function(frm) {
  //frappe.throw(("hello world from 'age' event"))
  //}
  //before_submit: function(frm) {
  //frappe.throw(("hello world from 'before save' event"))
  //}
  //on_submit: function(frm) {
  //frappe.throw(("hello world from 'on submit' event"))
  //}
  //after_cancel: function(frm) {
  //frappe.throw(("hello world from 'After cancel' event"))
  //}
  //after_save:function(frm){
  //frappe.msgprint(__("The age is {0}",[frm.doc.age]))
  //}
  //after_save:function(frm){
  //frappe.msgprint({
  //title:__("Notification"),
  //indicator:'green',
  //message:__("HEllo World")
  //});
  //}
  //refresh:function(frm){
  //frm.set_intro('Now you can create a new parent doctype')
  //}
  //refresh:function(frm){
  //if (frm.is_new()){
  //frm.set_intro('Now you can create a new parent doctype')
  //}
  //}
  //validate:function(frm){
  //frm.set_value('full_name',frm.doc.first_name + " "+  frm.doc.last_name)
  //}
  //refresh:function(frm){
  //if(frm.is_new()){
  //let d =new frappe.ui.Dialog({
  //title:'Please Enter the Parent Details',
  //fields:[{
  //label:'First Name',
  //fieldname:'first_name',
  //fieldtype:'Data'
  //},
  //{
  //label:'Last Name',
  //fieldname:'last_name',
  //fieldtype:'Data'
  //},
  //{
  //label:'Age',
  //fieldname:'age',
  //fieldtype:'Data'
  //}],
  //primary_action_label:'submit',
  //primary_action(values){
  //frm.set_value('first_name',values.first_name)
  //frm.set_value('last_name',values.last_name)
  //frm.set_value('age',values.age)
  //d.hide()
  //}
  //});
  //d.show();
  //}
  //}
  //enable:function(frm){
  //if(frm.is_dirty()){
  //frappe.msgprint(__('please save the document'))
  //}
  //}
  //Custom Button
  //refresh:function(frm){
  //frm.add_custom_button('click me',()=>{
  //frappe.msgprint(__('You clicked!'));
  //})
  //}
  //refresh:function(frm){
  //frm.add_custom_button('click me1',()=>{
  //frappe.msgprint(__('You clicked1!'));
  //})
  //frm.add_custom_button('click me2',()=>{
  //frappe.msgprint(__('You clicked2!'));
  //})
  //}
  //refresh:function(frm){
  //frm.add_custom_button('Click me1',()=>{
  //frappe.msgprint(__('You Clicked1!'));
  //},'click me')
  //frm.add_custom_button('Click me2',()=>{
  //frappe.msgprint(__('You clicked2!'));
  //},'click me')
  //}
  //Trigger Event /Function
  //refresh:function(frm) {
  //if(!frm.is_new()){
  //frm.trigger('enable');
  //}
  //},
  //enable:function(frm) {
  //frappe.msgprint(__('the event is triggered'))
  //}
  //How to triggered function using triggered method
  //refresh:function(frm){
  //if(!frm.is_new()){
  //frm.trigger('test_fun');
  //}
  //},
  //test_fun(frm){
  //frappe.msgprint(__('This message is from test_function'))
  //}
  //validate:function(frm){
  //frm.set_value('full_name',frm.doc.first_name+' '+frm.doc.last_name)
  //}
  //Set child Table field
  //enable:function(frm){
  //let row=frm.add_child('date_and_value',{
  //date:'25-01-2022',
  //value_1:10,
  //value_2:20
  //})
  //frm.refresh_field('date_and_value')
  //}
  //For fetching todays date
  //enable:function(frm){
  //let row=frm.add_child('date_and_value',{
  //date:frappe.datetime.get_today(),
  //value_1:10,
  //value_2:20
  //})
  //frm.refresh_field('date_and_value')
  //}
  //Custom Script/Client Script (Form)
  // validate:function(frm){
  // 	if(frm.doc.date<get_today()){
  // 		frappe.throw('You cannot select past date in Todays Date')
  // 	}
  //  }
  //Customize field properties
  //Make a field last_name read only after creating the document.
  //  refresh:function(frm){
  // 	frm.set_df_property('last_name', 'read_only', !frm.is_new());
  //  }
  //Make a field Age read only after creating the document.
  //  refresh:function(frm){
  // 	frm.set_df_property('age','read_only',!frm.is_new());
  //  }
  //Contact number length validation
  //  validate:function(frm){
  // 	 if(frm.doc.contact_number.length!=10){
  // 		frappe.throw("Enter valid phone number")
  // 	 }
  //  }
  //Form API
  // -frm.set_value
  // refresh:function(frm){
  // 	frm.set_value('full_name','mayur Jadav')
  // }
  // validate:function(frm){
  // 	frm.save('Submit');
  // }
  // -frm.save('Update')
  // validate:function(frm){
  // 	frm.save('Update');
  // }
  // -cancel
  // validate:function(frm){
  // 	frm.save('Cancel');
  // }
  //frm.enable_save / frm.disable_save
  // validate:function(frm){
  // if(frm.doc.contact_number.length!=10){
  // 	frm.disable_save();
  // 	}else{
  // 		frm.enable_save();
  // 	}
  // }
  //frm.email_doc
  // after_save:function(frm){
  // 	frm.email_doc(`Hello ${frm.doc.first_name}`);
  // }
  //frm.reload_doc
  // refresh:function(frm){
  // 	if(frm.is_new()){
  // 		let d =new frappe.ui.Dialog({
  // 			title:'Please Enter the Parent Details',
  // 			fields:[{
  // 					label:'First Name',
  // 					fieldname:'first_name',
  // 					fieldtype:'Data'
  // 				},
  // 				{
  // 					label:'Last Name',
  // 					fieldname:'last_name',
  // 					fieldtype:'Data'
  // 				},
  // 				{
  // 					label:'Age',
  // 					fieldname:'age',
  // 					fieldtype:'Data'
  // 				}],
  // 				primary_action_label:'submit',
  // 				primary_action(values){
  // 					frm.set_value('first_name',values.first_name)
  // 					frm.set_value('last_name',values.last_name)
  // 					frm.set_value('age',values.age)
  // 			//frm.reload_doc();
  // 			//frm.refresh();
  // 			d.hide()
  // 			frm.reload_doc();
  // 			frm.refresh();
  // 			}
  // 		});
  // 		d.show();
  // 	}
  // }
  //frm.refresh_field
  // before_save:function(frm){
  // 	if(frm.doc.age>30){
  // 		frm.refresh_field('age')
  // 	}
  // }
  // before_save:function(frm){
  // if(frm.doc.date<get_today()){
  // 	frm.refresh_field('date')
  // 	 	}
  // 	  }
  //frm.is_dirty
  //Check if form values has been changed and is not saved yet.
  // before_save:function(frm){
  // 	if(frm.is_dirty()){
  // 		frappe.show_alert('Please save form before attaching a file')
  // 	}
  // }
  //frm.clear_custom_buttons
  //frm.get_selected
  // refresh:function(frm){
  // 	let selected = frm.get_selected()
  // 	console.log(selected)
  // 	{
  // 		'date_and_value'
  // 	}
  // }
  // onload: function(frm) {
  //     // Ignore cancellation for all linked documents of respective DocTypes.
  //     frm.ignore_doctypes_on_cancel_all = ["pract", "demo 2"];
  // }
  // refresh:function(frm){
  // 	frm.add_custom_button('click me',()=>{
  // 		frappe.msgprint(__('You clicked!'));
  // 	})
  // }
  // refresh:function(frm){
  // 	frm.change_custom_button_type('Open Reference form', null, 'primary');
  // }
  // onload: function(frm) {
  //     // Ignore cancellation for all linked documents of respective DocTypes.
  //     frm.ignore_doctypes_on_cancel_all = ["pract", "demo 2"];
  // }
  //frm.toggle_reqd
  //frm.toggle_display
  //refresh(frm) {
  //frm.trigger('set_mandatory_fields');
  //},
  //set_mandatory_fields(frm) {
  //frm.toggle_reqd('priority', frm.doc.status === 'Open');
  //console.log(frm.doc.status)
  //frm.toggle_display('priority', frm.doc.status === 'Open');
  //frm.toggle_enable
  //let is_allowed = frappe.user_roles.includes('Lender');
  //frm.toggle_enable('priority', is_allowed);
  //frm.toggle_enable('priority', frm.doc.status === 'Open');
  //}
});
