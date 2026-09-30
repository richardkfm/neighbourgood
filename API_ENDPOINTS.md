# API Endpoints

Full reference for the NeighbourGood REST API. Interactive docs available at `/docs` when the backend is running.

## Status

| Endpoint  | Method | Auth | Description                         |
| --------- | ------ | ---- | ----------------------------------- |
| `/status` | GET    | No   | Health check, version, current mode |

## Authentication

| Endpoint         | Method | Auth | Description               |
| ---------------- | ------ | ---- | ------------------------- |
| `/auth/register` | POST   | No   | Create account, returns JWT |
| `/auth/login`    | POST   | No   | Authenticate, returns JWT |

## Users

| Endpoint                 | Method | Auth | Description                          |
| ------------------------ | ------ | ---- | ------------------------------------ |
| `/users/me`              | GET    | Yes  | Get current user profile             |
| `/users/me`              | PATCH  | Yes  | Update profile (name, neighbourhood) |
| `/users/me/reputation`   | GET    | Yes  | Get your reputation score            |
| `/users/{id}/reputation` | GET    | No   | Get a user's reputation score        |

## Resources

| Endpoint                         | Method | Auth | Description                        |
| -------------------------------- | ------ | ---- | ---------------------------------- |
| `/resources`                     | GET    | No   | List resources (search, filter)    |
| `/resources`                     | POST   | Yes  | Create a new resource listing      |
| `/resources/{id}`                | GET    | No   | Get resource details               |
| `/resources/{id}`                | PATCH  | Yes  | Update resource (owner only)       |
| `/resources/{id}`                | DELETE | Yes  | Delete resource (owner only)       |
| `/resources/categories`          | GET    | No   | List categories with labels/icons  |
| `/resources/{id}/image`          | POST   | Yes  | Upload resource image (owner only) |
| `/resources/{id}/image`          | GET    | No   | Serve resource image               |

## Bookings

| Endpoint                              | Method | Auth | Description                        |
| ------------------------------------- | ------ | ---- | ---------------------------------- |
| `/bookings`                           | POST   | Yes  | Request to borrow a resource       |
| `/bookings`                           | GET    | Yes  | List your bookings (role/status)   |
| `/bookings/{id}`                      | GET    | Yes  | Get booking details                |
| `/bookings/{id}`                      | PATCH  | Yes  | Update booking status              |
| `/bookings/resource/{id}/calendar`    | GET    | No   | Calendar view of resource bookings |

## Messages

| Endpoint                         | Method | Auth | Description                           |
| -------------------------------- | ------ | ---- | ------------------------------------- |
| `/messages`                      | POST   | Yes  | Send a message to another user        |
| `/messages`                      | GET    | Yes  | List messages (partner/booking filter) |
| `/messages/conversations`        | GET    | Yes  | List conversation summaries           |
| `/messages/unread`               | GET    | Yes  | Get unread message count              |
| `/messages/{id}/read`            | PATCH  | Yes  | Mark a message as read                |
| `/messages/conversation/{id}/read` | POST | Yes  | Mark conversation as read             |

## Communities

| Endpoint                                 | Method | Auth | Description                        |
| ---------------------------------------- | ------ | ---- | ---------------------------------- |
| `/communities/search`                    | GET    | No   | Search communities (name/PLZ/city) |
| `/communities`                           | POST   | Yes  | Create a new community             |
| `/communities/{id}`                      | GET    | No   | Get community details              |
| `/communities/{id}`                      | PATCH  | Yes  | Update community (admin only)      |
| `/communities/{id}/join`                 | POST   | Yes  | Join a community                   |
| `/communities/{id}/leave`                | POST   | Yes  | Leave a community                  |
| `/communities/{id}/members`              | GET    | No   | List community members             |
| `/communities/my`                        | GET    | Yes  | List your communities              |
| `/communities/{id}/merge`                | POST   | Yes  | Merge community into another       |
| `/communities/{id}/merge-suggestions`    | GET    | Yes  | Auto-suggest merge candidates      |

## Skills

| Endpoint              | Method | Auth | Description                  |
| --------------------- | ------ | ---- | ---------------------------- |
| `/skills`             | GET    | No   | List skills (search, filter) |
| `/skills`             | POST   | Yes  | Create a skill listing       |
| `/skills/{id}`        | GET    | No   | Get skill details            |
| `/skills/{id}`        | PATCH  | Yes  | Update skill (owner only)    |
| `/skills/{id}`        | DELETE | Yes  | Delete skill (owner only)    |
| `/skills/categories`  | GET    | No   | List skill categories        |

## Activity Feed

| Endpoint       | Method | Auth | Description               |
| -------------- | ------ | ---- | ------------------------- |
| `/activity`    | GET    | No   | Community activity feed   |
| `/activity/my` | GET    | Yes  | Your own activity history |

## Invites

| Endpoint                | Method | Auth | Description                  |
| ----------------------- | ------ | ---- | ---------------------------- |
| `/invites`              | POST   | Yes  | Create community invite code |
| `/invites`              | GET    | Yes  | List invites for a community |
| `/invites/{code}/redeem` | POST  | Yes  | Redeem an invite code        |
| `/invites/{id}`         | DELETE | Yes  | Revoke an invite code        |

## Reviews

| Endpoint                      | Method | Auth | Description                  |
| ----------------------------- | ------ | ---- | ---------------------------- |
| `/reviews`                    | POST   | Yes  | Leave a review on a booking  |
| `/reviews/booking/{id}`       | GET    | No   | Get reviews for a booking    |
| `/reviews/user/{id}`          | GET    | No   | Get reviews received by user |
| `/reviews/user/{id}/summary`  | GET    | No   | Get user's average rating    |

## Instance (Federation)

| Endpoint         | Method | Auth | Description                    |
| ---------------- | ------ | ---- | ------------------------------ |
| `/instance/info` | GET    | No   | Instance metadata (federation) |

## Federation – Instance Directory

| Endpoint                   | Method | Auth  | Description                              |
| -------------------------- | ------ | ----- | ---------------------------------------- |
| `/directory`               | GET    | No    | List known NeighbourGood instances       |
| `/directory`               | POST   | Admin | Add instance by URL (auto-fetches info)  |
| `/directory/{id}`          | DELETE | Admin | Remove instance from directory           |
| `/directory/refresh`       | POST   | Admin | Re-crawl all instances for updates       |

## Federation – Red Sky Alerts

| Endpoint                      | Method | Auth  | Description                              |
| ----------------------------- | ------ | ----- | ---------------------------------------- |
| `/alerts`                     | GET    | No    | List Red Sky alerts (active by default)  |
| `/alerts/send`                | POST   | Admin | Broadcast alert to all known instances   |
| `/alerts/receive`             | POST   | No    | Receive alert notification from a known instance; the alert is fetched back from its source to verify it |
| `/alerts/outgoing/{alert_uid}` | GET   | No    | An alert this instance broadcast (used by receivers to verify) |
| `/alerts/{id}/dismiss`        | PATCH  | Admin | Dismiss a Red Sky alert                  |

## Data Export & Migration

| Endpoint              | Method | Auth | Description                              |
| --------------------- | ------ | ---- | ---------------------------------------- |
| `/export/my-data`     | GET    | Yes  | Export all user data as portable JSON    |
| `/migrate/import`     | POST   | Yes  | Import resources/skills from export data |
