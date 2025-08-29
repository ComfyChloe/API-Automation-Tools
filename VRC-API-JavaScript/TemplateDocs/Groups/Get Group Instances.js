fetch("https://api.vrchat.cloud/api/1/groups/grp_00000000-0000-0000-0000-000000000000/instances", {
  headers: {
    "cookie": "auth="
  }
})


=====


Authorization
auth<token>

Auth Token via Cookie

In: cookie
Path Parameters
groupId string

Must be a valid group ID.



Response Body
200
Returns a list of GroupInstance objects.
instanceId string
Length 1 <= length
locationInstanceID

InstanceID can be "offline" on User profiles if you are not friends with that user and "private" if you are friends and user is in private instance.
world World
memberCount integer
Range 0 <= value