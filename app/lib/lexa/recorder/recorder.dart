/// Records what the member is watching, in complete ~15 s audio files.
///
/// Web only (microphone, or the audio of a tab the member chooses to share);
/// elsewhere [LexaRecorder.supported] is false and nothing is recorded.
library;

export 'recorder_stub.dart' if (dart.library.js_interop) 'recorder_web.dart';
