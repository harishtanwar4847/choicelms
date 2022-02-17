# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ParentDoc(Document):
    # doc.insert
    # def validate(self):
    # frappe.msgprint("HEllo frappe")
    # doc.save
    # def on_update(self):
    # frappe.msgprint("HEllo frappe")

    # def validate(self):
    # if self.age>60:
    # frappe.throw('Age must be less then 60')
    # return self.age

    # def get_fullname(self):
    # return self.first_name+''+self.last_name

    # def contact(self):
    # return self.contact_number

    # def Date(self):
    # return self.date

    # def DOB(self):
    # return self.dob

    # def after_insert(self):
    # frappe.sendmail(recipients=[self.email], message="Thank you for registering!")

    # Database API

    ##1.db.get_value
    # get firstname
    # def validate(self):
    # self.get_value()

    # def get_value(self):
    # first_name=frappe.db.get_value('Parent Doc','Prashant',['first_name'])
    # frappe.msgprint(("The Parent First Name is {0}").format(first_name))

    # get age
    # def validate(self):
    # self.get_value()

    # def get_value(self):
    # age=frappe.db.get_value('Parent Doc','Prashant',['age'])
    # frappe.msgprint(("The Parent Age is {0}").format(age))

    ##2.db.set_value
    # changing surname patel to jadav
    # db.set_value(Doctype Name,Document Name,field,jo update krna hai wo dalo)
    # def validate(self):
    # self.set_value()

    # def set_value(self):
    # frappe.db.set_value('Parent Doc','Prashant','last_name','Jadav')

    ##3. frappe.db.get_list()
    # frappe.db.get_list(doctype, filters, or_filters, fields, order_by, group_by, start, page_length)

    # def validate(self):
    # self.get_list()

    # def get_list(self):
    # doc=frappe.db.get_list('Parent Doc',
    # filters={
    #'enable':1
    # },
    # fields=['first_name'])
    # for v in doc:
    # frappe.msgprint(("The Parent First Name is {0}").format(v.first_name))

    ##4. frappe.db.get_all()
    # def validate(self):
    # 	self.get_list()

    # def get_list(self):
    # 	doc=frappe.db.get_all('Parent Doc',
    # 		filters={
    # 			'enable':0
    # 		},
    # 		fields=['first_name'])
    # 	for v in doc:
    # 		frappe.msgprint(("The Parent First Name is {0}").format(v.first_name))

    ##5. frappe.db.exists()

    # frappe.db.exists(doctype,document name)
    # def validate(self):
    # if frappe.db.exists('Parent Doc','Prashant'): #True
    # frappe.msgprint('Document is exists in Database')
    # else:
    # frappe.msgprint('Document does not exists in Database')

    ##6. frappe.db.count()
    # frappe.db.count(doctype,filters)
    # def validate(self):
    # 	doc_count=frappe.db.count('Parent Doc',{'enable':0})#True
    # 	frappe.msgprint(("The Enable Document Count is {0}").format(doc_count))

    ##7 frappe.db.get_single_value()
    # sngle doctype me hai
    # frappe.db.get_single_value(doctype, fieldname)
    # def on_update(self):
    # 	self.single_value()

    # def single_value(self):
    # 	doc=frappe.db.get_single_value('single','number')
    # 	frappe.msgprint(("Single value is{0}").format(doc))

    ##8 frappe.db.delete()
    # frappe.db.delete(doctype, filters)
    # def on_update(self):
    #  	self.delete_value()

    # def delete_value(self):
    # 	doc=frappe.db.delete('Parent Doc',{'enable':1})
    # 	frappe.msgprint(("You have succesfully deleted{0}").format(doc))
    pass

    ##9

    # def phone_validate(self):
    # a=self.contact_number
    # length=len(a)
    # if length>11:
    # frappe.throw("Please check the length of your Mobile Number ")
