# API Contract

All JSON endpoints use `/api`. Successful mutations return the updated resource or `{ "ok": true }`. Errors use `{ "detail": "message" }`.

## Authentication

- `POST /api/auth/register` `{ username, password }`
- `POST /api/auth/login` `{ username, password }`
- `POST /api/auth/logout`
- `GET /api/auth/me` -> `{ id, username, vipLevel, balance }`

## Experts

- `GET /api/experts` -> `{ items, sharedExpertId, allExpertId }`
- `POST /api/experts` `{ name }`
- `DELETE /api/experts/{expertId}`

## Documents

- `GET /api/documents?expert_id=&query=`
- `POST /api/documents` multipart: `expert_id`, `file`
- `DELETE /api/documents/{documentId}?expert_id=`

## Chat and notes

- `GET /api/chat/history`
- `POST /api/chat` `{ expertId, question, advanced }`
- `GET /api/notes?expert_id=`
- `POST /api/notes` `{ expertId, content }`

## Statistics and reports

- `GET /api/stats`
- `POST /api/reports/session`

RAG-dependent endpoints may return HTTP 503 with a user-readable explanation when external resources are unavailable.
