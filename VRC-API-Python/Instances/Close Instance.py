import requests

url = "https://api.vrchat.cloud/api/1/instances"
body = {
  "worldId": "wrld_ba913a96-fac4-4048-a062-9aa5db092812",
  "type": "hidden",
  "region": "us"
}
response = requests.request("POST", url, json = body, headers = {
  "Content-Type": "application/json"
}, cookies = {
  "auth": ""
})

print(response.text)