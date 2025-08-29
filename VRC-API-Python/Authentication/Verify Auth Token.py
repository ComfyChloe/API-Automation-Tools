import requests

url = "https://api.vrchat.cloud/api/1/auth"

response = requests.request("GET", url, cookies = {
  "auth": ""
})

print(response.text)