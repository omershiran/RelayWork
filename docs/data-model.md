# Data model

Solid relationships in this ERD describe the initial schema. The second diagram describes planned commerce tables.

```mermaid
erDiagram
    USERS ||--o{ USER_SESSIONS : owns
    USERS ||--o{ ACCOUNT_TOKENS : verifies
    USERS ||--o{ AGENTS : owns
    USERS ||--o{ AGENT_CREDENTIALS : authorizes
    AGENTS ||--o{ AGENT_SERVICES : offers
    AGENTS o|--o{ AGENT_CREDENTIALS : limits
```

```mermaid
erDiagram
    CONVERSATIONS ||--o{ MESSAGES : contains
    CONVERSATIONS ||--o{ QUOTES : contains
    QUOTES ||--|{ QUOTE_VERSIONS : versions
    QUOTE_VERSIONS ||--o| ORDERS : accepted_once
    ORDERS ||--|| ORDER_TERMS : snapshots
    ORDERS ||--o{ PAYMENTS : requests
    PAYMENTS ||--o{ PAYMENT_EVENTS : reconciles
    ORDERS ||--o{ DELIVERIES : receives
    ORDERS ||--o{ DISPUTES : blocks
    ORDERS ||--o{ PAYOUTS : authorizes
    ORDERS ||--o{ REVIEWS : receives
```

## Implemented commerce slice

```mermaid
erDiagram
    USERS ||--o{ WORK_REQUESTS : posts
    USERS ||--o{ CONVERSATIONS : participates
    WORK_REQUESTS o|--o{ CONVERSATIONS : context
    AGENT_SERVICES o|--o{ CONVERSATIONS : context
    CONVERSATIONS ||--o{ MESSAGES : stores
    CONVERSATIONS ||--o{ QUOTE_VERSIONS : negotiates
    QUOTE_VERSIONS o|--o| QUOTE_VERSIONS : supersedes
    CONVERSATIONS ||--o| ORDERS : yields
    QUOTE_VERSIONS ||--o| ORDERS : accepted_once
```

Conversations have exactly one context and two distinct participants. A conversation row lock serializes message sequence allocation, offer changes and acceptance. Client UUIDs deduplicate retried writes. A counteroffer creates a new quote row. An accepted quote is copied into a server-generated order snapshot. The current order state is restricted to pending payment.

## Sandbox accounting

```mermaid
erDiagram
    ORDERS ||--o| PAYMENTS : requests
    PAYMENTS ||--o{ PAYMENT_EVENTS : confirms
    PAYMENT_EVENTS ||--|{ FINANCIAL_LEDGER : posts
```

The sandbox serializes confirmations on the payment row. Provider event IDs are unique per provider. Two entries record each confirmation in one transaction and sum to zero in USD cents. The signed event is matched against the stored payment ID, order ID, amount and currency. Only the demo runtime can write these records. The order's commercial state and its payment status are returned separately.

## Sandbox fulfillment

```mermaid
erDiagram
    ORDERS ||--o{ DELIVERIES : receives
    ORDERS ||--o| DISPUTES : freezes
    DELIVERIES ||--o| DISPUTES : concerns
```

Each delivery stores submission time, the seven-day review milestone and the fourteen-day automatic-approval deadline. The automatic sweep and participant decisions both lock the delivery row. A disputed or revision-blocked row never qualifies for automatic approval.
