# This script will auto close any instances in specified groups that are not ageGated
# Supports monitoring multiple group monitoring
import vrchatapi
from vrchatapi.api import authentication_api, groups_api, instances_api
from vrchatapi.exceptions import UnauthorizedException, ApiException
from vrchatapi.models.two_factor_auth_code import TwoFactorAuthCode
from vrchatapi.models.two_factor_email_code import TwoFactorEmailCode
import time
import json
import os
import random
import getpass
import sys
import requests
from http.cookiejar import Cookie
# Configuration file (holds both cookies and config)
CONFIG_FILE = ".vrchat_agegate_config.json"
def getpass_asterisk(prompt="Password: "): 
    """Get password input with asterisk masking"""
    print(prompt, end='', flush=True)
    password = "" 
    # For Windows
    if sys.platform == 'win32':
        import msvcrt
        while True:
            char = msvcrt.getch()
            if char in [b'\r', b'\n']:  # Enter key
                print()  # New line
                break
            elif char == b'\x08':  # Backspace
                if len(password) > 0:
                    password = password[:-1]
                    print('\b \b', end='', flush=True)  # Erase the asterisk
            else:
                password += char.decode('utf-8', errors='ignore')
                print('*', end='', flush=True)
    else:
        # For Unix/Linux/Mac - fallback to getpass if needed
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            while True:
                char = sys.stdin.read(1)
                if char in ['\r', '\n']:
                    print()
                    break
                elif char == '\x7f':  # Backspace
                    if len(password) > 0:
                        password = password[:-1]
                        print('\b \b', end='', flush=True)
                else:
                    password += char
                    print('*', end='', flush=True)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return password
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
def save_config(auth_value, twofa_value, group_ids=None, total_closed=None):
    """Save both authentication cookies and configuration data to a single file"""
    data = {
        "auth": auth_value,
        "twoFactorAuth": twofa_value
    }
    if group_ids is not None:
        data["group_ids"] = group_ids
    if total_closed is not None:
        data["total_closed"] = total_closed
    # If file exists, load existing data to preserve other settings
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                existing_data = json.load(f)
                # Only update the keys we're setting, preserve others
                existing_data.update(data)
                data = existing_data
        except Exception:
            pass  # Use new data if file is corrupted
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
def load_config():
    """Load authentication cookies and configuration data from single file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                # Handle backwards compatibility with single group_id
                group_ids = data.get("group_ids", [])
                if not group_ids and "group_id" in data:
                    group_ids = [data["group_id"]]
                return (
                    data.get("auth"),
                    data.get("twoFactorAuth"),
                    group_ids,
                    data.get("total_closed", 0)
                )
        except Exception:
            pass
    return None, None, [], 0
def save_cookies(auth_value, twofa_value):
    """Save cookies only (wrapper for backwards compatibility)"""
    save_config(auth_value, twofa_value)
def load_cookies():
    """Load cookies only (wrapper for backwards compatibility)"""
    auth, twofa, _ = load_config()
    return auth, twofa
def close_instance_hard(full_location, auth_value, twofa_value):
    """Close an instance using the hardClose parameter with full location string"""
    try:
        # Construct the URL for closing instance using the full location
        url = f"https://api.vrchat.cloud/api/1/instances/{full_location}"
        # Prepare cookies
        cookies = {"auth": auth_value}
        if twofa_value:
            cookies["twoFactorAuth"] = twofa_value
        # Make the DELETE request with hardClose=true
        response = requests.delete(
            url,
            params={"hardClose": "true"},
            cookies=cookies,
            headers={"User-Agent": "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.0"}
        )
        if response.status_code == 200:
            print(f"Successfully closed instance")
            return True
        elif response.status_code == 403:
            # Check if it's already closed
            try:
                response_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_message = response_data.get('error', {}).get('message', '')
                if 'already closed' in error_message.lower():
                    print(f"Instance already closed (skipping)")
                    return True  # Treat as success since our goal is achieved
                else:
                    print(f"Permission denied: {error_message}")
                    return False
            except:
                print(f"Permission denied (403): {response.text}")
                return False
        else:
            print(f"Failed to close instance: Status {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error closing instance {full_location}: {str(e)}")
        return False
def main():
    # Load existing configuration and credentials
    print("VRChat AgeGate Instance Monitor & Auto-Closer")
    print("=============================================")
    print("This script monitors group instances and automatically closes non-ageGate instances.")
    print()
    # Check if we have valid stored credentials and config
    auth_value, twofa_value, last_group_ids, total_closed = load_config()
    
    # Display total closed instances from previous runs
    if total_closed > 0:
        print(f"Total instances closed in previous runs: {total_closed}")
        print()
    # If we don't have stored auth, prompt for credentials
    if not auth_value:
        print("Please enter your VRChat credentials:")
        username = input("Username: ")
        password = getpass_asterisk("Password: ")
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
        api_client.user_agent = "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.0"
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
        # Prompt for group IDs (multiple groups supported)
        print("\nGroup ID Configuration:")
        print("You can monitor multiple groups. Enter group IDs one by one.")
        print("Type 'done' when finished, or press Enter to use previously saved groups.")
        print()
        
        # Start with last saved groups if available
        group_ids = last_group_ids.copy() if last_group_ids else []
        
        if group_ids:
            print(f"Previously saved groups: {', '.join(group_ids)}")
            use_saved = input("Use these groups? (y/n, or press Enter for yes): ").strip().lower()
            if use_saved and use_saved not in ['y', 'yes', '']:
                group_ids = []
        
        if not group_ids:
            print("Enter group IDs to monitor:")
            while True:
                if group_ids:
                    current_list = ", ".join(group_ids)
                    prompt = f"Current groups: [{current_list}]\nEnter another group ID (or 'done' to finish): "
                else:
                    prompt = "Enter group ID (or 'done' if finished): "
                
                user_input = input(prompt).strip()
                
                if user_input.lower() == 'done':
                    break
                elif user_input:
                    if user_input not in group_ids:
                        group_ids.append(user_input)
                        print(f"Added group: {user_input}")
                    else:
                        print(f"Group {user_input} already in list.")
                elif not group_ids:
                    print("Please enter at least one group ID or type 'done'.")
        
        if not group_ids:
            print("No group IDs provided. Exiting.")
            return
        
        # Save config with group IDs
        save_config(auth_value, twofa_value, group_ids, total_closed)
        
        print(f"\nMonitoring {len(group_ids)} group(s): {', '.join(group_ids)}")
        print("⚠️  WARNING: This will automatically close non-ageGate instances!")
        print("Checking every 60 seconds. Press Ctrl+C to stop.")
        print("=" * 70)
        # Function to monitor and close non-ageGate instances across multiple groups
        def monitor_and_close_instances():
            nonlocal total_closed
            overall_closed_count = 0
            overall_agegate_count = 0
            
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking {len(group_ids)} group(s)...")
            
            for group_id in group_ids:
                try:
                    # Get group information
                    group_info = groups_api_instance.get_group(group_id=group_id, include_roles=False)
                    group_name = getattr(group_info, 'name', 'Unknown Group')
                    
                    # Get group instances
                    instances = groups_api_instance.get_group_instances(group_id=group_id)
                    
                    print(f"\n📋 Group: {group_name} ({group_id})")
                    
                    if not instances:
                        print(f"   No instances found.")
                        continue
                    
                    print(f"   Found {len(instances)} instance(s) - checking for non-ageGate instances...")
                    
                    group_closed_count = 0
                    group_agegate_count = 0
                    
                    for instance in instances:
                        # Convert instance to dict to access all fields correctly
                        if hasattr(instance, 'to_dict'):
                            instance_dict = instance.to_dict()
                            location = instance_dict.get('location', '')
                        else:
                            location = getattr(instance, 'location', '')
                        
                        # Parse the location to check for ageGate
                        is_agegate = 'ageGate' in location if location else False
                        
                        # Extract just the world:instance part for display
                        display_location = location
                        if location and '~' in location:
                            display_location = location.split('~')[0]  # Get just world:instance for display
                        
                        if location:
                            if is_agegate:
                                group_agegate_count += 1
                                print(f"   ✅ AgeGate instance (keeping): {display_location}")
                            else:
                                print(f"   ⚠️  Non-ageGate instance detected: {display_location}")
                                print(f"   🔨 Attempting to close with hardClose=true...")
                                
                                if close_instance_hard(location, auth_value, twofa_value):
                                    group_closed_count += 1
                                    total_closed += 1
                                    print(f"   ✅ Closed successfully")
                                else:
                                    print(f"   ❌ Failed to close instance")
                    
                    overall_closed_count += group_closed_count
                    overall_agegate_count += group_agegate_count
                    
                    print(f"   📊 Group Summary: {group_agegate_count} ageGate kept, {group_closed_count} non-ageGate closed")
                    
                except ApiException as e:
                    print(f"   ❌ API error for group {group_id}: {e}")
                    if e.status == 401:
                        print("Authentication expired. Please restart the script.")
                        return False
                    elif e.status == 404:
                        print(f"Group {group_id} not found. Please check the Group ID.")
                        # Continue with other groups instead of stopping
                        continue
                except Exception as e:
                    print(f"   ❌ Unexpected error for group {group_id}: {e}")
                    continue
            
            print(f"\n🎯 Overall Summary: {overall_agegate_count} ageGate instances kept, {overall_closed_count} non-ageGate instances closed this check")
            print(f"📈 Total instances closed across all runs: {total_closed}")
            
            # Save updated total to config if any instances were closed
            if overall_closed_count > 0:
                save_config(auth_value, twofa_value, group_ids, total_closed)
            
            return True
        # Main monitoring loop
        try:
            while True:
                if not monitor_and_close_instances():
                    break
                print(f"\nWaiting 60 seconds before next check...")
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user.")
        # Save final config with updated cookies
        try:
            cookie_jar = api_client.rest_client.cookie_jar._cookies["api.vrchat.cloud"]["/"]
            if "auth" in cookie_jar:
                auth_value = cookie_jar["auth"].value
            if "twoFactorAuth" in cookie_jar:
                twofa_value = cookie_jar["twoFactorAuth"].value
            save_config(auth_value, twofa_value, group_ids, total_closed)
        except Exception as e:
            print(f"Final cookie save error: {e}")
if __name__ == "__main__":
    main()
