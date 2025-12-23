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
# Log file for recording closed instances
INSTANCES_LOG_FILE = "instances_closed.log"
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
def save_config(auth_value, twofa_value, group_ids=None, total_closed=None, total_accepted=None, auto_accept_enabled=None, excluded_instance_tags=None):
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
    if excluded_instance_tags is not None:
        data["excluded_instance_tags"] = excluded_instance_tags
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
                    data.get("auto_accept_enabled", False),
                    data.get("excluded_instance_tags", [])
                )
        except Exception:
            pass
    return None, None, [], 0, 0, False, []
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
    
    # Get current user's groups to show available options
    try:
        # Get the current user ID from the API client context
        # We'll need to get this from the main function, but for now let's try to get it
        auth_api = authentication_api.AuthenticationApi(groups_api_instance.api_client)
        current_user = auth_api.get_current_user()
        current_user_id = current_user.id
        
        # Extract auth values from cookies
        cookie_jar = groups_api_instance.api_client.rest_client.cookie_jar._cookies.get("api.vrchat.cloud", {}).get("/", {})
        auth_value = cookie_jar.get("auth", {}).value if cookie_jar.get("auth") else None
        twofa_value = cookie_jar.get("twoFactorAuth", {}).value if cookie_jar.get("twoFactorAuth") else None
        
        if auth_value:
            user_groups = get_user_groups(current_user_id, auth_value, twofa_value)
            available_groups = []
            
            for group in user_groups:
                # Get the actual group ID from the group object, not the membership ID
                group_id = group.get('group', {}).get('id', '') if isinstance(group.get('group'), dict) else group.get('groupId', '')
                if group_id and group_id not in current_groups:
                    group_name = group.get('group', {}).get('name', 'Unknown Group') if isinstance(group.get('group'), dict) else group.get('name', 'Unknown Group')
                    member_count = group.get('group', {}).get('memberCount', 'Unknown') if isinstance(group.get('group'), dict) else group.get('memberCount', 'Unknown')
                    available_groups.append((group_name, group_id, member_count))
            
            if available_groups:
                print(f"You are a member of {len(available_groups)} groups that are NOT currently monitored:")
                for i, (group_name, group_id, member_count) in enumerate(available_groups[:10], 1):
                    print(f"  {i}. {group_name} ({member_count} members) - {group_id}")
                if len(available_groups) > 10:
                    print(f"  ... and {len(available_groups) - 10} more groups")
                print("\nYou can enter a number from the list above, multiple numbers separated by commas (e.g., '1,3,5'), or manually enter a group ID.")
                print()
    except Exception as e:
        print(f"⚠ Could not fetch your group memberships: {e}")
        available_groups = []
    
    while True:
        if available_groups:
            new_group_input = input("Enter group number(s) from list above (e.g., '1' or '1,3,5'), group ID, or 'cancel' to abort: ").strip()
        else:
            new_group_input = input("Enter new group ID to add (or 'cancel' to abort): ").strip()
        
        if new_group_input.lower() == 'cancel':
            print("Add group cancelled.")
            return current_groups, False
            
        if not new_group_input:
            print("Please enter a valid input.")
            continue
        
        # Check if input is a number (selecting from available groups)
        new_group_id = None
        if available_groups and new_group_input.isdigit():
            selection = int(new_group_input)
            if 1 <= selection <= len(available_groups):
                new_group_id = available_groups[selection - 1][1]  # Get group ID
                print(f"Selected: {available_groups[selection - 1][0]} ({new_group_id})")
            else:
                print(f"Please enter a number between 1 and {len(available_groups)}, or enter a group ID directly.")
                continue
        elif available_groups and ',' in new_group_input:
            # Handle multiple selections
            try:
                selections = [int(x.strip()) for x in new_group_input.split(',')]
                added_groups = []
                for selection in selections:
                    if 1 <= selection <= len(available_groups):
                        group_to_add = available_groups[selection - 1][1]  # Get group ID
                        if group_to_add not in current_groups:
                            try:
                                group_info = groups_api_instance.get_group(group_id=group_to_add, include_roles=False)
                                group_name = getattr(group_info, 'name', 'Unknown Group')
                                current_groups.append(group_to_add)
                                added_groups.append(f"{group_name} ({group_to_add})")
                                print(f"✓ Successfully added group: {group_name} ({group_to_add})")
                            except ApiException as e:
                                print(f"✗ Error adding group {group_to_add}: {e}")
                            except Exception as e:
                                print(f"✗ Unexpected error adding group {group_to_add}: {e}")
                        else:
                            print(f"Group {group_to_add} is already being monitored.")
                    else:
                        print(f"Invalid selection: {selection}")
                
                if added_groups:
                    print(f"\nSuccessfully added {len(added_groups)} group(s)")
                    print(f"Now monitoring {len(current_groups)} groups: {', '.join(current_groups)}")
                    return current_groups, True
                else:
                    print("No groups were added.")
                    continue
            except ValueError:
                print("Invalid input for multiple selections. Use format like '1,2,3'")
                continue
        else:
            # Treat as direct group ID input
            new_group_id = new_group_input
        
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
        
        # First, try to get instance info before closing for logging purposes
        instance_info = None
        try:
            info_response = requests.get(
                url,
                cookies=cookies,
                headers={"User-Agent": "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.1"}
            )
            if info_response.status_code == 200:
                instance_info = info_response.json()
        except:
            pass  # Continue without instance info if we can't get it
        
        # Make the DELETE request with hardClose=true
        response = requests.delete(
            url,
            params={"hardClose": "true"},
            cookies=cookies,
            headers={"User-Agent": "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.0"}
        )
        if response.status_code == 200:
            print(f"Successfully closed instance")
            # Return success with instance info for logging
            return True, instance_info
        elif response.status_code == 403:
            # Check if it's already closed
            try:
                response_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_message = response_data.get('error', {}).get('message', '')
                if 'already closed' in error_message.lower():
                    print(f"Instance already closed (skipping)")
                    return False, None  # Return False since no closing action was performed
                else:
                    print(f"Permission denied: {error_message}")
                    return False, None
            except:
                print(f"Permission denied (403): {response.text}")
                return False, None
        else:
            print(f"Failed to close instance: Status {response.status_code}")
            print(f"Response: {response.text}")
            return False, None
    except Exception as e:
        print(f"Error closing instance {full_location}: {str(e)}")
        return False, None

