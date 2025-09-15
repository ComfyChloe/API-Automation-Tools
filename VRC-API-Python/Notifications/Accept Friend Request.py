import requests

url = "https://api.vrchat.cloud/api/1/auth/user/notifications/string/accept"

response = requests.request("PUT", url, cookies = {
  "auth": "authcookie_41e2b898-6cfb-4099-9dd8-34b6a06a9eae"
})

print(response.text)