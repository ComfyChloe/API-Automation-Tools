import requests

url = "https://api.vrchat.cloud/api/1/auth/user"

response = requests.request("GET", url, headers = {
  "Authorization": "Basic Og=="
})

print(response.text)