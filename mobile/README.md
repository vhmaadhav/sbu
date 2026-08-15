# Study Buddy mobile

The Android client uses only live values from the same FastAPI backend as the
web dashboard. It does not contain sample notes, tasks, planner entries,
flashcards, statistics, or canned AI answers.

## Run

Start the complete backend from the repository root:

```bash
make backend
```

The connection fields are filled on first launch with the current laptop
address, `http://100.192.1.162:8010`. Open **ALL → Laptop backend** in the
mobile UI to enter the laptop's current API URL. **Save & Connect** applies the
new backend immediately and stores it in Android preferences, so it survives
app restarts and does not require rebuilding the APK.

Build-time properties remain available as initial defaults for managed builds:

```bash
./gradlew assembleDebug -PSTUDY_BUDDY_API_URL=http://192.168.1.20:8010
```

The phone and development machine must be on the same network, and the backend
must listen on an address reachable by the phone. Do not use `localhost` on a
physical device because that means the phone itself.

## Communication

`StudyBuddyApi` sends JSON over HTTP to the configured base URL. Every request
has `Accept: application/json` and a generated `X-Request-ID`; writes also use
`Content-Type: application/json`. The client reads the backend's
`X-Request-ID` response header and includes it in visible diagnostics when a
request fails.

The app uses these live endpoints:

| Mobile feature | Backend request |
| --- | --- |
| Home statistics | `GET /api/stats` |
| Notes | `GET /api/notes?limit=200` |
| Home tasks and planner | `GET /api/tasks` |
| Complete/uncomplete task | `PATCH /api/tasks/{id}` |
| Deck list | `GET /api/flashcards` |
| Selected deck and cards | `GET /api/flashcards/{id}` |
| Question paper API | `/api/question-papers/*` |
| Axiom AI | `POST /api/ask` |
| Files, text, and recordings | `POST /api/upload`, `GET /api/items` |
| Full note management | `/api/notes/*`, `/api/subjects` |
| Voice questions and chat | `/api/ask/audio`, `/api/chat` |
| Handwriting OCR | `/api/handwriting/*` |
| Video-board review | `/api/video/*` |
| Audiobooks | `/api/audiobooks/*` |
| Complete task management | `/api/tasks/*` |
| Google Calendar | `/api/calendar/*` |
| System status | `/api/health`, `/api/stats` |

At startup, the independent read requests run concurrently. Selecting a deck
loads that deck from the backend. Task changes are written to the backend and
then reflected in the UI. AI answers come directly from the backend retrieval
flow; failures are shown as errors and never replaced with canned text. The
25-minute focus timer is intentionally on-device state and is not represented
as backend data.

The **ALL** tab is implemented entirely with Kotlin and Jetpack Compose. Files
and images use Android's native document picker; recordings use
`MediaRecorder`; JSON and multipart requests go directly to FastAPI; OCR
images render in native `ImageView` components; and OAuth/download links use
Android intents. No feature loads the web dashboard or a WebView.

The native Calendar screen can connect or disconnect Google, sync reminders,
browse month events, open events in Google Calendar, and approve or dismiss
extracted proposals. Its current **Approve** action uses the compatibility
endpoint and adds the event directly. Conflict-plan review and dynamic
rescheduling are currently available in the web Calendar page; the shared
backend endpoints under `/api/calendar/plans/*` are ready for a future native
plan-review UI.

Question-paper generation and review are currently web features. The Android
client shares access to the backend contract but does not yet expose a native
question-paper screen.

API discovery is available at `/api`, and the source-of-truth OpenAPI contract
is `/api/openapi.json`.

## Security

The current backend is a local, single-user service and does not expose an
authentication contract. Development builds therefore connect directly without
an authorization header and allow cleartext HTTP for emulator/LAN use. Before
exposing this API outside a trusted local network, add backend authentication,
HTTPS, and a release network-security policy; the mobile client should then
send the issued access token rather than embedding credentials.

No mobile-specific backend process or route set is required.

## Accessibility

**Dyslexia-friendly reading** (ALL → Settings → READING) swaps the body
typeface to OpenDyslexic and widens tracking and line height on long-form
markdown. The preference is stored in the `study_buddy_appearance`
SharedPreferences file and mirrors the same toggle in the web app's Settings.

`Sans` (in `ui/axiom/AxiomType.kt`) is a `@Composable` getter reading
`LocalDyslexicReading`, so every `fontFamily = Sans` call site follows the
toggle automatically — new UI should use it rather than `FontFamily.SansSerif`.
`Mono` is deliberately never swapped: the small uppercase labels and code
blocks stay more legible in monospace.

The bundled font files under `app/src/main/res/font/` are OpenDyslexic,
licensed under the SIL Open Font License (see `OPEN_DYSLEXIC_LICENSE.txt`).
