## ADDED Requirements

### Requirement: SEBI no-advice guardrail

The agent SHALL never give opinions, advice, or recommendations on reports or investments, no matter how the user phrases or pressures the request. This MUST hold on the first message, on any follow-up, and after any tool use — including after a report tool (`cml_report`, `contract_note`) returns data, where the agent MUST present the returned facts only and decline to interpret, evaluate, or recommend. The guardrail instruction MUST be present in the system prompt on every model call so it persists across the whole conversation.

#### Scenario: Direct investment-advice request is declined

- **WHEN** a user asks the agent whether they should buy, sell, or hold an investment, or asks for the agent's opinion on a report
- **THEN** the agent declines to give advice, opinions, or recommendations and explains it cannot provide investment advice

#### Scenario: SEBI guardrail holds after report tool use

- **WHEN** the agent has just fetched a CML or contract-note report via a tool and the user asks "so is this good, what should I do?"
- **THEN** the agent presents only the factual report contents and still declines to interpret or recommend, even under repeated pressure

#### Scenario: Persistent pressure does not override the guardrail

- **WHEN** a user repeatedly pushes for a recommendation across multiple follow-up messages
- **THEN** the agent continues to decline on every turn and does not eventually provide advice

### Requirement: Choice FinX scope guardrail

The agent SHALL decline messages unrelated to Choice FinX and politely redirect the user to Choice FinX support topics. This MUST hold across turns and after tool use: an off-topic request MUST NOT be answered even if it follows an on-topic exchange, and the redirect MUST point the user back to the in-scope KB categories.

#### Scenario: Off-topic message is redirected

- **WHEN** a user asks something unrelated to Choice FinX (e.g. general trivia, coding help, or another company's product)
- **THEN** the agent politely declines and redirects the user to Choice FinX support topics without answering the off-topic request

#### Scenario: Scope guardrail persists after an on-topic turn

- **WHEN** a user first asks an in-scope Choice FinX question and then, in a follow-up, asks an off-topic question
- **THEN** the agent answers the in-scope question but declines and redirects the off-topic follow-up
