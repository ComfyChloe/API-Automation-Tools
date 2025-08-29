import requests

url = "https://api.vrchat.cloud/api/1/logout"

response = requests.request("PUT", url, cookies = {
  "auth": ""
})

print(response.text)