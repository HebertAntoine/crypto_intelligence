import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

typedef ChunkSink = Future<void> Function(Uint8List bytes, String mime);

/// Each 15 s slice is its own complete file: the recorder is restarted
/// rather than sliced, because only the first slice of a continuous
/// recording carries the container header.
class LexaRecorder {
  static const slice = Duration(seconds: 15);

  web.MediaStream? _stream;
  web.MediaRecorder? _recorder;
  Timer? _timer;
  bool _running = false;
  ChunkSink? _sink;
  String _mime = '';
  JSObject? _wakeLock;
  final _pending = <Future<void>>[];
  Completer<void>? _stopped;

  bool get supported =>
      web.window.navigator.has('mediaDevices') &&
      web.window.has('MediaRecorder');

  bool get running => _running;

  Future<void> start(
      {required bool shareTab, required ChunkSink onChunk}) async {
    final devices = web.window.navigator.mediaDevices;
    if (shareTab) {
      final shared = await devices
          .getDisplayMedia(
              web.DisplayMediaStreamOptions(video: true.toJS, audio: true.toJS))
          .toDart;
      final audio = shared.getAudioTracks().toDart;
      for (final track in shared.getVideoTracks().toDart) {
        track.stop();
      }
      if (audio.isEmpty) {
        throw 'Aucun son partagé : coche « Partager l\'audio de l\'onglet ».';
      }
      _stream = web.MediaStream(audio.toJS);
    } else {
      final constraints = web.MediaStreamConstraints(
          audio: {
        'echoCancellation': false,
        'noiseSuppression': false,
        'autoGainControl': true,
      }.jsify()!);
      _stream = await devices.getUserMedia(constraints).toDart;
    }
    _mime = const [
      'audio/webm;codecs=opus',
      'audio/mp4',
      'audio/webm',
      'audio/ogg'
    ].firstWhere(web.MediaRecorder.isTypeSupported, orElse: () => '');
    _sink = onChunk;
    _running = true;
    await _keepAwake();
    _next();
  }

  void _next() {
    if (!_running || _stream == null) return;
    final recorder = _mime.isEmpty
        ? web.MediaRecorder(_stream!)
        : web.MediaRecorder(
            _stream!, web.MediaRecorderOptions(mimeType: _mime));
    final parts = <web.Blob>[];
    recorder.ondataavailable = ((web.BlobEvent event) {
      if (event.data.size > 0) parts.add(event.data);
    }).toJS;
    recorder.onstop = ((web.Event _) {
      final type = recorder.mimeType.isEmpty ? _mime : recorder.mimeType;
      final blob = web.Blob(parts.toJS, web.BlobPropertyBag(type: type));
      _pending.add(_send(blob, type));
      _stopped?.complete();
      _stopped = null;
      _next();
    }).toJS;
    recorder.start();
    _recorder = recorder;
    _timer = Timer(slice, () {
      if (recorder.state == 'recording') recorder.stop();
    });
  }

  Future<void> _send(web.Blob blob, String type) async {
    if (blob.size == 0) return;
    final buffer = await blob.arrayBuffer().toDart;
    await _sink?.call(buffer.toDart.asUint8List(), type);
  }

  Future<void> _keepAwake() async {
    try {
      if (web.window.navigator.has('wakeLock')) {
        _wakeLock =
            await web.window.navigator.wakeLock.request('screen').toDart;
      }
    } catch (_) {
      // Best effort: the member keeps the screen on otherwise.
    }
  }

  Future<void> stop() async {
    _running = false;
    _timer?.cancel();
    final recorder = _recorder;
    if (recorder != null && recorder.state == 'recording') {
      _stopped = Completer<void>();
      recorder.stop(); // its onstop sends the last slice
      await _stopped!.future;
    }
    for (final track
        in _stream?.getTracks().toDart ?? <web.MediaStreamTrack>[]) {
      track.stop();
    }
    _stream = null;
    await Future.wait(_pending);
    _pending.clear();
    try {
      (_wakeLock as web.WakeLockSentinel?)?.release();
    } catch (_) {}
  }
}
