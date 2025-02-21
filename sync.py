import os
import re
import requests
from notion_client import Client
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================
# CẤU HÌNH API TOKENS (lấy từ biến môi trường)
# ==========================
CANVAS_API_URL = os.getenv("CANVAS_API_URL", "https://portal.uet.vnu.edu.vn/api/v1") #Thay đổi dựa trên Canvas của trường bạn
CANVAS_API_TOKEN = os.getenv("CANVAS_API_TOKEN")
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN")

# ID của các database trong Notion
NOTION_DATABASE_ID_COURSES = os.getenv("NOTION_DATABASE_ID_COURSES")
NOTION_DATABASE_ID_ASSIGNMENTS = os.getenv("NOTION_DATABASE_ID_ASSIGNMENTS")
NOTION_DATABASE_ID_FILES = os.getenv("NOTION_DATABASE_ID_FILES")
NOTION_DATABASE_ID_ANNOUNCEMENTS = os.getenv("NOTION_DATABASE_ID_ANNOUNCEMENTS")

# ==========================
# CẤU HÌNH TELEGRAM BOT (lấy từ biến môi trường)
# ==========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================
# KẾT NỐI API
# ==========================
headers_canvas = {"Authorization": f"Bearer {CANVAS_API_TOKEN}"}
notion = Client(auth=NOTION_API_TOKEN)

# ==========================
# HÀM ESCAPE MARKDOWN V2 (nếu dùng Markdown; ở đây không dùng parse_mode nên có thể bỏ qua escape)
# ==========================
def escape_markdown(text):
    escape_chars = r'_*\[\]()~`>#+\-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

# ==========================
# HÀM LÀM SẠCH HTML (dùng BeautifulSoup)
# ==========================
def clean_html(html_text):
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        return soup.get_text(separator="\n").strip()
    except Exception as e:
        print("Lỗi khi làm sạch HTML:", e)
        return html_text

# ==========================
# HÀM CHUYỂN ĐỊNH DẠNG THỜI GIAN (tuỳ chọn)
# ==========================
def format_datetime(iso_str):
    try:
        dt = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%b %d, %Y, %I:%M %p")
    except Exception as e:
        print("Lỗi định dạng thời gian:", e)
        return iso_str

# ==========================
# HÀM GỬI THÔNG BÁO TELEGRAM (dạng văn bản thuần)
# ==========================
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
        # Không sử dụng parse_mode để gửi tin nhắn thuần
    }
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            print("Telegram: Đã gửi thông báo thành công!")
        else:
            print("Telegram: Gửi thông báo thất bại:", response.text)
    except Exception as e:
        print("Telegram: Lỗi gửi thông báo:", e)

# ==========================
# HÀM KIỂM TRA TRÙNG LẶP (cho tất cả các database)
# ==========================
def get_existing_page(database_id, property_name, value):
    query = {
        "filter": {
            "property": property_name,
            "rich_text": {
                "equals": str(value)
            }
        }
    }
    try:
        response = notion.databases.query(database_id=database_id, **query)
        results = response.get("results", [])
        if results:
            return results[0]["id"]
        return None
    except Exception as e:
        print(f"Lỗi khi truy vấn property '{property_name}': {e}")
        return None

# ==========================
# KHÓA HỌC (Courses)
# ==========================
def get_all_canvas_courses():
    courses = []
    url = f"{CANVAS_API_URL}/courses?per_page=100&enrollment_state=active&include[]=concluded"
    while url:
        response = requests.get(url, headers=headers_canvas)
        if response.status_code != 200:
            print("Lỗi khi lấy khóa học:", response.status_code, response.text)
            break
        data = response.json()
        courses.extend(data)
        link_header = response.headers.get("Link")
        next_url = None
        if link_header:
            links = link_header.split(",")
            for link in links:
                if 'rel="next"' in link:
                    start = link.find("<") + 1
                    end = link.find(">")
                    next_url = link[start:end]
                    break
        url = next_url
    return courses

