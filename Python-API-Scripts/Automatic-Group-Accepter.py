# VRChat Automatic Group Invite Accepter
# Author: ComfyChloe
# Version: 1.2
#
# DESCRIPTION:
# This script continuously monitors your VRChat account for incoming group invites
# and automatically accepts them. It's useful for users who want to join groups
# without manually checking and accepting invites.
#
# FEATURES:
# - Automatic authentication with saved credentials
# - 2FA support (TOTP and Email)
# - Real-time monitoring every 60 seconds
# - Displays current group memberships
# - Tracks total accepted invites across sessions
# - Logs all accepted invites to group_invites_accepted.log

# NOTE: This script only accepts GROUP INVITES sent to you by others,
# not group join requests made by others to groups you manage.

import vrchatapi
from vrchatapi.api import authentication_api, notifications_api, groups_api
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
# Import select only on Unix/Linux systems
if sys.platform != 'win32':
    import select

# Configuration file for storing authentication cookies and statistics
CONFIG_FILE = ".vrchat_groupaccepter_config.json"
# Log file for recording accepted group invites
LOG_FILE = "group_invites_accepted.log"

def getpass_asterisk(prompt="Password: "): 
    """
    Get password input with asterisk masking for better security.
    Works on both Windows and Unix-like systems.
    """
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

# Function to handle API rate limiting with exponential backoff
def retry_with_backoff(func, max_retries=5, initial_delay=1):
    """
    Retry a function with exponential backoff to handle VRChat API rate limiting.
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds between retries
    """
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

# Function to create a cookie object for VRChat API authentication
def make_cookie(name, value):
    """
    Create a cookie object compatible with the VRChat API client.
    Used for maintaining authentication sessions.
    """
    return Cookie(0, name, value,
                 None, False,
                 "api.vrchat.cloud", True, False,
                 "/", False,
                 False,
                 173106866300,
                 False,
                 None,
                 None, {})

