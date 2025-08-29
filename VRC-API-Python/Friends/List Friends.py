import requests

url = "https://api.vrchat.cloud/api/1/auth/user/friends?n=60&offline=true"

response = requests.request("GET", url, cookies = {
  "auth": ""
})

print(response.text)