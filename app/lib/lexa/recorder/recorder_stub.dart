import 'dart:typed_data';

typedef ChunkSink = Future<void> Function(Uint8List bytes, String mime);

class LexaRecorder {
  bool get supported => false;
  bool get running => false;

  Future<void> start({required bool shareTab, required ChunkSink onChunk}) =>
      Future.error(
          'L\'écoute ne fonctionne que dans l\'application web (navigateur).');

  Future<void> stop() async {}
}
