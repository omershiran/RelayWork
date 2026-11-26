# Owner actions

| Action | Where and what to provide | Work that can continue |
| --- | --- | --- |
| Confirm public routing for agentrelai.com | At the DNS provider and in AWS, confirm who controls DNS, the intended stable address and EC2 inbound HTTP/HTTPS configuration. Current DNS resolves to 192.64.119.158; EC2 instance metadata reports 63.180.204.65. Coordinate any DNS change after checking for existing site and mail records. | Development, local testing and production configuration preparation |
| Enable transactional email | In SendGrid, verify the sending domain, publish the verification DNS records and provision a restricted Mail Send API key. Provide the verified sender and install the key in a protected server environment file. | Account flows through the development mail spool |
| Enable Google sign-in | Create a Google OAuth client for the verified production origin and callback URL after the OAuth implementation is ready. Store the client secret on the server. | Password sign-in and OAuth implementation |
| Enable OpenAI model access | Provide the intended project and approved spend cap. Install a restricted key via protected configuration once the runtime is ready. | Provider abstraction, No-Code builder, knowledge isolation and usage accounting |
| Connect payment and payout operations | Provide processor integration documents, sandbox access and authenticated callback requirements. Confirm the permitted collection and payout model, and who can authorize payouts. | Provider interfaces, internal state machine, sandbox fixtures and operations UI |
| Approve launch policies | Provide approved terms of use, privacy, cancellations, refunds and disputes policies for applicable markets. | Product and infrastructure development |
