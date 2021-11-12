# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.model.document import Document
from frappe.website.utils import cleanup_page_name

import lms


class NewsandBlog(Document):
    def before_save(self):
        if not self.publishing_date:
            self.publishing_date = frappe.utils.today()
        self.route = self.name

    def autoname(self):
        self.name = cleanup_page_name(self.title).replace("_", "-")

    def create_blog_entry(self, blog_name=None):
        las_settings = frappe.get_single("LAS Settings")
        news_blog_template = las_settings.get_news_blog_template()
        if self.author:
            author = self.author.strip()
        else:
            author = self.author
        blog_details = {
            "title": self.title,
            "blog_tags": self.blog_tags,
            "author": author,
            "publishing_date": self.publishing_date,
            "for_blog_view": self.for_blog_view,
            "description": self.description,
        }
        html = frappe.render_template(
            news_blog_template.get_content(), {"blog_details": blog_details}
        )
        if blog_name:
            web_page = frappe.get_doc("Web Page", blog_name)
        else:
            web_page = frappe.new_doc("Web Page")
        web_page.title = self.title
        web_page.route = "news-and-blogs/" + self.route
        web_page.content_type = "HTML"
        web_page.dynamic_template = True
        web_page.main_section_html = html
        web_page.meta_title = self.meta_title
        web_page.meta_description = self.meta_description
        web_page.meta_image = self.meta_image
        if blog_name:
            web_page.save(ignore_permissions=True)
            frappe.db.commit()
        else:
            web_page.insert(ignore_permissions=True)

    def after_insert(self):
        self.create_blog_entry()

    def on_update(self):
        if frappe.db.exists("Web Page", self.name):
            self.create_blog_entry(self.name)
        else:
            self.create_blog_entry()

    def on_trash(self):
        web_page = frappe.get_doc("Web Page", self.name)
        web_page.published = False
        web_page.save(ignore_permissions=True)
        frappe.db.commit()
