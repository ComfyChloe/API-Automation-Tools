import requests

url = "https://api.vrchat.cloud/api/1/auth/twofactorauth/totp/pending"

response = requests.request("DELETE", url, cookies = {
  "auth": ""
})

print(response.text)