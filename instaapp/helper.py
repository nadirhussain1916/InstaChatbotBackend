from playwright.sync_api import sync_playwright
from .models import Instagram_User, InstagramPost
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from urllib.parse import urlparse
from dateutil.parser import parse
import os
import logging
import requests
import datetime
from django.db import connection
import instaloader
from instaapp.header import header_set
import time, random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

ig_user_id = os.getenv('instagram_account_id')
long_term_access_token = os.getenv('long_term_access_token')

# Debug logging for environment variables
logger.info(f"[Environment Check] ig_user_id: {'SET' if ig_user_id else 'NOT SET'}")
logger.info(f"[Environment Check] long_term_access_token: {'SET' if long_term_access_token else 'NOT SET'}")

def check_instagram_credentials(username, password):
    """Check Instagram credentials using Playwright."""
    logger.info(f"[check_instagram_credentials] Checking credentials for username: {username}")
    try:
        connection.ensure_connection()
        logger.info("[check_instagram_credentials] Database connection OK.")
    except Exception as db_exc:
        logger.error(f"[check_instagram_credentials] Database connection error: {db_exc}")
        return {"status": "error", "message": "Database connection error."}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.instagram.com/accounts/login/")
            page.wait_for_timeout(3000)
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_timeout(5000)
            error_div_selector = 'div.xkmlbd1.xvs91rp.xd4r4e8.x1anpbxc.x11gldyt.xyorhqc.x11hdunq.x2b8uid'
            if page.locator(error_div_selector).is_visible():
                logger.warning(f"[check_instagram_credentials] Login failed for {username}.")
                return {"status": "error", "message": "Login failed"}
            logger.info(f"[check_instagram_credentials] Login successful for {username}.")
            return {"status": "success", "message": "Login successful"}
    except Exception as e:
        logger.error(f"[check_instagram_credentials] Exception: {str(e)}")
        return {"status": "error", "message": f"An error occurred: {str(e)}"}

def fetch_user_instagram_profile_data(username_to_discover):
    """Fetch Instagram user profile data from Facebook Graph API."""
    logger.info(f"[fetch_user_instagram_profile_data] Fetching profile for: {username_to_discover}")
    
    # Check if required environment variables are set
    if not ig_user_id:
        logger.error("[fetch_user_instagram_profile_data] instagram_account_id environment variable not set")
        return None
    
    if not long_term_access_token:
        logger.error("[fetch_user_instagram_profile_data] long_term_access_token environment variable not set")
        return None
    
    try:
        connection.ensure_connection()
        logger.info("[fetch_user_instagram_profile_data] Database connection OK.")
    except Exception as db_exc:
        logger.error(f"[fetch_user_instagram_profile_data] Database connection error: {db_exc}")
        return None
    
    url = f"https://graph.facebook.com/v23.0/{ig_user_id}"
    params = {
        "fields": f"business_discovery.username({username_to_discover}){{username, name, profile_picture_url, followers_count, follows_count, media_count}}",
        "access_token": long_term_access_token
    }
    logger.info(f"[fetch_user_instagram_profile_data] Request params: {params}")
    response = requests.get(url, params=params)
    logger.info(f"[fetch_user_instagram_profile_data] Response status: {response.status_code}, body: {response.text}")
    if response.status_code == 200:
        logger.info(f"[fetch_user_instagram_profile_data] Success for: {username_to_discover}")
        return response.json()
    else:
        logger.error(f"[fetch_user_instagram_profile_data] Error: {response.status_code}, {response.text}")
        return None        

def save_user_profile(username, full_name, followers, post_count, profile_img):
    """Save Instagram user profile data."""
    logger.info(f"[save_user_profile] Saving profile for: {username}")
    try:
        connection.ensure_connection()
        logger.info("[save_user_profile] Database connection OK.")
    except Exception as db_exc:
        logger.error(f"[save_user_profile] Database connection error: {db_exc}")
        return
    user_obj, created = Instagram_User.objects.get_or_create(username=username)
    user_obj.full_name = full_name
    user_obj.followers = followers
    user_obj.posts = post_count
    user_obj.media_url = profile_img
    if profile_img:
        logger.debug(f"[save_user_profile] Downloading profile image for: {username}")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        img_response = requests.get(profile_img)
        if img_response.status_code == 200:
            file_name = f"{username}_profile_{timestamp}.jpg"
            user_obj.profile_pic.save(file_name, ContentFile(img_response.content), save=False)
    user_obj.save()
    logger.info(f"[save_user_profile] IG data saved for: {username}")
   
