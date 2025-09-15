import requests

url = "https://api.vrchat.cloud/api/1/auth/user/notifications?type=all&sent=true&hidden=true&after=five_minutes_ago&n=60"

response = requests.request("GET", url, cookies = {
  "auth": "authcookie_41e2b898-6cfb-4099-9dd8-34b6a06a9eae"
})

print(response.text)