import frappe
import utils

import lms


@frappe.whitelist(allow_guest=True)
def get_videos_list(page_no, latest_video="", search_key=""):
    print("latest_video : ", latest_video)
    if latest_video == "true":
        limit = 3
    else:
        limit = 6
    offset = (int(page_no) - 1) * limit

    if len(search_key.strip()) > 0:
        videos_list = frappe.db.sql(
            "select video_title,youtube_id,video_description from `tabYoutube Id` where video_title LIKE '%{}%' or video_description LIKE '%{}%' order by modified desc limit {},{}".format(
                search_key, search_key, offset, limit
            ),
            as_dict=True,
        )
    else:
        videos_list = frappe.db.sql(
            "select video_title,youtube_id,video_description from `tabYoutube Id` order by modified desc limit {},{}".format(
                offset, limit
            ),
            as_dict=True,
        )

    response = {"videos_list_response": videos_list, "page_no": page_no}

    return utils.respondWithSuccess(data=response)
