import requests
from requests_oauthlib import OAuth1

# --- Step 1: Upload Media (OAuth 1.0a) ---
auth = OAuth1(
    client_key="YwZJcFvIdwRHaOd1Jpka1dWCK",
    client_secret="Dfa1Kef0qtQI6KqMB3BElbffk7ydVJVtZSgWWMyIcAShiZ6Ozp",
    resource_owner_key="1968206686297976832-zDUZnoKhVThyHrTiKWOpoBPu2G1yVR",
    resource_owner_secret="JNKZeWnfBMNKoI46GC6wD0ErSjHOCRtAdk3icsvwULfPw"
)

image_url = "https://aicrm.finbyz.tech/files/Generated%20Image%20September%2009,%202025%20-%2012_03PM.png"
image_data = requests.get(image_url).content

upload_url = "https://upload.twitter.com/1.1/media/upload.json"
files = {"media": image_data}
data = {"media_category": "tweet_image"}

upload_response = requests.post(upload_url, auth=auth, files=files, data=data)

print("Media Upload Status:", upload_response.status_code)
print("Media Upload Response:", upload_response.json())

if upload_response.status_code != 200:
    raise Exception("Media upload failed")

media_id = upload_response.json().get("media_id_string")
frappe.logger().info(f"Uploaded Media ID: {media_id}")


# --- Step 2: Post Tweet (OAuth 2.0 Bearer Token) ---
tweet_url = "https://api.x.com/2/tweets"

payload = {
    "for_super_followers_only": False,
    "nullcast": False,
    "share_with_followers": False,
    "text": "Hello all!",
    "media": {"media_ids": [media_id]}
}

headers = {
    "Authorization": "Bearer QVJTM254WDJoWUN0c1V0T2MzaUptOU1jUlRBMHlkeWpyTkZoQy16NG1pSGx4OjE3NTgwODgyMzQ4MDg6MToxOmF0OjE",
    "Content-Type": "application/json"
}

tweet_response = requests.post(tweet_url, json=payload, headers=headers)

print("Tweet Post Status:", tweet_response.status_code)
print("Tweet Post Response:", tweet_response.json())