def get_instance_name(full_location, auth_value, twofa_value):
    """
    Fetch the custom name of an instance from VRChat API.
    
    Args:
        full_location: Full instance location string
        auth_value: Authentication cookie value
        twofa_value: Two-factor authentication cookie value
        
    Returns:
        Instance name string or None if unable to fetch
    """
    try:
        url = f"https://api.vrchat.cloud/api/1/instances/{full_location}"
        cookies = {"auth": auth_value}
        if twofa_value:
            cookies["twoFactorAuth"] = twofa_value
        
        response = requests.get(
            url,
            cookies=cookies,
            headers={"User-Agent": "PythonAgeGateMonitor/1.0v ComfyChloe:GithubPublic-1.0"}
        )
        
        if response.status_code == 200:
            instance_data = response.json()
            return instance_data.get('displayName')
        return None
    except Exception as e:
        print(f"⚠ Error fetching instance name: {e}")
        return None

def is_instance_excluded(instance_name, excluded_tags):
    """
    Check if an instance name contains any of the excluded tags.
    
    Args:
        instance_name: The custom name of the instance
        excluded_tags: List of tag strings to check for
        
    Returns:
        True if instance should be excluded (not closed), False otherwise
    """
    if not instance_name or not excluded_tags:
        return False
    
    # Case-insensitive substring match - check if any tag appears anywhere in the name
    instance_name_lower = instance_name.lower()
    for tag in excluded_tags:
        if tag.lower() in instance_name_lower:
            return True
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
                    # Try multiple fields for the inviter name
                    manager_name = (notif_data.get('managerDisplayName') or 
                                  notif_data.get('managerName') or 
                                  notif_data.get('inviterDisplayName') or
                                  notif_data.get('inviterName') or
                                  notification.get('senderUsername') or
                                  'Unknown User')
                    
                    group_invites.append({
                        'notification_id': notification_id,
                        'group_id': group_id,
                        'group_name': notif_data.get('groupName', 'Unknown Group'),
                        'manager_name': manager_name,
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

def log_closed_instance(group_name, group_id, instance_location, player_count=None, world_name=None, excluded_reason=None):
    """
    Log a closed instance to the log file with timestamp and details.
    
    Args:
        group_name: Name of the group the instance belonged to
        group_id: ID of the group the instance belonged to
        instance_location: Full location string of the closed instance
        player_count: Number of players in the instance (if available)
        world_name: Name of the world (if available)
        excluded_reason: Reason for exclusion if instance was not closed (e.g., "Excluded by name tag: N-AV")
    """
    try:
        # Get current timestamp
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Extract world ID from location if world_name not provided
        display_world = world_name or "Unknown World"
        if not world_name and instance_location:
            # Extract world ID from location (format: wrld_xxx:instanceId~options)
            if ':' in instance_location:
                world_id = instance_location.split(':')[0]
                display_world = world_id
        
        # Format player count
        player_info = f"Players: {player_count}" if player_count is not None else "Players: Unknown"
        
        # Format the log entry with clear labels
        if excluded_reason:
            log_entry = f"Date: {timestamp} | Group: {group_name} | ID: {group_id} | World: {display_world} | Location: {instance_location} | {player_info} | Status: {excluded_reason}\n"
        else:
            log_entry = f"Date: {timestamp} | Group: {group_name} | ID: {group_id} | World: {display_world} | Location: {instance_location} | {player_info}\n"
        
        # Append to log file
        with open(INSTANCES_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
            
    except Exception as e:
        print(f"⚠ Error writing to instances log file: {e}")

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

def manual_close_instances_interactive(group_ids, groups_api_instance, auth_value, twofa_value):
    """
    Interactive function to manually close instances from monitored groups.
    """
    print("\n" + "="*60)
    print("MANUAL INSTANCE CLOSING")
    print("="*60)
    
    # Get all instances from monitored groups
    all_instances = []
    
    for group_id in group_ids:
        try:
            # Get group information
            group_info = groups_api_instance.get_group(group_id=group_id, include_roles=False)
            group_name = getattr(group_info, 'name', 'Unknown Group')
            
            # Get group instances
            instances = groups_api_instance.get_group_instances(group_id=group_id)
            
            if instances:
                for instance in instances:
                    # Convert instance to dict to access all fields correctly
                    if hasattr(instance, 'to_dict'):
                        instance_dict = instance.to_dict()
                        location = instance_dict.get('location', '')
                    else:
                        location = getattr(instance, 'location', '')
                    
                    if location:
                        # Parse the location to check for ageGate
                        is_agegate = 'ageGate' in location if location else False
                        
                        # Extract world ID from location for display
                        display_location = location
                        if location and '~' in location:
                            display_location = location.split('~')[0]  # Get just world:instance for display
                        
                        # Get additional instance info if available
                        user_count = getattr(instance, 'n_users', getattr(instance, 'userCount', 'Unknown'))
                        
                        all_instances.append({
                            'group_name': group_name,
                            'group_id': group_id,
                            'location': location,
                            'display_location': display_location,
                            'is_agegate': is_agegate,
                            'user_count': user_count
                        })
                        
        except Exception as e:
            print(f"⚠ Error getting instances for group {group_id}: {e}")
            continue
    
    if not all_instances:
        print("No instances found in any monitored groups.")
        return 0
    
    print(f"Found {len(all_instances)} instance(s) across monitored groups:")
    print()
    
    # Display numbered list of instances
    for i, instance in enumerate(all_instances, 1):
        agegate_status = "AgeGate" if instance['is_agegate'] else "Non-AgeGate"
        user_info = f"({instance['user_count']} users)" if instance['user_count'] != 'Unknown' else "(Unknown users)"
        print(f"  {i}. [{agegate_status}] {instance['group_name']} - {instance['display_location']} {user_info}")
    
    print()
    print("Enter number(s) to close (e.g., '1', '1,3,5', or 'all')")
    print("Press Enter or 'cancel' to abort")
    
    while True:
        choice = input("Selection: ").strip().lower()
        
        if choice in ['', 'cancel']:
            print("Manual instance closing cancelled.")
            return 0
        
        if choice == 'all':
            selected_indices = list(range(len(all_instances)))
        else:
            try:
                # Parse comma-separated numbers
                selected_indices = []
                for num_str in choice.split(','):
                    num = int(num_str.strip()) - 1
                    if 0 <= num < len(all_instances):
                        selected_indices.append(num)
                
                if not selected_indices:
                    print("No valid selections. Please try again.")
                    continue
                    
            except ValueError:
                print("Invalid input. Please enter numbers separated by commas.")
                continue
        
        # Confirm selection if more than 1 instance or if includes ageGate instances
        agegate_count = sum(1 for idx in selected_indices if all_instances[idx]['is_agegate'])
        if len(selected_indices) > 1 or agegate_count > 0:
            confirm_msg = f"You selected {len(selected_indices)} instance(s)"
            if agegate_count > 0:
                confirm_msg += f", including {agegate_count} AgeGate instance(s)"
            confirm_msg += ". Are you sure? (y/N): "
            
            confirm = input(confirm_msg).strip().lower()
            if confirm not in ['y', 'yes']:
                print("Cancelled.")
                continue
        
        # Close selected instances
        closed_count = 0
        for idx in selected_indices:
            instance = all_instances[idx]
            agegate_status = "AgeGate" if instance['is_agegate'] else "Non-AgeGate"
            print(f"Closing {agegate_status} instance: {instance['display_location']} from {instance['group_name']}...")
            
            success, instance_info = close_instance_hard(instance['location'], auth_value, twofa_value)
            if success:
                closed_count += 1
                print(f"✓ Successfully closed instance")
                
                # Log the closed instance
                try:
                    player_count = None
                    world_name = None
                    
                    # Extract info from instance_info if available
                    if instance_info:
                        player_count = instance_info.get('n_users', instance_info.get('userCount'))
                        world_name = instance_info.get('world', {}).get('name') if isinstance(instance_info.get('world'), dict) else None
                    
                    log_closed_instance(instance['group_name'], instance['group_id'], instance['location'], player_count, world_name)
                except Exception as log_error:
                    print(f"⚠ Error logging closed instance: {log_error}")
            else:
                print(f"✗ Failed to close instance")
        
        print(f"\nManual close complete: {closed_count}/{len(selected_indices)} instances closed.")
        return closed_count

def manage_exclusion_tags_interactive(auth_value, twofa_value):
    """
    Interactive function to manage instance name exclusion tags.
    
    Returns:
        tuple: (new_tags_list, changed_boolean)
    """
    # Load current config to get existing tags
    _, _, _, _, _, _, current_tags = load_config()
    
    print("\n" + "="*60)
    print("MANAGE EXCLUDED INSTANCE NAME TAGS")
    print("="*60)
    print("\nInstances with these tags in their name will NOT be auto-closed.")
    print()
    
    while True:
        if current_tags:
            print("Current excluded tags:")
            for i, tag in enumerate(current_tags, 1):
                print(f"  {i}. \"{tag}\"")
        else:
            print("No excluded tags configured.")
        
        print("\nOptions:")
        print("  A = add new tag")
        print("  R = remove tag")
        print("  C = clear all tags")
        print("  ENTER = save and return")
        
        choice = input("\nEnter command: ").strip().lower()
        
        if choice in ['', ' ']:
            # Save the tags
            save_config(auth_value, twofa_value, excluded_instance_tags=current_tags)
            print("Exclusion tags saved.")
            return current_tags, True
        
        elif choice == 'a':
            print("\nEnter the tag to exclude (will match anywhere in instance name):")
            print("Example: \"N-AV\" will prevent closing instances like \"Chloe's Instance N-AV\"")
            new_tag = input("Tag: ").strip()
            
            if new_tag:
                if new_tag not in current_tags:
                    current_tags.append(new_tag)
                    print(f"Added tag: \"{new_tag}\"")
                else:
                    print(f"Tag \"{new_tag}\" already exists.")
            else:
                print("Tag cannot be empty.")
            print()
        
        elif choice == 'r':
            if not current_tags:
                print("No tags to remove.")
                continue
            
            print("\nEnter number of tag to remove (or 'cancel'):")
            remove_choice = input("Selection: ").strip().lower()
            
            if remove_choice == 'cancel':
                continue
            
            try:
                idx = int(remove_choice) - 1
                if 0 <= idx < len(current_tags):
                    removed_tag = current_tags.pop(idx)
                    print(f"Removed tag: \"{removed_tag}\"")
                else:
                    print("Invalid selection.")
            except ValueError:
                print("Invalid input. Please enter a number.")
            print()
        
        elif choice == 'c':
            if current_tags:
                confirm = input(f"Clear all {len(current_tags)} tag(s)? (y/N): ").strip().lower()
                if confirm in ['y', 'yes']:
                    current_tags = []
                    print("All tags cleared.")
                else:
                    print("Cancelled.")
            else:
                print("No tags to clear.")
            print()
        
        else:
            print(f"Unknown command: '{choice}'")

def pause_script(current_user, group_ids, total_closed, total_accepted, auto_accept_enabled, groups_api_instance, auth_value, twofa_value):
    """Function to handle pause functionality with interactive menu"""
    print("\n" + "="*50)
    print("SCRIPT PAUSED - INTERACTIVE MENU")
    print("="*50)
    
    while True:
        print("\nAvailable commands while paused:")
        print("  A = add group to monitor")
        print("  R = remove group from monitoring")
        print("  E = manage excluded instance name tags")
        print("  T = toggle group invite auto-acceptance (ON/OFF)")
        print("  M = manual accept group invites")
        print("  J = manual reject group invites")
        print("  C = manual close instances")
        print("  S = show current status")
        print("  H = show this help menu")
        print("  Q = quit/exit script")
        print("  ENTER/SPACE = resume monitoring")
        
        choice = input("\nEnter command: ").strip().lower()
        
        if choice in ['', ' ']:  # Enter or Space to resume
            print("Resuming monitoring...")
            return {'action': 'resume'}
            
        elif choice == 'a':
            new_groups, changed = add_group_interactive(group_ids, groups_api_instance)
            if changed:
                return {'action': 'update_groups', 'group_ids': new_groups}
            
        elif choice == 'r':
            new_groups, changed = remove_group_interactive(group_ids, groups_api_instance)
            if changed:
                return {'action': 'update_groups', 'group_ids': new_groups}
                
        elif choice == 'e':
            new_tags, changed = manage_exclusion_tags_interactive(auth_value, twofa_value)
            if changed:
                return {'action': 'update_exclusion_tags', 'excluded_instance_tags': new_tags}
                
        elif choice == 't':
            new_auto_accept = not auto_accept_enabled
            print(f"Group invite auto-accept: {'ENABLED' if new_auto_accept else 'DISABLED'}")
            return {'action': 'toggle_auto_accept', 'auto_accept_enabled': new_auto_accept}
            
        elif choice == 'm':
            print("\nPausing monitoring for manual invite management...")
            accepted = manual_accept_invites_interactive(auth_value, twofa_value)
            if accepted > 0:
                return {'action': 'update_accepted', 'accepted_count': accepted}
            
        elif choice == 'j':
            print("\nPausing monitoring for manual invite management...")
            manual_reject_invites_interactive(auth_value, twofa_value)
            
        elif choice == 'c':
            print("\nPausing monitoring for manual instance management...")
            closed = manual_close_instances_interactive(group_ids, groups_api_instance, auth_value, twofa_value)
            if closed > 0:
                return {'action': 'update_closed', 'closed_count': closed}
            
        elif choice == 's':
            print("\n" + "="*40)
            print("CURRENT STATUS")
            print("="*40)
            print(f"Logged in as: {current_user.display_name}")
            print(f"Monitoring {len(group_ids)} group(s): {', '.join(group_ids)}")
            print(f"Auto-accept invites: {'ENABLED' if auto_accept_enabled else 'DISABLED'}")
            print(f"Total instances closed: {total_closed}")
            print(f"Total invites accepted: {total_accepted}")
            
        elif choice == 'h':
            continue  # Show menu again
            
        elif choice == 'q':
            confirm = input("Are you sure you want to quit? (y/N): ").strip().lower()
            if confirm in ['y', 'yes']:
                return {'action': 'quit'}
            else:
                print("Cancelled.")
                
        else:
            print(f"Unknown command: '{choice}'. Type 'H' for help.")
            
    return {'action': 'resume'}
def main():
    # Load existing configuration and credentials
    print("VRChat AgeGate Instance Monitor & Auto-Closer + Group Invite Manager")
    print("====================================================================")
    print("This script monitors group instances and automatically closes non-ageGate instances.")
    print("It also monitors for group invites with automatic and manual acceptance options.")
    print()
    # Check if we have valid stored credentials and config
    auth_value, twofa_value, last_group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags = load_config()
    
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
        save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags)
        
        print(f"\nMonitoring {len(group_ids)} group(s): {', '.join(group_ids)}")
        print("WARNING: This will automatically close non-ageGate instances!")
        print("Also monitoring for group invites with manual controls.")
        print("Checking every 60 seconds. Press Ctrl+C to stop.")
        print()
        print("CONTROLS:")
        print("  P = pause script (interactive menu)")
        print("  H = show help/pause menu")
        print("  T = toggle group invite auto-acceptance (ON/OFF)")
        print("  Ctrl+C = Stop")
        print(f"Group invite auto-accept: {'ENABLED' if auto_accept_enabled else 'DISABLED'}")
        print("=" * 70)
        # Function to monitor and close non-ageGate instances across multiple groups
        def monitor_and_close_instances(current_group_ids):
            nonlocal total_closed, total_accepted, auto_accept_enabled
            overall_closed_count = 0
            overall_agegate_count = 0
            initial_accepted = total_accepted
            
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking {len(current_group_ids)} group(s)...")
            print(f"Auto-accept invites: {'ON' if auto_accept_enabled else 'OFF'}")
            
            # Handle auto-accept of group invites silently
            try:
                pending_invites = get_pending_group_invites(auth_value, twofa_value)
                
                if pending_invites and auto_accept_enabled:
                    for invite in pending_invites:
                        if accept_group_invite_via_response(invite['notification_id'], invite['group_id'], auth_value, twofa_value):
                            total_accepted += 1
                            # Log the acceptance
                            try:
                                group_details = get_group_details(invite['group_id'], auth_value, twofa_value)
                                member_count = group_details.get('memberCount', 'Unknown') if group_details else 'Unknown'
                                log_accepted_group_invite(invite['group_name'], invite['group_id'], invite['manager_name'], member_count)
                            except:
                                pass
                    
            except Exception as e:
                print(f"⚠ Error checking group invites: {e}")
            
            # Check group instances for age gate monitoring with concise output
            for i, group_id in enumerate(current_group_ids, 1):
                try:
                    # Get group information
                    group_info = groups_api_instance.get_group(group_id=group_id, include_roles=False)
                    group_name = getattr(group_info, 'name', 'Unknown Group')
                    # Get group instances
                    instances = groups_api_instance.get_group_instances(group_id=group_id)
                    
                    if not instances:
                        continue
                        
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
                        
                        if location:
                            if is_agegate:
                                group_agegate_count += 1
                            else:
                                # Extract just the world:instance part for display
                                display_location = location
                                if location and '~' in location:
                                    display_location = location.split('~')[0]  # Get just world:instance for display
                                
                                # Check if instance name contains any excluded tags
                                should_exclude = False
                                matching_tag = None
                                if excluded_instance_tags:
                                    print(f"  Checking instance name for exclusion tags: {excluded_instance_tags}")
                                    instance_name = get_instance_name(location, auth_value, twofa_value)
                                    print(f"  Instance name: '{instance_name}'")
                                    if instance_name and is_instance_excluded(instance_name, excluded_instance_tags):
                                        should_exclude = True
                                        # Find which tag matched
                                        for tag in excluded_instance_tags:
                                            if tag.lower() in instance_name.lower():
                                                matching_tag = tag
                                                break
                                
                                if should_exclude:
                                    print(f"Group {i} ({group_name}) - Skipping excluded instance: {display_location} (name tag: \"{matching_tag}\")")
                                else:
                                    print(f"Group {i} ({group_name}) - Closing non-ageGate: {display_location}")
                                    success, instance_info = close_instance_hard(location, auth_value, twofa_value)
                                    if success:
                                        group_closed_count += 1
                                        total_closed += 1
                                        
                                        # Log the closed instance
                                        try:
                                            player_count = None
                                            world_name = None
                                            
                                            # Extract info from instance_info if available
                                            if instance_info:
                                                player_count = instance_info.get('n_users', instance_info.get('userCount'))
                                                world_name = instance_info.get('world', {}).get('name') if isinstance(instance_info.get('world'), dict) else None
                                            
                                            log_closed_instance(group_name, group_id, location, player_count, world_name)
                                        except Exception as log_error:
                                            print(f"⚠ Error logging closed instance: {log_error}")
                                        
                    overall_closed_count += group_closed_count
                    overall_agegate_count += group_agegate_count
                    
                except ApiException as e:
                    if e.status == 401:
                        print("Authentication expired. Please restart the script.")
                        return False
                    elif e.status == 404:
                        print(f"Group {i} not found: {group_id}")
                        # Continue with other groups instead of stopping
                        continue
                except Exception as e:
                    print(f"Error checking group {i}: {e}")
                    continue
            
            # Get current group memberships for unmonitored group alerts
            unmonitored_groups = []
            try:
                user_groups = get_user_groups(current_user_id, auth_value, twofa_value)
                if user_groups:
                    for group in user_groups:
                        # Get the actual group ID from the group object, not the membership ID
                        group_id = group.get('group', {}).get('id', '') if isinstance(group.get('group'), dict) else group.get('groupId', '')
                        group_name = group.get('group', {}).get('name', 'Unknown Group') if isinstance(group.get('group'), dict) else group.get('name', 'Unknown Group')
                        member_count = group.get('group', {}).get('memberCount', 'Unknown') if isinstance(group.get('group'), dict) else group.get('memberCount', 'Unknown')
                        
                        if group_id and group_id not in current_group_ids:
                            unmonitored_groups.append((group_name, group_id, member_count))
                            
            except Exception as e:
                print(f"⚠ Error getting group memberships: {e}")
            
            # Check for pending invites to display at end
            pending_invites_display = []
            try:
                pending_invites_display = get_pending_group_invites(auth_value, twofa_value)
            except Exception as e:
                print(f"⚠ Error checking pending invites: {e}")
            
            # Display pending invites alert
            if pending_invites_display:
                print(f"\n⚠ PENDING GROUP INVITES ({len(pending_invites_display)}):")
                for invite in pending_invites_display:
                    print(f"  • {invite['group_name']} - invited by {invite['manager_name']}")
                if not auto_accept_enabled:
                    print("  Auto-accept is OFF. Press 'P' to pause and use 'M' to manually accept or 'T' to enable auto-accept.")
            
            # Display unmonitored groups alert
            if unmonitored_groups:
                print(f"\n⚠ UNMONITORED GROUPS ({len(unmonitored_groups)}):")
                for group_name, group_id, member_count in unmonitored_groups[:5]:
                    print(f"  • {group_name} ({member_count} members) - {group_id}")
                if len(unmonitored_groups) > 5:
                    print(f"  ... and {len(unmonitored_groups) - 5} more unmonitored groups")
                print("  (Press 'P' to pause and use 'A' command to add groups to monitoring)")
            
            print(f"\nOverall Summary:")
            print(f"  Instances: {overall_agegate_count} ageGate kept, {overall_closed_count} non-ageGate closed")
            print(f"  Total instances closed across all runs: {total_closed}")
            print(f"  Total invites accepted across all runs: {total_accepted}")
            # Save updated totals to config if any instances were closed or invites were accepted
            if overall_closed_count > 0 or total_accepted > initial_accepted:
                save_config(auth_value, twofa_value, current_group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags)
            return True
        # Main monitoring loop
        try:
            while True:
                # Run the monitoring check
                if not monitor_and_close_instances(group_ids):
                    break
                print(f"\nWaiting 60 seconds before next check...")
                print(f"Press: P=Pause, H=Help, T=Toggle auto-accept, Ctrl+C=Stop")
                
                # Wait 60 seconds but check for input every second
                for i in range(60):
                    time.sleep(1)
                    # Check for user input
                    if check_for_input():
                        char = get_single_char()
                        if char in ['p', 'h']:
                            print(f"\nPausing monitoring...")
                            result = pause_script(current_user, group_ids, total_closed, total_accepted, auto_accept_enabled, groups_api_instance, auth_value, twofa_value)
                            
                            if result['action'] == 'quit':
                                print("Exiting script...")
                                return
                            elif result['action'] == 'update_groups':
                                group_ids = result['group_ids']
                                save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags)
                            elif result['action'] == 'update_exclusion_tags':
                                excluded_instance_tags = result['excluded_instance_tags']
                                save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags)
                            elif result['action'] == 'toggle_auto_accept':
                                auto_accept_enabled = result['auto_accept_enabled']
                                save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags)
                            elif result['action'] == 'update_accepted':
                                total_accepted += result['accepted_count']
                                save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags)
                            elif result['action'] == 'update_closed':
                                total_closed += result['closed_count']
                                save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags)
                            
                            print(f"Resuming monitoring...")
                            print(f"Continuing wait... ({60-i-1} seconds remaining)")
                        elif char == 't':
                            auto_accept_enabled = not auto_accept_enabled
                            save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags)
                            print(f"\nGroup invite auto-accept: {'ENABLED' if auto_accept_enabled else 'DISABLED'}")
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
            save_config(auth_value, twofa_value, group_ids, total_closed, total_accepted, auto_accept_enabled, excluded_instance_tags)
        except Exception as e:
            print(f"Final cookie save error: {e}")
if __name__ == "__main__":
    main()
