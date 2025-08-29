import vrchatapi
from vrchatapi.api import authentication_api, groups_api
from vrchatapi.exceptions import UnauthorizedException, ApiException
from vrchatapi.models.two_factor_auth_code import TwoFactorAuthCode
from vrchatapi.models.two_factor_email_code import TwoFactorEmailCode
import time
import json
import os
import random
import getpass
from http.cookiejar import Cookie
# Configuration files
COOKIE_FILE = ".vrchat_cookies.json"
CONFIG_FILE = "group_viewer_config.json"
# Function to handle retries with exponential backoff
def retry_with_backoff(func, max_retries=5, initial_delay=1):
    retries = 0
    while retries < max_retries:
        try:
            return func()
        except ApiException as e:
            if e.status == 429:  # Too Many Requests
                wait_time = initial_delay * (2 ** retries) + random.uniform(0, 1)
                print(f"Rate limited. Waiting {wait_time:.2f} seconds before retry...")
                time.sleep(wait_time)
                retries += 1
            else:
                raise
    raise Exception(f"Failed after {max_retries} retries")
# Function to create a cookie object
def make_cookie(name, value):
    return Cookie(0, name, value,
                 None, False,
                 "api.vrchat.cloud", True, False,
                 "/", False,
                 False,
                 173106866300,
                 False,
                 None,
                 None, {})
def save_cookies(auth_value, twofa_value):
    data = {"auth": auth_value, "twoFactorAuth": twofa_value}
    with open(COOKIE_FILE, "w") as f:
        json.dump(data, f)
def load_cookies():
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "r") as f:
                data = json.load(f)
                return data.get("auth"), data.get("twoFactorAuth")
        except Exception:
            pass
    return None, None
