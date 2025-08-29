const body = JSON.stringify({
  "worldId": "wrld_ba913a96-fac4-4048-a062-9aa5db092812",
  "type": "hidden",
  "region": "us"
})

fetch("https://api.vrchat.cloud/api/1/instances", {
  headers: {
    "cookie": "auth="
  },
  body
})