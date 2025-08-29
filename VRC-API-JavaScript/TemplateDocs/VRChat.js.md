VRChat.js

VRChat.js is a JavaScript SDK for interacting with the VRChat API, allowing developers to create applications that can access and manipulate VRChat data.
Install

To use the VRChat.js SDK, you need to install it using one of the following methods:

npm install vrchat@next

Usage

You can import the VRChat class from the SDK and create an instance of it, providing your application details such as name, version, and contact information.

import { VRChat } from "vrchat";

const vrchat = new VRChat({
	/**
	 * When using the VRChat API, you must provide an application name, version, and contact information.
	 * This is used to identify your application to VRChat, and to provide support if needed.
	 */
	application: {
		name: "Example",
		version: "1.5.1",
		/**
		 * An email, or a URL to a support page.
		 */
		contact: "you@example.com"
	},
});

Authentication

To interact with the VRChat API, you need to authenticate your application.
Automatic (recommended)

import { VRChat } from "vrchat";

const vrchat = new VRChat({
	// ...
	authentication: {
		credentials: {
			username: "",
			password: "",
			twoFactorCode: "",
			/* Or, ask for the two-factor code interactively. */
			// twoFactorCode: () => "",
			/**
			 * Or, automatically generate a code from a secret.
			 * Useful for service accounts & automated workflows.
			 *
			 * If this is a user-initiated login, don't use this.
			 */
			// totpSecret: "",
		}
	}
});

const { data: user } = await vrchat.getCurrentUser({ throwOnError: true });
console.log(`Logged in as ${data.displayName}.`);

Optimistic

By default, when given credentials, the SDK will immediately attempt to log in using the provided credentials. You can change this behavior by setting authentication.optimistic to false.

If set to true (the default), the client will attempt to authenticate immediately after being created, otherwise will only re-authenticate on request failure (e.g. 401 Unauthorized).

import { VRChat } from "vrchat";

const vrchat = new VRChat({
	// ...
	authentication: {
		optimistic: false,
		// ...
	}
});

On-demand (lazy authentication)

If you don't have the credentials available at the time of creating the VRChat instance, you can lazily re-authenticate when needed. Use a function to provide credentials only when required (e.g., after an expired session):

import { VRChat } from "vrchat";

const vrchat = new VRChat({
	application: { /* ... */ },
	authentication: {
		// Use a function to lazily provide credentials when needed.
		// Will be called when re-authentication is required.
		credentials: async () => ({
			username: "",
			password: "",
			twoFactorCode: "",
		})
	}
});

const { data: user } = await vrchat.getCurrentUser({ throwOnError: true });
console.log(`Logged in as ${data.displayName}.`);

Manually (using login(...))

If you prefer to handle authentication manually, you can use the login(...) method. This is useful if you want to handle errors or two-factor authentication in a custom way.

const { data: user } = await vrchat
	.getCurrentUser({ throwOnError: true })
	/**
	 * `throwOnError: true` will throw on failed requests, instead of returning the error
	 * as part of the response. This is useful for handling errors in a more structured way.
	 */
	.catch(async (error) => {
		// Only handle the error if it is a 401 response, which means the user was not logged in.
		if (!(error instanceof VRChatError) || error.statusCode !== 401)
			throw error;

		return vrchat.login({
			username,
			password,
			twoFactorCode: async () => {
				const { code } = await prompts({
					name: "code",
					type: "text",
					message: "Two-factor authentication code",
				});

				return code;
			},
			throwOnError: true,
		});
	});

console.log(`Logged in as ${data.displayName}.`);

Persistent sessions across restarts

The VRChat.js SDK supports persistent sessions, allowing you to log in once and reuse your session cookies across application restarts—no need to log in again every time.

By default, if you don't provide a keyv instance, the SDK uses an in-memory store, meaning your session data will be lost on restart. To persist sessions, pass a keyv instance when creating your VRChat client.

Any Keyv-compatible adapter will work—such as keyv-file, @keyv/redis, or @keyv/postgres. For this example, we'll use keyv-file to store cookies on disk.

Install it with:

npm install keyv-file

And then use it in your code like this:

import KeyvFile from "keyv-file";
import { VRChat } from "vrchat";

const vrchat = new VRChat({
	application: { /* ... */ },
	// Save cookies to a file, so you can reuse them later.
	keyv: new KeyvFile({ filename: "./data.json" }),
});

Closing notes

Most editors provide autocompletion for the VRChat object, allowing you to explore the available methods and properties. It is recommended to use an editor with TypeScript support for the best experience.

vrchat.

Frequently Asked Questions
Error: You must provide an application name, version, and contact information.

This error occurs when you create a new instance of the VRChat class without providing the required application information. The application object must include a name, version, and contact field. VRChat requires this information to identify your application and contact you if necessary.

To resolve this error, ensure that you provide the necessary information when creating a new VRChat instance. Here is an example of how to do this:
example.ts

import { VRChat } from "vrchat";

const vrchat = new VRChat({
	// Remember to change this!
  application: {
		name: "Example",
		version: "1.5.1",
		contact: "you@example.com"
	}
});