def save_config(auth_value, twofa_value, group_id):
    data = {
        "auth": auth_value,
        "twoFactorAuth": twofa_value,
        "group_id": group_id
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return (
                    data.get("auth"),
                    data.get("twoFactorAuth"),
                    data.get("group_id")
                )
        except Exception:
            pass
    return None, None, None
def main():
    # Prompt for credentials if not already stored
    print("VRChat Group Viewer")
    print("==================")
    # Check if we have valid stored credentials
    auth_value, twofa_value, last_group_id = load_config()
    # If we don't have stored auth, prompt for credentials
    if not auth_value:
        print("Please enter your VRChat credentials:")
        username = input("Username: ")
        password = getpass.getpass("Password: ")
        print("Credentials entered. Attempting to authenticate...")
    else:
        print("Found stored authentication, attempting to use saved session...")
        username = ''
        password = ''
    # Create configuration
    configuration = vrchatapi.Configuration(
        username=username,
        password=password,
    )
    # Enter a context with an instance of the API client
    with vrchatapi.ApiClient(configuration) as api_client:
        # Set our User-Agent as per VRChat Usage Policy
        api_client.user_agent = "PythonGroupViewer/1.0v ComfyChloe:GithubPublic-1.0"
        # Instantiate instances of API classes
        auth_api = authentication_api.AuthenticationApi(api_client)
        # Set cookies if loaded from previous session
        if auth_value:
            api_client.rest_client.cookie_jar.set_cookie(make_cookie("auth", auth_value))
        if twofa_value:
            api_client.rest_client.cookie_jar.set_cookie(make_cookie("twoFactorAuth", twofa_value))
        # Authenticate with retry logic and proper verification according to OpenAPI spec
        def authenticate():
            while True:
                try:
                    # Try to get current user (logs in if not already logged in)
                    return auth_api.get_current_user()
                except UnauthorizedException as e:
                    if e.status == 200:
                        # Parse the response body to better determine the 2FA type
                        if hasattr(e, 'body') and e.body:
                            try:
                                body_data = json.loads(e.body)
                                required_factors = body_data.get('requiresTwoFactorAuth', [])
                                if 'emailOtp' in required_factors:
                                    while True:
                                        code = input("Email 2FA Code: ")
                                        try:
                                            auth_api.verify2_fa_email_code(two_factor_email_code=TwoFactorEmailCode(code))
                                            break
                                        except ApiException as err:
                                            print(f"Invalid Email 2FA code: {err}. Try again.")
                                            time.sleep(2)
                                elif 'totp' in required_factors or 'otp' in required_factors:
                                    while True:
                                        code = input("2FA Code: ")
                                        try:
                                            auth_api.verify2_fa(two_factor_auth_code=TwoFactorAuthCode(code))
                                            break
                                        except ApiException as err:
                                            print(f"Invalid 2FA code: {err}. Try again.")
                                            time.sleep(2)
                            except Exception as err:
                                # Fallback to the original string-based detection if JSON parsing fails
                                if "Email 2 Factor Authentication" in e.reason:
                                    while True:
                                        code = input("Email 2FA Code: ")
                                        try:
                                            auth_api.verify2_fa_email_code(two_factor_email_code=TwoFactorEmailCode(code))
                                            break
                                        except ApiException as err:
                                            print(f"Invalid Email 2FA code: {err}. Try again.")
                                            time.sleep(2)
                                elif "2 Factor Authentication" in e.reason:
                                    while True:
                                        code = input("2FA Code: ")
                                        try:
                                            auth_api.verify2_fa(two_factor_auth_code=TwoFactorAuthCode(code))
                                            break
                                        except ApiException as err:
                                            print(f"Invalid 2FA code: {err}. Try again.")
                                            time.sleep(2)
                        # After successful 2FA, wait a moment and try to get the user again
                        time.sleep(2)
                        continue
                    else:
                        print(f"Authentication error: {e.reason}")
                        raise
                except ApiException as e:
                    print(f"API error during authentication: {e}")
                    raise
        try:
            # Use retry logic for authentication
            print("Authenticating with VRChat...")
            current_user = retry_with_backoff(authenticate)
            print("Logged in as:", current_user.display_name)
            # Extract and store cookies properly
            try:
                # Access cookie jar directly
                cookie_jar = api_client.rest_client.cookie_jar._cookies["api.vrchat.cloud"]["/"]
                if "auth" in cookie_jar:
                    auth_value = cookie_jar["auth"].value
                    print(f"Auth cookie found: {auth_value[:10]}...")
                if "twoFactorAuth" in cookie_jar:
                    twofa_value = cookie_jar["twoFactorAuth"].value
                    print(f"TwoFactorAuth cookie found: {twofa_value[:10]}...")
                save_cookies(auth_value, twofa_value)
            except Exception as e:
                print(f"Cookie extraction error: {e}")
            # If we couldn't find the cookies in the jar, try creating a new request to capture them
            if not auth_value:
                try:
                    # Make a test request to get authentication headers
                    _, _, headers = auth_api.get_current_user_with_http_info()
                    if 'Set-Cookie' in headers:
                        cookies_str = headers['Set-Cookie']
                        print(f"Set-Cookie header: {cookies_str[:50]}...")
                        # Extract auth and twoFactorAuth cookies
                        if 'auth=' in cookies_str:
                            auth_value = cookies_str.split('auth=')[1].split(';')[0]
                            print(f"Extracted auth from headers: {auth_value[:10]}...")
                        if 'twoFactorAuth=' in cookies_str:
                            twofa_value = cookies_str.split('twoFactorAuth=')[1].split(';')[0]
                            print(f"Extracted twoFactorAuth from headers: {twofa_value[:10]}...")
                        save_cookies(auth_value, twofa_value)
                except Exception as e:
                    print(f"Header extraction error: {e}")
            # Set the auth cookies directly in the API client
            if auth_value:
                print("Setting auth cookie in API client...")
                api_client.rest_client.cookie_jar.set_cookie(make_cookie("auth", auth_value))
            if twofa_value:
                print("Setting twoFactorAuth cookie in API client...")
                api_client.rest_client.cookie_jar.set_cookie(make_cookie("twoFactorAuth", twofa_value))
            # Re-instantiate needed API instances with the authenticated API client
            groups_api_instance = groups_api.GroupsApi(api_client)
        except Exception as e:
            print(f"Failed to authenticate: {e}")
            return
        # Prompt for group ID
        group_id = last_group_id if last_group_id else ""
        custom_group_id = input(f"Enter the group ID (or press Enter to use last: {group_id}): ")
        if custom_group_id.strip():
            group_id = custom_group_id.strip()
        if not group_id:
            print("No group ID provided. Exiting.")
            return
        # Save config
        save_config(auth_value, twofa_value, group_id)
        print(f"\nViewing group instances for {group_id}")
        print("Refreshing every 90 seconds. Press Ctrl+C to stop.")
        print("Format: InstanceID :: World name :: Player count")
        print("-" * 60)
        # Function to fetch and display group instances
        def fetch_and_display_instances():
            try:
                instances = groups_api_instance.get_group_instances(group_id=group_id)
                if not instances:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] No instances found for this group.")
                    return
                print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Found {len(instances)} instance(s):")
                for instance in instances:
                    # Extract instance information
                    instance_id = getattr(instance, 'instance_id', 'Unknown')
                    world_name = "Unknown World"
                    player_count = getattr(instance, 'n_users', 0)
                    # Get world information
                    if hasattr(instance, 'world'):
                        world = instance.world
                        if isinstance(world, dict):
                            world_name = world.get('name', 'Unknown World')
                        elif hasattr(world, 'name'):
                            world_name = world.name
                    # Display in the requested format
                    print(f"{instance_id} :: {world_name} :: Player count: {player_count}")
            except ApiException as e:
                print(f"API error when fetching instances: {e}")
                if e.status == 401:
                    print("Authentication expired. Please restart the script.")
                    return False
            except Exception as e:
                print(f"Unexpected error when fetching instances: {e}")
                return False
            return True
        # Main loop
        try:
            while True:
                if not fetch_and_display_instances():
                    break
                
                print(f"\nWaiting 90 seconds before next refresh...")
                time.sleep(90)
        except KeyboardInterrupt:
            print("\n\nStopped by user.")
        # Save final config
        try:
            cookie_jar = api_client.rest_client.cookie_jar._cookies["api.vrchat.cloud"]["/"]
            if "auth" in cookie_jar:
                auth_value = cookie_jar["auth"].value
            if "twoFactorAuth" in cookie_jar:
                twofa_value = cookie_jar["twoFactorAuth"].value
            save_config(auth_value, twofa_value, group_id)
        except Exception as e:
            print(f"Final cookie save error: {e}")
if __name__ == "__main__":
    main()