def get_top_instagram_posts(username_to_discover, max_posts=50, top_n=3):
    """Fetch top Instagram posts for a user."""
    logger.info(f"[get_top_instagram_posts] Fetching top posts for: {username_to_discover}")
    try:
        connection.ensure_connection()
        logger.info("[get_top_instagram_posts] Database connection OK.")
    except Exception as db_exc:
        logger.error(f"[get_top_instagram_posts] Database connection error: {db_exc}")
        return None
    url = f"https://graph.facebook.com/v23.0/{ig_user_id}"
    fields = (
        f"business_discovery.username({username_to_discover})"
        f"{{media.limit({max_posts})"
        f"{{id,permalink,media_type,media_url,like_count,comments_count,timestamp}}}}"
    )
    params = {
        "fields": fields,
        "access_token": long_term_access_token
    }
    logger.info(f"[get_top_instagram_posts] Request params: {params}")
    response = requests.get(url, params=params,timeout=10)
    logger.info(f"[get_top_instagram_posts] Response status: {response.status_code}, body: {response.text}")
    if response.status_code == 200:
        logger.info(f"[get_top_instagram_posts] Success for: {username_to_discover}")
        media_data = response.json().get("business_discovery", {}).get("media", {}).get("data", [])
        sorted_posts = sorted(media_data, key=lambda x: x.get("like_count", 0), reverse=True)
        return sorted_posts[:top_n]
    else:
        logger.error(f"[get_top_instagram_posts] Error: {response.status_code}, {response.text}")
        return None

def download_and_save_media(url, filename=None):
    """Download and save media from a URL."""
    logger.info(f"[download_and_save_media] Downloading media from: {url}")
    try:
        response = requests.get(url)
        logger.info(f"[download_and_save_media] Response status: {response.status_code}")
        if response.status_code == 200:
            logger.info(f"[download_and_save_media] Downloaded successfully: {url}")
            if not filename:
                filename = urlparse(url).path.split("/")[-1].split("?")[0]
            return ContentFile(response.content, name=filename)
    except Exception as e:
        logger.error(f"[download_and_save_media] Download error: {e}")
    return None

def get_and_save_post_detail(username):
    """Get and save post details for a user."""
    logger.info(f"[get_and_save_post_detail] Getting and saving post details for: {username}")
    try:
        connection.ensure_connection()
        logger.info("[get_and_save_post_detail] Database connection OK.")
    except Exception as db_exc:
        logger.error(f"[get_and_save_post_detail] Database connection error: {db_exc}")
        return
    user = get_object_or_404(Instagram_User, username=username)
    InstagramPost.objects.filter(user=user).delete()
    top_posts = get_top_instagram_posts(username)
    logger.info(f"[get_and_save_post_detail] Top posts: {top_posts}")
    for post in top_posts or []:
        logger.debug(f"[get_and_save_post_detail] Processing post: {post}")
        media_type = post.get("media_type", "unknown").lower()
        if media_type == "carousel_album":
            media_type = "carousel"
        elif media_type not in ["image", "video", "reel", "carousel"]:
            media_type = "unknown"
        media_url = post.get("media_url")
        post_id = post.get("id")
        post_url = post.get("permalink")
        if not media_url or not post_id:
            continue
        if media_type == "image":
            extension = "jpg"
        else:
            extension = media_url.split("?")[0].split(".")[-1]
        filename = f"{post_id}_{media_type}.{extension}"
        media_file = download_and_save_media(media_url, filename)
        instagram_post = InstagramPost.objects.create(
            user=user,
            post_url=post_url,
            media_url=media_url,
            post_type=media_type,
            likes=post.get("like_count"),
            comments=post.get("comments_count"),
            timestamp=parse(post.get("timestamp")) if post.get("timestamp") else None,
            shortcode=post_id,
        )
        if media_file:
            logger.info(f"[get_and_save_post_detail] Media file saved for post: {post_id}")
            instagram_post.thumbnail_url.save(media_file.name, media_file)


