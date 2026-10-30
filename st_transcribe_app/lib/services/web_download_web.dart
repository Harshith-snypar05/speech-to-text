import 'dart:convert';
// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use
// This file is only ever reached via conditional import on web builds.
import 'dart:html' as html;

/// Browsers can't write to the local filesystem directly; this is the
/// standard web way to "save a file" -- trigger a Blob download, which
/// lands in the user's actual Downloads folder.
void triggerWebDownload(String filename, String content) {
  final bytes = utf8.encode(content);
  final blob = html.Blob([bytes], 'text/plain');
  final url = html.Url.createObjectUrlFromBlob(blob);
  html.AnchorElement(href: url)
    ..setAttribute('download', '$filename.txt')
    ..click();
  html.Url.revokeObjectUrl(url);
}
