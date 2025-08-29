import requests

url = "https://api.vrchat.cloud/api/1/auth/twofactorauth/emailotp/verify"
body = {
  "code": "string"
}
response = requests.request("POST", url, json = body, headers = {
  "Content-Type": "application/json"
}, cookies = {
  "auth": ""
})

print(response.text)