fetch("https://api.vrchat.cloud/api/1/auth/twofactorauth/totp/pending", {
  headers: {
    "cookie": "auth="
  }
})


========

Authorization
auth<token>

Auth Token via Cookie

In: cookie

========

Response Body
200
OK
removed boolean

401
Error response due to missing auth cookie.
error?Response
