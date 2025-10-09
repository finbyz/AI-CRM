import requests
import json
import time
from typing import Optional, Dict, List, Any, Union
from urllib.parse import urlencode
import base64


class RedditAuthManager:
    """
    Manages Reddit API authentication and token operations.
    
    Handles OAuth2 authentication, token refresh, and credential management
    separately from API operations.
    """
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str , user_agent: str):
        """
        Initialize Reddit authentication manager.
        
        Args:
            client_id: Reddit app client ID
            client_secret: Reddit app client secret
            user_agent: User agent string for API requests
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.redirect_uri = redirect_uri
        
        self.base_url = "https://www.reddit.com"
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        self.token_type = "bearer"
    
    def set_existing_token(self, access_token: str, refresh_token: Optional[str] = None,
                          expires_in: Optional[int] = None, token_type: str = "bearer"):
        """
        Set existing authentication tokens.
        
        Args:
            access_token: Existing access token
            refresh_token: Existing refresh token (optional)
            expires_in: Token expiry time in seconds from now (optional)
            token_type: Token type (default: bearer)
        """
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_type = token_type
        
        if expires_in:
            self.token_expires_at = time.time() + expires_in
        else:
            # Default to 1 hour if not specified
            self.token_expires_at = time.time() + 3600
    
    def authenticate_script(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate using script app credentials (username/password).
        
        Args:
            username: Reddit username
            password: Reddit password
            
        Returns:
            Authentication response data
        """
        auth_data = {
            'grant_type': 'password',
            'username': username,
            'password': password
        }
        
        return self._request_token(auth_data)
    
    def authenticate_client_credentials(self) -> Dict[str, Any]:
        """
        Authenticate using client credentials (read-only access).
        
        Returns:
            Authentication response data
        """
        auth_data = {
            'grant_type': 'client_credentials'
        }
        
        return self._request_token(auth_data)
    
    def get_access_token_with_code(self, code: str) -> Dict[str, Any]:
        """
        Authenticate using authorization code from OAuth2 flow.
        
        Args:
            code: Authorization code from OAuth2 callback
            redirect_uri: Redirect URI used in OAuth2 flow
            
        Returns:
            Authentication response data
        """
        auth_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        
        return self._request_token(auth_data)
    
    def _request_token(self, auth_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Request access token from Reddit.
        
        Args:
            auth_data: Authentication data for the request
            
        Returns:
            Token response data
        """
        auth_str = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            'Authorization': f'Basic {auth_str}',
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        response = requests.post(
            f"{self.base_url}/api/v1/access_token",
            data=auth_data,
            headers=headers
        )
        
        if response.status_code == 200:
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')
            self.token_type = token_data.get('token_type', 'bearer')
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = time.time() + expires_in
            
            return token_data
        else:
            raise Exception(f"Authentication failed: {response.status_code} - {response.text}")
    
    def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh the access token using refresh token.
        
        Returns:
            New token data
        """
        if not self.refresh_token:
            raise Exception("No refresh token available")
        
        auth_data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        
        return self._request_token(auth_data)
    
    def is_token_valid(self) -> bool:
        """
        Check if the current access token is valid and not expired.
        
        Returns:
            True if token is valid, False otherwise
        """
        if not self.access_token:
            return False
        
        if self.token_expires_at and time.time() >= self.token_expires_at:
            return False
        
        return True
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for API requests.
        
        Returns:
            Dictionary with authorization headers
        """
        if not self.access_token:
            raise Exception("No access token available")
        
        return {
            'Authorization': f'{self.token_type.title()} {self.access_token}',
            'User-Agent': self.user_agent
        }
    
    def revoke_token(self, token: Optional[str] = None, token_type: str = "access_token") -> bool:
        """
        Revoke an access or refresh token.
        
        Args:
            token: Token to revoke (uses current access_token if None)
            token_type: Type of token ("access_token" or "refresh_token")
            
        Returns:
            True if successful
        """
        if not token:
            token = self.access_token if token_type == "access_token" else self.refresh_token
        
        if not token:
            raise Exception(f"No {token_type} available to revoke")
        
        auth_str = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            'Authorization': f'Basic {auth_str}',
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'token': token,
            'token_type_hint': token_type
        }
        
        response = requests.post(
            f"{self.base_url}/api/v1/revoke_token",
            data=data,
            headers=headers
        )
        
        return response.status_code == 204
    
    def get_oauth_url(self, redirect_uri: str, scopes: List[str], state: str = "") -> str:
        """
        Generate OAuth2 authorization URL.
        
        Args:
            redirect_uri: Redirect URI after authorization
            scopes: List of requested scopes
            state: State parameter for security
            
        Returns:
            Authorization URL
        """
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'scope': ' '.join(scopes),
            'state': state,
            'duration': 'permanent'
        }
        
        return f"{self.base_url}/api/v1/authorize?{urlencode(params)}"


class RedditClient:
    """
    Reddit API client for performing operations.
    
    Provides methods for all Reddit API operations like posts, comments,
    users, and subreddits. Authentication and token management are handled
    internally by this client.
    """
    
    def __init__(
        self,
        user_agent: str,
        *,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_type: str = "bearer",
        expires_in: Optional[int] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        """
        Initialize Reddit client with direct authentication parameters.
        
        Args:
            user_agent: User agent string for API requests
            access_token: Optional existing access token
            refresh_token: Optional existing refresh token
            token_type: Token type, defaults to "bearer"
            expires_in: Optional seconds until expiry for the access token
            client_id: Optional Reddit app client ID (required for refresh/flows)
            client_secret: Optional Reddit app client secret (required for refresh/flows)
            redirect_uri: Optional redirect URI for OAuth flows
        """
        self.oauth_url = "https://oauth.reddit.com"
        self.session = requests.Session()
        self.user_agent = user_agent

        # Credentials for token operations
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

        # Token state
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_type = token_type
        self.token_expires_at = None
        if expires_in is not None:
            self.token_expires_at = time.time() + expires_in
    
    def _ensure_authenticated(self):
        """Ensure we have a valid access token."""
        if not self.is_token_valid():
            if self.refresh_token:
                self.refresh_access_token()
            else:
                raise Exception("No valid access token and no refresh token available")
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                     data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make authenticated API request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            
        Returns:
            API response data
        """
        self._ensure_authenticated()
        
        url = f"{self.oauth_url}{endpoint}"
        headers = self.get_auth_headers()
        
        if method.upper() == 'GET':
            response = self.session.get(url, params=params, headers=headers)
        elif method.upper() == 'POST':
            response = self.session.post(url, data=data, params=params, headers=headers)
        elif method.upper() == 'DELETE':
            response = self.session.delete(url, params=params, headers=headers)
        elif method.upper() == 'PUT':
            response = self.session.put(url, data=data, params=params, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        if response.status_code in [200, 201]:
            try:
                return response.json()
            except json.JSONDecodeError:
                return {'success': True, 'response': response.text}
        else:
            raise Exception(f"API request failed: {response.status_code} - {response.text}")

    # ============ Internal auth/token management ============

    def set_existing_token(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        *,
        expires_in: Optional[int] = None,
        token_type: str = "bearer",
    ) -> None:
        """Set existing tokens on the client."""
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_type = token_type
        if expires_in is not None:
            self.token_expires_at = time.time() + expires_in
        else:
            self.token_expires_at = time.time() + 3600

    def _request_token(self, auth_data: Dict[str, str]) -> Dict[str, Any]:
        """Request an access token from Reddit using stored client credentials."""
        if not self.client_id or not self.client_secret:
            raise Exception("client_id and client_secret are required for token requests")

        auth_str = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            'Authorization': f'Basic {auth_str}',
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        response = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            data=auth_data,
            headers=headers,
        )

        if response.status_code == 200:
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')
            self.token_type = token_data.get('token_type', 'bearer')
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = time.time() + expires_in
            return token_data
        else:
            raise Exception(f"Authentication failed: {response.status_code} - {response.text}")

    def refresh_access_token(self) -> Dict[str, Any]:
        """Refresh the access token using the stored refresh token."""
        if not self.refresh_token:
            raise Exception("No refresh token available")
        auth_data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
        }
        return self._request_token(auth_data)

    def is_token_valid(self) -> bool:
        """Check whether the current access token exists and is not expired."""
        if not self.access_token:
            return False
        if self.token_expires_at and time.time() >= self.token_expires_at:
            return False
        return True

    def get_auth_headers(self) -> Dict[str, str]:
        """Build authorization headers for API requests."""
        if not self.access_token:
            raise Exception("No access token available")
        return {
            'Authorization': f'{self.token_type.title()} {self.access_token}',
            'User-Agent': self.user_agent,
        }
    
    # POST OPERATIONS
    
    def submit_post(self, subreddit: str, title: str, text: Optional[str] = None, 
                   url: Optional[str] = None, nsfw: bool = False, 
                   spoiler: bool = False, flair_id: Optional[str] = None,
                   flair_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Submit a new post to a subreddit.
        
        Args:
            subreddit: Name of the subreddit
            title: Post title
            text: Post text content (for text posts)
            url: URL (for link posts)
            nsfw: Mark as NSFW
            spoiler: Mark as spoiler
            flair_id: Flair template ID
            flair_text: Custom flair text
            
        Returns:
            Post creation response
        """
        if not text and not url:
            raise ValueError("Either text or url must be provided")
        
        kind = "self" if text else "link"
        
        data = {
            'sr': subreddit,
            'title': title,
            'kind': kind,
            'nsfw': nsfw,
            'spoiler': spoiler,
            'api_type': 'json'
        }
        
        if text:
            data['text'] = text
        if url:
            data['url'] = url
        if flair_id:
            data['flair_id'] = flair_id
        if flair_text:
            data['flair_text'] = flair_text
        
        return self._make_request('POST', '/api/submit', data=data)
    
    def delete_post(self, post_id: str) -> Dict[str, Any]:
        """Delete a post."""
        data = {'id': f"t3_{post_id}"}
        return self._make_request('POST', '/api/del', data=data)
    
    def get_post(self, subreddit: str, post_id: str) -> Dict[str, Any]:
        """Get a specific post from a subreddit."""
        endpoint = f"/r/{subreddit}/comments/{post_id}"
        return self._make_request('GET', endpoint)
    
    def get_posts(self, subreddit: str, sort: str = "hot", limit: int = 25, 
                 time_filter: str = "all", after: Optional[str] = None,
                 before: Optional[str] = None) -> Dict[str, Any]:
        """
        Get posts from a subreddit.
        
        Args:
            subreddit: Subreddit name
            sort: Sort type (hot, new, top, rising)
            limit: Number of posts to retrieve (1-100)
            time_filter: Time filter for top posts (hour, day, week, month, year, all)
            after: Get posts after this fullname
            before: Get posts before this fullname
        """
        params = {
            'limit': min(limit, 100),
            'raw_json': 1
        }
        
        if sort == 'top':
            params['t'] = time_filter
        if after:
            params['after'] = after
        if before:
            params['before'] = before
        
        endpoint = f"/r/{subreddit}/{sort}"
        return self._make_request('GET', endpoint, params=params)
    
    def search_posts(self, query: str, subreddit: Optional[str] = None, 
                    sort: str = "relevance", time_filter: str = "all", 
                    limit: int = 25, after: Optional[str] = None) -> Dict[str, Any]:
        """
        Search for posts.
        
        Args:
            query: Search query
            subreddit: Specific subreddit to search (None for all)
            sort: Sort type (relevance, hot, top, new, comments)
            time_filter: Time filter
            limit: Number of results
            after: Get results after this fullname
        """
        params = {
            'q': query,
            'sort': sort,
            't': time_filter,
            'limit': min(limit, 100),
            'type': 'link',
            'raw_json': 1
        }
        
        if after:
            params['after'] = after
        
        if subreddit:
            params['restrict_sr'] = 'true'
            endpoint = f"/r/{subreddit}/search"
        else:
            endpoint = "/search"
        
        return self._make_request('GET', endpoint, params=params)
    
    # COMMENT OPERATIONS
    
    def create_comment(self, parent_id: str, text: str) -> Dict[str, Any]:
        """
        Create a comment on a post or reply to a comment.
        
        Args:
            parent_id: ID of parent (post: t3_xxx, comment: t1_xxx)
            text: Comment text
        """
        data = {
            'thing_id': parent_id,
            'text': text,
            'api_type': 'json'
        }
        return self._make_request('POST', '/api/comment', data=data)
    
    def create_post(self, subreddit, title, content=None, url=None, image=None, kind="text") -> Dict[str, Any]:
        """Create a post on Reddit"""
        try:
            self._ensure_authenticated()
            data = {
                "sr": subreddit,
                "title": title,
                "kind": kind,
                "api_type": "json"
            }
            if kind == "text" and content:
                data["text"] = content
            elif kind == "link" and url:
                data["url"] = url
            else:
                raise ValueError("Invalid kind or missing content/url")
            
            response = self._make_request('POST', '/api/submit', data=data)            
            if response.get("json", {}).get("errors"):
                errors = response["json"]["errors"]
                error_msg = "; ".join([str(error) for error in errors])
                return {
                    "status": "error",
                    "message": f"Reddit API Error: {error_msg}"
                }
                
            post_data = response.get("json", {}).get("data", {})
            api_url_value = post_data.get("url", "")
            
            
            if api_url_value.startswith("http"):
                post_url = api_url_value
            else:
                post_url = f"https://www.reddit.com{api_url_value}"
            
            return {
                "status": "success",
                "message": "Post created successfully",
                "url": post_url,
                "id": post_data.get("id")
            }   
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
    def get_comments(self, subreddit: str, post_id: str, sort: str = "best", 
                    limit: int = 100, depth: Optional[int] = None) -> Dict[str, Any]:
        """
        Get comments for a post.
        
        Args:
            subreddit: Subreddit name
            post_id: Post ID
            sort: Comment sort (confidence/best, top, new, controversial, old, random, qa, live)
            limit: Maximum number of comments
            depth: Maximum depth of comment tree
        """
        params = {
            'sort': sort,
            'limit': limit,
            'raw_json': 1
        }
        
        if depth is not None:
            params['depth'] = depth
        
        endpoint = f"/r/{subreddit}/comments/{post_id}"
        return self._make_request('GET', endpoint, params=params)
    
    def reply_to_comment(self, comment_id: str, text: str) -> Dict[str, Any]:
        """Reply to a comment."""
        return self.create_comment(f"t1_{comment_id}", text)
    
    def delete_comment(self, comment_id: str) -> Dict[str, Any]:
        """Delete a comment."""
        data = {'id': f"t1_{comment_id}"}
        return self._make_request('POST', '/api/del', data=data)
    
    def edit_comment(self, comment_id: str, text: str) -> Dict[str, Any]:
        """Edit a comment."""
        data = {
            'thing_id': f"t1_{comment_id}",
            'text': text,
            'api_type': 'json'
        }
        return self._make_request('POST', '/api/editusertext', data=data)
    
    # USER OPERATIONS
    
    def get_user_profile(self, username: str) -> Dict[str, Any]:
        """Get user profile information."""
        endpoint = f"/user/{username}/about"
        return self._make_request('GET', endpoint)
    
    def get_user_posts(self, username: str, sort: str = "new", 
                      time_filter: str = "all", limit: int = 25,
                      after: Optional[str] = None) -> Dict[str, Any]:
        """Get posts submitted by a user."""
        params = {
            'sort': sort,
            't': time_filter,
            'limit': min(limit, 100),
            'raw_json': 1
        }
        
        if after:
            params['after'] = after
        
        endpoint = f"/user/{username}/submitted"
        return self._make_request('GET', endpoint, params=params)
    
    def get_user_comments(self, username: str, sort: str = "new", 
                         time_filter: str = "all", limit: int = 25,
                         after: Optional[str] = None) -> Dict[str, Any]:
        """Get comments made by a user."""
        params = {
            'sort': sort,
            't': time_filter,
            'limit': min(limit, 100),
            'raw_json': 1
        }
        
        if after:
            params['after'] = after
        
        endpoint = f"/user/{username}/comments"
        return self._make_request('GET', endpoint, params=params)
    
    def get_me(self) -> Dict[str, Any]:
        """Get information about the authenticated user."""
        return self._make_request('GET', '/api/v1/me')
    
    # SUBREDDIT OPERATIONS
    
    def get_subreddit_info(self, subreddit: str) -> Dict[str, Any]:
        """Get subreddit information."""
        endpoint = f"/r/{subreddit}/about"
        return self._make_request('GET', endpoint)
    
    def search_subreddits(self, query: str, limit: int = 25,
                         after: Optional[str] = None) -> Dict[str, Any]:
        """Search for subreddits."""
        params = {
            'q': query,
            'limit': min(limit, 100),
            'raw_json': 1
        }
        
        if after:
            params['after'] = after
        
        return self._make_request('GET', '/subreddits/search', params=params)
    
    def get_popular_subreddits(self, limit: int = 25,
                              after: Optional[str] = None) -> Dict[str, Any]:
        """Get popular subreddits."""
        params = {
            'limit': min(limit, 100),
            'raw_json': 1
        }
        
        if after:
            params['after'] = after
        
        return self._make_request('GET', '/subreddits/popular', params=params)
    
    def get_subreddit_rules(self, subreddit: str) -> Dict[str, Any]:
        """Get rules for a subreddit."""
        endpoint = f"/r/{subreddit}/about/rules"
        return self._make_request('GET', endpoint)
    
    # VOTING OPERATIONS
    
    def vote(self, thing_id: str, direction: int) -> Dict[str, Any]:
        """
        Vote on a post or comment.
        
        Args:
            thing_id: Full thing ID (e.g., t3_abc123 for post, t1_def456 for comment)
            direction: Vote direction (1 for upvote, -1 for downvote, 0 for no vote)
        """
        data = {
            'id': thing_id,
            'dir': str(direction)
        }
        return self._make_request('POST', '/api/vote', data=data)
    
    def upvote(self, thing_id: str) -> Dict[str, Any]:
        """Upvote a post or comment."""
        return self.vote(thing_id, 1)
    
    def downvote(self, thing_id: str) -> Dict[str, Any]:
        """Downvote a post or comment."""
        return self.vote(thing_id, -1)
    
    def remove_vote(self, thing_id: str) -> Dict[str, Any]:
        """Remove vote from a post or comment."""
        return self.vote(thing_id, 0)
    
    # SAVE/UNSAVE OPERATIONS
    
    def save_post(self, post_id: str) -> Dict[str, Any]:
        """Save a post."""
        data = {'id': f"t3_{post_id}"}
        return self._make_request('POST', '/api/save', data=data)
    
    def unsave_post(self, post_id: str) -> Dict[str, Any]:
        """Unsave a post."""
        data = {'id': f"t3_{post_id}"}
        return self._make_request('POST', '/api/unsave', data=data)
    
    def save_comment(self, comment_id: str) -> Dict[str, Any]:
        """Save a comment."""
        data = {'id': f"t1_{comment_id}"}
        return self._make_request('POST', '/api/save', data=data)
    
    def unsave_comment(self, comment_id: str) -> Dict[str, Any]:
        """Unsave a comment."""
        data = {'id': f"t1_{comment_id}"}
        return self._make_request('POST', '/api/unsave', data=data)


# Example usage
if __name__ == "__main__":
    # Initialize client with an existing token (no auth manager)
    reddit_client = RedditClient(
        user_agent="YourApp/1.0 by YourUsername",
        access_token="your_existing_access_token",
        refresh_token="your_existing_refresh_token",  # optional
        token_type="bearer",
        expires_in=3600,
        # client_id and client_secret are only needed if you want auto-refresh
        client_id="your_client_id",
        client_secret="your_client_secret",
    )

    try:
        user_info = reddit_client.get_me()
        print(f"Logged in as: {user_info.get('name')}")

        posts = reddit_client.get_posts("python", sort="hot", limit=5)
        print(f"Found {len(posts['data']['children'])} posts")

        search_results = reddit_client.search_posts("machine learning", limit=5)
        print(f"Search found {len(search_results['data']['children'])} posts")

        subreddit_info = reddit_client.get_subreddit_info("python")
        print(f"Subreddit subscribers: {subreddit_info['data']['subscribers']}")

        # Submit a post (if you have write permissions)
        # post_response = reddit_client.submit_post(
        #     subreddit="test",
        #     title="Test Post",
        #     text="This is a test post from Python"
        # )

    except Exception as e:
        print(f"Error: {e}")
