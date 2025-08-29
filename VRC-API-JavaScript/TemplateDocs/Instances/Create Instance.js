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



======


Authorization
auth <token>

Auth Token via Cookie
In: cookie

Request Body
200
worldId WorldID

WorldID be "offline" on User profiles if you are not friends with that user.
type InstanceType
Value in "public" | "hidden" | "friends" | "private" | "group"
region InstanceRegion

Instance region
Default "us"
Value in "us" | "use" | "eu" | "jp" | "unknown"
ownerId? InstanceOwnerId

A groupId if the instance type is "group", null if instance type is public, or a userId otherwise
roleIds? array <GroupRoleID>

Group roleIds that are allowed to join if the type is "group" and groupAccessType is "member"
groupAccessType? GroupAccessType

Group access type when the instance type is "group"
Default"members"
Value in"public" | "plus" | "members"
queueEnabled? boolean
Default false
closedAt? string

The time after which users won't be allowed to join the instance. This doesn't work for public instances.
Formatdate-time
canRequestInvite? boolean

Only applies to invite type instances to make them invite+
Default false
hardClose? boolean

Currently unused, but will eventually be a flag to set if the closing of the instance should kick people.
Default false
inviteOnly? boolean
Default false
ageGate? boolean
Default false
instancePersistenceEnabled? boolean
displayName? string
contentSettings? InstanceContentSettings

Types of dynamic user content permitted in an instance
drones? boolean
Default true
emoji? boolean
Default true
pedestals? boolean
Default true
prints? boolean
Default true
stickers? boolean
Default true
props? boolean
Default true