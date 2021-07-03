import frappe
import utils

import lms


def get_context(context):
    # TODO : get all tags of main blog
    # TODO : apply in query to filter related blogs
    # TODO : ajax method
    # TODO : handle view more html(received through ajax response)
    # TODO : ajax method with search key
    # TODO : manage search html(received through ajax response)

    blog_details = frappe.get_doc("News and Blog", frappe.form_dict.blog_name)
    tags_list = [i.website_tags for i in blog_details.blog_tags]

    # context.related_articles = frappe.db.sql(
    #     "select nb.title, nb.publishing_date, GROUP_CONCAT(bt.website_tags) as website_tags, nb.for_banner_view from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.name <> '{}' AND website_tags in {} group by nb.name".format(frappe.form_dict.blog_name, lms.convert_list_to_tuple_string(tags_list)),
    # as_dict=True, debug=True)

    context.related_articles = frappe.db.sql(
        "select nb.title, nb.publishing_date, GROUP_CONCAT(bt.website_tags) as website_tags, nb.for_banner_view from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.name in (Select nb.name from `tabNews and Blog` nb, `tabBlog Tags` bt where bt.parent=nb.name AND nb.name <> '{}' AND bt.website_tags in {} group by nb.name) group by nb.name order by nb.creation desc limit 3;".format(
            frappe.form_dict.blog_name, lms.convert_list_to_tuple_string(tags_list)
        ),
        as_dict=True,
        debug=True,
    )


@frappe.whitelist(allow_guest=True)
def fetch_related_articles(blog_name, page_no):

    blog_details = frappe.get_doc("News and Blog", frappe.form_dict.blog_name)
    tags_list = [i.website_tags for i in blog_details.blog_tags]

    limit = 3
    offset = (page_no - 1) * limit

    related_articles = frappe.db.sql(
        "select nb.title, nb.publishing_date, GROUP_CONCAT(bt.website_tags) as website_tags, nb.for_banner_view from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.name in (Select nb.name from `tabNews and Blog` nb, `tabBlog Tags` bt where bt.parent=nb.name AND nb.name <> '{}' AND bt.website_tags in {} group by nb.name) group by nb.name order by nb.creation desc limit {}, 3;".format(
            blog_name, lms.convert_list_to_tuple_string(tags_list), offset
        ),
        as_dict=True,
        debug=True,
    )

    response = {"related_articles": related_articles, "page_no": page_no}

    return utils.respondWithSuccess(data=response)
