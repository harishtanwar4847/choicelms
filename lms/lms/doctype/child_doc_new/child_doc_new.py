# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

# import frappe
from frappe.model.document import Document


class ChildDocNew(Document):

    # get_doc
    # def validate(self):
    # 	self.get_document()

    # #get_doc
    # def get_document(self):
    # 	doc=frappe.get_doc('Parent Doc',self.parent_doc_link)#parent_doc_link is field name of DoctypeChild DocNew
    # 	frappe.msgprint(("The Parent Surname is {0}").format(doc.last_name))

    # #get_doc
    # def get_document(self):
    # 	doc=frappe.get_doc('Parent Doc',self.parent_doc_link)#parent_doc_link is field name of DoctypeChild DocNew
    # 	frappe.msgprint(("The Parent Contact Number is {0}").format(doc.contact_number))

    # new_doc
    # def validate(self):
    # self.new_document()

    # new_doc
    # def new_document(self):
    # doc=frappe.new_doc('Parent Doc')
    # doc.first_name='Rajesh'
    # doc.last_name='Vadgama'
    # doc.age=35
    # doc.save()

    # delete_doc
    # frappe.delete_doc(Doctype,Document Name)
    # def validate(self):
    # frappe.delete_doc('Parent Doc','rahul')

    # doc.insert
    # def validate(self):
    # self.new_document()

    # doc.insert
    # def new_document(self):
    # doc=frappe.new_doc('Parent Doc')
    # doc.first_name='Kuntal1'
    # doc.last_name='Sardesai1'
    # doc.age=37
    # doc.insert()

    # doc.save
    # def validate(self):
    # self.save_document()

    # doc.save
    # def save_document(self):
    # doc=frappe.new_doc('Parent Doc')
    # doc.first_name='Suresh'
    # doc.last_name='Rathod'
    # doc.age=50
    # doc.save()

    # doc.delete
    # def validate(self):
    # self.delete_document()
    # doc.delete
    # def delete_document(self):
    # doc=frappe.get_doc('Parent Doc','Suresh')
    # doc.delete()

    # doc.db_set
    # def validate(self):
    # self.db_set_document()

    # def db_set_document(self):
    # doc=frappe.get_doc('Parent Doc','Prashant')
    # doc.db_set('age',40)

    # doc.append()
    # def validate(self):
    # self.append()

    # def append(self):
    # doc=frappe.get_doc('Child Doc New','Tom')
    # doc.append('parent_date_and_value',{
    # "child_table_field": "value",
    # "child_table_int_field": 0,
    # })
    # doc.save(ignore_permissions=True)

    # @frappe.whitelist()
    # def list_all_parent_docs(self,doctype):
    # 	data=frappe.get_all(doctype,fields=["*"])

    # 	for v in data:
    # 		self.append("parent_list",{
    # 			"first_name":v.first_name,
    # 			"age":v.age
    # 		})

    # frappe.db.sql(""" """)

    # def validate(self):
    # 	self.sql()

    # def sql(self):
    # 	data=frappe.db.sql("""
    # 				SELECT first_name,last_name
    # 				FROM `tabParent Doc`
    # 				WHERE enable=1
    # 				""",as_dict=1)
    # 	for v in data:
    # 		frappe.msgprint(("Parent firstname is {0} and lastname is {1} ").format(v.first_name,v.last_name))

    # def sql(self):
    # 	data=frappe.db.sql("""
    # 	SELECT full_name
    # 	FROM `tabParent Doc`
    # 	WHERE enable=1

    # 	""",as_dict=1)

    # 	for v in data:
    #  		frappe.msgprint(("Parent fullname is {0}").format(v.full_name))
    pass

    # def validate(self):
    # frappe.msgprint("Hello frappe from validate event")

    # def before_save(self):
    # frappe.throw("Hello frappe from before_save event")

    # def before_insert(self):
    # frappe.throw("Hello frappe from before_insert event")

    # def after_insert(self):
    # frappe.throw("Hello frappe from after_insert event")

    # def on_update(self):
    # frappe.msgprint("Hello frappe from on_update event")

    # def before_submit(self):
    # frappe.msgprint("Hello frappe from before_submit event")

    # def on_submit(self):
    # frappe.msgprint("Hello frappe from on_submit event")

    # def on_cancel(self):
    # frappe.msgprint("Hello frappe from on_cancel event")

    # def after_delete(self):
    # frappe.msgprint("Hello frappe from after_delete event")