def save_course_to_notion(course):
    course_id = course.get('id')
    existing_page = get_existing_page(NOTION_DATABASE_ID_COURSES, "Course ID", course_id)
    if existing_page:
        print(f"Khóa học '{course.get('name')}' (ID: {course_id}) đã tồn tại, bỏ qua tạo mới.")
        return None
    # Xây dựng URL của khóa học dựa vào ID
    course_url = f"https://portal.uet.vnu.edu.vn/courses/{course_id}"
    properties = {
        "Name": {"title": [{"text": {"content": course.get('name', 'No Name')}}]},
        "Course ID": {"rich_text": [{"text": {"content": str(course_id)}}]},
        "URL": {"url": course_url}
    }
    try:
        result = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID_COURSES},
            properties=properties
        )
        print(f"Khóa học '{course.get('name')}' đã được tạo mới.")
        send_telegram_message(f"Khóa học mới: {course.get('name')} (ID: {course_id})\nLink: {course_url}")
        return result
    except Exception as e:
        print("Lỗi lưu khóa học:", e)
        return None

# ==========================
# BÀI TẬP (Assignments)
# ==========================
def get_canvas_assignments(course_id):
    url = f"{CANVAS_API_URL}/courses/{course_id}/assignments"
    response = requests.get(url, headers=headers_canvas)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Lỗi khi lấy bài tập của khóa học {course_id}:", response.status_code, response.text)
        return []

def save_assignment_to_notion(assignment, course_name):
    assignment_id = assignment.get("id")
    existing_page = get_existing_page(NOTION_DATABASE_ID_ASSIGNMENTS, "Assignment ID", assignment_id)
    if existing_page:
        print(f"Bài tập '{assignment.get('name')}' (ID: {assignment_id}) đã tồn tại, bỏ qua.")
        return None
    due_date = assignment.get("due_at")
    unlock_date = assignment.get("unlock_at")
    lock_date = assignment.get("lock_at")
    properties = {
        "Assignment Name": {"title": [{"text": {"content": assignment.get('name', 'No Name')}}]},
        "Assignment ID": {"rich_text": [{"text": {"content": str(assignment_id)}}]},
        "Course": {"rich_text": [{"text": {"content": course_name}}]},
        "Points": {"number": assignment.get("points_possible", 0)},
        "URL": {"url": assignment.get("html_url", "")}
    }
    if due_date:
        properties["Due Date"] = {"date": {"start": due_date}}
    if unlock_date:
        properties["Available From"] = {"date": {"start": unlock_date}}
    if lock_date:
        properties["Available To"] = {"date": {"start": lock_date}}
    try:
        result = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID_ASSIGNMENTS},
            properties=properties
        )
        print(f"Bài tập '{assignment.get('name')}' đã được thêm vào Notion.")
        msg = f"Bài tập mới\nTên: {assignment.get('name', 'No Name')}\nCourse: {course_name}\nLink: {assignment.get('html_url', '')}"
        if due_date:
            msg += f"\nDue: {format_datetime(due_date)}"
        if unlock_date:
            msg += f"\nAvailable From: {format_datetime(unlock_date)}"
        if lock_date:
            msg += f"\nAvailable To: {format_datetime(lock_date)}"
        send_telegram_message(msg)
        return result
    except Exception as e:
        print("Lỗi lưu bài tập vào Notion:", e)
        return None

# ==========================
# TỆP TIN (Files)
# ==========================
def get_canvas_files(course_id):
    url = f"{CANVAS_API_URL}/courses/{course_id}/files"
    response = requests.get(url, headers=headers_canvas)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Lỗi khi lấy file của khóa học {course_id}:", response.status_code, response.text)
        return []

def save_file_to_notion(file, course_name):
    file_id = file.get("id")
    existing_page = get_existing_page(NOTION_DATABASE_ID_FILES, "File ID", file_id)
    if existing_page:
        print(f"File '{file.get('display_name')}' (ID: {file_id}) của khóa học '{course_name}' đã tồn tại, bỏ qua.")
        return None
    download_link = file.get("url", "")
    properties = {
        "File Name": {"title": [{"text": {"content": file.get('display_name', 'No Name')}}]},
        "File ID": {"rich_text": [{"text": {"content": str(file_id)}}]},
        "Course": {"rich_text": [{"text": {"content": course_name}}]},
        "File Type": {"rich_text": [{"text": {"content": file.get('content-type', '')}}]}
    }
    if download_link:
        properties["Download Link"] = {"url": download_link}
    try:
        result = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID_FILES},
            properties=properties
        )
        print(f"File '{file.get('display_name')}' của khóa học '{course_name}' đã được tạo mới.")
        send_telegram_message(f"File mới\nTên: {file.get('display_name', 'No Name')}\nCourse: {course_name}\nLink: {download_link}")
        return result
    except Exception as e:
        print("Lỗi lưu file:", e)
        return None

