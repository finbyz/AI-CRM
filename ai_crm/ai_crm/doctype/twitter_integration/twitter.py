import os
import requests
import json
import mimetypes
from typing import List, Dict, Optional, Union
from requests_oauthlib import OAuth1Session
import base64
import time

class TwitterMediaPoster:
    """
    A Python class to handle Twitter media upload and posting functionality.
    Based on the n8n Twitter node implementation.
    """
    
    def __init__(self, consumer_key: str, consumer_secret: str, 
                 access_token: str, access_token_secret: str):
        """
        Initialize the Twitter API client with OAuth 1.0a credentials.
        
        Args:
            consumer_key: Twitter API consumer key
            consumer_secret: Twitter API consumer secret  
            access_token: User access token
            access_token_secret: User access token secret
        """
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        
        # Create OAuth1Session for API v1.1 (media upload)
        self.oauth_v1 = OAuth1Session(
            consumer_key,
            client_secret=consumer_secret,
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret
        )
        
        # API endpoints
        self.media_upload_url = "https://upload.twitter.com/1.1/media/upload.json"
        self.tweet_create_url = "https://api.twitter.com/2/tweets"
        
    def upload_media(self, media_path: str, media_category: str = "tweet_image") -> Optional[str]:
        """
        Upload media to Twitter and return media ID.
        
        Args:
            media_path: Path to the media file
            media_category: Category of media (tweet_image, tweet_video, tweet_gif)
            
        Returns:
            Media ID string if successful, None if failed
        """
        if not os.path.exists(media_path):
            raise FileNotFoundError(f"Media file not found: {media_path}")
            
        # Get file info
        file_size = os.path.getsize(media_path)
        mime_type, _ = mimetypes.guess_type(media_path)
        
        if not mime_type:
            raise ValueError("Could not determine media type")
            
        # For large files (>5MB), use chunked upload
        if file_size > 5 * 1024 * 1024:  # 5MB
            return self._upload_media_chunked(media_path, media_category)
        else:
            return self._upload_media_simple(media_path, media_category)
    
    def _upload_media_simple(self, media_path: str, media_category: str) -> Optional[str]:
        """Upload media in a single request (for files < 5MB)."""
        try:
            with open(media_path, 'rb') as media_file:
                files = {'media': media_file}
                data = {'media_category': media_category}
                
                response = self.oauth_v1.post(
                    self.media_upload_url,
                    files=files,
                    data=data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return str(result['media_id'])
                else:
                    print(f"Media upload failed: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"Error uploading media: {str(e)}")
            return None
    
    def _upload_media_chunked(self, media_path: str, media_category: str) -> Optional[str]:
        """Upload media using chunked upload for large files."""
        try:
            file_size = os.path.getsize(media_path)
            mime_type, _ = mimetypes.guess_type(media_path)
            
            # Step 1: Initialize upload
            init_data = {
                'command': 'INIT',
                'total_bytes': file_size,
                'media_type': mime_type,
                'media_category': media_category
            }
            
            response = self.oauth_v1.post(self.media_upload_url, data=init_data)
            if response.status_code != 202:
                print(f"Upload initialization failed: {response.status_code}")
                return None
                
            media_id = response.json()['media_id']
            
            # Step 2: Upload chunks
            chunk_size = 1024 * 1024  # 1MB chunks
            segment_index = 0
            
            with open(media_path, 'rb') as media_file:
                while True:
                    chunk = media_file.read(chunk_size)
                    if not chunk:
                        break
                        
                    append_data = {
                        'command': 'APPEND',
                        'media_id': media_id,
                        'segment_index': segment_index
                    }
                    
                    files = {'media': chunk}
                    
                    response = self.oauth_v1.post(
                        self.media_upload_url,
                        data=append_data,
                        files=files
                    )
                    
                    if response.status_code != 204:
                        print(f"Chunk upload failed: {response.status_code}")
                        return None
                        
                    segment_index += 1
            
            # Step 3: Finalize upload
            finalize_data = {
                'command': 'FINALIZE',
                'media_id': media_id
            }
            
            response = self.oauth_v1.post(self.media_upload_url, data=finalize_data)
            if response.status_code != 201:
                print(f"Upload finalization failed: {response.status_code}")
                return None
            
            # Step 4: Check processing status (for videos)
            result = response.json()
            if 'processing_info' in result:
                if not self._wait_for_processing(media_id):
                    return None
            
            return str(media_id)
            
        except Exception as e:
            print(f"Error in chunked upload: {str(e)}")
            return None
    
    def _wait_for_processing(self, media_id: str, max_wait: int = 300) -> bool:
        """Wait for media processing to complete."""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_data = {
                'command': 'STATUS',
                'media_id': media_id
            }
            
            response = self.oauth_v1.get(self.media_upload_url, params=status_data)
            if response.status_code != 200:
                return False
                
            result = response.json()
            processing_info = result.get('processing_info', {})
            state = processing_info.get('state')
            
            if state == 'succeeded':
                return True
            elif state == 'failed':
                error = processing_info.get('error', {})
                print(f"Media processing failed: {error}")
                return False
            elif state == 'in_progress':
                check_after = processing_info.get('check_after_secs', 5)
                time.sleep(check_after)
            else:
                time.sleep(5)
                
        print("Media processing timeout")
        return False
    
    def post_tweet(self, text: str, media_ids: Optional[List[str]] = None, 
                   reply_to_tweet_id: Optional[str] = None) -> Optional[Dict]:
        """
        Post a tweet with optional media attachments.
        
        Args:
            text: Tweet text content
            media_ids: List of media IDs to attach
            reply_to_tweet_id: Tweet ID to reply to (optional)
            
        Returns:
            Tweet data if successful, None if failed
        """
        # Prepare tweet data
        tweet_data = {
            "text": text
        }
        
        # Add media if provided
        if media_ids and len(media_ids) > 0:
            tweet_data["media"] = {
                "media_ids": media_ids
            }
        
        # Add reply information if provided
        if reply_to_tweet_id:
            tweet_data["reply"] = {
                "in_reply_to_tweet_id": reply_to_tweet_id
            }
        
        try:
            # Use OAuth 1.0a for API v2 as well
            response = self.oauth_v1.post(
                self.tweet_create_url,
                json=tweet_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 201:
                return response.json()
            else:
                print(f"Tweet posting failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error posting tweet: {str(e)}")
            return None
    
    def post_tweet_with_media(self, text: str, media_paths: List[str], 
                             reply_to_tweet_id: Optional[str] = None) -> Optional[Dict]:
        """
        Upload media and post tweet in one operation.
        
        Args:
            text: Tweet text content
            media_paths: List of paths to media files
            reply_to_tweet_id: Tweet ID to reply to (optional)
            
        Returns:
            Tweet data if successful, None if failed
        """
        if not media_paths or len(media_paths) == 0:
            return self.post_tweet(text, reply_to_tweet_id=reply_to_tweet_id)
        
        # Upload all media files
        media_ids = []
        for media_path in media_paths:
            # Determine media category based on file extension
            _, ext = os.path.splitext(media_path.lower())
            if ext in ['.mp4', '.mov', '.avi']:
                media_category = "tweet_video"
            elif ext in ['.gif']:
                media_category = "tweet_gif"
            else:
                media_category = "tweet_image"
            
            media_id = self.upload_media(media_path, media_category)
            if media_id:
                media_ids.append(media_id)
            else:
                print(f"Failed to upload media: {media_path}")
                return None
        
        # Post tweet with media
        return self.post_tweet(text, media_ids, reply_to_tweet_id)
    
    def delete_tweet(self, tweet_id: str) -> bool:
        """
        Delete a tweet.
        
        Args:
            tweet_id: ID of the tweet to delete
            
        Returns:
            True if successful, False if failed
        """
        try:
            delete_url = f"https://api.twitter.com/2/tweets/{tweet_id}"
            response = self.oauth_v1.delete(delete_url)
            
            if response.status_code == 200:
                return True
            else:
                print(f"Tweet deletion failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error deleting tweet: {str(e)}")
            return False



twitter = TwitterMediaPoster(
    consumer_key="ZElxajNhVC1taWNhdUh4WTZpX2E6MTpjaQ",
    consumer_secret="53kDuMjqDs_mC2zXo-Ti_EqSA-88uyZakSZ3BXuLkFBP9P5n1b",
    access_token="1968206686297976832-pyhGYw92RYXxUadg0uHpAQLtuyN5Pi",
    access_token_secret="iu99t5bzqV7cLog9LyC7OJyRySXkSRbxN4tyWJRNUG8KY"
)


def example_usage():
    """Example of how to use the TwitterMediaPoster class."""
    
    # Initialize with your Twitter API credentials
    twitter = TwitterMediaPoster(
        consumer_key="WwC5AXXrk99KJi1knrE6Fo8nX",
        consumer_secret="PTBiKwtpk3QbnyAkcsEM0aXoQou2DUeSTXsTmrpuQ0Jlf7kSx3",
        access_token="1968206686297976832-pyhGYw92RYXxUadg0uHpAQLtuyN5Pi",
        access_token_secret="iu99t5bzqV7cLog9LyC7OJyRySXkSRbxN4tyWJRNUG8KY"
    )
    
    # Example 1: Post a simple text tweet
    result = twitter.post_tweet("Hello from Python! 🐍")
    if result:
        print(f"Tweet posted successfully: {result['data']['id']}")
    
    # Example 2: Post a tweet with a single image
    result = twitter.post_tweet_with_media(
        text="Check out this image!",
        media_paths=["path/to/your/image.jpg"]
    )
    
    # Example 3: Post a tweet with multiple media files
    result = twitter.post_tweet_with_media(
        text="Multiple media files in one tweet!",
        media_paths=[
            "public/About Us 1.png",
        ]
    )
    
    media_id = twitter.upload_media("path/to/your/image.jpg")
    if media_id:
        result = twitter.post_tweet(
            text="Posted with pre-uploaded media!",
            media_ids=[media_id]
        )
    
    # Example 5: Reply to a tweet with media
    result = twitter.post_tweet_with_media(
        text="This is a reply with an image!",
        media_paths=["path/to/reply_image.jpg"],
        reply_to_tweet_id="1234567890123456789"
    )
