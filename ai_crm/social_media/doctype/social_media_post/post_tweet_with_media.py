import requests
from requests_oauthlib import OAuth1

def upload_image_on_twitter():
    auth = OAuth1(
        client_key="YwZJcFvIdwRHaOd1Jpka1dWCK",
        client_secret="Dfa1Kef0qtQI6KqMB3BElbffk7ydVJVtZSgWWMyIcAShiZ6Ozp",
        resource_owner_key="1968206686297976832-zDUZnoKhVThyHrTiKWOpoBPu2G1yVR",
        resource_owner_secret="JNKZeWnfBMNKoI46GC6wD0ErSjHOCRtAdk3icsvwULfPw"
    )

    # Download image from URL
    image_url = "https://aicrm.finbyz.tech/files/Generated%20Image%20September%2009,%202025%20-%2012_03PM.png"
    image_data = requests.get(image_url).content

    # Upload to Twitter
    url = "https://upload.twitter.com/1.1/media/upload.json"
    files = {"media": image_data}  # binary data
    data = {"media_category": "tweet_image"}

    response = requests.post(url, auth=auth, files=files, data=data)
    print(response.status_code)
    try:
        print(response.json())
    except Exception:
        print(response.text)

# Run the function
upload_image_on_twitter()