def save_config(auth_value, twofa_value, total_accepted=None):
    """
    Save authentication cookies and statistics to configuration file.
    
    Args:
        auth_value: VRChat auth cookie value
        twofa_value: VRChat 2FA cookie value  
        total_accepted: Total number of accepted group invites (optional)
    """
    data = {
        "auth": auth_value,
        "twoFactorAuth": twofa_value
    }
    if total_accepted is not None:
        data["total_accepted"] = total_accepted
    
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
    """
    Load authentication cookies and statistics from configuration file.
    
    Returns:
        tuple: (auth_cookie, twofa_cookie, total_accepted_count)
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return (
                    data.get("auth"),
                    data.get("twoFactorAuth"),
                    data.get("total_accepted", 0)
                )
        except Exception:
            pass
    return None, None, 0

def check_for_input():
    """
    Check if there's keyboard input available (non-blocking).
    Used during wait periods to allow for clean exit.
    """
    if sys.platform == 'win32':
        import msvcrt
        return msvcrt.kbhit()
    else:
        # Unix/Linux
        import select
        return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

def get_single_char():
    """
    Get a single character from keyboard input.
    Cross-platform implementation for Windows and Unix-like systems.
    """
    if sys.platform == 'win32':
        import msvcrt
        return msvcrt.getch().decode('utf-8', errors='ignore').lower()
    else:
        # Unix/Linux
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            char = sys.stdin.read(1).lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return char

def get_user_groups(user_id, auth_value, twofa_value):
    """
    Get the groups that a user is a member of using the VRChat REST API.
    
    Args:
        user_id: VRChat user ID
        auth_value: Authentication cookie value
        twofa_value: Two-factor authentication cookie value
        
    Returns:
        list: List of group objects the user is a member of
    """
    try:
        # Construct the URL for getting user groups
        url = f"https://api.vrchat.cloud/api/1/users/{user_id}/groups"
        
        # Prepare cookies
        cookies = {"auth": auth_value}
        if twofa_value:
            cookies["twoFactorAuth"] = twofa_value
        
        # Make the GET request
        response = requests.get(
            url,
            headers={
                "User-Agent": "PythonGroupAccepter/1.0v ComfyChloe:GithubPublic-1.0"
            },
            cookies=cookies
        )
        
        if response.status_code == 200:
            groups_data = response.json()
            return groups_data
        else:
            print(f"Failed to get user groups: Status {response.status_code}")
            return []
    except Exception as e:
        print(f"Error getting user groups: {str(e)}")
        return []

def accept_group_invite_via_response(notification_id, group_id, auth_value, twofa_value):
    """
    Accept a group invite using the VRChat notification response system.
    
    This is the proper way to accept group invites received via notifications.
    The invite must be responded to through the notification system rather than
    directly accepting the notification.
    
    Args:
        notification_id: ID of the group invite notification
        group_id: ID of the group being invited to
        auth_value: Authentication cookie value
        twofa_value: Two-factor authentication cookie value
        
    Returns:
        bool: True if invite was successfully accepted, False otherwise
    """
    try:
        # Construct the URL for responding to the notification
        url = f"https://api.vrchat.cloud/api/1/notifications/{notification_id}/respond"
        
        # Prepare authentication cookies
        cookies = {"auth": auth_value}
        if twofa_value:
            cookies["twoFactorAuth"] = twofa_value
        
        # Prepare request body for accepting the group invite
        body = {
            "responseType": "accept",
            "responseData": group_id
        }
        
        # Make the POST request to accept the invite
        response = requests.post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "PythonGroupAccepter/1.0v ComfyChloe:GithubPublic-1.0"
            },
            cookies=cookies
        )
        
        if response.status_code == 200:
            return True
        elif response.status_code == 404:
            print(f"⚠ Group invite notification not found (may have been already processed)")
            return False
        elif response.status_code == 403:
            print(f"⚠ Permission denied - may not have permissions to respond to notification")
            return False
        else:
            print(f"⚠ Failed to accept group invite: Status {response.status_code}")
            return False
    except Exception as e:
        print(f"⚠ Error accepting group invite: {str(e)}")
        return False

def log_accepted_group_invite(group_name, group_id, inviter_name, member_count):
    """
    Log an accepted group invite to the log file with timestamp and details.
    
    Args:
        group_name: Name of the group that was joined
        group_id: ID of the group that was joined
        inviter_name: Display name of the user who sent the invite
        member_count: Total number of members in the group
    """
    try:
        # Get current timestamp
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Format the log entry with clear labels
        log_entry = f"Date: {timestamp} | Group: {group_name} | ID: {group_id} | Invited by: {inviter_name} | Members: {member_count}\n"
        
        # Append to log file
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
            
    except Exception as e:
        print(f"⚠ Error writing to log file: {e}")

def get_group_details(group_id, auth_value, twofa_value):
    """
    Get detailed information about a specific group using the VRChat REST API.
    
    Args:
        group_id: ID of the group to fetch details for
        auth_value: Authentication cookie value
        twofa_value: Two-factor authentication cookie value
        
    Returns:
        dict: Group details including member count, or None if failed
    """
    try:
        # Construct the URL for getting group details
        url = f"https://api.vrchat.cloud/api/1/groups/{group_id}"
        
        # Prepare cookies
        cookies = {"auth": auth_value}
        if twofa_value:
            cookies["twoFactorAuth"] = twofa_value
        
        # Make the GET request
        response = requests.get(
            url,
            headers={
                "User-Agent": "PythonGroupAccepter/1.0v ComfyChloe:GithubPublic-1.0"
            },
            cookies=cookies
        )
        
        if response.status_code == 200:
            group_data = response.json()
            return group_data
        else:
            print(f"⚠ Failed to get group details: Status {response.status_code}")
            return None
    except Exception as e:
        print(f"⚠ Error getting group details: {str(e)}")
        return None

def main():
    """Main function that handles authentication and starts the monitoring loop"""
    # Load existing configuration and credentials
    print("VRChat Automatic Group Invite Accepter")
    print("=====================================")
    print("This script monitors for group invites and automatically accepts them.")
    print()
    
    # Check if we have valid stored credentials and config
    auth_value, twofa_value, total_accepted = load_config()
    
    # Display total accepted invites from previous runs
    if total_accepted > 0:
        print(f"Total group invites accepted in previous runs: {total_accepted}")
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
        api_client.user_agent = "PythonGroupAccepter/1.0v ComfyChloe:GithubPublic-1.0"
        
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
                save_config(auth_value, twofa_value, total_accepted)
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
                        save_config(auth_value, twofa_value, total_accepted)
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
            notifications_api_instance = notifications_api.NotificationsApi(api_client)
            groups_api_instance = groups_api.GroupsApi(api_client)
            
            # Store current user ID for group membership checks
            current_user_id = current_user.id
            
        except Exception as e:
            print(f"Failed to authenticate: {e}")
            return
        
        print("\nStarting automatic group invite accepter...")
        print("Monitoring for new group invites every 60 seconds.")
        print("Will also display current group memberships during each check.")
        print("Press Ctrl+C to stop.")
        print("=" * 70)
        
        # Function to monitor and accept group invites
        def monitor_and_accept_invites():
            """
            Main monitoring function that:
            1. Displays current group memberships
            2. Scans for new group invite notifications
            3. Automatically accepts any found invites
            """
            nonlocal total_accepted
            accepted_count = 0
            
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking for group invites...")
            
            # Display current group memberships for status awareness
            print("Fetching current group memberships...")
            try:
                user_groups = get_user_groups(current_user_id, auth_value, twofa_value)
                if user_groups:
                    print(f"Currently member of {len(user_groups)} group(s):")
                    for i, group in enumerate(user_groups, 1):
                        group_name = group.get('name', 'Unknown Group')
                        group_id = group.get('id', 'Unknown ID')
                        member_count = group.get('memberCount', 0)
                        membership_status = group.get('membershipStatus', 'member')
                        my_member = group.get('myMember', {})
                        role_ids = my_member.get('roleIds', []) if my_member else []
                        
                        role_info = f" (Roles: {len(role_ids)})" if role_ids else ""
                        status_info = f" [{membership_status}]" if membership_status != 'member' else ""
                        
                        print(f"  {i}. {group_name} ({group_id})")
                        print(f"      Members: {member_count}{role_info}{status_info}")
                else:
                    print("Not currently a member of any groups.")
                print()
            except Exception as e:
                print(f"Error fetching group memberships: {e}")
                print()
            
            # Scan for new group invite notifications
            print("Scanning for new group invites...")
            
            try:
                # Use VRChat's v2 notifications API to get recent notifications
                url = f"https://api.vrchat.cloud/api/1/notifications"
                cookies = {"auth": auth_value}
                if twofa_value:
                    cookies["twoFactorAuth"] = twofa_value
                
                response = requests.get(
                    url,
                    params={"n": 20},  # Get last 20 notifications
                    headers={"User-Agent": "PythonGroupAccepter/1.0v ComfyChloe:GithubPublic-1.0"},
                    cookies=cookies
                )
                
                notifications = []
                if response.status_code == 200:
                    notifications = response.json()
                
                if not notifications:
                    print("No notifications found.")
                    return True
                
                print(f"Found {len(notifications)} notification(s) - scanning for group invites...")
                
                # Count notification types for summary
                notification_types = set(notif.get('type', 'unknown') for notif in notifications)
                group_invite_count = sum(1 for notif in notifications if notif.get('type') == 'group.invite')
                
                if group_invite_count > 0:
                    print(f"Found {group_invite_count} group invite notification(s)")
                else:
                    print("No group invite notifications found")
                
                # Process each notification to find and accept group invites
                for notification in notifications:
                    try:
                        notif_type = notification.get('type', '')
                        
                        # Only process group invite notifications
                        if notif_type == 'group.invite':
                            notif_data = notification.get('data', {})
                            notification_id = notification.get('id', '')
                            link = notification.get('link', '')
                            
                            # Extract group ID from the notification link (format: "group:grp_...")
                            group_id = None
                            if link and link.startswith('group:'):
                                group_id = link.split('group:')[1]
                            
                            if notification_id and group_id:
                                group_name = notif_data.get('groupName', 'Unknown Group')
                                manager_name = notif_data.get('managerUserDisplayName', 'Unknown Manager')
                                print(f"Found group invite to '{group_name}' from {manager_name}")
                                
                                # Accept the group invite using the notification response system
                                print(f"Accepting group invite...")
                                if accept_group_invite_via_response(notification_id, group_id, auth_value, twofa_value):
                                    accepted_count += 1
                                    total_accepted += 1
                                    
                                    # Get group details directly to get accurate member count
                                    try:
                                        group_details = get_group_details(group_id, auth_value, twofa_value)
                                        
                                        if group_details:
                                            member_count = group_details.get('memberCount', 'Unknown')
                                            # Update group name with the official name if different
                                            official_group_name = group_details.get('name', group_name)
                                        else:
                                            member_count = "Unknown"
                                            official_group_name = group_name
                                        
                                        # Log the successful acceptance with accurate details
                                        log_accepted_group_invite(official_group_name, group_id, manager_name, member_count)
                                        
                                    except Exception as log_error:
                                        # If we can't get group details, log with basic info
                                        log_accepted_group_invite(group_name, group_id, manager_name, "Unknown")
                                        print(f"⚠ Could not fetch group details for logging: {log_error}")
                                    
                                    print(f"✓ Successfully accepted invite to {group_name}")
                                else:
                                    print(f"✗ Failed to accept invite to {group_name}")
                            else:
                                print(f"⚠ Group invite notification missing required data")
                    
                    except Exception as e:
                        print(f"Error processing notification: {e}")
                        continue
                
                # Summary of this check
                if accepted_count > 0:
                    print(f"\n✓ Accepted {accepted_count} group invite(s) this check.")
                    print(f"Total group invites accepted: {total_accepted}")
                    
                    # Update group membership display after accepting invites
                    try:
                        user_groups = get_user_groups(current_user_id, auth_value, twofa_value)
                        group_count = len(user_groups) if user_groups else 0
                        print(f"Current status: Member of {group_count} group(s)")
                    except:
                        pass
                    
                    # Save updated total to config
                    save_config(auth_value, twofa_value, total_accepted)
                else:
                    print("No new group invites to accept.")
                
                return True
                
            except Exception as e:
                print(f"Error while checking notifications: {e}")
                return True
        
        # Main monitoring loop - runs continuously until stopped by user
        try:
            while True:
                # Run the monitoring check for new group invites
                if not monitor_and_accept_invites():
                    break
                
                # Wait 60 seconds before next check
                print(f"\nWaiting 60 seconds before next check...")
                print(f"Press Ctrl+C to stop")
                
                # Wait 60 seconds but check for input every second to allow clean exit
                for i in range(60):
                    time.sleep(1)
                    # Clear any input to avoid buildup
                    if check_for_input():
                        get_single_char()
                        
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user.")
        
        # Save final configuration with updated cookies and statistics
        try:
            cookie_jar = api_client.rest_client.cookie_jar._cookies["api.vrchat.cloud"]["/"]
            if "auth" in cookie_jar:
                auth_value = cookie_jar["auth"].value
            if "twoFactorAuth" in cookie_jar:
                twofa_value = cookie_jar["twoFactorAuth"].value
            save_config(auth_value, twofa_value, total_accepted)
        except Exception as e:
            print(f"Final cookie save error: {e}")

# Entry point - run the main function when script is executed directly
if __name__ == "__main__":
    main()