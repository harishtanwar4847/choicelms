from warnings import filters

import frappe
from frappe.website.utils import cleanup_page_name


def execute():
    las_settings = frappe.get_single("LAS Settings")
    news_blog_template = las_settings.get_news_blog_template()
    # blogs = frappe.get_all("News and Blog", filters=["*"])
    # for blog in blogs:
    #     frappe.db.sql("""
    #     update `tabNews and Blog`
    #     set name = '{name}'
    #     where name = '{name}'
    #     """.format(name = cleanup_page_name(blog.title).replace("_", "-")))
    #     # blog.name = cleanup_page_name(blog.title).replace("_", "-")
    #     # blog.save()
    #     frappe.db.commit()
    # blog_details = {
    #     "title": blog.title,
    #     "blog_tags": blog.blog_tags,
    #     "author": blog.author,
    #     "publishing_date": blog.publishing_date,
    #     "for_blog_view": blog.for_blog_view,
    #     "description": blog.description,
    # }
    # html = frappe.render_template(
    #     news_blog_template.get_content(), {"blog_details": blog_details}
    # )
    # web_page = frappe.new_doc("Web Page")
    # web_page.title = blog.title
    # web_page.route = "news-and-blogs/" + blog.route
    # web_page.content_type = "HTML"
    # web_page.dynamic_template = True
    # web_page.main_section_html = html
    # web_page.meta_title = blog.meta_title
    # web_page.meta_description = blog.meta_description
    # web_page.meta_image = blog.meta_image
    # web_page.insert(ignore_permissions=True)
