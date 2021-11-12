from types import new_class
from warnings import filters

import frappe
from frappe.website.utils import cleanup_page_name


def execute():
    frappe.reload_doc("Lms", "DocType", "LAS Settings")
    las_settings = frappe.get_single("LAS Settings")
    news_blog_template = las_settings.get_news_blog_template()
    blogs = frappe.get_all("News and Blog", fields=["*"])
    for blog in blogs:
        new_name = cleanup_page_name(blog.title).replace("_", "-")
        blog_tag_name = frappe.db.get_value("Blog Tags", {"parent": blog.name}, "name")
        frappe.db.set_value(
            "Blog Tags", blog_tag_name, "parent", new_name, update_modified=False
        )
        frappe.db.sql(
            """
        update `tabNews and Blog`
        set name = '{new_name}', route = '{new_name}'
        where name = '{name}'
        """.format(
                new_name=new_name, name=blog.name
            )
        )
        if blog.author:
            author = blog.author.strip()
        else:
            author = blog.author
        blog_details = {
            "title": blog.title,
            "blog_tags": blog.blog_tags,
            "author": author,
            "publishing_date": blog.publishing_date,
            "for_blog_view": blog.for_blog_view,
            "description": blog.description,
        }
        html = frappe.render_template(
            news_blog_template.get_content(), {"blog_details": blog_details}
        )
        web_page = frappe.new_doc("Web Page")
        web_page.title = blog.title
        web_page.route = "news-and-blogs/" + new_name
        web_page.content_type = "HTML"
        web_page.dynamic_template = True
        web_page.main_section_html = html
        web_page.meta_title = blog.title
        web_page.meta_description = blog.short_description
        web_page.meta_image = blog.for_blog_view
        web_page.insert(ignore_permissions=True)