def get_random_headers():
    return random.choice(header_set)

def create_context(browser):
    headers = get_random_headers()
    return browser.new_context(extra_http_headers=headers)

def get_post_playwright(username):
    retries = 2
    attempt = 0
    while attempt <= retries:
        try:
            with sync_playwright() as p:
                browser = p.firefox.launch(headless=True)
                context = create_context(browser)
                page = context.new_page()
                print(f"Opening Instagram profile: {username} (Attempt {attempt+1})")
                page.goto(f"https://www.instagram.com/{username}/", timeout=20000)
                page.wait_for_selector("article a", timeout=10000)

                post_links = page.locator("article a").all()
                if not post_links:
                    print("No posts found.")
                    return []

                results = []
                for link in post_links[:3]:
                    href = link.get_attribute("href")
                    if not href:
                        continue

                    post_url = f"https://www.instagram.com{href}"
                    post_page = context.new_page()
                    post_page.goto(post_url, timeout=10000)
                    post_page.wait_for_selector("article", timeout=10000)

                    # Media URL & Post Type
                    media_url = None
                    post_type = "Image"
                    video = post_page.query_selector("video")
                    if video:
                        media_url = video.get_attribute("src")
                        post_type = "Video"
                    else:
                        img = post_page.query_selector("article img")
                        media_url = img.get_attribute("src") if img else None

                    # Likes
                    likes = None
                    likes_el = post_page.query_selector("section span span")
                    if likes_el:
                        try:
                            likes = int(likes_el.inner_text().replace(",", ""))
                        except:
                            pass

                    # Comments count
                    comments = len(post_page.query_selector_all("ul > ul"))

                    # Timestamp
                    timestamp_el = post_page.query_selector("time")
                    timestamp = timestamp_el.get_attribute("datetime") if timestamp_el else None
                    if timestamp:
                        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                    # Append result
                    results.append({
                        "media_url": media_url,
                        "post_type": post_type,
                        "likes": likes,
                        "comments": comments,
                        "timestamp": timestamp
                    })

                    post_page.close()

                browser.close()
                return results

        except PlaywrightTimeoutError as e:
            print(f"[TimeoutError] Retrying in 10 seconds... ({attempt+1}/{retries})")
            time.sleep(10)
            attempt += 1
        except Exception as e:
            print(f"[Error] {str(e)} — Retrying in 10 seconds... ({attempt+1}/{retries})")
            time.sleep(10)
            attempt += 1

    print("Failed after multiple attempts.")
    return []


def get_and_save_post_detail_byplaywright(username):
    try:
        data = get_post_playwright(username)
    except Exception as e:
        print(f"Failed to fetch posts for {username}: {e}")
        return
    user = get_object_or_404(Instagram_User, username=username)
    InstagramPost.objects.filter(user=user).delete()

    for post in data:
        try:
            media_url = post.get("media_url")
            media_type = post.get("post_type")
            likes = post.get("likes")
            comments = post.get("comments")
            timestamp = parse(post.get("timestamp")) if post.get("timestamp") else None
            post_id = post.get("shortcode")
            post_url = f"https://www.instagram.com/p/{post_id}/" if post_id else None

            if all([media_url, post_id]):  # Basic validation
                InstagramPost.objects.create(
                    user=user,
                    post_url=post_url,
                    media_url=media_url,
                    post_type=media_type,
                    likes=likes,
                    comments=comments,
                    timestamp=timestamp,
                    shortcode=post_id,
                )
            else:
                print("Skipping post due to missing media_url or shortcode.")

        except Exception as e:
            print(f"Error saving post: {e}")
            continue


def fetch_user_instagram_profile_data_byInstaloader(username):
    L = instaloader.Instaloader()
    
    try:
        profile = instaloader.Profile.from_username(L.context, username)

        return {
            "name": profile.full_name,
            "followers": profile.followers,
            "media_count": profile.mediacount,
            "profile_picture_url": profile.profile_pic_url
        }

    except Exception as e:
        # Return None on any error (user not found, rate limit, private profile, etc.)
        return None
