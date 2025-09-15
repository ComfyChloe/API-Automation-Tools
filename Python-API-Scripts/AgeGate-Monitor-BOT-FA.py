# This script will auto close any instances in specified groups that are not ageGated
# Also monitors and can automatically accept group invites with manual controls
# Supports monitoring multiple groups with interactive management (Add/Remove groups while running)
import vrchatapi
from vrchatapi.api import authentication_api, groups_api, instances_api, notifications_api
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
import threading
from http.cookiejar import Cookie
# Import select only on Unix/Linux systems
if sys.platform != 'win32':
    import select
    import termios
    import tty
else:
    import msvcrt
# Configuration file (holds both cookies and config)
CONFIG_FILE = ".vrchat_agegate_config.json"
# Log file for recording accepted group invites
LOG_FILE = "group_invites_accepted.log"
def getpass_asterisk(prompt="Password: "): 
    """Get password input with asterisk masking"""
    print(prompt, end='', flush=True)
    password = "" 
    # For Windows
    if sys.platform == 'win32':
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
def save_config(auth_value, twofa_value, group_ids=None, total_closed=None, total_accepted=None, auto_accept_enabled=None):
    """Save both authentication cookies and configuration data to a single file"""
    data = {
        "auth": auth_value,
        "twoFactorAuth": twofa_value
    }
    if group_ids is not None:
        data["group_ids"] = group_ids
    if total_closed is not None:
        data["total_closed"] = total_closed
    if total_accepted is not None:
        data["total_accepted"] = total_accepted
    if auto_accept_enabled is not None:
        data["auto_accept_enabled"] = auto_accept_enabled
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
                    data.get("total_closed", 0),
                    data.get("total_accepted", 0),
                    data.get("auto_accept_enabled", False)
                )
        except Exception:
            pass
    return None, None, [], 0, 0, False
def save_cookies(auth_value, twofa_value):
    """Save cookies only (wrapper for backwards compatibility)"""
    save_config(auth_value, twofa_value)
def load_cookies():
    """Load cookies only (wrapper for backwards compatibility)"""
    auth, twofa, _ = load_config()
    return auth, twofa
def check_for_input():
    """Check if there's input available (non-blocking)"""
    if sys.platform == 'win32':
        return msvcrt.kbhit()
    else:
        # Unix/Linux
        return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])
def get_single_char():
    """Get a single character from input"""
    if sys.platform == 'win32':
        return msvcrt.getch().decode('utf-8', errors='ignore').lower()
    else:
        # Unix/Linux
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            char = sys.stdin.read(1).lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return char
def add_group_interactive(current_groups, groups_api_instance):
    """Interactive function to add a new group"""
    print("\n" + "="*50)
    print("ADD NEW GROUP")
    print("="*50)
    while True:
        new_group_id = input("Enter new group ID to add (or 'cancel' to abort): ").strip()
        
        if new_group_id.lower() == 'cancel':
            print("Add group cancelled.")
            return current_groups, False
        if not new_group_id:
            print("Please enter a valid group ID.")
            continue
        if new_group_id in current_groups:
            print(f"Group {new_group_id} is already being monitored.")
            continue
        # Test if the group exists and is accessible
        try:
            group_info = groups_api_instance.get_group(group_id=new_group_id, include_roles=False)
            group_name = getattr(group_info, 'name', 'Unknown Group')
            current_groups.append(new_group_id)
            print(f"Successfully added group: {group_name} ({new_group_id})")
            print(f"Now monitoring {len(current_groups)} groups: {', '.join(current_groups)}")
            return current_groups, True
        except ApiException as e:
            if e.status == 404:
                print(f"Group {new_group_id} not found. Please check the Group ID.")
            elif e.status == 403:
                print(f"Access denied to group {new_group_id}. You may not have permission.")
            else:
                print(f"Error accessing group {new_group_id}: {e}")
            continue
        except Exception as e:
            print(f"Unexpected error: {e}")
            continue
