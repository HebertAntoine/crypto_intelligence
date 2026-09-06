# Crypto Intelligence — app

Flutter client for the Crypto Intelligence backend. Runs on the web (deployed
to Vercel), Android and iOS from one codebase.

**Analysis only. This app never places orders and gives no financial advice.**

## What it renders

The app computes nothing. Every threshold, verdict and edge decision is made by
the backend, so the phone, the web build and the research output can never
disagree about what the data says.

Four screens:

| Screen | Question it answers |
| --- | --- |
| Today | What do we actually know about BTC, ETH and SOL right now? |
| Chart | What structure is on the chart, and what has been verified about it? |
| Research | What did the system measure about its own signals? |
| Knowledge | What do sources claim, and what do the data show? |

## The invariant

A pattern's **recognition confidence** and its **edge state** are always
rendered together. A double bottom can match its definition at 91/100 and still
carry `NO_MEASURABLE_EDGE` — that pairing is the intended reading, not a
contradiction.

Green is reserved for a *measured* edge. A bullish market is rendered in a
neutral accent, so a rising chart never visually reads as verified evidence.
`test/edge_separation_test.dart` fails the build if either rule is broken.

## Running it

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8100
```

A phone cannot reach `127.0.0.1` — that is the phone itself. Use the LAN
address of the machine running the backend, or a deployed URL.

## Building

```bash
flutter build web --release --dart-define=API_BASE_URL=https://your-backend
flutter build apk --release --dart-define=API_BASE_URL=https://your-backend
```

`API_BASE_URL` is compiled in at build time. Changing it needs a rebuild.
Omitting it makes the app call its own origin, which fails visibly rather than
quietly pointing somewhere unintended.

## Tests

```bash
flutter analyze && flutter test
```

Deployment details, including why the backend cannot run on Vercel, are in
[../docs/deployment.md](../docs/deployment.md).