# ==========================
# THÔNG BÁO (Announcements)
# ==========================
def get_canvas_announcements(course_id):
    url_announcements = f"{CANVAS_API_URL}/courses/{course_id}/announcements"
    response = requests.get(url_announcements, headers=headers_canvas)
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        print(f"Endpoint /announcements không khả dụng cho khóa học {course_id}. Thử /discussion_topics.")
        url_discussions = f"{CANVAS_API_URL}/courses/{course_id}/discussion_topics?only_announcements=true"
        response = requests.get(url_discussions, headers=headers_canvas)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Lỗi khi lấy thông báo (discussion_topics) của khóa học {course_id}: {response.status_code}, {response.text}")
            return []
    else:
        print(f"Lỗi khi lấy thông báo của khóa học {course_id}: {response.status_code}, {response.text}")
        return []

def save_announcement_to_notion(announcement, course_name):
    announcement_id = announcement.get("id")
    existing_page = get_existing_page(NOTION_DATABASE_ID_ANNOUNCEMENTS, "Announcement ID", announcement_id)
    if existing_page:
        print(f"Thông báo '{announcement.get('title')}' (ID: {announcement_id}) của khóa học '{course_name}' đã tồn tại, bỏ qua.")
        return None
    posted_at = announcement.get("posted_at")
    full_content = announcement.get("message", "")
    clean_content = clean_html(full_content)
    properties = {
        "Title": {"title": [{"text": {"content": announcement.get('title', 'No Title')}}]},
        "Announcement ID": {"rich_text": [{"text": {"content": str(announcement_id)}}]},
        "Course": {"rich_text": [{"text": {"content": course_name}}]},
        "URL": {"url": announcement.get("html_url", "")},
        "Content": {"rich_text": [{"text": {"content": clean_content}}]}
    }
    if posted_at:
        properties["Posted At"] = {"date": {"start": posted_at}}
    try:
        result = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID_ANNOUNCEMENTS},
            properties=properties
        )
        print(f"Thông báo '{announcement.get('title')}' của khóa học '{course_name}' đã được tạo mới.")
        announcement_link = announcement.get("html_url", "")
        msg = (
            "Thông báo mới từ Canvas:\n"
            f"Title: {announcement.get('title', 'No Title')}\n"
            f"Course: {course_name}\n"
            f"Content: {clean_content}\n"
            f"Link: {announcement_link}"
        )
        send_telegram_message(msg)
        return result
    except Exception as e:
        print("Lỗi lưu thông báo:", e)
        return None

# ==========================
# CHẠY SCRIPT - ĐỒNG BỘ TẤT CẢ NỘI DUNG
# ==========================
def main():
    courses = get_all_canvas_courses()
    if not courses:
        print("Không có khóa học nào được lấy từ Canvas.")
        return
    print(f"Tổng số khóa học: {len(courses)}")
    for course in courses:
        course_name = course.get('name', 'No Name')
        course_id = course.get('id')
        print(f"\nĐồng bộ khóa học: {course_name} (ID: {course_id})")
        save_course_to_notion(course)
        print(f"Đang lấy bài tập từ {course_name}...")
        assignments = get_canvas_assignments(course_id)
        for assignment in assignments:
            save_assignment_to_notion(assignment, course_name)
        print(f"Đang lấy file từ {course_name}...")
        files = get_canvas_files(course_id)
        for file in files:
            save_file_to_notion(file, course_name)
        print(f"Đang lấy thông báo từ {course_name}...")
        announcements = get_canvas_announcements(course_id)
        for announcement in announcements:
            save_announcement_to_notion(announcement, course_name)
    print("\nHoàn tất đồng bộ toàn bộ nội dung từ Canvas vào Notion!")

if __name__ == "__main__":
    main()