def remove_group_interactive(current_groups, groups_api_instance):
    """Interactive function to remove a group"""
    print("\n" + "="*50)
    print("REMOVE GROUP")
    print("="*50)
    if len(current_groups) <= 1:
        print("Cannot remove group - at least one group must be monitored.")
        return current_groups, False
    print("Current groups being monitored:")
    # Fetch group names for better display
    group_info_list = []
    for i, group_id in enumerate(current_groups, 1):
        try:
            group_info = groups_api_instance.get_group(group_id=group_id, include_roles=False)
            group_name = getattr(group_info, 'name', 'Unknown Group')
            group_info_list.append((group_id, group_name))
            print(f"  {i}. {group_name} ({group_id})")
        except ApiException as e:
            if e.status == 404:
                group_info_list.append((group_id, "Group Not Found"))
                print(f"  {i}. Group Not Found ({group_id})")
            elif e.status == 403:
                group_info_list.append((group_id, "Access Denied"))
                print(f"  {i}. Access Denied ({group_id})")
            else:
                group_info_list.append((group_id, "Error Loading"))
                print(f"  {i}. Error Loading ({group_id})")
        except Exception as e:
            group_info_list.append((group_id, "Unknown Error"))
            print(f"  {i}. Unknown Error ({group_id})")
    while True:
        choice = input("\nEnter group number to remove (or 'cancel' to abort): ").strip()
        if choice.lower() == 'cancel':
            print("Remove group cancelled.")
            return current_groups, False
        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(current_groups):
                removed_group = current_groups.pop(choice_num - 1)
                removed_group_name = group_info_list[choice_num - 1][1]
                print(f"Removed group: {removed_group_name} ({removed_group})")
                print(f"Now monitoring {len(current_groups)} groups: {', '.join(current_groups)}")
                return current_groups, True
            else:
                print(f"Please enter a number between 1 and {len(current_groups)}.")
        except ValueError:
            print("Please enter a valid number.")
            continue
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

def get_pending_group_invites(auth_value, twofa_value):
    """
    Get all pending group invite notifications.
    
    Args:
        auth_value: Authentication cookie value
        twofa_value: Two-factor authentication cookie value
        
    Returns:
        list: List of group invite notifications with details
    """
    try:
        # Use VRChat's notifications API to get recent notifications
        url = f"https://api.vrchat.cloud/api/1/notifications"
        cookies = {"auth": auth_value}
        if twofa_value:
            cookies["twoFactorAuth"] = twofa_value
        
        response = requests.get(
            url,
            params={"n": 50},  # Get more notifications to ensure we catch all invites
            headers={"User-Agent": "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.0"},
            cookies=cookies
        )
        
        notifications = []
        if response.status_code == 200:
            notifications = response.json()
        
        # Filter for group invite notifications
        group_invites = []
        for notification in notifications:
            notif_type = notification.get('type', '')
            if notif_type == 'group.invite':
                notif_data = notification.get('data', {})
                notification_id = notification.get('id', '')
                link = notification.get('link', '')
                
                # Extract group ID from the notification link
                group_id = None
                if link and link.startswith('group:'):
                    group_id = link.replace('group:', '')
                
                if notification_id and group_id:
                    group_invites.append({
                        'notification_id': notification_id,
                        'group_id': group_id,
                        'group_name': notif_data.get('groupName', 'Unknown Group'),
                        'manager_name': notif_data.get('managerDisplayName', 'Unknown User'),
                        'created_at': notification.get('created_at', '')
                    })
        
        return group_invites
        
    except Exception as e:
        print(f"⚠ Error getting pending group invites: {e}")
        return []

