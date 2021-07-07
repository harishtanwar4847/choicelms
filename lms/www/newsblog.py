from datetime import datetime
from re import DEBUG

import frappe
import utils

import lms


def get_context(context):
    context.blog_details = frappe.get_doc(
        "News and Blog", frappe.form_dict.blog_name
    ).as_dict()
    context.blog_details.publishing_date = (
        context.blog_details.publishing_date
    ).strftime("%d %B, %Y")
    tags_list = [i.website_tags for i in context.blog_details.blog_tags]

    # context.related_articles = frappe.db.sql(
    #     "select nb.title, nb.publishing_date, GROUP_CONCAT(bt.website_tags) as website_tags, nb.for_banner_view from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.name <> '{}' AND website_tags in {} group by nb.name".format(frappe.form_dict.blog_name, lms.convert_list_to_tuple_string(tags_list)),
    # as_dict=True, debug=True)
    context.related_articles = frappe.db.sql(
        "select nb.title, DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date, GROUP_CONCAT(bt.website_tags) as website_tags, nb.for_banner_view from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.name in (Select nb.name from `tabNews and Blog` nb, `tabBlog Tags` bt where bt.parent=nb.name AND nb.name <> '{}' AND bt.website_tags in {} group by nb.name) group by nb.name order by nb.creation desc limit 3;".format(
            frappe.form_dict.blog_name, lms.convert_list_to_tuple_string(tags_list)
        ),
        {"format": "%d %M, %Y"},
        debug=True,
        as_dict=True,
    )
    # context.page_change = ""
    context.page_change = frappe.db.sql(
        "SELECT name, (SELECT name FROM `tabNews and Blog` nb1 WHERE nb1.creation < nb.creation ORDER BY creation DESC LIMIT 1) as previous_name, (SELECT name FROM `tabNews and Blog` nb2 WHERE nb2.creation > nb.creation ORDER BY creation ASC LIMIT 1) as next_name FROM `tabNews and Blog` nb WHERE name = '{}'".format(
            frappe.form_dict.blog_name
        ),
        as_dict=True,
    )[0]
    # print(context.page_change)


@frappe.whitelist(allow_guest=True)
def fetch_related_articles(blog_name, page_no):

    blog_details = frappe.get_doc("News and Blog", frappe.form_dict.blog_name)
    tags_list = [i.website_tags for i in blog_details.blog_tags]

    limit = 3
    offset = (int(page_no) - 1) * limit

    related_articles = frappe.db.sql(
        "select nb.name, nb.title, DATE_FORMAT(nb.publishing_date, %(format)s) as publishing_date, GROUP_CONCAT(bt.website_tags) as website_tags, nb.for_banner_view from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.name in (Select nb.name from `tabNews and Blog` nb, `tabBlog Tags` bt where bt.parent=nb.name AND nb.name <> '{}' AND bt.website_tags in {} group by nb.name) group by nb.name order by nb.creation desc limit {}, 3;".format(
            blog_name, lms.convert_list_to_tuple_string(tags_list), offset
        ),
        {"format": "%d %M, %Y"},
        as_dict=True,
    )
    # print(related_articles)

    response = {"related_articles": related_articles, "page_no": page_no}

    return utils.respondWithSuccess(data=response)
