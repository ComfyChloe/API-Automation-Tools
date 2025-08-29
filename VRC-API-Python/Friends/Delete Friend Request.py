import requests

url = "https://api.vrchat.cloud/api/1/user/string/friendRequest"

response = requests.request("DELETE", url, cookies = {
  "auth": ""
})

print(response.text)