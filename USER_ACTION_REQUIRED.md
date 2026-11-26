# Owner actions

| Action | Where and what to provide | Work that can continue |
| --- | --- | --- |
| Verify end-to-end email receipt | Public account mail is configured with the supplied SendGrid key and no-reply@agentrelai.com. To confirm delivery, register using an address you control and open the verification email. Check Sender Authentication in SendGrid if delivery fails. | Development and demo account flows use private mail spools |
| Enable Google sign-in | Create a Google OAuth client for the verified production origin and callback URL after the OAuth implementation is ready. Store the client secret on the server. | Password sign-in and OAuth implementation |
| Approve an OpenAI generation budget | The key is configured and the models metadata endpoint accepted it. Provide the intended model and approved maximum spend before live generation is enabled. | Provider abstraction, No-Code builder, knowledge isolation and usage accounting |
| Connect payment and payout operations | Provide processor integration documents, sandbox access and authenticated callback requirements. Confirm the permitted collection and payout model, and who can authorize payouts. | Provider interfaces, internal state machine, sandbox fixtures and operations UI |
| Approve launch policies | Provide approved terms of use, privacy, cancellations, refunds and disputes policies for applicable markets. | Product and infrastructure development |