def accept_group_invite_via_response(notification_id, group_id, auth_value, twofa_value):
    """
    Accept a group invite using the VRChat notification response system.
    
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
                "User-Agent": "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.0"
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

def reject_group_invite_via_response(notification_id, group_id, auth_value, twofa_value):
    """
    Reject a group invite using the VRChat notification response system.
    
    Args:
        notification_id: ID of the group invite notification
        group_id: ID of the group being invited to
        auth_value: Authentication cookie value
        twofa_value: Two-factor authentication cookie value
        
    Returns:
        bool: True if invite was successfully rejected, False otherwise
    """
    try:
        # Construct the URL for responding to the notification
        url = f"https://api.vrchat.cloud/api/1/notifications/{notification_id}/respond"
        
        # Prepare authentication cookies
        cookies = {"auth": auth_value}
        if twofa_value:
            cookies["twoFactorAuth"] = twofa_value
        
        # Prepare request body for rejecting the group invite
        body = {
            "responseType": "decline",
            "responseData": group_id
        }
        
        # Make the POST request to reject the invite
        response = requests.post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.0"
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
            print(f"⚠ Failed to reject group invite: Status {response.status_code}")
            return False
    except Exception as e:
        print(f"⚠ Error rejecting group invite: {str(e)}")
        return False

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
                "User-Agent": "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.0"
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
                "User-Agent": "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.0"
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

def manual_accept_invites_interactive(auth_value, twofa_value):
    """
    Interactive function to manually accept group invites.
    """
    print("\n" + "="*60)
    print("MANUAL ACCEPT GROUP INVITES")
    print("="*60)
    
    # Get pending invites
    pending_invites = get_pending_group_invites(auth_value, twofa_value)
    
    if not pending_invites:
        print("No pending group invites found.")
        return 0
    
    print(f"Found {len(pending_invites)} pending group invite(s):")
    print()
    
    # Display numbered list of invites
    for i, invite in enumerate(pending_invites, 1):
        print(f"  {i}. {invite['group_name']} ({invite['group_id']}) - invited by {invite['manager_name']}")
    
    print()
    print("Enter number(s) to accept (e.g., '1', '1,3,5', or 'all')")
    print("Press Enter or 'cancel' to abort")
    
    while True:
        choice = input("Selection: ").strip().lower()
        
        if choice in ['', 'cancel']:
            print("Manual accept cancelled.")
            return 0
        
        if choice == 'all':
            selected_indices = list(range(len(pending_invites)))
        else:
            try:
                # Parse comma-separated numbers
                selected_indices = []
                for num_str in choice.split(','):
                    num = int(num_str.strip()) - 1
                    if 0 <= num < len(pending_invites):
                        selected_indices.append(num)
                
                if not selected_indices:
                    print("No valid selections. Please try again.")
                    continue
                    
            except ValueError:
                print("Invalid input. Please enter numbers separated by commas.")
                continue
        
        # Accept selected invites
        accepted_count = 0
        for idx in selected_indices:
            invite = pending_invites[idx]
            print(f"Accepting invite to {invite['group_name']}...")
            
            if accept_group_invite_via_response(invite['notification_id'], invite['group_id'], auth_value, twofa_value):
                accepted_count += 1
                print(f"✓ Successfully accepted invite to {invite['group_name']}")
                
                # Log the acceptance
                try:
                    # Get group details for member count
                    group_details = get_group_details(invite['group_id'], auth_value, twofa_value)
                    member_count = group_details.get('memberCount', 'Unknown') if group_details else 'Unknown'
                    log_accepted_group_invite(invite['group_name'], invite['group_id'], invite['manager_name'], member_count)
                except:
                    pass
            else:
                print(f"✗ Failed to accept invite to {invite['group_name']}")
        
        print(f"\nManual accept complete: {accepted_count}/{len(selected_indices)} invites accepted.")
        return accepted_count

def manual_reject_invites_interactive(auth_value, twofa_value):
    """
    Interactive function to manually reject group invites.
    """
    print("\n" + "="*60)
    print("MANUAL REJECT GROUP INVITES")
    print("="*60)
    
    # Get pending invites
    pending_invites = get_pending_group_invites(auth_value, twofa_value)
    
    if not pending_invites:
        print("No pending group invites found.")
        return 0
    
    print(f"Found {len(pending_invites)} pending group invite(s):")
    print()
    
    # Display numbered list of invites
    for i, invite in enumerate(pending_invites, 1):
        print(f"  {i}. {invite['group_name']} ({invite['group_id']}) - invited by {invite['manager_name']}")
    
    print()
    print("Enter number(s) to reject (e.g., '1', '1,3,5', or 'all')")
    print("Press Enter or 'cancel' to abort")
    
    while True:
        choice = input("Selection: ").strip().lower()
        
        if choice in ['', 'cancel']:
            print("Manual reject cancelled.")
            return 0
        
        if choice == 'all':
            selected_indices = list(range(len(pending_invites)))
        else:
            try:
                # Parse comma-separated numbers
                selected_indices = []
                for num_str in choice.split(','):
                    num = int(num_str.strip()) - 1
                    if 0 <= num < len(pending_invites):
                        selected_indices.append(num)
                
                if not selected_indices:
                    print("No valid selections. Please try again.")
                    continue
                    
            except ValueError:
                print("Invalid input. Please enter numbers separated by commas.")
                continue
        
        # Reject selected invites
        rejected_count = 0
        for idx in selected_indices:
            invite = pending_invites[idx]
            print(f"Rejecting invite to {invite['group_name']}...")
            
            if reject_group_invite_via_response(invite['notification_id'], invite['group_id'], auth_value, twofa_value):
                rejected_count += 1
                print(f"✓ Successfully rejected invite to {invite['group_name']}")
            else:
                print(f"✗ Failed to reject invite to {invite['group_name']}")
        
        print(f"\nManual reject complete: {rejected_count}/{len(selected_indices)} invites rejected.")
        return rejected_count
def main():
    # Load existing configuration and credentials
    print("VRChat AgeGate Instance Monitor & Auto-Closer + Group Invite Manager")
    print("====================================================================")
    print("This script monitors group instances and automatically closes non-ageGate instances.")
    print("It also monitors for group invites with automatic and manual acceptance options.")
    print()
    # Check if we have valid stored credentials and config
    auth_value, twofa_value, last_group_ids, total_closed, total_accepted, auto_accept_enabled = load_config()
    
    # Display total closed instances from previous runs
    if total_closed > 0:
        print(f"Total instances closed in previous runs: {total_closed}")
    
    # Display total accepted invites from previous runs
    if total_accepted > 0:
        print(f"Total group invites accepted in previous runs: {total_accepted}")
        
    if total_closed > 0 or total_accepted > 0:
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
            
            # Store current user ID for group membership checks
            current_user_id = current_user.id
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
        save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled)
        
        print(f"\nMonitoring {len(group_ids)} group(s): {', '.join(group_ids)}")
        print("WARNING: This will automatically close non-ageGate instances!")
        print("Also monitoring for group invites with manual controls.")
        print("Checking every 60 seconds. Press Ctrl+C to stop.")
        print()
        print("CONTROLS:")
        print("  A = Add group to monitor")
        print("  R = Remove group from monitoring")
        print("  T = Toggle group invite auto-acceptance (ON/OFF)")
        print("  M = Manual accept group invites")
        print("  J = Manual reject group invites")
        print("  Ctrl+C = Stop")
        print(f"Group invite auto-accept: {'ENABLED' if auto_accept_enabled else 'DISABLED'}")
        print("=" * 70)
        # Function to monitor and close non-ageGate instances across multiple groups
        def monitor_and_close_instances(current_group_ids):
            nonlocal total_closed, total_accepted, auto_accept_enabled
            overall_closed_count = 0
            overall_agegate_count = 0
            accepted_count = 0
            
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking {len(current_group_ids)} group(s)...")
            print(f"Auto-accept invites: {'ON' if auto_accept_enabled else 'OFF'}")
            
            # Check for group invites first
            print("Scanning for pending group invites...")
            try:
                pending_invites = get_pending_group_invites(auth_value, twofa_value)
                
                if pending_invites:
                    print(f"Found {len(pending_invites)} pending group invite(s):")
                    for invite in pending_invites:
                        print(f"  • {invite['group_name']} - invited by {invite['manager_name']}")
                    
                    if auto_accept_enabled:
                        print("Auto-accept is enabled, accepting all invites...")
                        for invite in pending_invites:
                            print(f"Accepting invite to {invite['group_name']}...")
                            if accept_group_invite_via_response(invite['notification_id'], invite['group_id'], auth_value, twofa_value):
                                accepted_count += 1
                                total_accepted += 1
                                print(f"✓ Successfully accepted invite to {invite['group_name']}")
                                
                                # Log the acceptance
                                try:
                                    group_details = get_group_details(invite['group_id'], auth_value, twofa_value)
                                    member_count = group_details.get('memberCount', 'Unknown') if group_details else 'Unknown'
                                    log_accepted_group_invite(invite['group_name'], invite['group_id'], invite['manager_name'], member_count)
                                except:
                                    pass
                            else:
                                print(f"✗ Failed to accept invite to {invite['group_name']}")
                    else:
                        print("Auto-accept is disabled. Use 'M' to manually accept or 'T' to enable auto-accept.")
                else:
                    print("No pending group invites found.")
                    
            except Exception as e:
                print(f"⚠ Error checking group invites: {e}")
            
            # Display current group memberships for status awareness
            print("Fetching current group memberships...")
            try:
                user_groups = get_user_groups(current_user_id, auth_value, twofa_value)
                if user_groups:
                    print(f"Currently a member of {len(user_groups)} group(s):")
                    for group in user_groups[:5]:  # Show first 5 groups
                        group_name = group.get('name', 'Unknown Group')
                        member_count = group.get('memberCount', 'Unknown')
                        print(f"  • {group_name} ({member_count} members)")
                    if len(user_groups) > 5:
                        print(f"  ... and {len(user_groups) - 5} more groups")
                else:
                    print("Not currently a member of any groups.")
            except Exception as e:
                print(f"⚠ Error getting group memberships: {e}")
            
            # Now check group instances for age gate monitoring
            print(f"\nChecking instances in monitored groups...")
            
            for group_id in current_group_ids:
                try:
                    # Get group information
                    group_info = groups_api_instance.get_group(group_id=group_id, include_roles=False)
                    group_name = getattr(group_info, 'name', 'Unknown Group')
                    # Get group instances
                    instances = groups_api_instance.get_group_instances(group_id=group_id)
                    print(f"\nGroup: {group_name} ({group_id})")
                    if not instances:
                        print(f"No instances found.")
                        continue
                    print(f"Found {len(instances)} instance(s) - checking for non-ageGate instances...")
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
                                print(f"AgeGate instance (keeping): {display_location}")
                            else:
                                print(f"Non-ageGate instance detected: {display_location}")
                                print(f"Attempting to close with hardClose=true...")
                                if close_instance_hard(location, auth_value, twofa_value):
                                    group_closed_count += 1
                                    total_closed += 1
                                    print(f"Closed successfully")
                                else:
                                    print(f"Failed to close instance")
                    overall_closed_count += group_closed_count
                    overall_agegate_count += group_agegate_count
                    print(f"Group Summary: {group_agegate_count} ageGate kept, {group_closed_count} non-ageGate closed")
                except ApiException as e:
                    print(f"API error for group {group_id}: {e}")
                    if e.status == 401:
                        print("Authentication expired. Please restart the script.")
                        return False
                    elif e.status == 404:
                        print(f"Group {group_id} not found. Please check the Group ID.")
                        # Continue with other groups instead of stopping
                        continue
                except Exception as e:
                    print(f"Unexpected error for group {group_id}: {e}")
                    continue
            print(f"\nOverall Summary:")
            print(f"  Instances: {overall_agegate_count} ageGate kept, {overall_closed_count} non-ageGate closed")
            print(f"  Group Invites: {accepted_count} accepted this check")
            print(f"  Total instances closed across all runs: {total_closed}")
            print(f"  Total invites accepted across all runs: {total_accepted}")
            # Save updated totals to config if any instances were closed or invites accepted
            if overall_closed_count > 0 or accepted_count > 0:
                save_config(auth_value, twofa_value, current_group_ids, total_closed, total_accepted, auto_accept_enabled)
            return True
        # Main monitoring loop
        try:
            while True:
                # Run the monitoring check
                if not monitor_and_close_instances(group_ids):
                    break
                print(f"\nWaiting 60 seconds before next check...")
                print(f"Press: A=Add group, R=Remove group, T=Toggle auto-accept, M=Manual accept, J=Manual reject, Ctrl+C=Stop")
                # Wait 60 seconds but check for input every second
                for i in range(60):
                    time.sleep(1)
                    # Check for user input
                    if check_for_input():
                        char = get_single_char()
                        if char == 'a':
                            print(f"\nPausing monitoring for group management...")
                            new_groups, changed = add_group_interactive(group_ids, groups_api_instance)
                            if changed:
                                group_ids = new_groups
                                save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled)
                            print(f"Resuming monitoring...")
                            print(f"Continuing wait... ({60-i-1} seconds remaining)")
                        elif char == 'r':
                            print(f"\nPausing monitoring for group management...")
                            new_groups, changed = remove_group_interactive(group_ids, groups_api_instance)
                            if changed:
                                group_ids = new_groups
                                save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled)
                            print(f"Resuming monitoring...")
                            print(f"Continuing wait... ({60-i-1} seconds remaining)")
                        elif char == 't':
                            auto_accept_enabled = not auto_accept_enabled
                            save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled)
                            print(f"\nGroup invite auto-accept: {'ENABLED' if auto_accept_enabled else 'DISABLED'}")
                            print(f"Continuing wait... ({60-i-1} seconds remaining)")
                        elif char == 'm':
                            print(f"\nPausing monitoring for manual invite management...")
                            accepted = manual_accept_invites_interactive(auth_value, twofa_value)
                            if accepted > 0:
                                total_accepted += accepted
                                save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled)
                            print(f"Resuming monitoring...")
                            print(f"Continuing wait... ({60-i-1} seconds remaining)")
                        elif char == 'j':
                            print(f"\nPausing monitoring for manual invite management...")
                            manual_reject_invites_interactive(auth_value, twofa_value)
                            print(f"Resuming monitoring...")
                            print(f"Continuing wait... ({60-i-1} seconds remaining)")
                        # Clear any remaining input
                        while check_for_input():
                            get_single_char()
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user.")
        # Save final config with updated cookies
        try:
            cookie_jar = api_client.rest_client.cookie_jar._cookies["api.vrchat.cloud"]["/"]
            if "auth" in cookie_jar:
                auth_value = cookie_jar["auth"].value
            if "twoFactorAuth" in cookie_jar:
                twofa_value = cookie_jar["twoFactorAuth"].value
            save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled)
        except Exception as e:
            print(f"Final cookie save error: {e}")
if __name__ == "__main__":
    main()
