import 'dart:math';

/// Short random token for a share link (e.g. "k3f8x9q2"). No crypto needs
/// here -- it's a casual share-link identifier, not a secret.
String generateSessionId() {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  final rnd = Random();
  return List.generate(10, (_) => chars[rnd.nextInt(chars.length)]).join();
}
