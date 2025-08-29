const body = JSON.stringify({
  "code": "string"
})

fetch("https://api.vrchat.cloud/api/1/auth/twofactorauth/totp/pending/verify", {
  headers: {
    "cookie": "auth="
  },
  body
})


=======


Authorization
auth<token>

Auth Token via Cookie

In: cookie

Request Body
code string


Response Body
200
OK
verified boolean
enabled? boolean
Default true

401
Error response due to missing auth cookie.
error? Response