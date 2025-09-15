import requests

url = "https://api.vrchat.cloud/api/1/users/string/groups"

response = requests.request("GET", url, cookies = {
  "auth": "authcookie_41e2b898-6cfb-4099-9dd8-34b6a06a9eae"
})

print(response.text)