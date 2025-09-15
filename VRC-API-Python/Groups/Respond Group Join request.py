import requests

url = "https://api.vrchat.cloud/api/1/groups/grp_00000000-0000-0000-0000-000000000000/requests/string"
body = {
  "action": "accept"
}
response = requests.request("PUT", url, json = body, headers = {
  "Content-Type": "application/json"
}, cookies = {
  "auth": "authcookie_41e2b898-6cfb-4099-9dd8-34b6a06a9eae"
})

print(response.text)