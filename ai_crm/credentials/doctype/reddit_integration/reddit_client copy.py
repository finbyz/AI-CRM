import requests
import json
import time
from typing import Optional, Dict, Any
import base64


class RedditAuthManager:
    """
    Simple Reddit authentication manager focused only on token management.
    
    Responsibilities:
    - Get access tokens
    - Refresh access tokens
    - Basic token validation
    """
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, user_agent: str):
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
        self.base_url = "https://www.reddit.com"
        
        # Token storage
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        self.redirect_uri = redirect_uri
    
    def get_access_token_with_password(self, username: str, password: str) -> Dict[str, Any]:
        """
        Get access token using username and password (script app).
        
        Args:
            username: Reddit username
            password: Reddit password
            
        Returns:
            Dictionary with access_token, refresh_token, expires_in
        """
        auth_data = {
            'grant_type': 'password',
            'username': username,
            'password': password
        }
        
        return self._request_token(auth_data)
    
    def get_access_token_with_code(self, code: str) -> Dict[str, Any]:
        """
        Get access token using authorization code (web app).
        
        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Redirect URI used in OAuth flow
            
        Returns:
            Dictionary with access_token, refresh_token, expires_in
        """
        auth_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        
        return self._request_token(auth_data)
    
    def get_client_credentials_token(self) -> Dict[str, Any]:
        """
        Get access token using client credentials (read-only access).
        
        Returns:
            Dictionary with access_token, expires_in (no refresh token)
        """
        auth_data = {
            'grant_type': 'client_credentials'
        }
        
        return self._request_token(auth_data)
    
    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Get new access token using refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            Dictionary with new access_token, refresh_token, expires_in
        """
        auth_data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        return self._request_token(auth_data)
    
    def _request_token(self, auth_data: Dict[str, str]) -> Dict[str, Any]:
        """
        Request token from Reddit API.
        
        Args:
            auth_data: Authentication data for the request
            
        Returns:
            Token response data
        """
        # Prepare authentication header
        auth_str = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            'Authorization': f'Basic {auth_str}',
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Make request
        response = requests.post(
            f"{self.base_url}/api/v1/access_token",
            data=auth_data,
            headers=headers
        )
        
        # Handle response
        if response.status_code == 200:
            token_data = response.json()
            
            # Store tokens internally (optional)
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')
            
            if token_data.get('expires_in'):
                self.token_expires_at = time.time() + token_data.get('expires_in')
            
            return {
                'access_token': token_data.get('access_token'),
                'refresh_token': token_data.get('refresh_token'),
                'token_type': token_data.get('token_type', 'bearer'),
                'expires_in': token_data.get('expires_in'),
                'scope': token_data.get('scope', '')
            }
        else:
            error_data = response.json() if response.content else {}
            raise Exception(
                f"Token request failed: {response.status_code} - "
                f"{error_data.get('error', 'Unknown error')}: "
                f"{error_data.get('error_description', response.text)}"
            )
    
    def is_token_expired(self, expires_at: float) -> bool:
        """
        Check if token is expired based on timestamp.
        
        Args:
            expires_at: Unix timestamp when token expires
            
        Returns:
            True if token is expired
        """
        return time.time() >= expires_at


class RedditClient:
    """
    Reddit API client for performing operations.
    Takes access tokens directly from RedditAuthManager.
    """
    
    def __init__(self, user_agent: str):
        """
        Initialize Reddit client.
        
        Args:
            user_agent: User agent string for API requests
        """
        self.user_agent = user_agent
        self.oauth_url = "https://oauth.reddit.com"
        self.session = requests.Session()
    
    def _make_request(self, method: str, endpoint: str, access_token: str,
                     params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make authenticated API request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            access_token: Valid access token
            params: Query parameters
            data: Request body data
            
        Returns:
            API response data
        """
        url = f"{self.oauth_url}{endpoint}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': self.user_agent
        }
        
        if method.upper() == 'GET':
            response = self.session.get(url, params=params, headers=headers)
        elif method.upper() == 'POST':
            response = self.session.post(url, data=data, params=params, headers=headers)
        elif method.upper() == 'DELETE':
            response = self.session.delete(url, params=params, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        if response.status_code in [200, 201]:
            try:
                return response.json()
            except json.JSONDecodeError:
                return {'success': True, 'response': response.text}
        else:
            raise Exception(f"API request failed: {response.status_code} - {response.text}")
    
    # Example API methods that require access token
    
    def get_me(self, access_token: str) -> Dict[str, Any]:
        """Get authenticated user info."""
        return self._make_request('GET', '/api/v1/me', access_token)
    
    def get_posts(self, subreddit: str, access_token: str, sort: str = "hot", limit: int = 25) -> Dict[str, Any]:
        """Get posts from subreddit."""
        params = {'limit': min(limit, 100), 'raw_json': 1}
        endpoint = f"/r/{subreddit}/{sort}"
        return self._make_request('GET', endpoint, access_token, params=params)
    
    def submit_post(self, subreddit: str, title: str, access_token: str,
                   text: Optional[str] = None, url: Optional[str] = None) -> Dict[str, Any]:
        """Submit a post."""
        if not text and not url:
            raise ValueError("Either text or url must be provided")
        
        kind = "self" if text else "link"
        data = {
            'sr': subreddit,
            'title': title,
            'kind': kind,
            'api_type': 'json'
        }
        
        if text:
            data['text'] = text
        if url:
            data['url'] = url
        
        return self._make_request('POST', '/api/submit', access_token, data=data)


# Usage Examples
if __name__ == "__main__":
    
    # Initialize auth manager
    auth_manager = RedditAuthManager(
        client_id="your_client_id",
        client_secret="your_client_secret",
        user_agent="YourApp/1.0"
    )
    
    try:
        # Example 1: Get token with username/password
        print("=== Getting Access Token with Password ===")
        token_response = auth_manager.get_access_token_with_password("username", "password")
        
        access_token = token_response['access_token']
        refresh_token = token_response['refresh_token']
        expires_in = token_response['expires_in']
        
        print(f"Access Token: {access_token[:20]}...")
        print(f"Refresh Token: {refresh_token[:20]}..." if refresh_token else "No refresh token")
        print(f"Expires in: {expires_in} seconds")
        
    except Exception as e:
        print(f"Password auth failed: {e}")
    
    try:
        # Example 2: Get token with authorization code
        print("\n=== Getting Access Token with Code ===")
        token_response = auth_manager.get_access_token_with_code(
            code="auth_code_from_callback",
            redirect_uri="http://localhost:8080/callback"
        )
        
        access_token = token_response['access_token']
        refresh_token = token_response['refresh_token']
        
        print(f"Access Token: {access_token[:20]}...")
        print(f"Refresh Token: {refresh_token[:20]}..." if refresh_token else "No refresh token")
        
    except Exception as e:
        print(f"Code auth failed: {e}")
    
    try:
        # Example 3: Get client credentials token (read-only)
        print("\n=== Getting Client Credentials Token ===")
        token_response = auth_manager.get_client_credentials_token()
        
        access_token = token_response['access_token']
        expires_in = token_response['expires_in']
        
        print(f"Access Token: {access_token[:20]}...")
        print(f"Expires in: {expires_in} seconds")
        print("Note: Client credentials don't provide refresh token")
        
    except Exception as e:
        print(f"Client credentials auth failed: {e}")
    
    # Example 4: Refresh token
    if 'refresh_token' in locals() and refresh_token:
        try:
            print("\n=== Refreshing Access Token ===")
            new_token_response = auth_manager.refresh_access_token(refresh_token)
            
            new_access_token = new_token_response['access_token']
            new_refresh_token = new_token_response['refresh_token']
            
            print(f"New Access Token: {new_access_token[:20]}...")
            print(f"New Refresh Token: {new_refresh_token[:20]}..." if new_refresh_token else "Same refresh token")
            
        except Exception as e:
            print(f"Token refresh failed: {e}")
    
    # Example 5: Using tokens with Reddit client
    if 'access_token' in locals() and access_token:
        print("\n=== Using Access Token with Reddit Client ===")
        reddit_client = RedditClient(user_agent="YourApp/1.0")
        
        try:
            # Get user info
            user_info = reddit_client.get_me(access_token)
            print(f"User: {user_info.get('name', 'Unknown')}")
            
            # Get posts
            posts = reddit_client.get_posts("python", access_token, limit=3)
            print(f"Retrieved {len(posts['data']['children'])} posts from r/python")
            
        except Exception as e:
            print(f"API calls failed: {e}")


# Simple token management helper
class SimpleTokenManager:
    """Helper class for simple token management workflow"""
    
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        self.auth_manager = RedditAuthManager(client_id, client_secret, user_agent)
        self.current_tokens = {}
    
    def authenticate_with_password(self, username: str, password: str) -> Dict[str, str]:
        """Authenticate and store tokens"""
        tokens = self.auth_manager.get_access_token_with_password(username, password)
        self.current_tokens = tokens
        return {
            'access_token': tokens['access_token'],
            'refresh_token': tokens.get('refresh_token', '')
        }
    
    def authenticate_with_code(self, code: str, redirect_uri: str) -> Dict[str, str]:
        """Authenticate with code and store tokens"""
        tokens = self.auth_manager.get_access_token_with_code(code, redirect_uri)
        self.current_tokens = tokens
        return {
            'access_token': tokens['access_token'],
            'refresh_token': tokens.get('refresh_token', '')
        }
    
    def get_valid_access_token(self) -> Optional[str]:
        """Get current access token (refresh if needed)"""
        if not self.current_tokens:
            return None
        
        # Check if token is expired
        if self.current_tokens.get('expires_in'):
            # This is simplified - in real app you'd store the expiry timestamp
            pass
        
        return self.current_tokens.get('access_token')
    
    def refresh_current_token(self) -> Optional[str]:
        """Refresh current access token"""
        if not self.current_tokens.get('refresh_token'):
            return None
        
        try:
            new_tokens = self.auth_manager.refresh_access_token(
                self.current_tokens['refresh_token']
            )
            self.current_tokens.update(new_tokens)
            return new_tokens['access_token']
        except:
            return None
        
        