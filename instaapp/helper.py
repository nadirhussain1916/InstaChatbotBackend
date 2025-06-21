from playwright.sync_api import sync_playwright
from .models import Instagram_User,InstagramPost
import requests
import datetime
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from .models import Instagram_User, InstagramPost
import os 
from urllib.parse import urlparse
from dateutil.parser import parse
ig_user_id = os.getenv('instagram_account_id') 
long_term_access_token = os.getenv('long_term_access_token') 

def check_instagram_credentials(username, password):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)  # Headless = True for no browser UI
            context = browser.new_context()
            page = context.new_page()

            # 1. Go to Instagram login page
            page.goto("https://www.instagram.com/accounts/login/")
            page.wait_for_timeout(3000)

            # 2. Fill login credentials
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)

            # 3. Click login button
            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)
            error_div_selector = 'div.xkmlbd1.xvs91rp.xd4r4e8.x1anpbxc.x11gldyt.xyorhqc.x11hdunq.x2b8uid'

            if page.locator(error_div_selector).is_visible():
                error_text = page.locator(error_div_selector).inner_text()
                if 'incorrect' in error_text.lower():
                    return {"status": "error", "message": "Sorry, your password was incorrect. Please double-check your password."}
                else:
                    return {"status": "error", "message": error_text}
                        # ✅ Launch background thread (doesn't block response)

            # If no error div is visible, assume login success
            return {"status": "success", "message": "Login successful"}
            
    except Exception as e:
        return {"status": "error", "message": f"An error occurred: {str(e)}"}
      
def fetch_user_instagram_profile_data(username_to_discover):


    url = f"https://graph.facebook.com/v23.0/{ig_user_id}"
    params = {
        "fields": f"business_discovery.username({username_to_discover}){{username, name, profile_picture_url, followers_count, follows_count, media_count}}",
        "access_token": long_term_access_token
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        print("Error:", response.status_code, response.text)
        return None        

def save_user_profile(username, full_name, followers, post_count, profile_img):
    user_obj, created = Instagram_User.objects.get_or_create(username=username)
    user_obj.full_name = full_name
    user_obj.followers = followers
    user_obj.posts = post_count

    if profile_img:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        img_response = requests.get(profile_img)
        if img_response.status_code == 200:
            file_name = f"{username}_profile_{timestamp}.jpg"
            user_obj.profile_pic.save(file_name, ContentFile(img_response.content), save=False)

    user_obj.save()

    print(f"\n✅ IG data saved for: {username}")
   
def get_top_instagram_posts(username_to_discover, max_posts=50, top_n=3):

    url = f"https://graph.facebook.com/v23.0/{ig_user_id}"
    fields = (
        f"business_discovery.username({username_to_discover})"
        f"{{media.limit({max_posts})"
        f"{{id,media_type,media_url,like_count,comments_count,timestamp}}}}"
    )

    params = {
        "fields": fields,
        "access_token": long_term_access_token
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        media_data = response.json().get("business_discovery", {}).get("media", {}).get("data", [])
        
        # Sort by like_count descending
        sorted_posts = sorted(media_data, key=lambda x: x.get("like_count", 0), reverse=True)
        
        return sorted_posts[:top_n]
    else:
        print("Error:", response.status_code, response.text)
        return None

def download_and_save_media(url, filename=None):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Use custom filename or fallback to last URL part
            if not filename:
                filename = urlparse(url).path.split("/")[-1].split("?")[0]
            return ContentFile(response.content, name=filename)
    except Exception as e:
        print("Download error:", e)
    return None

def get_and_save_post_detail(username):
    user = get_object_or_404(Instagram_User, username=username)

    # Delete old posts
    InstagramPost.objects.filter(user=user).delete()

    top_posts = get_top_instagram_posts(username)

    for post in top_posts:
        media_type = post.get("media_type", "unknown").lower()
        if media_type == "carousel_album":
            media_type = "carousel"
        elif media_type not in ["image", "video", "reel", "carousel"]:
            media_type = "unknown"

        media_url = post.get("media_url")
        post_id = post.get("id")
        if not media_url or not post_id:
            continue  # Skip if required fields are missing
        # Use .jpg for image posts, otherwise extract the extension from media_url
        if media_type == "image":
            extension = "jpg"
        else:
        # Set filename using post ID and extension from URL
            extension = media_url.split("?")[0].split(".")[-1]  # e.g., jpg, mp4
        filename = f"{post_id}_{media_type}.{extension}"


        media_file = download_and_save_media(media_url, filename)

        instagram_post = InstagramPost.objects.create(
            user=user,
            post_url=f"https://www.instagram.com/p/{post_id}/",
            media_url=media_url,
            post_type=media_type,
            likes=post.get("like_count"),
            comments=post.get("comments_count"),
            timestamp=parse(post.get("timestamp")) if post.get("timestamp") else None,
            shortcode=post_id,
        )

        if media_file:
            instagram_post.thumbnail_url.save(media_file.name, media_file)

