import 'dart:math';

/// Short random token for a share link (e.g. "k3f8x9q2") and an optional
/// access code to gate who can join as a viewer. Both use Random.secure()
/// (a CSPRNG) -- the session id is the only thing standing between a
/// leaked/guessed link and someone joining a session, so it shouldn't be
/// predictable even though it's not a password.
String generateSessionId() => _randomToken(10, _lowerAlnum);

/// Matches the relay's access-code validation (core/protocol.py):
/// 4-32 alphanumeric characters.
String generateAccessCode() => _randomToken(8, _upperAlnum);

const _lowerAlnum = 'abcdefghijklmnopqrstuvwxyz0123456789';
const _upperAlnum = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no 0/O/1/I -- easier to read aloud/type

String _randomToken(int length, String alphabet) {
  final rnd = Random.secure();
  return List.generate(length, (_) => alphabet[rnd.nextInt(alphabet.length)]).join();
}
